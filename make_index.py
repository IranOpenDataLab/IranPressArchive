#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_index.py — سازنده فهرست دانلود آرشیو

دو کار انجام می‌دهد:
  1) scan_and_register(manifest): همه فایل‌های archive/ را اسکن می‌کند و
     فایل‌های جدید را با متادیتا (نام، تاریخ استخراج‌شده از نام فایل،
     اندازه، sha256) در data/manifest.json ثبت می‌کند.
  2) rebuild_index(manifest): بخش «فهرست نشریات» README.md را بین
     نشانگرهای AUTO-INDEX بازسازی می‌کند.

اجراهای مجدد امن (idempotent) هستند و دست‌نویس‌های README را حفظ می‌کنند.

اجرای مستقل:
  python make_index.py     # فقط اسکن + بازسازی فهرست (بدون دانلود)
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

README_PATH = "README.md"
MARK_START = "<!-- AUTO-INDEX:START -->"
MARK_END = "<!-- AUTO-INDEX:END -->"
MANIFEST_PATH = "data/manifest.json"

# ---------- تبدیل تاریخ جلالی به میلادی (الگوریتم استاندارد) ----------

def _is_gregorian_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33 + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    ml = [0, 31, 29 if _is_gregorian_leap(gy) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 12 and gd > ml[gm + 1]:
        gd -= ml[gm + 1]
        gm += 1
    return gy, gm + 1, gd


# ---------- استخراج تاریخ از نام فایل ----------

RE_JALALI = re.compile(r"(?<!\d)(1[34]\d{2})[-_./ ]?([0-1]?\d)[-_./ ]?([0-3]?\d)(?!\d)")
RE_GREGORIAN = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_./ ]?([0-1]?\d)[-_./ ]?([0-3]?\d)(?!\d)")
RE_JALALI_COMPACT = re.compile(r"(?<!\d)(1[34]\d{2})([0-1]\d)([0-3]\d)(?!\d)")
RE_GREGORIAN_COMPACT = re.compile(r"(?<!\d)((?:19|20)\d{2})([0-1]\d)([0-3]\d)(?!\d)")


def _valid_jalali(y, m, d):
    return 1300 <= y <= 1500 and 1 <= m <= 12 and 1 <= d <= 31


def extract_date(text, custom_regex=None):
    """تاریخ را از نام فایل استخراج می‌کند؛ خروجی:
    (نمایش، تاریخ میلادی ISO برای مرتب‌سازی) یا (None, None)"""
    if custom_regex:
        m = re.search(custom_regex, text)
        if m:
            y, mo, d = (int(g) for g in m.groups())
            return f"{y:04d}/{mo:02d}/{d:02d}", f"{y:04d}-{mo:02d}-{d:02d}"
    for rx in (RE_JALALI, RE_JALALI_COMPACT):
        m = rx.search(text)
        if m:
            y, mo, d = (int(g) for g in m.groups())
            if _valid_jalali(y, mo, d):
                gy, gm, gd = jalali_to_gregorian(y, mo, d)
                return f"{y:04d}/{mo:02d}/{d:02d}", f"{gy:04d}-{gm:02d}-{gd:02d}"
    for rx in (RE_GREGORIAN, RE_GREGORIAN_COMPACT):
        m = rx.search(text)
        if m:
            y, mo, d = (int(g) for g in m.groups())
            if 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}/{mo:02d}/{d:02d}", f"{y:04d}-{mo:02d}-{d:02d}"
    return None, None


# ---------- اسکن و ثبت فایل‌ها ----------

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path=MANIFEST_PATH):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"version": 2, "sources": {}}


def save_manifest(m, path=MANIFEST_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


def scan_and_register(manifest):
    """فایل‌های archive/ را اسکن و فایل‌های جدید را در منیفست ثبت می‌کند.
    تعداد فایل‌های تازه ثبت‌شده را برمی‌گرداند."""
    n_new = 0
    if not os.path.isdir("archive"):
        return 0
    for sid in sorted(os.listdir("archive")):
        src_dir = os.path.join("archive", sid)
        if not os.path.isdir(src_dir):
            continue
        src = manifest["sources"].setdefault(sid, {"name": sid, "files": {}})
        files = src.setdefault("files", {})
        for root, _, fnames in os.walk(src_dir):
            for fn in fnames:
                if fn.endswith(".part"):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, "archive").replace(os.sep, "/")
                if rel in files:
                    continue
                disp, iso = extract_date(fn, src.get("date_regex"))
                files[rel] = {
                    "filename": fn,
                    "date_display": disp,
                    "date_iso": iso,
                    "size": os.path.getsize(full),
                    "sha256": sha256_of(full),
                    "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                n_new += 1
                print(f"  [ثبت] {rel}" + (f" | تاریخ: {disp}" if disp else ""))
    return n_new


# ---------- ساخت فهرست README ----------

def _row(entry_rel, meta):
    disp = meta.get("date_display") or "—"
    link = f"[دانلود](archive/{entry_rel})"
    title = meta.get("filename", os.path.basename(entry_rel)).replace(".pdf", "")
    title = title.replace("_", " ").strip() or os.path.basename(entry_rel)
    return f"| {disp} | {title} | {link} |"


def render_index(manifest):
    out = []
    for sid in sorted(manifest["sources"]):
        src = manifest["sources"][sid]
        files = src.get("files", {})
        if not files:
            continue
        out.append(f"\n### {src.get('name', sid)} (`{sid}`)\n")
        out.append(f"تعداد شماره‌های آرشیوشده: **{len(files)}**\n")
        out.append("| تاریخ | عنوان / شماره | فایل |")
        out.append("|---|---|---|")
        rows = sorted(
            files.items(),
            key=lambda kv: (kv[1].get("date_iso") or "0000", kv[0]),
            reverse=True,
        )
        for rel, meta in rows:
            out.append(_row(rel, meta))
    return "\n".join(out)


def rebuild_index(manifest, readme_path=README_PATH):
    """بخش بین نشانگرها را در README بازسازی می‌کند."""
    body = render_index(manifest).strip()
    section = f"{MARK_START}\n{body}\n{MARK_END}"
    if not os.path.exists(readme_path):
        content = section + "\n"
    else:
        with open(readme_path, encoding="utf-8") as f:
            content = f.read()
        if MARK_START in content and MARK_END in content:
            pre = content.split(MARK_START)[0]
            post = content.split(MARK_END)[1]
            content = pre + section + post
        else:
            content = content.rstrip() + "\n\n" + section + "\n"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("فهرست README.md بازسازی شد.")


if __name__ == "__main__":
    m = load_manifest()
    n = scan_and_register(m)
    save_manifest(m)
    rebuild_index(m)
    print(f"ثبت‌شده‌های جدید: {n}")
