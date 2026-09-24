#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片 Review 進度總表
--------------------
把三份紀錄兜起來,回答「哪些資料夾還沒 review / 做到哪」:
  - notes/照片庫總表.csv        全庫資料夾主索引(資料夾名 + 檔案數)
  - notes/照片日記總表.csv      每張留用照一列(資料夾)
  - notes/照片Review_刪除log.csv 每張丟垃圾桶一列(資料夾)

每夾狀態:
  ✅ 完成   已處理(留用+刪除) >= 原檔案數
  🟡 進行中 已處理 > 0 但 < 原檔案數(還有沒評的)
  ⬜ 未開始 完全沒紀錄

用法:
    python3 -m photo_review.library.progress            # 快速版:靠主索引檔案數(含 ._/非圖片,分母略虛)
    python3 -m photo_review.library.progress --scan     # 精準版:實際掃 Camera 各夾圖片數(需 SSD),剩幾張是真的
    python3 -m photo_review.library.progress --all      # 列出每一個資料夾
    python3 -m photo_review.library.progress --todo     # 只列未開始 + 進行中
"""
import csv, os, sys, collections

from photo_review import config

NOTES = config.NOTES_DIR
MASTER = config.MASTER_CSV
DIARY  = config.DIARY_CSV
DELLOG = config.DELLOG_CSV

CAMERA = config.CAMERA_ROOT
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp",
           ".heic", ".heif", ".cr2", ".cr3", ".arw", ".nef", ".dng",
           ".tif", ".tiff", ".raf", ".orf"}


def scan_images(folder):
    """遞迴數資料夾內圖片檔(排除 ._ 垃圾檔與 .previews)。"""
    n = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".previews"]
        for f in files:
            if f.startswith("._"):
                continue
            if os.path.splitext(f)[1].lower() in IMG_EXT:
                n += 1
    return n


def load_kept_paths():
    """日記總表 → {資料夾: 該夾留用照的絕對路徑 set}(留用照仍在硬碟)。"""
    m = collections.defaultdict(set)
    if os.path.exists(DIARY):
        for row in csv.DictReader(open(DIARY, encoding="utf-8-sig")):
            m[row["資料夾"]].add(row.get("路徑", ""))
    return m


def load(path, col):
    if not os.path.exists(path):
        return collections.Counter()
    r = csv.DictReader(open(path, encoding="utf-8-sig"))
    return collections.Counter(row[col] for row in r if row.get(col))


def build_rows_master(master, kept, deld):
    """快速版:分母用主索引檔案數(含 ._/非圖片,略虛)。"""
    rows = []
    for name, total in master.items():
        k, d = kept.get(name, 0), deld.get(name, 0)
        done = k + d
        if done == 0:
            status = "⬜ 未開始"
        elif done >= total and total > 0:
            status = "✅ 完成"
        else:
            status = "🟡 進行中"
        rows.append((name, total, k, d, done, status))
    return rows


def build_rows_scan(kept_paths, deld):
    """精準版:實際掃 Camera 各夾圖片數。剩 = 硬碟現存圖片 - 已留用。"""
    if not os.path.isdir(CAMERA):
        print(f"✗ 掃不到 {CAMERA}(SSD 沒掛?),--scan 無法執行。"); sys.exit(1)
    names = sorted(d for d in os.listdir(CAMERA)
                   if os.path.isdir(os.path.join(CAMERA, d)) and not d.startswith("."))
    rows = []
    for i, name in enumerate(names, 1):
        print(f"\r掃描 {i}/{len(names)} …", end="", flush=True)
        folder = os.path.join(CAMERA, name)
        actual = scan_images(folder)          # 硬碟現存圖片(刪掉的已不算在內)
        k = len(kept_paths.get(name, set()))  # 已留用(仍在硬碟)
        d = deld.get(name, 0)                 # 曾刪除(已離開硬碟)
        remain = max(0, actual - k)           # 還沒評的 = 現存 - 已留用
        if k == 0 and d == 0:
            status = "⬜ 未開始"
        elif remain == 0:
            status = "✅ 完成"
        else:
            status = "🟡 進行中"
        # total 用「已處理過 + 現在還剩」的實際總量表達
        total = k + d + remain
        rows.append((name, total, k, d, k + d, status, remain))
    print("\r" + " " * 30 + "\r", end="")
    return rows


def main():
    show_all = "--all" in sys.argv
    todo_only = "--todo" in sys.argv
    scan = "--scan" in sys.argv

    master = {}
    for row in csv.DictReader(open(MASTER, encoding="utf-8-sig")):
        name = row["資料夾名"]
        try:
            n = int(row.get("檔案數", "0") or 0)
        except ValueError:
            n = 0
        master[name] = n

    kept = load(DIARY, "資料夾")
    deld = load(DELLOG, "資料夾")

    if scan:
        rows6 = build_rows_scan(load_kept_paths(), deld)
        rows = [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows6]
        remain_of = {r[0]: r[6] for r in rows6}
        universe = {r[0] for r in rows6}
    else:
        rows = build_rows_master(master, kept, deld)
        remain_of = None
        universe = set(master)

    # 已處理但不在盤點範圍的(防呆)
    orphan = (set(kept) | set(deld)) - universe

    rows.sort(key=lambda x: x[0])
    n_done = sum(1 for r in rows if r[5].startswith("✅"))
    n_prog = sum(1 for r in rows if r[5].startswith("🟡"))
    n_todo = sum(1 for r in rows if r[5].startswith("⬜"))

    mode = "精準(掃實際資料夾)" if scan else "快速(靠主索引,分母含垃圾檔略虛)"
    print(f"模式:{mode}")
    print(f"全庫 {len(rows)} 夾  →  ✅ 完成 {n_done} ・ 🟡 進行中 {n_prog} ・ ⬜ 未開始 {n_todo}")
    print(f"已留用 {sum(kept.values())} 張 ・ 已刪除 {sum(deld.values())} 張", end="")
    if remain_of is not None:
        print(f" ・ 尚待評 {sum(remain_of.values())} 張")
    else:
        print()
    print("-" * 64)

    def line(r):
        name, total, k, d, done, status = r
        tail = f"  還剩 {remain_of[name]} 張沒評" if (remain_of is not None and r[5].startswith("🟡")) else ""
        return f"  {status}  {name}  [{done}/{total}]  留用{k} 刪{d}{tail}"

    print("進行中(還沒評完,優先接續):")
    prog = [r for r in rows if r[5].startswith("🟡")]
    print("\n".join(line(r) for r in prog) if prog else "  (無)")

    print("\n已完成:")
    done_rows = [r for r in rows if r[5].startswith("✅")]
    print("\n".join(line(r) for r in done_rows) if done_rows else "  (無)")

    if show_all or todo_only:
        print("\n未開始:")
        todo = [r for r in rows if r[5].startswith("⬜")]
        print("\n".join(line(r) for r in todo) if todo else "  (無)")
    else:
        print(f"\n未開始:{n_todo} 夾(加 --todo 或 --all 列出)")

    if orphan:
        print(f"\n⚠️ 有 {len(orphan)} 個處理過的夾不在主索引(可能改名/新夾):{sorted(orphan)}")


if __name__ == "__main__":
    main()
