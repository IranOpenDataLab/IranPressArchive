#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch.py — واکشگر آرشیو اسناد/مطبوعات ایران

پشتیبانی از چهار نوع ساختار لینک (تعریف در urls.yml):
  google_drive_folder / google_drive_file / index_page / direct_files

جریان کار:
  1) دانلود فایل‌های جدید به archive/<id>/
  2) ثبت همه فایل‌ها در data/manifest.json (نام، تاریخ، اندازه، sha256، منبع)
  3) بازسازی خودکار بخش فهرست دانلود در README.md

نمونه اجرا:
  python fetch.py                      # همه منابع + بازسازی فهرست
  python fetch.py --source neshat     # فقط یک منبع
  python fetch.py --dry-run           # فقط گزارش، بدون دانلود
  python fetch.py --commit            # بعد از دانلود، کامیت و پوش git
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

from make_index import scan_and_register, rebuild_index, save_manifest

USER_AGENT = "IranPressArchiveFetcher/2.0 (+https://github.com/IranOpenDataLab/IranPressArchive)"
DEFAULT_EXTENSIONS = [".pdf"]
MANIFEST_PATH = "data/manifest.json"


# ---------- کانفیگ ----------

def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg or "sources" not in cfg:
        raise ValueError("فرمت کانفیگ نادرست است؛ کلید sources یافت نشد.")
    return cfg["sources"]


# ---------- ابزارهای شبکه ----------

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


# ---------- دانلود ----------

def download_file(url, dest_dir, seen_urls):
    if url in seen_urls:
        return "skipped"
    os.makedirs(dest_dir, exist_ok=True)
    name = safe_filename(os.path.basename(urlparse(url).path))
    dest = os.path.join(dest_dir, name)
    if os.path.exists(dest):
        seen_urls.add(url)
        return "skipped"
    tmp = dest + ".part"
    with http_get(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(tmp, dest)
    seen_urls.add(url)
    return "downloaded"


def gdown_available():
    return subprocess.run(["gdown", "--version"], capture_output=True).returncode == 0


def fetch_drive_folder(url, dest_dir):
    cmd = ["gdown", "--folder", url, "-O", dest_dir, "--no-cookies", "--remaining-ok"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("gdown خطا داد:\n" + res.stderr[-2000:])


# ---------- پردازش هر منبع ----------

def process_source(src, args, manifest):
    sid = src.get("id") or src["name"]
    stype = src["type"]
    dest_dir = os.path.join("archive", sid)
    src_state = manifest["sources"].setdefault(sid, {"name": src["name"], "files": {}, "seen_urls": []})
    seen_urls = set(src_state.get("seen_urls", []))
    print(f"\n=== {src['name']} ({sid}) | نوع: {stype} ===")

    if stype == "google_drive_folder":
        if args.dry_run:
            print("[dry-run] پوشه درایو با gdown همگام می‌شود.")
            return 0
        if not gdown_available():
            raise RuntimeError("gdown نصب نیست: pip install gdown")
        os.makedirs(dest_dir, exist_ok=True)
        fetch_drive_folder(src["url"], dest_dir)

    elif stype == "google_drive_file":
        if not args.dry_run:
            if not gdown_available():
                raise RuntimeError("gdown نصب نیست: pip install gdown")
            os.makedirs(dest_dir, exist_ok=True)
            cmd = ["gdown", src["url"], "-O", dest_dir + "/", "--no-cookies", "--fuzzy"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError("gdown خطا داد:\n" + res.stderr[-2000:])

    elif stype == "index_page":
        exts = [e.lower() for e in src.get("extensions", DEFAULT_EXTENSIONS)]
        links = crawl_index(src["url"], exts, src.get("recursive", True))
        print(f"{len(links)} فایل در صفحه یافت شد.")
        n_new = 0
        for link in links:
            if args.dry_run:
                status = "skipped" if link in seen_urls else "would-download"
                print(f"  [{status}] {os.path.basename(unquote(link))}")
                continue
            try:
                status = download_file(link, dest_dir, seen_urls)
                if status == "downloaded":
                    n_new += 1
                print(f"  [{status}] {os.path.basename(unquote(link))}")
            except Exception as e:
                print(f"  [خطا] {link}: {e}")
        src_state["seen_urls"] = sorted(seen_urls)
        return n_new

    elif stype == "direct_files":
        n_new = 0
        for url in src.get("files", []):
            if args.dry_run:
                print(f"  [would-download] {url}")
                continue
            try:
                if download_file(url, dest_dir, seen_urls) == "downloaded":
                    n_new += 1
            except Exception as e:
                print(f"  [خطا] {url}: {e}")
        src_state["seen_urls"] = sorted(seen_urls)
        return n_new

    else:
        raise ValueError(f"نوع منبع پشتیبانی نمی‌شود: {stype}")
    return None


def git_commit(n_new):
    if n_new <= 0:
        print("فایل جدیدی برای کامیت نیست.")
        return
    subprocess.run(["git", "add", "archive", MANIFEST_PATH, "README.md"], check=True)
    msg = f"آرشیو: افزودن {n_new} فایل جدید"
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push"], check=True)
    print(f"کامیت و پوش انجام شد: {msg}")


def main():
    ap = argparse.ArgumentParser(description="واکشگر آرشیو اسناد/مطبوعات")
    ap.add_argument("--config", default="urls.yml")
    ap.add_argument("--source", help="اجرای فقط یک منبع (id)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true", help="بعد از دانلود، تغییرات را کامیت و پوش کن")
    args = ap.parse_args()

    sources = load_config(args.config)
    if args.source:
        sources = [s for s in sources if (s.get("id") or s["name"]) == args.source]
        if not sources:
            sys.exit(f"منبعی با id برابر {args.source} یافت نشد.")

    manifest = None
    if not args.dry_run:
        from make_index import load_manifest
        manifest = load_manifest()

    any_ok = False
    for src in sources:
        sid = src.get("id") or src["name"]
        try:
            if args.dry_run:
                process_source(src, args, {"sources": {}})
            else:
                process_source(src, args, manifest)
            any_ok = True
        except Exception as e:
            print(f"!!! منبع {sid} شکست خورد: {e}")

    if not args.dry_run:
        n_new = scan_and_register(manifest)
        save_manifest(manifest)
        rebuild_index(manifest)
        print(f"\nفایل‌های تازه ثبت‌شده در منیفست: {n_new}")
        if args.commit:
            git_commit(n_new)

    sys.exit(0 if any_ok else 1)


if __name__ == "__main__":
    main()
