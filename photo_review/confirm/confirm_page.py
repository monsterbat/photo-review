#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 確認頁產生器
--------------------
吃「Phase 1 匯出 JSON」+「Claude 的提案 JSON」→ 產一頁確認 HTML:
每張照片顯示 AI 提案的心得(整理過)/星等/顏色/標籤,使用者可改;
AI 有調整的卡片黃底、沒動的綠底。確認後匯出 confirmed JSON → 交 apply.py 落地。

提案 JSON 格式(Claude 產,只需列有提案的照片,其餘沿用原值):
    {"photos":[{"path":"...","note":"整理後心得","stars":4,"color":"green","tags":["新宿","拉麵"],"delete":false}, ...]}

用法:
    python3 -m photo_review.confirm.confirm_page <phase1匯出.json> <提案.json> [--out-dir DIR] [--no-open]
"""
import os, sys, json, argparse, subprocess
from photo_review.review.generate import make_preview, file_url, NEED_PRE

from photo_review import config


def norm_tags(t):
    if isinstance(t, list):
        return t
    if isinstance(t, str):
        return [x for x in t.replace(",", " ").split() if x]
    return []


def changed(orig, prop):
    if (orig.get("note", "") or "") != (prop.get("note", "") or ""): return True
    if int(orig.get("stars", 0) or 0) != int(prop.get("stars", 0) or 0): return True
    if (prop.get("color", "") or "") != (orig.get("color", "") or ""): return True
    if norm_tags(prop.get("tags", [])) != norm_tags(orig.get("tags", [])): return True
    if bool(orig.get("delete", False)) != bool(prop.get("delete", False)): return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export"); ap.add_argument("proposals")
    ap.add_argument("--out-dir", default=""); ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    exp = json.load(open(a.export, encoding="utf-8"))
    prop_raw = json.load(open(a.proposals, encoding="utf-8"))
    props = {p["path"]: p for p in prop_raw.get("photos", [])}

    out_dir = os.path.abspath(a.out_dir) if a.out_dir else config.OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    prev_dir = os.path.join(out_dir, ".previews")

    root = exp.get("root", "")
    data = []
    for ph in exp["photos"]:
        path = ph["path"]
        orig = {"note": ph.get("note", ""), "stars": ph.get("stars", 0),
                "color": ph.get("color", ""), "tags": ph.get("tags", []),
                "delete": ph.get("delete", False)}
        pr = props.get(path, {})
        prop = {"note": pr.get("note", orig["note"]),
                "stars": int(pr.get("stars", orig["stars"]) or 0),
                "color": pr.get("color", orig["color"]),
                "tags": norm_tags(pr.get("tags", orig["tags"])),
                "delete": bool(pr.get("delete", orig["delete"]))}
        ext = ph.get("ext", os.path.splitext(path)[1].lstrip(".")).lower()
        src, warn = file_url(path), ""
        if ("." + ext) in NEED_PRE:
            pv = make_preview(path, prev_dir)
            src = file_url(pv) if pv else ""
            if not pv: warn = "RAW/HEIC 預覽失敗"
        try:
            mb = round(os.path.getsize(path) / 1048576, 1)
        except OSError:
            mb = 0
        data.append({"path": path, "name": ph.get("name", os.path.basename(path)),
                     "src": src, "ext": ext, "mb": mb, "warn": warn,
                     "orig": orig, "prop": prop, "changed": changed(orig, prop)})

    tpl = open(os.path.join(config.TEMPLATES_DIR, "template2.html"), encoding="utf-8").read()
    base = os.path.basename(root.rstrip("/")) or "photos"
    html = (tpl.replace("__TITLE__", base).replace("__ROOT__", root)
               .replace("__STORAGE_KEY__", json.dumps("photoconfirm::" + root))
               .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    fp = os.path.join(out_dir, f"confirm_{base}.html")
    open(fp, "w", encoding="utf-8").write(html)

    n_chg = sum(1 for d in data if d["changed"])
    print(f"✓ 確認頁:{fp}\n  {len(data)} 張,AI 調整 {n_chg} 張")
    if not a.no_open:
        subprocess.run(["open", fp], check=False)


if __name__ == "__main__":
    main()
