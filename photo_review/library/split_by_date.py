#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一夾混在一起的照片,按「拍攝當天」分成 YYYYMMDD 子資料夾。

── 為什麼(2026-08-27)──────────────────────────────────────────
從手機拖幾百張到電腦的暫存夾之後,要照「拍攝日分夾」的規矩
(資料夾 = 一趟活動,命名 YYYYMMDD 或 YYYYMMDD_描述)分好再進隨身硬碟。
以前是寫一次性腳本做這件事、做完就丟 —— 這支是把它工具化,
一次幾萬張的整批搬移也是跑這支。

⛔ 不准用檔案的修改時間(mtime)當拍攝日。 剛拖過來的檔 mtime 全是「拖曳的那一刻」,
   用它會把幾百張全部堆進今天那一夾,而且**不會報錯**,看起來像成功了。
   讀不到 EXIF 就老實丟進 `_讀不到日期`,⛔ 不猜。

⛔ 永不覆蓋(沿用 2026-07-10 大整理的鐵則):同名加 `_2`、`_3`。
只掃第一層,⛔ 不進子資料夾 —— 已經分好的夾重跑不會被再拆一次。

用法:
    python3 -m photo_review.library.split_by_date "<來源夾>"            # 只看計畫,不動任何檔案
    python3 -m photo_review.library.split_by_date "<來源夾>" --apply    # 真的搬
"""
import os, sys, re, csv, argparse, subprocess, datetime
from concurrent.futures import ThreadPoolExecutor

from photo_review import config

LOG = os.path.join(config.NOTES_DIR, "按日期分夾_log.csv")

IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif",
           ".cr2", ".cr3", ".arw", ".nef", ".dng", ".tif", ".tiff", ".raf", ".orf"}
VID_EXT = {".mov", ".mp4", ".m4v", ".avi"}
SIDECAR = {".aae", ".xmp"}          # 跟同名主檔走,不自己找日期
NO_DATE = "_讀不到日期"


def shot_date(path):
    """回 'YYYYMMDD',讀不到回 None。⛔ 絕不 fallback 到 mtime。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXT:
        try:
            out = subprocess.run(["sips", "-g", "creation", path],
                                 capture_output=True, text=True, timeout=15).stdout
        except Exception:
            return None
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("creation:"):
                m = re.match(r"(\d{4}):(\d{2}):(\d{2})", s[9:].strip())
                return "".join(m.groups()) if m else None
        return None
    if ext in VID_EXT:
        # sips 不吃影片 → 走 Spotlight 的「內容建立時間」(iPhone 影片 = 拍攝時間)
        try:
            out = subprocess.run(["mdls", "-raw", "-name", "kMDItemContentCreationDate", path],
                                 capture_output=True, text=True, timeout=15).stdout.strip()
        except Exception:
            return None
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", out)
        return "".join(m.groups()) if m else None
    return None


def unique(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    src = os.path.abspath(os.path.expanduser(a.src))
    if not os.path.isdir(src):
        print(f"❌ 找不到資料夾:{src}")
        sys.exit(1)

    # 只掃第一層的檔案
    files, sidecars = [], []
    for name in sorted(os.listdir(src)):
        if name.startswith("."):
            continue
        p = os.path.join(src, name)
        if not os.path.isfile(p):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in SIDECAR:
            sidecars.append(p)
        elif ext in IMG_EXT or ext in VID_EXT:
            files.append(p)

    if not files and not sidecars:
        print(f"📂 {src}\n   第一層沒有照片或影片(子資料夾不掃)。")
        return

    print(f"📂 {src}")
    print(f"   第一層找到 {len(files)} 個照片/影片" +
          (f" + {len(sidecars)} 個附屬檔(.aae/.xmp)" if sidecars else ""))
    print("   讀拍攝日期中…")

    with ThreadPoolExecutor(max_workers=8) as ex:
        dates = list(ex.map(shot_date, files))

    # 主檔 → 目標夾
    plan = {}
    for p, d in zip(files, dates):
        plan[p] = d or NO_DATE

    # 附屬檔跟同名主檔走(IMG_1234.AAE 跟著 IMG_1234.HEIC)
    stem2dir = {os.path.splitext(os.path.basename(p))[0]: v for p, v in plan.items()}
    for p in sidecars:
        stem = os.path.splitext(os.path.basename(p))[0]
        plan[p] = stem2dir.get(stem, NO_DATE)

    buckets = {}
    for p, d in plan.items():
        buckets.setdefault(d, []).append(p)

    print()
    for d in sorted(buckets, key=lambda x: (x == NO_DATE, x)):
        mark = "⚠️ " if d == NO_DATE else "   "
        print(f"{mark}{d}/   {len(buckets[d])} 個")
    print()

    if not a.apply:
        print("🔍 這只是計畫,還沒有動任何檔案。")
        print("   要真的搬:同一行指令後面加 --apply")
        return

    rows, moved, failed = [], 0, 0
    for d, paths in buckets.items():
        dest_dir = os.path.join(src, d)
        os.makedirs(dest_dir, exist_ok=True)
        for p in paths:
            dst = unique(os.path.join(dest_dir, os.path.basename(p)))
            try:
                os.rename(p, dst)
                rows.append(["MOVE", p, dst, "改名避免覆蓋" if os.path.basename(dst) != os.path.basename(p) else ""])
                moved += 1
            except OSError as e:
                rows.append(["FAIL", p, dst, str(e)])
                failed += 1
                print(f"⚠️ 搬不動 {os.path.basename(p)}:{e}")

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["時間", "動作", "來源", "目標", "備註"])
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in rows:
            w.writerow([stamp] + r)

    print(f"✅ 搬好 {moved} 個" + (f",{failed} 個失敗" if failed else ""))
    print(f"📝 紀錄寫進 {LOG}")
    if NO_DATE in buckets:
        print(f"⚠️ 有 {len(buckets[NO_DATE])} 個讀不到拍攝日期,放在 {NO_DATE}/,要自己看一下。")


if __name__ == "__main__":
    main()
