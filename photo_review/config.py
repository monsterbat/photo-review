#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""這台機器上「東西放在哪」的設定,全部集中在這一支。

為什麼要有它:程式碼只有一份,但每個人的照片、筆記放的位置都不一樣。
把位置寫死在程式裡,換一個人用就要改程式;集中到這裡之後,換人只要換一份設定檔。

找設定的順序(先找到的贏):
  ① 環境變數 PHOTO_REVIEW_CAMERA_ROOT / PHOTO_REVIEW_NOTES_DIR / PHOTO_REVIEW_VOCAB_FILE
  ② 同一個資料夾底下的 config.local.json    ← 自己的設定,不對外
  ③ 同一個資料夾底下的 config.example.json  ← 範例設定
  ④ 下面的 DEFAULTS

相容:舊的環境變數 SC_CAMERA_ROOT / SC_SSD_ROOT 仍然有效(測試在用)。

用法:
    import config
    config.CAMERA_ROOT    # 照片正本的根目錄
    config.NOTES_DIR      # 三份 CSV 紀錄放哪
    config.DIARY_CSV / MASTER_CSV / DELLOG_CSV / VOCAB_FILE
    python3 -m photo_review.config     # 印出現在實際用的是什麼,以及是從哪裡讀到的
"""
import json
import os

PKG = os.path.dirname(os.path.abspath(__file__))        # photo_review/ 套件本身
ROOT = os.path.dirname(PKG)                             # 專案根目錄
TEMPLATES_DIR = os.path.join(PKG, "templates")          # 審片頁與確認頁的樣板
OUTPUT_DIR = os.path.join(ROOT, "output")               # 產出的審片頁
LOCAL_FILE = os.path.join(ROOT, "config.local.json")
EXAMPLE_FILE = os.path.join(ROOT, "config.example.json")

# 沒有任何設定檔時的最後防線。刻意寫成通用的,不綁任何一台機器。
DEFAULTS = {
    "camera_root": "~/Pictures/PhotoLibrary",
    "notes_dir": "../../notes",
    "vocab_file": "vocab.example.md",
    "temp_dir": "./temp",
}

# 每個欄位各自的環境變數(新名字優先,舊名字沿用)
ENV = {
    "camera_root": ("PHOTO_REVIEW_CAMERA_ROOT", "SC_CAMERA_ROOT"),
    "notes_dir": ("PHOTO_REVIEW_NOTES_DIR",),
    "vocab_file": ("PHOTO_REVIEW_VOCAB_FILE",),
    "temp_dir": ("PHOTO_REVIEW_TEMP_DIR",),
}


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _resolve(value):
    """設定檔裡可以寫相對路徑(相對於這個工具的資料夾)或 ~。"""
    value = os.path.expanduser(str(value))
    if not os.path.isabs(value):
        value = os.path.join(ROOT, value)
    return os.path.normpath(value)


def _load():
    """回傳 (設定, 每個欄位是從哪裡來的)。"""
    local, example = _read(LOCAL_FILE), _read(EXAMPLE_FILE)
    out, where = {}, {}
    for key, default in DEFAULTS.items():
        for name in ENV[key]:
            if os.environ.get(name):
                out[key], where[key] = os.environ[name], f"環境變數 {name}"
                break
        else:
            if key in local:
                out[key], where[key] = local[key], "config.local.json"
            elif key in example:
                out[key], where[key] = example[key], "config.example.json"
            else:
                out[key], where[key] = default, "程式內建預設"
    return out, where


_CFG, SOURCES = _load()

CAMERA_ROOT = _resolve(_CFG["camera_root"])
# 隨身硬碟的掛載點 = 照片根目錄的上一層。generate.py 用它判斷「來源在不在硬碟上」。
SSD_ROOT = os.environ.get("SC_SSD_ROOT") or os.path.dirname(CAMERA_ROOT)
NOTES_DIR = _resolve(_CFG["notes_dir"])
VOCAB_FILE = _resolve(_CFG["vocab_file"])
TEMP_DIR = _resolve(_CFG["temp_dir"])    # 匯出檔的中繼站

DIARY_CSV = os.path.join(NOTES_DIR, "照片日記總表.csv")
MASTER_CSV = os.path.join(NOTES_DIR, "照片庫總表.csv")
DELLOG_CSV = os.path.join(NOTES_DIR, "照片Review_刪除log.csv")


def describe():
    """一行一個設定,標明值與出處 —— 位置不對的時候一眼看得出是哪一份設定檔在生效。"""
    rows = [
        ("照片正本 camera_root", CAMERA_ROOT, SOURCES["camera_root"]),
        ("紀錄目錄 notes_dir", NOTES_DIR, SOURCES["notes_dir"]),
        ("標籤表 vocab_file", VOCAB_FILE, SOURCES["vocab_file"]),
        ("中繼站 temp_dir", TEMP_DIR, SOURCES["temp_dir"]),
    ]
    out = []
    for label, value, src in rows:
        mark = "✅" if os.path.exists(value) else "⚠️ 不存在"
        out.append(f"{label:24s} {value}\n{'':24s} └ 來自 {src}　{mark}")
    return "\n".join(out)


if __name__ == "__main__":
    print(describe())
