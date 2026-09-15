#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch.py — واکشگر آرشیو اسناد/مطبوعات ایران (نسخه ۴)

پشتیبانی از پنج نوع ساختار لینک (تعریف در urls.yml):
  google_drive_folder / google_drive_file / index_page / url_sequence / direct_files

جریان کار:
  1) دانلود فایل‌های جدید به archive/<id>/
  2) ثبت همه فایل‌ها در data/manifest.json (نام، تاریخ، اندازه، sha256، منبع)
  3) بازسازی خودکار بخش فهرست دانلود در README.md

ویژگی‌های تاب‌آوری:
  - خطای یک فایل، دانلود بقیه را متوقف نمی‌کند (رفتن به لینک بعدی)
  - خطای یک منبع، منابع بعدی را متوقف نمی‌کند
  - تلاش مجدد خودکار (۳ بار) برای خطاهای شبکه/سرور؛ 404 فقط ثبت می‌شود
  - فایل موجود روی دیسک هرگز دوباره دانلود نمی‌شود
  - سقف حجم هر فایل دقیقا ۱۰۰ مگابایت (۱۰۰ MiB — هاردلیمیت گیت‌هاب)
  - چاپ کامل traceback هر خطا برای عیب‌یابی در لاگ Workflow

نمونه اجرا:
  python fetch.py                      # همه منابع + بازسازی فهرست
  python fetch.py --source neshat     # فقط یک منبع
  python fetch.py --dry-run           # فقط گزارش، بدون دانلود
"""

import argparse
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen

try:
    import yaml
except ImportError:
    sys.exit("PyYAML نصب نیست: pip install pyyaml")

from make_index import sha256_of, scan_and_register, rebuild_index, save_manifest, load_manifest

USER_AGENT = "IranPressArchiveFetcher/4.0 (+https://github.com/IranOpenDataLab/IranPressArchive)"
DEFAULT_EXTENSIONS = [".pdf"]
MANIFEST_PATH = "data/manifest.json"
MAX_FILE_MB_DEFAULT = 100         # دقیقا هاردلیمیت گیت‌هاب (۱۰۰ MiB)
RETRIES = 3


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg or "sources" not in cfg:
        raise ValueError("فرمت کانفیگ نادرست است؛ کلید sources یافت نشد.")
    return cfg["sources"]


# ---------- ابزارهای شبکه ----------

def http_get(url, timeout=120):
    req = Request(url, headers={"User-Agent": USER_AGENT})
    return urlopen(req, timeout=timeout)


def safe_filename(name):
    name = unquote(name).strip() or "file"
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def download_file(url, dest, max_bytes):
    """دانلود با تلاش مجدد و سقف حجم.
    خروجی: (status, info) که status یکی از
    downloaded / exists / missing / too-large / error است.
    اگر فایل مقصد از قبل روی دیسک باشد، هیچ درخواست شبکه‌ای زده نمی‌شود."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return "exists", os.path.getsize(dest)

    last_err = None
    for attempt in range(1, RETRIES + 1):
        tmp = dest + ".part"
        try:
            with http_get(url) as r:
                cl = r.headers.get("Content-Length")
                if cl and int(cl) > max_bytes:
                    return "too-large", f"{int(cl)/1e6:.1f}MB"
                written = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_bytes:
                            break
                        f.write(chunk)
                if written > max_bytes:
                    os.remove(tmp)
                    return "too-large", f"{written/1e6:.1f}MB"
            os.replace(tmp, dest)
            return "downloaded", written
        except HTTPError as e:
            if e.code in (404, 410):
                return "missing", e.code
            last_err = e
        except Exception as e:
            last_err = e
        if os.path.exists(tmp):
            os.remove(tmp)
        if attempt < RETRIES:
            wait = 5 * attempt
            print(f"  [تلاش {attempt}/{RETRIES} شکست خورد: {last_err} | {wait}s صبر...]")
            time.sleep(wait)
    print(f"  [خطای کامل] {url}:")
    traceback.print_exc()
    return "error", str(last_err)


# ---------- خزنده صفحات ایندکس ----------

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.links.append(v)


def extract_links(page_url):
    with http_get(page_url) as r:
        html = r.read().decode("utf-8", errors="replace")
    p = LinkParser()
    p.feed(html)
    return [urljoin(page_url, href) for href in p.links]


