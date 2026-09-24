#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「下載」資料夾裡的審片匯出檔搬到專案的 temp/,好讓後面的工具看得到。

── 為什麼 ──────────────────────────────────────────────────
瀏覽器只會下載到「下載」資料夾,而後面的工具都在專案的 temp/ 底下找檔案。
⛔ 不要叫使用者每次自己拖檔案:打開審查台時順手搬就好。

只搬 `pick_*.json` / `review_*.json` / `confirmed_*.json`,⛔ 不碰其他檔案。
同名就加 `_2`、`_3`,⛔ 不覆蓋。

── 內容一樣的就不要再搬一次 ────────────────────────────────────
瀏覽器每按一次「匯出」就多一個檔,按兩次就有兩份一模一樣的,
搬過來變成 `xxx.json` 和 `xxx_2.json`,落地時被當成兩批各做一次。
**xmp 那邊不會壞(已有就跳過),但照片日記總表會多出一整批重複的列。**
所以搬之前先比對內容:跟 temp/ 或 temp/已處理/ 裡任何一份完全相同 → 不搬,
來源那份直接丟垃圾桶(⛔ 用 trash 不用 rm,救得回來)。
"""
import os, shutil, glob, hashlib, subprocess

from photo_review import config

HOME = os.path.expanduser("~")
DOWNLOADS = os.path.join(HOME, "Downloads")
DEST = config.TEMP_DIR
PATTERNS = ("pick_*.json", "review_*.json", "confirmed_*.json")


def sha(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def known_hashes():
    """temp/ 與 temp/已處理/ 裡已經有的匯出檔內容指紋。"""
    out = {}
    for d in (DEST, os.path.join(DEST, "已處理")):
        for f in glob.glob(os.path.join(d, "*.json")):
            k = sha(f)
            if k:
                out.setdefault(k, f)
    return out


def unique(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def main():
    if not os.path.isdir(DOWNLOADS):
        return []
    os.makedirs(DEST, exist_ok=True)
    seen = known_hashes()
    moved, dupes = [], []
    for pat in PATTERNS:
        for src in sorted(glob.glob(os.path.join(DOWNLOADS, pat))):
            k = sha(src)
            if k and k in seen:
                # 內容跟已經有的一模一樣 → 重複按了匯出。⛔ 不要搬進來變成第二批。
                subprocess.run(["trash", src], check=False)
                dupes.append((os.path.basename(src), os.path.basename(seen[k])))
                continue
            dst = unique(os.path.join(DEST, os.path.basename(src)))
            try:
                shutil.move(src, dst)
                moved.append(dst)
                if k:
                    seen[k] = dst
            except OSError as e:
                print(f"⚠️ 搬不動 {os.path.basename(src)}:{e}")
    if dupes:
        print(f"♻️ 有 {len(dupes)} 個是重複按匯出產生的,內容完全一樣 → 已丟垃圾桶,沒有搬進來:")
        for a, b in dupes:
            print(f"   {a}  ≡  {b}")
    if moved:
        print(f"📤 從「下載」搬了 {len(moved)} 個匯出檔到 temp/,後面的工具看得到了:")
        for m in moved:
            print("   " + os.path.basename(m))
        print("   → 把上面的檔名跟 AI 說一聲就行。")
    return moved


if __name__ == "__main__":
    main()
