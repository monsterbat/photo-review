#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「版面比 template.html 舊」的審片頁全部自動重產 —— 不需要使用者動任何手。

── 為什麼要有這支 ──────────────────────────────────────────────
審片頁是**產生當下把 template.html 烤進去的靜態檔**,所以版面一改,舊頁不會自己長出新功能。
第一版的做法是「在首頁標出舊版面,請使用者自己回去重產一次」。那是錯的:

  「為什麼要搞這麼複雜?為什麼不直接讓大家都套用最新的就好了,然後保留原本已經有的資訊,
   也套用在新的上面?你為什麼要把事情搞這麼複雜,又讓我操作這麼多東西?」

他是對的。⛔ 不要把工具的內部性質變成使用者的步驟。現在改成:每次打開審查台就自動重產。

**評分為什麼不會掉:** 評分存在瀏覽器 localStorage,key = `photoreview::<根路徑>`(generate.py)。
同一個資料夾重產 → key 一樣 → 星等/心得/標籤全部原封不動接回去。⛔ 改 key 的規則就會弄丟他的評分。

**為什麼夠快:** EXIF 有快取(generate.py 的 .meta_cache.json)、預覽圖已存在就跳過。
所以重產通常只是把 HTML 重寫一次。
"""
import os, re, sys, json, subprocess

from photo_review import config

OUT = config.OUTPUT_DIR
TEMPLATE = os.path.join(config.TEMPLATES_DIR, "template.html")
PAGE_SUFFIX = re.compile(r"_p(\d+)$")
# ⚠️ 這裡一定要用 json 解碼:`generate` 用 json.dumps 寫這一行,中文會變成 \uXXXX。
#    直接拿字面值去 os.path.isdir(),所有「名字有中文」的資料夾都會被判成
#    「找不到,硬碟沒插?」而安靜跳過,只有純數字命名的夾更新成功。錯得很像環境問題,查很久。
KEY_RE = re.compile(r'const KEY\s*=\s*("(?:[^"\\]|\\.)*");')
DATA_RE = re.compile(r'^const DATA = (\[.*\]);\s*$', re.M)


def groups():
    """output/*.html → {夾名: [檔名…]}(第 1 頁在前)"""
    g = {}
    if not os.path.isdir(OUT):
        return g
    for fn in sorted(os.listdir(OUT)):
        if not fn.endswith(".html") or fn == "index.html":
            continue
        if fn.startswith("confirm_"):
            continue
        stem = fn[:-5]
        m = PAGE_SUFFIX.search(stem)
        base, n = (stem[:m.start()], int(m.group(1))) if m else (stem, 1)
        g.setdefault(base, []).append((n, fn))
    return {b: [f for _, f in sorted(v)] for b, v in g.items()}


def roots_of(page_path):
    """從產好的頁面裡挖回「當初是用哪幾個資料夾產的」與「有沒有掃子資料夾」。"""
    try:
        with open(page_path, encoding="utf-8") as f:
            html = f.read()
    except OSError:
        return None, False
    m = KEY_RE.search(html)
    if not m:
        return None, False
    try:
        key = json.loads(m.group(1))
    except ValueError:
        return None, False
    if not key.startswith("photoreview::"):
        return None, False
    roots = [r for r in key[len("photoreview::"):].split("|") if r]
    recursive = False
    d = DATA_RE.search(html)
    if d:
        try:
            for ph in json.loads(d.group(1)):
                if os.path.dirname(ph["path"]) not in roots:
                    recursive = True
                    break
        except Exception:
            pass
    return roots, recursive


def main():
    quiet = "--quiet" in sys.argv
    if not os.path.exists(TEMPLATE):
        return 0
    tpl = os.path.getmtime(TEMPLATE)

    todo = []
    for base, pages in groups().items():
        first = os.path.join(OUT, pages[0])
        if os.path.getmtime(first) >= tpl:
            continue                      # 已經是最新版面
        roots, rec = roots_of(first)
        if not roots:
            print(f"⚠️ {base}:讀不出當初的資料夾,跳過(要用新版面請重新選一次資料夾)")
            continue
        missing = [r for r in roots if not os.path.isdir(r)]
        if missing:
            # 隨身硬碟沒插 / 資料夾搬走了 → 誠實跳過,⛔ 不要重產成一頁空的把舊頁蓋掉
            if not quiet:
                print(f"⏭ {base}:找不到 {missing[0]}(硬碟沒插?),先跳過")
            continue
        todo.append((base, roots, rec))

    if not todo:
        return 0

    print(f"版面更新了,正在把 {len(todo)} 個審片頁換成新版面(你打過的星等與心得會原樣接回去)…")
    ok = 0
    for i, (base, roots, rec) in enumerate(todo, 1):
        print(f"  [{i}/{len(todo)}] {base}", flush=True)
        # --yes:這是「重產已經存在的頁面」,來源當初就選過了。
        # ⛔ 不加的話,來源在暫存夾的舊頁會在這裡停下來等人打 y,而這時沒有人在看(2026-09-08)。
        cmd = ([sys.executable, "-m", "photo_review.review.generate"]
               + roots + ["--no-open", "--yes"])
        if rec:
            cmd.append("--recursive")
        # ⛔ 不要 capture_output —— 吞掉輸出會讓幾千張的夾看起來像當掉。讓它直接印出來。
        r = subprocess.run(cmd)
        if r.returncode == 0:
            ok += 1
        else:
            print(f"     ❌ 失敗(回傳碼 {r.returncode}),這一夾維持舊版面,下次打開會再試一次")
    print(f"完成:{ok}/{len(todo)} 個已換成新版面")
    return 0


if __name__ == "__main__":
    sys.exit(main())
