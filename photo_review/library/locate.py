#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""照片現在到底在哪、Darktable 讀得到的評分檔(.xmp)在不在。

── 為什麼(2026-08-27)──────────────────────────────────────────
實例:落地三夾共 260 張,Darktable 卻只看到 75 張(只有一夾)。
可能的原因有三種,而且**三種的修法完全不同**:
  ① 另外兩夾根本沒匯入 Darktable        → 他去匯入就好
  ② 照片搬過家,但 .xmp 沒跟著走          → 星等標籤全丟,要重寫
  ③ 照片搬過家,總表還記著舊路徑          → 以後查得到卻找不到檔
⛔ 憑猜的會叫他做錯事,所以先量出來。

搬過家的還會自動去 Camera/ 底下找同名檔(只比對檔名,找到多個就列出來讓使用者自己選,
⛔ 不自作主張)。加 `--fix` 才會把總表的路徑改成找到的新位置。

用法(⚠️ 要在照片正本看得到的那台電腦跑):
    python3 -m photo_review.library.locate                     # 看最近一批
    python3 -m photo_review.library.locate --batch 批次|20260827
    python3 -m photo_review.library.locate --batch 批次|20260827 --fix
    python3 -m photo_review.library.locate --all               # 總表全部(照片整批搬過家之後用這個)
    python3 -m photo_review.library.locate --all --fix

