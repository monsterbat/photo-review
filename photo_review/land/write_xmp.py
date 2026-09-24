#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
寫 Darktable 相容的 .xmp 旁檔
------------------------------
把審片頁評的星等 / 色標 / 標籤,寫進照片旁邊的 `<檔名>.xmp`,Darktable 匯入時就讀得到。

⛔ 舊版寫「已經有 .xmp 就整張跳過」,那是**假的保護**(見 DESIGN.md §7):
   Darktable 的設定是 `write_sidecar_files = on import`,照片一匯進去,它當場就在每張旁邊
   放一個 .xmp。所以「有 .xmp」不等於「有評分」——只要先把資料夾匯進 Darktable 看過一眼,
   舊版就一張都不會寫,而且不報錯,只印「跳過 N 張」。

⚠️ 實測 Darktable 自己寫出來的 .xmp(五個檔):
   連沒特別修過的照片,Darktable 也會自己塞進 `darktable:history`(colorin/colorout/gamma/flip)
   和 `darktable|exported`、`darktable|format|jpg` 這類自動標籤。
   → 想靠「有沒有 history、有沒有標籤」來判斷這是不是空白檔,**行不通**,會把每一張都判成
     「編輯過」→ 還是一張都不寫。

所以現在的做法是**併入**,不是覆蓋:
  · 沒有 .xmp                            → 寫一份新的
  · 已經有 .xmp                          → 只動星等/色標/標籤這三欄,檔案裡其他東西
                                           (修圖步驟、EXIF、遮罩、Darktable 自己的標籤)原封不動
  · 那三欄已經有人填過、而且跟這次不一樣    → ⛔ 整張不動,列出來讓你自己看

用法:
    python3 -m photo_review.land.write_xmp <final.json> [--apply]     # 預設只是預覽,加 --apply 才真的寫