def crawl_index(base_url, extensions, recursive=True, max_depth=3, _depth=0, _seen=None):
    if _seen is None:
        _seen = set()
    if _depth > max_depth or base_url in _seen:
        return []
    _seen.add(base_url)
    files, subdirs = [], []
    for link in extract_links(base_url):
        path = unquote(urlparse(link).path)
        scheme = urlparse(base_url).scheme
        if not link.startswith(scheme + "://"):
            continue
        if any(path.lower().endswith(e) for e in extensions):
            files.append(link)
        elif recursive and path.endswith("/") and link.startswith(base_url.rstrip("/") + "/"):
            subdirs.append(link)
    for sub in subdirs:
        files.extend(crawl_index(sub, extensions, recursive, max_depth, _depth + 1, _seen))
    return files


# ---------- گوگل‌درایو ----------

def gdown_available():
    return subprocess.run(["gdown", "--version"], capture_output=True).returncode == 0


def fetch_drive_folder(url, dest_dir):
    """خروجی gdown مستقیم به لاگ می‌رود تا خطاها کامل دیده شوند.
    گزینه --continue باعث می‌شود فایل کامل موجود دوباره گرفته نشود و
    دانلود نیمه‌تمام از سر گرفته شود."""
    cmd = ["gdown", "--folder", url, "-O", dest_dir, "--no-cookies", "--remaining-ok", "--continue"]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"gdown با کد {res.returncode} شکست خورد (لاگ بالا)")


def enforce_size_limit(dest_dir, max_bytes):
    """فایل‌های بزرگ‌تر از سقف گیت را حذف می‌کند تا پوش نرم شکسته نشود."""
    for root, _, fnames in os.walk(dest_dir):
        for fn in fnames:
            p = os.path.join(root, fn)
            if os.path.getsize(p) > max_bytes:
                print(f"  [حذف — بزرگ‌تر از سقف {max_bytes//1048576}MiB] {p}")
                os.remove(p)


# ---------- ثبت در منیفست ----------

