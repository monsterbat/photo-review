#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把一個標籤整批改名:照片日記總表 +(選用)照片旁的 .xmp
----------------------------------------------------------
為什麼要有這支:固定用語表改了寫法之後,舊資料不會自己跟著變。
  實例:後來決定日本地名一律用日文漢字「渋谷」,但更早落地的 45 張還寫著「澀谷」,
  同一個地方裂成兩個標籤,在 Darktable 查「渋谷」會漏掉那 45 張。
  同一類的還有「御台場 → お台場」這種寫法之爭。

⛔ 只動「標籤」那一欄。心得是使用者自己寫的話,裡面提到某個地名是正常的,一個字都不碰。

用法(預設只預覽,加 --apply 才真的改):
    python3 -m photo_review.library.rename_tag "地點|澀谷" "地點|渋谷"                  # 總表:列出會改哪幾張
    python3 -m photo_review.library.rename_tag "地點|澀谷" "地點|渋谷" --apply          # 總表:改(原檔先複製一份進垃圾桶)
    python3 -m photo_review.library.rename_tag "地點|澀谷" "地點|渋谷" --xmp            # 照片旁的 .xmp:預覽(要硬碟插著)
    python3 -m photo_review.library.rename_tag "地點|澀谷" "地點|渋谷" --xmp --apply
