#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片 Review 產生器
-------------------
吃一個資料夾 → 掃出裡面的照片 → 產生一頁可滾輪快速 review 的 HTML。

特色:
- JPG/PNG 直接用 file:// 指向原圖(不複製、不搬動),靠 lazy-load 保持流暢。
- HEIC/RAW 瀏覽器不能直接看 → 用 macOS 內建 sips/qlmanage 產一張縮圖預覽,
  放在工具自己的 .previews/ cache(不碰原始照片夾),可續跑。
- HTML 裡:⭐評分 / 🗑刪除標記 / 心得文字框(macOS fn fn 口述),即時存 localStorage。
- 「匯出」下載一個 JSON,回報給 Claude → 打 Darktable 標籤 + 寫進照片日記總表。

用法:
    python3 -m photo_review.review.generate "<資料夾路徑>" [--recursive] [--page-size N] [--out-dir DIR]
"""
import os, sys, csv, json, argparse, hashlib, subprocess, re, datetime
from photo_review import config  # 照片、紀錄、用語表放在哪
from photo_review import vocab   # 固定用語表 → 審片頁的標籤按鈕
from photo_review import gpsread # 讀 EXIF 裡的拍攝座標(沒有就是 None,不編造)
from urllib.request import pathname2url

WEB_OK   = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
NEED_PRE = {".heic", ".heif", ".cr2", ".cr3", ".arw", ".nef", ".dng", ".tif", ".tiff", ".raf", ".orf"}
IMG_EXT  = WEB_OK | NEED_PRE

VOCAB_PAYLOAD = vocab.as_payload()


# 照片正本住的地方(config.py 決定)。來源不在這底下 → 出聲警告,見 DESIGN.md §7。
SSD    = config.SSD_ROOT
CAMERA = config.CAMERA_ROOT


def check_source(roots, assume_yes):
    """來源不在隨身硬碟上就講清楚,要他打 y 才繼續。⛔ 不做硬性拒絕。"""
    outside = [r for r in roots if r != SSD and not r.startswith(SSD + os.sep)]
    if not outside:
        return
    if assume_yes:
        print(f"⚠️ 來源不在隨身硬碟上({outside[0]}),已指定 --yes,繼續。")
        return
    print("")
    print("⚠️ 你選的資料夾不在隨身硬碟上,而是在:")
    for r in outside:
        print(f"     {r}")
    print(f"   照片正本應該住在 {CAMERA}/ 底下。")
    print("   在這裡評分的話,評完的分數會留在這一份,隨身硬碟那一份還是空白的。")
    if not sys.stdin.isatty():
        print("   (現在不是你在旁邊操作的模式,我不停下來問,直接繼續)")
        return
    try:
        ans = input("   確定要繼續嗎?(y = 繼續,其他任何鍵 = 取消)> ").strip().lower()
    except EOFError:
        print("   (讀不到回答,直接繼續)")
        return
    if ans != "y":
        print("   已取消,什麼都沒做。")
        sys.exit(1)


def scan(folder, recursive):
    out = []
    if recursive:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".previews"]
            for f in files:
                if os.path.splitext(f)[1].lower() in IMG_EXT and not f.startswith("._"):
                    out.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            if os.path.isfile(p) and os.path.splitext(f)[1].lower() in IMG_EXT and not f.startswith("._"):
                out.append(p)
    out.sort()
    return out


def make_preview(src, prev_dir):
    """把不能直接顯示的格式產成 jpg 預覽,回傳預覽路徑(失敗回 None)。"""
    os.makedirs(prev_dir, exist_ok=True)
    key = hashlib.md5(src.encode("utf-8")).hexdigest()[:16]
    dst = os.path.join(prev_dir, key + ".jpg")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    # 先試 sips(HEIC/TIFF/部分 RAW)
    r = subprocess.run(["sips", "-s", "format", "jpeg", "-Z", "1800", src, "--out", dst],
                       capture_output=True)
    if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    # 再試 qlmanage(RAW 靠 Quick Look)
    tmp = os.path.join(prev_dir, "_ql")
    os.makedirs(tmp, exist_ok=True)
    subprocess.run(["qlmanage", "-t", "-s", "1800", "-o", tmp, src],
                   capture_output=True)
    ql = os.path.join(tmp, os.path.basename(src) + ".png")
    if os.path.exists(ql):
        try:
            os.replace(ql, dst)
            return dst
        except OSError:
            pass
    return None


def file_url(path):
    return "file://" + pathname2url(path)


def exif_meta(path):
    """一次讀 EXIF 拍攝時間+相機型號。回 (dev, 型號, 時間顯示, 時間排序key)。
    dev = 'iPhone'|'單眼'|''。一次 sips 拿三個值,省 subprocess。"""
    try:
        r = subprocess.run(["sips", "-g", "creation", "-g", "make", "-g", "model", path],
                           capture_output=True, text=True, timeout=10).stdout
    except Exception:
        r = ""
    make = model = creation = ""
    for line in r.splitlines():
        s = line.strip()
        if s.startswith("creation:"): creation = s[9:].strip()
        elif s.startswith("make:"):   make = s[5:].strip()
        elif s.startswith("model:"):  model = s[6:].strip()
    make = "" if make in ("<nil>", "(null)") else make
    model = "" if model in ("<nil>", "(null)") else model
    # creation 例:"2024:01:24 09:51:40"
    dt_disp = dt_sort = ""
    m = re.match(r"(\d{4}):(\d{2}):(\d{2})\s+(\d{2}):(\d{2}):(\d{2})", creation)
    if m:
        y, mo, d, h, mi, se = m.groups()
        dt_disp = f"{mo}/{d} {h}:{mi}"
        dt_sort = y + mo + d + h + mi + se
    else:
        try:
            t = datetime.datetime.fromtimestamp(os.path.getmtime(path))
            dt_disp = t.strftime("%m/%d %H:%M"); dt_sort = t.strftime("%Y%m%d%H%M%S")
        except Exception:
            pass
    if "Apple" in make or "iPhone" in model or "iPad" in model:
        dev = "iPhone"
    elif make or model:
        dev = "單眼"
    else:
        dev = ""
    return dev, (model or make), dt_disp, dt_sort


def load_prior(load_path):
    """讀先前匯出/確認的 JSON → {照片路徑: {s,d,n}},重跑時把分數烤回頁面。"""
    if not load_path or not os.path.exists(load_path):
        return {}
    try:
        d = json.load(open(load_path, encoding="utf-8"))
    except Exception:
        return {}
    m = {}
    for p in d.get("photos", []):
        m[p["path"]] = {"s": int(p.get("stars", 0) or 0),
                        "d": 1 if p.get("delete") else 0,
                        "n": p.get("note", "") or ""}
    return m


def _cache_path(out_dir):
    return os.path.join(out_dir, ".meta_cache.json")


def load_meta_cache(out_dir):
    """EXIF 讀一次就好。key=路徑,值帶 mtime+大小,檔案動過就自動失效。

    改版面之後要能**自動重產**所有審片頁(否則舊頁面永遠停在舊版面),
    而 1055 張照片各跑一次 `sips` 要好幾分鐘 → 快取讓重產幾乎是瞬間的。
    """
    try:
        return json.load(open(_cache_path(out_dir), encoding="utf-8"))
    except Exception:
        return {}


def save_meta_cache(out_dir, cache):
    try:
        os.makedirs(out_dir, exist_ok=True)
        json.dump(cache, open(_cache_path(out_dir), "w", encoding="utf-8"),
                  ensure_ascii=False)
    except Exception:
        pass


def build_photos(paths, prev_dir, prior=None, meta_cache=None):
    prior = prior or {}
    cache = meta_cache if meta_cache is not None else {}
    photos, need = [], [p for p in paths if os.path.splitext(p)[1].lower() in NEED_PRE]
    done = 0
    total_n = len(paths)
    for idx, p in enumerate(paths, 1):
        # 幾百張以上會跑一陣子,沒有進度就像當掉了
        if total_n >= 200 and (idx % 100 == 0 or idx == total_n):
            print(f"  讀照片資訊 {idx}/{total_n}", flush=True)
        ext = os.path.splitext(p)[1].lower()
        try:
            st = os.stat(p)
            size_mb = round(st.st_size / 1048576, 1)
        except OSError:
            size_mb = 0
        src, warn = file_url(p), ""
        if ext in NEED_PRE:
            done += 1
            print(f"  產預覽 {done}/{len(need)}  {os.path.basename(p)}", flush=True)
            pv = make_preview(p, prev_dir)
            if pv:
                src = file_url(pv)
            else:
                src, warn = "", "無法預覽(RAW/HEIC 預覽失敗)"
        try:
            sig = [int(st.st_mtime), int(st.st_size)]
        except Exception:
            sig = None
        hit = cache.get(p) if sig else None
        if hit and hit[:2] == sig and len(hit) >= 7:
            dev, devmodel, dt_disp, dt_sort, gps = hit[2], hit[3], hit[4], hit[5], hit[6]
        else:
            dev, devmodel, dt_disp, dt_sort = exif_meta(p)
            gps = gpsread.read(p)
            gps = list(gps) if gps else None
            if sig:
                cache[p] = sig + [dev, devmodel, dt_disp, dt_sort, gps]
        photos.append({
            "path": p,
            "name": os.path.basename(p),
            "src": src,
            "mb": size_mb,
            "ext": ext.lstrip("."),
            "warn": warn,
            "dev": dev,
            "devmodel": devmodel,
            "dt": dt_disp,
            "dtsort": dt_sort,
            "gps": gps,
            "pre": prior.get(p, {"s": 0, "d": 0, "n": ""}),
        })
    # 依「資料夾 → 拍攝時間」排序:同夾內舊→新,多夾各自成組
    photos.sort(key=lambda x: (os.path.dirname(x["path"]), x["dtsort"] or "9", x["name"]))
    return photos


def render(photos, title, root_display, storage_key, out_base, page_size, out_dir):
    tpl = open(os.path.join(config.TEMPLATES_DIR, "template.html"), encoding="utf-8").read()
    total = len(photos)
    pages = [photos[i:i + page_size] for i in range(0, total, page_size)] or [[]]
    base = out_base
    written = []
    for idx, chunk in enumerate(pages, 1):
        # 分頁導覽
        if len(pages) > 1:
            links = []
            for j in range(1, len(pages) + 1):
                fn = f"{base}.html" if j == 1 else f"{base}_p{j}.html"
                cls = "cur" if j == idx else ""
                links.append(f'<a class="{cls}" href="{fn}">{j}</a>')
            nav = '<div class="pagenav">頁:' + " ".join(links) + "</div>"
        else:
            nav = ""
        html = (tpl
                .replace("__TITLE__", title)
                .replace("__ROOT__", root_display)
                .replace("__STORAGE_KEY__", json.dumps(storage_key))
                .replace("__TOTAL__", str(total))
                .replace("__NAV__", nav)
                .replace("__VOCAB__", json.dumps(VOCAB_PAYLOAD, ensure_ascii=False))
                .replace("__DATA__", json.dumps(chunk, ensure_ascii=False)))
        fn = f"{base}.html" if idx == 1 else f"{base}_p{idx}.html"
        fp = os.path.join(out_dir, fn)
        open(fp, "w", encoding="utf-8").write(html)
        written.append(fp)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--page-size", type=int, default=250)
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--load", default="", help="先前匯出/確認的 JSON,把分數烤回頁面")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--yes", action="store_true", help="來源不在隨身硬碟時不要停下來問(重產舊頁面用)")
    a = ap.parse_args()

    roots = []
    for f in a.folders:
        r = os.path.abspath(os.path.expanduser(f))
        if not os.path.isdir(r):
            print(f"✗ 找不到資料夾:{r}"); sys.exit(1)
        if r not in roots:
            roots.append(r)

    check_source(roots, a.yes)

    out_dir = os.path.abspath(a.out_dir) if a.out_dir else config.OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    prev_dir = os.path.join(out_dir, ".previews")

    paths = []
    for r in roots:
        print(f"掃描:{r}" + ("(含子資料夾)" if a.recursive else ""))
        sub = scan(r, a.recursive)
        print(f"  {len(sub)} 張")
        paths.extend(sub)
    print(f"合計找到 {len(paths)} 張照片(跨 {len(roots)} 夾)")
    if not paths:
        print("沒有照片,結束。"); sys.exit(0)

    # 單夾 vs 多夾的標題/儲存key/檔名
    if len(roots) == 1:
        title = os.path.basename(roots[0].rstrip("/")) or "photos"
        root_display = roots[0]
        storage_key = "photoreview::" + roots[0]
        out_base = title
    else:
        title = f"{len(roots)} 個資料夾"
        root_display = " ; ".join(os.path.basename(r.rstrip("/")) for r in roots)
        storage_key = "photoreview::" + "|".join(roots)   # 同一組選取穩定 → 評分不掉
        out_base = "multi_" + hashlib.md5("|".join(roots).encode()).hexdigest()[:8]

    prior = load_prior(a.load)
    if prior:
        print(f"讀回先前評分:{len(prior)} 筆")
    mcache = load_meta_cache(out_dir)
    photos = build_photos(paths, prev_dir, prior, mcache)
    save_meta_cache(out_dir, mcache)
    written = render(photos, title, root_display, storage_key, out_base, a.page_size, out_dir)

    n_warn = sum(1 for p in photos if p["warn"])
    print(f"\n✓ 完成:{len(written)} 頁,{len(photos)} 張" + (f"({n_warn} 張預覽失敗)" if n_warn else ""))
    print(f"  輸出:{written[0]}")
    if not a.no_open:
        subprocess.run(["open", written[0]], check=False)


if __name__ == "__main__":
    main()