「照片整批搬家之後修總表路徑」已經長在 --fix 上,只差沒辦法一次看全部。
加了 --all 之後,⛔ 不另外寫一支獨立的搬家工具
(兩支做同一件事,遲早只有一支被更新)。
"""
import os, csv, io, sys, argparse, collections, shutil, datetime

from photo_review import config

NOTES = config.NOTES_DIR
DIARY = config.DIARY_CSV
CAMERA = config.CAMERA_ROOT


def load():
    with io.open(DIARY, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def index_camera():
    """Camera/ 底下所有檔名 → 路徑清單(可能同名多個)。硬碟沒插就回空的。"""
    idx = collections.defaultdict(list)
    if not os.path.isdir(CAMERA):
        return idx, False
    for root, dirs, files in os.walk(CAMERA):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if not fn.startswith("."):
                idx[fn].append(os.path.join(root, fn))
    return idx, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--all", action="store_true", help="總表全部,不只最近一批")
    a = ap.parse_args()

    rows = load()
    if a.all:
        title = "總表全部"
    elif a.batch:
        rows = [r for r in rows if a.batch in (r.get("標籤") or "")]
        title = a.batch
    else:
        # ⛔ 不多問一句 —— 直接抓總表最後一天做的那些。
        days = sorted({r["review日期"] for r in rows if r.get("review日期")})
        last = days[-1] if days else ""
        rows = [r for r in rows if r.get("review日期") == last]
        title = f"最近一批({last} 做的)"

    if not rows:
        print("❌ 總表裡找不到符合的列。"); sys.exit(1)

    print(f"📋 {title}:總表有 {len(rows)} 張")
    idx, has_disk = index_camera()
    if not has_disk:
        print(f"⚠️ 沒偵測到 {CAMERA} —— 隨身硬碟沒插,只能檢查總表記的路徑本身。")
    print()

    stat = collections.defaultdict(lambda: dict(n=0, ok=0, xmp=0, moved=0, lost=0, amb=0, dup=0))
    fixes = []
    dups = []
    for r in rows:
        d = r["資料夾"]; p = r["路徑"]; s = stat[d]; s["n"] += 1
        if os.path.exists(p):
            s["ok"] += 1
            if os.path.exists(p + ".xmp"):
                s["xmp"] += 1
            # ⚠️ 原位還在,但 Camera/ 底下也有同名檔 → **同一張照片有兩份**。
            # 真的發生過:落地作用在 temp 那一份(刪了 46 張、寫了 94 個 xmp),
            # 而 Darktable 匯入的是硬碟上那份**落地之前**的副本(140 張、零個 xmp)。
            # 看起來「匯入了卻讀不到標籤」,其實是在看另一份照片。
            for c in idx.get(os.path.basename(p), []):
                if os.path.abspath(c) != os.path.abspath(p):
                    s["dup"] += 1
                    dups.append((p, c))
                    break
            continue
        # 原位置沒了 → 去 Camera 找同名
        cands = idx.get(os.path.basename(p), [])
        if len(cands) == 1:
            s["moved"] += 1
            if os.path.exists(cands[0] + ".xmp"):
                s["xmp"] += 1
            fixes.append((r, cands[0]))
        elif len(cands) > 1:
            s["amb"] += 1
        else:
            s["lost"] += 1

    hdr = f"{'資料夾':<28}{'總表':>5}{'在原位':>7}{'搬過家':>7}{'找不到':>7}{'有.xmp':>8}{'硬碟也有':>9}"
    print(hdr); print("─" * len(hdr))
    for d, s in sorted(stat.items()):
        amb = f"  ⚠️同名{s['amb']}" if s["amb"] else ""
        print(f"{d:<28}{s['n']:>5}{s['ok']:>7}{s['moved']:>7}{s['lost']:>7}{s['xmp']:>8}{s['dup']:>9}{amb}")
    print()

    tot = sum(s["n"] for s in stat.values())
    txmp = sum(s["xmp"] for s in stat.values())
    tlost = sum(s["lost"] for s in stat.values())
    tmoved = sum(s["moved"] for s in stat.values())

    # ⛔ 不要丟一張表叫使用者自己判讀 —— 直接講結論與要做的動作。
    print("──────────────────────────────────────────")
    if not has_disk:
        print("❓ 硬碟沒插,量不準。插上去再點一次這個。")
    elif tlost == tot:
        print("❓ 這一批的照片一張都找不到。是不是搬到 Camera/ 以外的地方了?")
    elif sum(s["dup"] for s in stat.values()):
        n = sum(s["dup"] for s in stat.values())
        print(f"⚠️ 有 {n} 張照片同時存在兩個地方 —— 你有兩份副本。")
        print("   評分檔(.xmp)只寫在其中一份旁邊,Darktable 匯入另一份就什麼都讀不到。")
        print("   範例:")
        for a, b in dups[:3]:
            print(f"     有評分 {a}\n     沒評分 {b}")
        print("   → 建議:把沒評分的那一份丟垃圾桶,再把有評分的整夾搬過去。")
    elif txmp == tot and tmoved == 0:
        print("✅ 照片都在原位,評分檔也都在。")
        print("   → Darktable 看不到的話,原因是**那些資料夾還沒匯入**。")
        print("     Darktable 左下角「匯入」→「加入資料夾」,把缺的那幾夾加進去就好。")
    elif txmp == tot:
        print("✅ 評分檔都跟著照片走了,資料沒掉。")
        print(f"   → 但有 {tmoved} 張搬過家,總表記的還是舊路徑(下面可以修)。")
        print("     Darktable 那邊:把搬到新位置的資料夾重新匯入一次。")
    else:
        miss = tot - txmp
        print(f"⚠️ 有 {miss} 張照片旁邊沒有評分檔(.xmp)。")
        print("   Darktable 匯入這些只會看到空白 —— 星等、標籤、心得都讀不到。")
        print("   最常見的原因:搬家時只選了照片,沒把旁邊的 .xmp 一起搬。")
        print("   → 先去舊位置看看 .xmp 還在不在;還在就整批補搬過去。")
        print("     真的沒了要跟 AI 說,可以從總表重寫一份。")

    if fixes:
        print(f"\n🔀 有 {len(fixes)} 張搬過家,總表的路徑已經失效。範例:")
        for r, new in fixes[:3]:
            print(f"   {r['檔名']}\n     舊 {r['路徑']}\n     新 {new}")
        if a.fix:
            byold = {r["路徑"]: new for r, new in fixes}
            allrows = load()
            for r in allrows:
                if r["路徑"] in byold:
                    r["路徑"] = byold[r["路徑"]]
            # 備份放垃圾桶(可從 Finder 還原),⛔ 不放筆記資料夾 —— 那裡可能正在被同步
            bak = os.path.expanduser("~/.Trash/照片日記總表_修路徑前_"
                                     + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv")
            shutil.copy2(DIARY, bak)
            tmp = DIARY + ".tmp"
            with io.open(tmp, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(allrows[0]), lineterminator="\r\n")
                w.writeheader(); w.writerows(allrows)
            os.replace(tmp, DIARY)
            print(f"\n✅ 已更新 {len(fixes)} 列的路徑(舊檔備份在垃圾桶:{os.path.basename(bak)})")
        else:
            print("\n   要修的話:同一行指令後面加 --fix(會先備份總表)")


if __name__ == "__main__":
    main()
