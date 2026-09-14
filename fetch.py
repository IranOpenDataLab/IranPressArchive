#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch.py — واکشگر عمومی آرشیو اسناد/مطبوعات

از چهار نوع ساختار لینک پشتیبانی می‌کند:
  - google_drive_folder : پوشه عمومی گوگل‌درایو (نیازمند gdown)
  - google_drive_file   : فایل تکی گوگل‌درایو (نیازمند gdown)
  - index_page          : صفحه ایندکس/فهرست لینک (مثل Apache index یا هر صفحه با لینک فایل)
  - direct_files        : فهرست مستقیم URL فایل‌ها

فایل‌های دریافت‌شده در state.json ثبت می‌شوند تا در اجراهای بعدی دوباره دانلود نشوند.

نمونه اجرا:
  python fetch.py                      # همه منابع
  python fetch.py --source neshat      # فقط یک منبع
  python fetch.py --dry-run            # فقط فهرست، بدون دانلود
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen

try:
    import yaml
except ImportError:
    sys.exit("PyYAML نصب نیست: pip install pyyaml")

USER_AGENT = "IranPressArchiveFetcher/1.0 (+https://github.com/IranOpenDataLab/IranPressArchive)"
DEFAULT_EXTENSIONS = [".pdf"]
MAX_DEPTH = 3


# ---------- ابزارهای پایه ----------

def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg or "sources" not in cfg:
        raise ValueError("فرمت کانفیگ نادرست است؛ کلید sources یافت نشد.")
    return cfg["sources"]