def register_file(src_state, rel_path, full_path, url=None, date_display=None, date_iso=None, extra=None):
    entry = {
        "filename": os.path.basename(rel_path),
        "date_display": date_display,
        "date_iso": date_iso,
        "size": os.path.getsize(full_path),
        "sha256": sha256_of(full_path),
        "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if url:
        entry["url"] = url
    if extra:
        entry.update(extra)
    src_state["files"][rel_path] = entry


# ---------- پردازش هر منبع ----------

def process_source(src, args, manifest):
    sid = src.get("id") or src["name"]
    stype = src["type"]
    dest_dir = os.path.join("archive", sid)
    max_bytes = int(src.get("max_file_mb", MAX_FILE_MB_DEFAULT)) * 1024 * 1024  # MiB
    src_state = manifest["sources"].setdefault(sid, {"name": src["name"], "files": {}, "seen_urls": []})
    files = src_state.setdefault("files", {})
    seen_urls = set(src_state.get("seen_urls", []))
    print(f"\n=== {src['name']} ({sid}) | نوع: {stype} ===")

    # --- پوشه گوگل‌درایو ---
    if stype == "google_drive_folder":
        if args.dry_run:
            print("[dry-run] پوشه درایو با gdown همگام می‌شود.")
            return
        if not gdown_available():
            raise RuntimeError("gdown نصب نیست: pip install gdown")
        os.makedirs(dest_dir, exist_ok=True)
        fetch_drive_folder(src["url"], dest_dir)
        enforce_size_limit(dest_dir, max_bytes)

    # --- فایل تکی درایو ---
    elif stype == "google_drive_file":
        if args.dry_run:
            print(f"[dry-run] فایل درایو: {src['url']}")
            return
        if not gdown_available():
            raise RuntimeError("gdown نصب نیست: pip install gdown")
        os.makedirs(dest_dir, exist_ok=True)
        res = subprocess.run(["gdown", src["url"], "-O", dest_dir + "/", "--no-cookies", "--fuzzy", "--continue"])
        if res.returncode != 0:
            raise RuntimeError(f"gdown با کد {res.returncode} شکست خورد (لاگ بالا)")
        enforce_size_limit(dest_dir, max_bytes)

    # --- دنباله ترتیبی URL (مثل نشاط: /dl/neshat/1377/1.pdf) ---
    elif stype == "url_sequence":
        tmpl = src["url_template"]
        name_tmpl = src.get("filename_template", f"{sid}_{{year}}_{{issue:03d}}.pdf")
        delay = float(src.get("delay_seconds", 1))
        counts = {"downloaded": 0, "missing": 0, "error": 0, "too-large": 0, "skipped": 0}
        for seq in src.get("sequences", []):
            year, start, end = seq["year"], seq["start"], seq["end"]
            print(f"— سال {year}: شماره {start} تا {end}")
            for issue in range(start, end + 1):
                url = tmpl.format(year=year, issue=issue)
                fname = name_tmpl.format(year=year, issue=issue)
                rel = f"{sid}/{fname}"
                if args.dry_run:
                    if rel in files or os.path.exists(os.path.join("archive", rel)):
                        status = "exists"
                    else:
                        status = "would-download"
                    print(f"  [{status}] {url}")
                    continue
                os.makedirs(dest_dir, exist_ok=True)
                status, info = download_file(url, os.path.join(dest_dir, fname), max_bytes)
                if status == "downloaded":
                    register_file(
                        src_state, rel, os.path.join(dest_dir, fname), url=url,
                        date_display=f"سال {year} — شماره {issue}",
                        date_iso=f"{year:04d}-{issue:06d}",
                        extra={"year": year, "issue": issue},
                    )
                    counts["downloaded"] += 1
                    print(f"  [ok] {fname} ({info/1e6:.1f}MB)")
                elif status == "exists":
                    counts["skipped"] += 1
                else:
                    counts[status] = counts.get(status, 0) + 1
                    print(f"  [{status}] {url} | {info}")
                if delay:
                    time.sleep(delay)
        print(f"خلاصه {sid}: {counts}")
        src_state["seen_urls"] = sorted(seen_urls)
        return

    # --- صفحه ایندکس ---
    elif stype == "index_page":
        exts = [e.lower() for e in src.get("extensions", DEFAULT_EXTENSIONS)]
        links = crawl_index(src["url"], exts, src.get("recursive", True))
        print(f"{len(links)} فایل در صفحه یافت شد.")
        delay = float(src.get("delay_seconds", 1))
        for link in links:
            if args.dry_run:
                status = "skipped" if link in seen_urls else "would-download"
                print(f"  [{status}] {os.path.basename(unquote(link))}")
                continue
            if link in seen_urls:
                continue
            fname = safe_filename(os.path.basename(urlparse(link).path))
            rel = f"{sid}/{fname}"
            status, info = download_file(link, os.path.join(dest_dir, fname), max_bytes)
            if status == "downloaded":
                register_file(src_state, rel, os.path.join(dest_dir, fname), url=link)
                print(f"  [ok] {fname}")
            elif status == "exists":
                if rel not in files:
                    register_file(src_state, rel, os.path.join(dest_dir, fname), url=link)
                print(f"  [exists] {fname}")
            else:
                print(f"  [{status}] {link} | {info}")
            seen_urls.add(link)
            if delay:
                time.sleep(delay)
        src_state["seen_urls"] = sorted(seen_urls)

    # --- فهرست مستقیم ---
    elif stype == "direct_files":
        for url in src.get("files", []):
            if args.dry_run:
                print(f"  [would-download] {url}")
                continue
            if url in seen_urls:
                continue
            fname = safe_filename(os.path.basename(urlparse(url).path))
            rel = f"{sid}/{fname}"
            status, info = download_file(url, os.path.join(dest_dir, fname), max_bytes)
            if status == "downloaded":
                register_file(src_state, rel, os.path.join(dest_dir, fname), url=url)
                print(f"  [ok] {fname}")
            elif status == "exists":
                if rel not in files:
                    register_file(src_state, rel, os.path.join(dest_dir, fname), url=url)
                print(f"  [exists] {fname}")
            else:
                print(f"  [{status}] {url} | {info}")
            seen_urls.add(url)

    else:
        raise ValueError(f"نوع منبع پشتیبانی نمی‌شود: {stype}")


def main():
    ap = argparse.ArgumentParser(description="واکشگر آرشیو اسناد/مطبوعات")
    ap.add_argument("--config", default="urls.yml")
    ap.add_argument("--source", help="اجرای فقط یک منبع (id)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = load_config(args.config)
    if args.source:
        sources = [s for s in sources if (s.get("id") or s["name"]) == args.source]
        if not sources:
            sys.exit(f"منبعی با id برابر {args.source} یافت نشد.")

    manifest = load_manifest()
    any_ok, had_error = False, False
    for src in sources:
        sid = src.get("id") or src["name"]
        try:
            process_source(src, args, manifest)
            any_ok = True
        except Exception:
            had_error = True
            print(f"!!! منبع {sid} شکست خورد — خطای کامل:")
            traceback.print_exc()
            print("→ ادامه با منبع بعدی...")

    if not args.dry_run:
        n_new = scan_and_register(manifest)
        save_manifest(manifest)
        rebuild_index(manifest)
        print(f"\nفایل‌های تازه ثبت‌شده در منیفست: {n_new}")

    print("\n===== پایان اجرا =====")
    sys.exit(2 if had_error else (0 if any_ok else 1))


if __name__ == "__main__":
    main()
