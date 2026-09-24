#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片 Review 落地工具
--------------------
讀 review / 確認頁匯出的 JSON →
  1) delete=true 的照片丟垃圾桶(macOS Trash,可復原),記 log
  2) 有星等/顏色/標籤/心得的照片,寫進可搜尋的「照片日記總表」

安全:預設 dry-run(只印不動),加 --apply 才真的執行。刪除一律用 trash 不用 rm。

用法:
    python3 -m photo_review.land.apply <匯出的.json> [--apply]
"""
import json, os, sys, csv, subprocess, datetime

from photo_review import config

NOTES = config.NOTES_DIR
DIARY  = config.DIARY_CSV
DELLOG = config.DELLOG_CSV


def folder_of(path):
    return os.path.basename(os.path.dirname(path))


def has_meta(p):
    return bool(p.get("stars")) or bool(p.get("note")) or bool(p.get("tags")) or bool(p.get("color"))


def main():
    if len(sys.argv) < 2:
        print("用法:python3 -m photo_review.land.apply <匯出的.json> [--apply]"); sys.exit(1)
    jf = sys.argv[1]
    apply = "--apply" in sys.argv
    d = json.load(open(jf, encoding="utf-8"))
    photos = d["photos"]
    today = datetime.date.today().isoformat()

    dels = [p for p in photos if p.get("delete")]
    metas = [p for p in photos if not p.get("delete") and has_meta(p)]
    missing = [p for p in dels if not os.path.exists(p["path"])]

    print(f"讀取:{jf}")
    print(f"  標記刪除:{len(dels)} 張(其中 {len(missing)} 張已不在)")
    print(f"  入總表(有星等/顏色/標籤/心得):{len(metas)} 張")
    if not apply:
        print("\n[預覽模式] 加 --apply 才真的執行。將刪除:")
        for p in dels:
            print("   🗑", p["name"], "" if os.path.exists(p["path"]) else "(已不在)")
        return

    # 1) 刪除 → 垃圾桶
    trashed = 0
    new = not os.path.exists(DELLOG)
    with open(DELLOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["丟垃圾桶日期", "資料夾", "檔名", "原路徑"])
        for p in dels:
            if os.path.exists(p["path"]):
                subprocess.run(["trash", p["path"]], check=False)
                w.writerow([today, folder_of(p["path"]), p["name"], p["path"]])
                trashed += 1

    # 2) 入總表
    added = 0
    new = not os.path.exists(DIARY)
    with open(DIARY, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["review日期", "資料夾", "檔名", "星等", "顏色", "標籤", "心得", "路徑"])
        for p in metas:
            tags = p.get("tags", "")
            if isinstance(tags, list):
                tags = " ".join(tags)
            w.writerow([today, folder_of(p["path"]), p["name"],
                        p.get("stars", 0), p.get("color", ""), tags,
                        p.get("note", ""), p["path"]])
            added += 1

    print(f"\n✓ 已丟垃圾桶 {trashed} 張(記於 {DELLOG})")
    print(f"✓ 入總表 {added} 張(記於 {DIARY})")


if __name__ == "__main__":
    main()
