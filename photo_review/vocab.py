#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""從用語表的「固定用語表」一節讀出四類標籤用語 —— 審片頁的標籤按鈕就是拿這份長出來的。

用語表是哪個檔,由 `config` 的 vocab_file 決定(預設 `vocab.example.md`)。
這裡只負責讀,**不另存一份清單** —— 同一份資料抄成兩份,遲早會對不起來。

回傳形狀:
    {"作品": [...], "用途": [...], "地點": [...], "主題": [...]}

鍵盤快捷鍵在 KEYS 這裡定,不在用語表裡 —— 用語表管「有哪些用語」,快捷鍵是工具自己的事。
"""
import os, re

from photo_review import config

VOCAB_FILE = config.VOCAB_FILE

CATS = ["作品", "用途", "地點", "主題"]

# 每一類分到哪幾個字母。⛔ 不要用數字(0–5 已經是星等)、不要用 x(刪除)、f(心得框)、c(沿用上一張)。
KEYS = {"作品": "qwerty", "用途": "asdghj", "地點": "zvbnm", "主題": "uiop"}

# 一行一類,形如:**作品:** A、B、C …(可能有 (中文…) 這種括號註解要拿掉)
LINE = re.compile(r"^\*\*(作品|用途|地點|主題)[:：]\*\*\s*(.+)$", re.M)
DROP = re.compile(r"[（(][^）)]*[）)]")          # 去掉行內括號註解
TAIL = re.compile(r"\s*…+\s*$")                  # 去掉結尾的「…」


def load():
    out = {c: [] for c in CATS}
    if not os.path.isfile(VOCAB_FILE):
        return out
    with open(VOCAB_FILE, encoding="utf-8") as f:
        text = f.read()
    for cat, body in LINE.findall(text):
        body = DROP.sub("", body)
        body = TAIL.sub("", body)
        terms = []
        for t in re.split(r"[、,，]", body):
            t = t.strip().strip("*")
            t = TAIL.sub("", t)
            if t and t not in terms:
                terms.append(t)
        out[cat] = terms
    return out


def as_payload():
    """給 template.html 用的形狀:{類: {"keys": "...", "items": [...]}}"""
    v = load()
    return {c: {"keys": KEYS.get(c, ""), "items": v[c]} for c in CATS}


if __name__ == "__main__":
    import json
    v = load()
    for c in CATS:
        print(f"{c}({len(v[c])}): {'、'.join(v[c])}")