"""
import os, re, sys, csv, io, shutil, datetime
import xml.etree.ElementTree as ET

from photo_review import config

DIARY = config.DIARY_CSV
SSD = config.SSD_ROOT
TAGCOL = "標籤"


def die(msg):
    print(f"❌ {msg}")
    sys.exit(1)


def rename_in(tags, old, new):
    """一列的標籤清單:old 換成 new,換完去重(new 本來就在的話不要出現兩次)。"""
    out = []
    for t in tags:
        t = new if t == old else t
        if t not in out:
            out.append(t)
    return out


def read_diary():
    raw = open(DIARY, "rb").read()
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    return raw, rows


def do_diary(old, new, apply):
    raw, rows = read_diary()
    head, body = rows[0], rows[1:]
    if TAGCOL not in head:
        die(f"總表找不到「{TAGCOL}」欄,欄位是:{head}")
    ti = head.index(TAGCOL)
    fi, ni = head.index("資料夾"), head.index("檔名")

    hits = [i for i, r in enumerate(body) if old in r[ti].split()]
    print(f"總表:{len(body)} 列,其中 {len(hits)} 列有「{old}」")
    by_folder = {}
    for i in hits:
        by_folder.setdefault(body[i][fi], []).append(body[i][ni])
    for f, names in sorted(by_folder.items()):
        print(f"   {f}  {len(names)} 張:{'、'.join(names[:6])}{' …' if len(names) > 6 else ''}")
    if not hits:
        return 0
    if not apply:
        print(f"\n(這只是預覽。加 --apply 才會把這 {len(hits)} 列的「{old}」改成「{new}」)")
        return len(hits)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = os.path.expanduser(f"~/.Trash/照片日記總表_改名前_{stamp}.csv")
    shutil.copy2(DIARY, backup)

    new_body = [list(r) for r in body]
    for i in hits:
        new_body[i][ti] = " ".join(rename_in(new_body[i][ti].split(), old, new))

    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")     # 跟 apply.py 寫出來的一樣:CRLF
    w.writerow(head)
    w.writerows(new_body)
    tmp = DIARY + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        f.write(buf.getvalue())

    # 寫出去之前自己驗一次:列數一樣、除了標籤欄以外每一格都一樣、舊標籤一個不剩
    check = list(csv.reader(io.StringIO(open(tmp, "rb").read().decode("utf-8-sig"), newline="")))
    cb = check[1:]
    problems = []
    if len(cb) != len(body):
        problems.append(f"列數變了 {len(body)} → {len(cb)}")
    for a, b in zip(body, cb):
        if [x for k, x in enumerate(a) if k != ti] != [x for k, x in enumerate(b) if k != ti]:
            problems.append(f"標籤以外的欄位被動到:{a[fi]}/{a[ni]}")
            break
    left = sum(1 for r in cb if old in r[ti].split())
    if left:
        problems.append(f"還剩 {left} 列有「{old}」")
    if problems:
        os.remove(tmp)
        die("驗證沒過,總表沒有動:" + ";".join(problems))
    os.replace(tmp, DIARY)
    print(f"\n✅ 已改 {len(hits)} 列。原檔備份在垃圾桶:{os.path.basename(backup)}")
    return len(hits)


def do_xmp(old, new, apply):
    if not os.path.isdir(SSD):
        die(f"隨身硬碟沒插({SSD} 不存在),照片旁的 .xmp 看不到。插上再跑一次。")
    _, rows = read_diary()
    head, body = rows[0], rows[1:]
    pi = head.index("路徑")
    old_leaf, new_leaf = old.split("|")[-1], new.split("|")[-1]
    # ⛔ 不靠總表篩「哪幾張有舊標籤」:總表可能已經改過了。總表裡每一張都打開來看。
    paths = sorted({r[pi] for r in body if r[pi]})
    print(f"照片旁的 .xmp:總表共 {len(paths)} 張,逐張打開檢查")
    missing, todo, broken = 0, [], []
    for p in paths:
        x = p + ".xmp"
        if not os.path.exists(x):
            missing += 1
            continue
        try:
            text = open(x, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            broken.append((x, "讀不開"))
            continue
        if f">{old}<" not in text:
            continue
        out = text.replace(f"<rdf:li>{old}</rdf:li>", f"<rdf:li>{new}</rdf:li>")
        # 去重:new 本來就在的話,換完會出現兩次
        out = re.sub(rf"(<rdf:li>{re.escape(new)}</rdf:li>)(\s*)<rdf:li>{re.escape(new)}</rdf:li>", r"\1", out)
        # dc:subject 放的是最後一段(「澀谷」)。還有別的階層標籤也以它結尾,就不要換
        still = re.findall(rf"<rdf:li>[^<]*\|{re.escape(old_leaf)}</rdf:li>", out)
        if not still:
            out = out.replace(f"<rdf:li>{old_leaf}</rdf:li>", f"<rdf:li>{new_leaf}</rdf:li>")
            out = re.sub(rf"(<rdf:li>{re.escape(new_leaf)}</rdf:li>)(\s*)<rdf:li>{re.escape(new_leaf)}</rdf:li>", r"\1", out)
        elif f"<rdf:li>{new_leaf}</rdf:li>" not in out:
            # 舊的最後一段還有人要用,留著;新的那段也要補上,不然 dc:subject 會少一個
            out = out.replace(f"<rdf:li>{old_leaf}</rdf:li>",
                              f"<rdf:li>{old_leaf}</rdf:li><rdf:li>{new_leaf}</rdf:li>", 1)
        try:
            ET.fromstring(out)
        except ET.ParseError:
            broken.append((x, "改完不是合法的 XML,沒動"))
            continue
        todo.append((x, out))

    print(f"   有「{old}」的:{len(todo)} 張;旁邊沒有 .xmp 的:{missing} 張")
    for x, _ in todo[:8]:
        print(f"   · {os.path.relpath(x, SSD)}")
    if len(todo) > 8:
        print(f"   …還有 {len(todo) - 8} 張")
    for x, why in broken:
        print(f"   ❓ {os.path.relpath(x, SSD)} — {why}")
    if not todo:
        return 0
    if not apply:
        print(f"\n(這只是預覽。加 --xmp --apply 才會改這 {len(todo)} 個 .xmp)")
        return len(todo)
    for x, out in todo:
        tmp = x + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(out)
        os.replace(tmp, x)
    print(f"\n✅ 已改 {len(todo)} 個 .xmp。")
    print("   ⚠️ Darktable 如果已經匯入過這些照片,它的資料庫還記著舊名字。")
    print("      要它重讀:在 Darktable 選取那些照片 →「中繼資料」→「載入評分檔」。")
    return len(todo)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    old, new = args
    for t in (old, new):
        if "|" not in t or re.search(r"\s", t):
            die(f"「{t}」不像一個標籤:要有「|」(例:地點|渋谷),而且不能有空白")
    if old == new:
        die("新舊一樣,不用改")
    apply = "--apply" in sys.argv
    if "--xmp" in sys.argv:
        do_xmp(old, new, apply)
    else:
        do_diary(old, new, apply)


if __name__ == "__main__":
    main()