"""
import os, re, sys, json, html
import xml.etree.ElementTree as ET

COLOR = {"red": 0, "yellow": 1, "green": 2, "blue": 3, "purple": 4}
COLOR_ZH = {0: "紅", 1: "黃", 2: "綠", 3: "藍", 4: "紫"}

NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_XMP = "http://ns.adobe.com/xap/1.0/"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_LR = "http://ns.adobe.com/lightroom/1.0/"
NS_DT = "http://darktable.sf.net/"

XMLNS = {
    "xmp": NS_XMP,
    "dc": NS_DC,
    "lr": NS_LR,
    "darktable": NS_DT,
}

DESC_OPEN_RE = re.compile(r"<rdf:Description\b[^>]*?/?>", re.S)


def esc(s):
    return html.escape(s, quote=False)


# ── 全新的 .xmp(照片旁邊本來什麼都沒有) ────────────────────────────────

def build_xmp(stars, color, tags):
    leaves = [t.split("|")[-1] for t in tags]
    subj = "".join(f"<rdf:li>{esc(x)}</rdf:li>" for x in leaves)
    hier = "".join(f"<rdf:li>{esc(t)}</rdf:li>" for t in tags)
    blocks = []
    if leaves:
        blocks.append(f"   <dc:subject><rdf:Seq>{subj}</rdf:Seq></dc:subject>")
        blocks.append(f"   <lr:hierarchicalSubject><rdf:Seq>{hier}</rdf:Seq></lr:hierarchicalSubject>")
    if color in COLOR:
        blocks.append(f"   <darktable:colorlabels><rdf:Seq><rdf:li>{COLOR[color]}</rdf:li></rdf:Seq></darktable:colorlabels>")
    body = "\n".join(blocks)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="review-tool">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:lr="http://ns.adobe.com/lightroom/1.0/"
    xmlns:darktable="http://darktable.sf.net/"
    xmp:Rating="{int(stars)}">
{body}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
'''


# ── 讀既有的 .xmp ────────────────────────────────────────────────────

def _li_texts(node):
    if node is None:
        return []
    out = []
    for li in node.iter(f"{{{NS_RDF}}}li"):
        t = (li.text or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def read_existing(text):
    """讀既有 .xmp 的三軸。看不懂就回 None —— 看不懂的一律不碰。"""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    desc = root.find(f".//{{{NS_RDF}}}Description")
    if desc is None:
        return None
    raw = desc.get(f"{{{NS_XMP}}}Rating")
    if raw is None:
        el = desc.find(f"{{{NS_XMP}}}Rating")
        raw = (el.text or "").strip() if el is not None else None
    try:
        rating = int(float(raw)) if raw not in (None, "") else 0
    except ValueError:
        rating = 0
    colors = []
    for c in _li_texts(desc.find(f"{{{NS_DT}}}colorlabels")):
        try:
            colors.append(int(c))
        except ValueError:
            pass
    return {
        "rating": rating,
        "colors": sorted(colors),
        "tags": _li_texts(desc.find(f"{{{NS_LR}}}hierarchicalSubject")),
    }


# ── 把三欄併進既有的 .xmp(其他東西一個字都不動) ──────────────────────

def _normalize_desc(text):
    """`<rdf:Description … />` 這種自我關閉的寫法,展開成有頭有尾的,才塞得進東西。"""
    m = DESC_OPEN_RE.search(text)
    if not m:
        return None
    tag = m.group(0)
    if not tag.endswith("/>"):
        return text
    opened = tag[:-2].rstrip() + ">\n  </rdf:Description>"
    return text[: m.start()] + opened + text[m.end():]


def _ensure_xmlns(text):
    """要用到的命名空間沒宣告的話,補進 rdf:Description 的開頭標籤。"""
    missing = [f'xmlns:{p}="{u}"' for p, u in XMLNS.items() if f"xmlns:{p}=" not in text]
    if not missing:
        return text
    m = DESC_OPEN_RE.search(text)
    tag = m.group(0)
    new_tag = tag[:-1].rstrip() + "\n   " + "\n   ".join(missing) + ">"
    return text[: m.start()] + new_tag + text[m.end():]


def _set_rating(text, stars):
    m = DESC_OPEN_RE.search(text)
    tag = m.group(0)
    if re.search(r'\bxmp:Rating\s*=\s*"[^"]*"', tag):
        new_tag = re.sub(r'(\bxmp:Rating\s*=\s*")[^"]*(")',
                         lambda mm: mm.group(1) + str(int(stars)) + mm.group(2), tag)
        return text[: m.start()] + new_tag + text[m.end():]
    if re.search(r"<xmp:Rating>.*?</xmp:Rating>", text, re.S):
        return re.sub(r"(<xmp:Rating>).*?(</xmp:Rating>)",
                      lambda mm: mm.group(1) + str(int(stars)) + mm.group(2),
                      text, count=1, flags=re.S)
    new_tag = tag[:-1].rstrip() + f'\n   xmp:Rating="{int(stars)}">'
    return text[: m.start()] + new_tag + text[m.end():]


def _put_block(text, tagname, block):
    """換掉(或新增)某一整塊。block=None 代表把它拿掉。"""
    pat = re.compile(rf"[ \t]*<{re.escape(tagname)}(?:\s[^>]*)?>.*?</{re.escape(tagname)}>\n?", re.S)
    self_close = re.compile(rf"[ \t]*<{re.escape(tagname)}(?:\s[^>]*)?/>\n?", re.S)
    rep = (block + "\n") if block else ""
    if pat.search(text):
        return pat.sub(lambda _: rep, text, count=1)
    if self_close.search(text):
        return self_close.sub(lambda _: rep, text, count=1)
    if not block:
        return text
    i = text.find("</rdf:Description>")
    if i < 0:
        return None
    head = text[:i].rstrip(" \t")          # 收掉關閉標籤本來的縮排,免得新區塊被推歪
    return head + block + "\n  " + text[i:]


def _bag(tagname, items):
    lis = "\n".join(f"     <rdf:li>{esc(x)}</rdf:li>" for x in items)
    # 用 rdf:Bag 而不是 rdf:Seq —— 跟 Darktable 自己寫出來的格式一模一樣,
    # 免得它重讀時對容器型別有意見(對照過 Darktable 現有的 .xmp)。
    return f"   <{tagname}>\n    <rdf:Bag>\n{lis}\n    </rdf:Bag>\n   </{tagname}>"


def merge_into(text, stars, color, tags, old):
    """回傳併好的新內容;不動就回 None。"""
    out = _normalize_desc(text)
    if out is None:
        return None
    out = _ensure_xmlns(out)

    # ⛔ 只在「原本沒有人評過」時才寫星等。原本已經有分數而且跟這次不一樣 → 不動它。
    #    ⚠️ 但那不能連累標籤(理由見下面 main 的註解)。
    if int(stars or 0) > 0 and old["rating"] == 0:
        out = _set_rating(out, stars)

    if color in COLOR and not old["colors"]:
        out = _put_block(out, "darktable:colorlabels",
                         f"   <darktable:colorlabels>\n    <rdf:Seq>\n     <rdf:li>{COLOR[color]}</rdf:li>\n    </rdf:Seq>\n   </darktable:colorlabels>")
        if out is None:
            return None

    merged = list(old["tags"])
    for t in tags:
        if t not in merged:
            merged.append(t)
    if merged != old["tags"]:
        leaves = []
        for t in merged:
            leaf = t.split("|")[-1]
            if leaf not in leaves:
                leaves.append(leaf)
        out = _put_block(out, "dc:subject", _bag("dc:subject", leaves))
        if out is None:
            return None
        out = _put_block(out, "lr:hierarchicalSubject", _bag("lr:hierarchicalSubject", merged))
        if out is None:
            return None

    if out == text:
        return None
    try:
        ET.fromstring(out)          # 改壞了就不要寫出去
    except ET.ParseError:
        return None
    return out


def conflicts_of(stars, color, old):
    """既有的三欄跟這次評的對不起來的地方,講白話。"""
    bad = []
    if int(stars or 0) > 0 and old["rating"] > 0 and old["rating"] != int(stars):
        bad.append(f"星等 已經是 {old['rating']}★,這次評 {int(stars)}★")
    if color in COLOR and old["colors"] and old["colors"] != [COLOR[color]]:
        was = "、".join(COLOR_ZH.get(c, str(c)) for c in old["colors"])
        bad.append(f"色標 已經是 {was},這次評 {COLOR_ZH[COLOR[color]]}")
    return bad


def write_atomic(path, content):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def main():
    if len(sys.argv) < 2:
        print("用法:python3 -m photo_review.land.write_xmp <final.json> [--apply]")
        sys.exit(1)
    jf = sys.argv[1]
    apply = "--apply" in sys.argv
    d = json.load(open(jf, encoding="utf-8"))
    targets = [p for p in d["photos"]
               if not p.get("delete") and (p.get("stars") or p.get("tags") or p.get("color"))]

    created = merged = same = 0
    clash, broken = [], []

    for p in targets:
        xmp = p["path"] + ".xmp"
        stars = p.get("stars", 0)
        color = p.get("color", "")
        tags = p.get("tags", []) if isinstance(p.get("tags"), list) else []
        base = os.path.basename(p["path"])

        if not os.path.exists(xmp):
            created += 1
            if apply:
                write_atomic(xmp, build_xmp(stars, color, tags))
            continue

        try:
            text = open(xmp, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            broken.append((base, "檔案讀不開"))
            continue

        old = read_existing(text)
        if old is None:
            broken.append((base, "這個 .xmp 的格式我看不懂"))
            continue

        # ⛔ 有衝突不代表整張跳過。
        #    流程上**每一張都要有標籤**,那是不可跳過的一步:評分、標籤,然後才輸出。
        #    而三軸本來就各管各的:星等管好壞、色標管要注意、標籤管這是什麼。
        #    所以「星等對不上」⛔ 不該連累標籤。衝突的那一欄不動,其他照寫。
        bad = conflicts_of(stars, color, old)
        if bad:
            clash.append((base, ";".join(bad)))

        new = merge_into(text, stars, color, tags, old)
        if new is None:
            same += 1
            continue
        merged += 1
        if apply:
            write_atomic(xmp, new)

    verb = "已" if apply else "將"
    print(f"對象:{len(targets)} 張")
    print(f"{verb}新建 .xmp:{created} 張")
    print(f"{verb}併進既有 .xmp(只動星等/色標/標籤):{merged} 張")
    if same:
        print(f"本來就一樣,不用動:{same} 張")
    if clash:
        print(f"\n⚠️ 這 {len(clash)} 張的標籤照樣寫進去了,但下面這幾欄我沒有蓋掉 ——")
        print("   你在 Darktable 裡評的跟這次評的不一樣,我不敢替你決定:")
        for b, why in clash[:20]:
            print(f"   ⚠️ {b} — {why}")
        if len(clash) > 20:
            print(f"   …還有 {len(clash) - 20} 張")
        print("   要用這次的為準,就去 Darktable 把那幾張改回來,再跑一次。")
    if broken:
        print(f"\n⛔ 這 {len(broken)} 張的 .xmp 我看不懂,一個字都沒動:")
        for b, why in broken[:20]:
            print(f"   ❓ {b} — {why}")
    if not apply:
        print("\n(這只是預覽,加 --apply 才真的寫檔)")


if __name__ == "__main__":
    main()