def load_state(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(path, state):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def http_get(url, timeout=60):
    req = Request(url, headers={"User-Agent": USER_AGENT})
    return urlopen(req, timeout=timeout)


def safe_filename(name):
    name = unquote(name).strip() or "file"
    return re.sub(r'[\\/:*?"<>|]', "_", name)


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


def crawl_index(base_url, extensions, recursive=True, _depth=0, _seen=None):
    """فهرست بازگشتی لینک فایل‌ها از صفحه ایندکس."""
    if _seen is None:
        _seen = set()
    if _depth > MAX_DEPTH or base_url in _seen:
        return []
    _seen.add(base_url)

    files, subdirs = [], []
    for link in extract_links(base_url):
        parsed = urlparse(link)
        path = unquote(parsed.path)
        scheme = urlparse(base_url).scheme
        if not link.startswith(scheme + "://"):
            continue
        if any(path.lower().endswith(e) for e in extensions):
            files.append(link)
        elif recursive and path.endswith("/") and link.startswith(base_url.rstrip("/") + "/"):
            subdirs.append(link)

    for sub in subdirs:
        files.extend(crawl_index(sub, extensions, recursive, _depth + 1, _seen))
    return files


# ---------- دانلود ----------

def download_file(url, dest_dir, state):
    name = safe_filename(os.path.basename(urlparse(url).path))
    dest = os.path.join(dest_dir, name)
    if url in state and os.path.exists(dest):
        return "skipped", dest
    os.makedirs(dest_dir, exist_ok=True)
    tmp = dest + ".part"
    with http_get(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(tmp, dest)
    state[url] = {"path": dest, "size": os.path.getsize(dest)}
    return "downloaded", dest


def gdown_available():
    return subprocess.run(["gdown", "--version"], capture_output=True).returncode == 0


def fetch_drive_folder(url, dest_dir):
    """دانلود کامل پوشه عمومی درایو؛ gdown فایل‌های موجود را دوباره نمی‌گیرد."""
    cmd = ["gdown", "--folder", url, "-O", dest_dir, "--no-cookies", "--remaining-ok"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"gdown خطا داد:\n{res.stderr[-2000:]}")
    return res.stdout


def fetch_drive_file(url, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    cmd = ["gdown", url, "-O", dest_dir + "/", "--no-cookies", "--fuzzy"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"gdown خطا داد:\n{res.stderr[-2000:]}")
    return res.stdout


# ---------- اجرای هر منبع ----------

def process_source(src, args, state):
    sid = src.get("id") or src["name"]
    stype = src["type"]
    dest_dir = os.path.join(args.output, sid)
    print(f"\n=== {src['name']} ({sid}) | نوع: {stype} ===")

    state.setdefault("__sources__", {})
    src_state = state["__sources__"].setdefault(sid, {})

    if stype == "google_drive_folder":
        if args.dry_run:
            print("[dry-run] پوشه درایو؛ در حالت واقعی با gdown دانلود می‌شود.")
            return {"downloaded": 0, "skipped": 0, "failed": 0}
        if not gdown_available():
            raise RuntimeError("gdown نصب نیست: pip install gdown")
        os.makedirs(dest_dir, exist_ok=True)
        fetch_drive_folder(src["url"], dest_dir)
        n = sum(len(files) for _, _, files in os.walk(dest_dir))
        print(f"پوشه همگام شد؛ مجموع فایل‌ها: {n}")
        return {"downloaded": n, "skipped": 0, "failed": 0}

    if stype == "google_drive_file":
        if args.dry_run:
            print(f"[dry-run] فایل درایو: {src['url']}")
            return {"downloaded": 0, "skipped": 0, "failed": 0}
        if not gdown_available():
            raise RuntimeError("gdown نصب نیست: pip install gdown")
        fetch_drive_file(src["url"], dest_dir)
        return {"downloaded": 1, "skipped": 0, "failed": 0}

    if stype == "index_page":
        exts = [e.lower() for e in src.get("extensions", DEFAULT_EXTENSIONS)]
        links = crawl_index(src["url"], exts, src.get("recursive", True))
        print(f"{len(links)} فایل یافت شد.")
        counts = {"downloaded": 0, "skipped": 0, "failed": 0}
        for link in links:
            if args.dry_run:
                status = "skipped" if link in src_state else "would-download"
                print(f"  [{status}] {link}")
                continue
            try:
                status, dest = download_file(link, dest_dir, src_state)
                counts["downloaded" if status == "downloaded" else "skipped"] += 1
                print(f"  [{status}] {os.path.basename(dest)}")
            except Exception as e:
                counts["failed"] += 1
                print(f"  [خطا] {link}: {e}")
        return counts

    if stype == "direct_files":
        counts = {"downloaded": 0, "skipped": 0, "failed": 0}
        for url in src.get("files", []):
            if args.dry_run:
                print(f"  [would-download] {url}")
                continue
            try:
                status, dest = download_file(url, dest_dir, src_state)
                counts["downloaded" if status == "downloaded" else "skipped"] += 1
            except Exception as e:
                counts["failed"] += 1
                print(f"  [خطا] {url}: {e}")
        return counts

    raise ValueError(f"نوع منبع پشتیبانی نمی‌شود: {stype}")


def main():
    ap = argparse.ArgumentParser(description="واکشگر آرشیو اسناد/مطبوعات")
    ap.add_argument("--config", default="urls.yml")
    ap.add_argument("--source", help="اجرای فقط یک منبع (id)")
    ap.add_argument("--output", default="archive")
    ap.add_argument("--state", default="state.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = load_config(args.config)
    if args.source:
        sources = [s for s in sources if (s.get("id") or s["name"]) == args.source]
        if not sources:
            sys.exit(f"منبعی با id برابر {args.source} یافت نشد.")

    state = load_state(args.state)
    summary, any_ok = {}, False
    for src in sources:
        sid = src.get("id") or src["name"]
        try:
            summary[sid] = process_source(src, args, state)
            any_ok = True
        except Exception as e:
            summary[sid] = {"error": str(e)}
            print(f"!!! منبع {sid} شکست خورد: {e}")

    if not args.dry_run:
        save_state(args.state, state)

    print("\n===== خلاصه =====")
    for sid, res in summary.items():
        print(f"  {sid}: {res}")
    sys.exit(0 if any_ok else 1)


if __name__ == "__main__":
    main()
