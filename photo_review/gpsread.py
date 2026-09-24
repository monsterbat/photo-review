#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""讀照片裡的 GPS 座標(拍攝地點)。只用 Python 內建的東西,⛔ 不裝任何套件。

── 為什麼要自己寫(2026-08-23)────────────────────────────────────
需求:相機拍的照片通常帶著座標,希望在審片頁點一下就跳出地圖標點。
- `sips` 讀不到 GPS(它只給時間/廠牌/型號)。
- `exiftool` 不是內建的,⛔ 不該為了一個小功能就要使用者去裝東西。
- 所以直接解 EXIF:JPEG 走 APP1 區塊,ARW/NEF/DNG/TIFF 本身就是 TIFF 結構,同一套解法。
- HEIC 不是 TIFF 結構,解不了 → 退回 macOS 內建的 `mdls`(靠 Spotlight;外接碟沒建索引就會沒有)。

⚠️ **相機有沒有寫 GPS 是另一回事。** Sony A7 IV 機身沒有 GPS,要用手機的 App 連著相機才會寫進去;
iPhone 拍的則一定有。讀不到就是讀不到,⛔ 不要猜一個座標出來。
"""
import os, struct, subprocess

TIFF_EXT = {".arw", ".nef", ".dng", ".cr2", ".cr3", ".tif", ".tiff", ".orf", ".raf", ".rw2"}
JPEG_EXT = {".jpg", ".jpeg"}
MDLS_EXT = {".heic", ".heif", ".png", ".webp"}


def _rational(buf, off, order, count):
    out = []
    for i in range(count):
        num, den = struct.unpack(order + "II", buf[off + i * 8: off + i * 8 + 8])
        out.append(num / den if den else 0.0)
    return out


def _read_ifd(buf, base, off, order, want):
    """回傳 {tag: (type, count, value_offset_or_inline)},只挑 want 裡的 tag。"""
    got = {}
    try:
        n = struct.unpack(order + "H", buf[off:off + 2])[0]
    except struct.error:
        return got
    for i in range(n):
        e = off + 2 + i * 12
        if e + 12 > len(buf):
            break
        tag, typ, cnt = struct.unpack(order + "HHI", buf[e:e + 8])
        if tag not in want:
            continue
        raw = buf[e + 8:e + 12]
        size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}.get(typ, 1) * cnt
        if size > 4:
            ptr = struct.unpack(order + "I", raw)[0] + base
        else:
            ptr = e + 8
        got[tag] = (typ, cnt, ptr)
    return got


def _from_tiff(buf, base=0):
    """buf[base:] 是 TIFF 結構 → (lat, lon) 或 None"""
    head = buf[base:base + 4]
    if head[:2] == b"II":
        order = "<"
    elif head[:2] == b"MM":
        order = ">"
    else:
        return None
    ifd0 = struct.unpack(order + "I", buf[base + 4:base + 8])[0] + base
    top = _read_ifd(buf, base, ifd0, order, {0x8825})
    if 0x8825 not in top:
        return None
    gps_off = struct.unpack(order + "I", buf[top[0x8825][2]:top[0x8825][2] + 4])[0] + base
    g = _read_ifd(buf, base, gps_off, order, {1, 2, 3, 4})
    if 2 not in g or 4 not in g:
        return None
    try:
        lat = _rational(buf, g[2][2], order, 3)
        lon = _rational(buf, g[4][2], order, 3)
    except struct.error:
        return None
    latref = chr(buf[g[1][2]]) if 1 in g else "N"
    lonref = chr(buf[g[3][2]]) if 3 in g else "E"
    la = lat[0] + lat[1] / 60 + lat[2] / 3600
    lo = lon[0] + lon[1] / 60 + lon[2] / 3600
    if latref == "S":
        la = -la
    if lonref == "W":
        lo = -lo
    if la == 0 and lo == 0:
        return None
    return round(la, 6), round(lo, 6)


def _from_mdls(path):
    """HEIC 之類解不了的,借 macOS 內建的 Spotlight metadata。外接碟沒索引就會拿不到。"""
    try:
        r = subprocess.run(["mdls", "-name", "kMDItemLatitude", "-name", "kMDItemLongitude",
                            "-raw", path], capture_output=True, text=True, timeout=6).stdout
    except Exception:
        return None
    parts = [x for x in r.replace("\x00", "\n").split("\n") if x.strip()]
    try:
        la, lo = float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        return None
    if la == 0 and lo == 0:
        return None
    return round(la, 6), round(lo, 6)


def read(path):
    """回 (緯度, 經度) 或 None。讀不到就是 None,⛔ 不編造。"""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in JPEG_EXT:
            with open(path, "rb") as f:
                buf = f.read(256 * 1024)          # EXIF 一定在檔頭,不必整張讀
            i = 2
            while i + 4 < len(buf):
                if buf[i] != 0xFF:
                    break
                marker = buf[i + 1]
                seg = struct.unpack(">H", buf[i + 2:i + 4])[0]
                if marker == 0xE1 and buf[i + 4:i + 10] == b"Exif\x00\x00":
                    return _from_tiff(buf, i + 10)
                if marker in (0xDA, 0xD9):
                    break
                i += 2 + seg
            return None
        if ext in TIFF_EXT:
            with open(path, "rb") as f:
                buf = f.read(1024 * 1024)
            return _from_tiff(buf, 0)
        if ext in MDLS_EXT:
            return _from_mdls(path)
    except Exception:
        return None
    return None


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(read(p), p)
