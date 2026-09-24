#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
對帳:3 顆星以上的照片,是不是都有匯出成品
------------------------------------------
分級規則是「星等 ≥ 3 ⟺ 一定會有匯出成品」,但一直沒有程式在查。
這支拿「照片日記總表」跟 Darktable 自己的資料庫對:
Darktable 每匯出一張,就會幫它貼上 `darktable|exported` 這個標籤。

⛔ 只讀不寫。資料庫用唯讀模式打開,Darktable 開著也可以跑。
⚠️ 要在裝了 Darktable 的那台電腦跑(它讀 Darktable 的資料庫)。不需要照片正本。

用法:
    python3 -m photo_review.library.check_exports            # 全部
    python3 -m photo_review.library.check_exports 東京       # 只看資料夾名稱含「東京」的
"""
import os, sys, csv, io, sqlite3, collections

from photo_review import config

DIARY = config.DIARY_CSV
DTCONF = os.environ.get("SC_DT_CONFIG", os.path.expanduser("~/.config/darktable"))   # 環境變數只給測試用
SHOW = 6


def ro(path):
    if not os.path.exists(path):
        print(f"❌ 找不到 {path}")
        print("   這支要在裝了 Darktable 的那台電腦上跑。")
        sys.exit(1)
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def stars(r):
    try:
        return int(float(r.get("星等") or 0))
    except ValueError:
        return 0


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    rows = list(csv.DictReader(io.open(DIARY, encoding="utf-8-sig")))
    if only:
        rows = [r for r in rows if only in (r.get("資料夾") or "")]

    lib = ro(os.path.join(DTCONF, "library.db"))
    data = ro(os.path.join(DTCONF, "data.db"))
    t = data.execute("select id from tags where name='darktable|exported'").fetchone()
    exported_tag = t[0] if t else None

    # Darktable 裡每一張照片:完整路徑 → 有沒有匯出過
    in_dt = {}
    for folder, fname, iid in lib.execute(
            "select f.folder, i.filename, i.id from images i join film_rolls f on f.id = i.film_id"):
        in_dt[os.path.join(folder, fname)] = iid
    done = set()
    if exported_tag is not None:
        done = {r[0] for r in lib.execute("select imgid from tagged_images where tagid=?", (exported_tag,))}

    good = [r for r in rows if stars(r) >= 3]
    print(f"📋 總表 {len(rows)} 張{'(資料夾含「' + only + '」)' if only else ''},其中 3 顆星以上 {len(good)} 張")
    print(f"   Darktable 資料庫裡有 {len(in_dt)} 張,匯出過 {len(done)} 張\n")

    ok, not_yet, not_imported = [], collections.defaultdict(list), collections.defaultdict(list)
    for r in good:
        iid = in_dt.get(r["路徑"])
        if iid is None:
            not_imported[r["資料夾"]].append(r["檔名"])
        elif iid in done:
            ok.append(r)
        else:
            not_yet[r["資料夾"]].append(r["檔名"])

    # 反方向:匯出了,星等卻不到 3
    low_but_out = [r for r in rows if 0 < stars(r) < 3 and in_dt.get(r["路徑"]) in done]

    print(f"✅ 已經匯出:{len(ok)} 張")
    n_yet = sum(map(len, not_yet.values()))
    if n_yet:
        print(f"⚠️ 已經匯進 Darktable、但還沒匯出:{n_yet} 張 —— 這些違反「3 星以上一定要匯出」")
        for f, names in sorted(not_yet.items()):
            print(f"   {f}  {len(names)} 張:{'、'.join(names[:SHOW])}{' …' if len(names) > SHOW else ''}")
    n_imp = sum(map(len, not_imported.values()))
    if n_imp:
        print(f"⏳ 還沒匯進 Darktable:{n_imp} 張(要先匯入才能修圖、匯出)")
        for f, names in sorted(not_imported.items()):
            print(f"   {f}  {len(names)} 張")
    if low_but_out:
        print(f"❓ 反過來:匯出了,星等卻不到 3 顆:{len(low_but_out)} 張(星等要不要調高?)")
        for r in low_but_out[:SHOW]:
            print(f"   {r['資料夾']}/{r['檔名']}  {stars(r)} 星")
    if not (n_yet or n_imp or low_but_out):
        print("🎉 全部對得上。")


if __name__ == "__main__":
    main()
