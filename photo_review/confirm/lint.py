#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
落地前的一致性檢查 —— 工作流的倒數第二步,原本丟給 AI 做的那一步
------------------------------------------------------------------
為什麼要有這支:實測一批 406 張的照片,AI 在這一步只改了 6 張(1.5%),
而且那 6 張全是機械比對就抓得到的東西。**不需要 AI,也不必等 AI 在線。**

檢查的東西(⛔ 只提醒,不擋落地 —— 要不要改由人決定):
  ① 標了刪除,卻也有星等/標籤/心得           → 刪除優先,落地會丟垃圾桶
  ② 沒標刪除,卻是 0 顆星                      → 落地後會被當成「沒評過」
  ③ 3 顆星以上,卻沒有作品/用途/地點/主題標籤   → 以後用標籤撈不到它
  ④ 1–2 顆星,卻標了「用途|風景精選」          → 精選跟星等對不起來
  ⑤ 標籤不在固定用語表裡(用語表第 7 節)         → 可能是打錯字,或是新詞還沒收進表
  ⑥ 同時有好幾份等著落地,批次名卻不一樣       → 如果是同一趟,在 Darktable 會分成好幾堆

⑤ 的根本原因:審片頁上按「加進來」的新詞會放進匯出檔的 new_terms,
   但以前沒有程式把它寫回用語表,要靠 AI 記得 → 於是用了幾百次的詞仍然不在表上。
   現在加 --add-new-terms 就自動寫回去。

用法:
    python3 -m photo_review.confirm.lint <匯出檔.json> [...]                  # 只檢查,不改任何檔案
    python3 -m photo_review.confirm.lint <匯出檔.json> [...] --add-new-terms  # 另外把頁面上新加的用語寫回用語表第 7 節
"""
import os, re, sys, json
from photo_review import vocab

CONTENT_NS = tuple(c + "|" for c in vocab.CATS)          # 作品| 用途| 地點| 主題|
SKIP_NS = ("批次|", "darktable|")                        # 工作用的、Darktable 自己加的,不算用語
MIGRATE = {"地點|澀谷": "地點|渋谷"}                      # 跟 template.html 的 MIGRATE 同一份意思
SHOW = 8                                                 # 每一項最多列幾個檔名


def stars_of(p):
    try:
        return int(p.get("stars") or 0)
    except (TypeError, ValueError):
        return 0


def tags_of(p):
    t = p.get("tags")
    return [x for x in t if isinstance(x, str) and x.strip()] if isinstance(t, list) else []


def load_export(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"❌ 讀不開 {os.path.basename(path)}:{e}")
        return None
    if not isinstance(d.get("photos"), list):
        print(f"❌ {os.path.basename(path)} 裡面沒有照片清單,這不是審片頁的匯出檔")
        return None
    return d


def sop_section():
    try:
        s = open(vocab.VOCAB_FILE, encoding="utf-8").read()
    except OSError:
        return ""
    # ⛔ 不要用 s.split("## 7. 固定用語表"):第七節裡面的範例指令也含這串字,
    #    split 會在那裡被切斷,只拿到前面一小段 → 幾乎每個詞都會被誤判成不在表上。
    m = re.search(r"^## 7\. 固定用語表.*?(?=^## \d+\.|\Z)", s, re.S | re.M)
    return m.group(0) if m else s


def in_vocab(tag, voc, sec):
    ns, _, leaf = tag.partition("|")
    if not leaf:
        return False
    if ns in voc:
        return leaf in voc[ns]
    return leaf in sec          # 發佈| 這類 vocab.py 沒有讀的,退回整段文字比對


def lint_one(path, d, voc, sec):
    """回傳這一份的問題清單 [(代號, 說明, [檔名...])],並印出來。"""
    photos = d["photos"]
    name = lambda p: p.get("name") or os.path.basename(p.get("path", "?"))
    new_terms = d.get("new_terms") if isinstance(d.get("new_terms"), dict) else {}
    intended = {f"{c}|{t}" for c, ts in new_terms.items() if isinstance(ts, list) for t in ts}

    found = []
    both = [p for p in photos if p.get("delete") and (stars_of(p) or p.get("note", "").strip()
            or any(not t.startswith(SKIP_NS) for t in tags_of(p)))]
    if both:
        found.append(("①", "標了刪除,但也有星等/標籤/心得。落地時刪除優先,會丟進垃圾桶", [name(p) for p in both]))

    zero = [p for p in photos if not p.get("delete") and stars_of(p) == 0]
    if zero:
        found.append(("②", "沒標刪除,但是 0 顆星。落地後會被當成沒評過", [name(p) for p in zero]))

    notag = [p for p in photos if not p.get("delete") and stars_of(p) >= 3
             and not any(t.startswith(CONTENT_NS) for t in tags_of(p))]
    if notag:
        found.append(("③", "3 顆星以上,但沒有作品/用途/地點/主題標籤,以後用標籤撈不到", [name(p) for p in notag]))

    lowpick = [p for p in photos if not p.get("delete") and 1 <= stars_of(p) <= 2
               and "用途|風景精選" in tags_of(p)]
    if lowpick:
        found.append(("④", "只有 1–2 顆星,卻標了「用途|風景精選」", [name(p) for p in lowpick]))

    unknown = {}
    for p in photos:
        for t in tags_of(p):
            if t.startswith(SKIP_NS) or in_vocab(t, voc, sec):
                continue
            unknown.setdefault(t, []).append(name(p))
    for t, names in sorted(unknown.items()):
        if t in MIGRATE:
            why = f"「{t}」是舊寫法,應該用「{MIGRATE[t]}」"
        elif t in intended:
            why = f"「{t}」是你在頁面上新加的詞,還沒收進固定用語表(落地時會自動收進去)"
        else:
            why = f"「{t}」不在固定用語表裡,是不是打錯字?"
        found.append(("⑤", why, names))

    kept = sum(1 for p in photos if not p.get("delete"))
    dels = len(photos) - kept
    batch = d.get("batch") or "(整夾匯出,沒有批次)"
    print(f"🔎 {os.path.basename(path)}:{len(photos)} 張(留用 {kept}、標刪 {dels}),批次 {batch}")
    if not found:
        print("   ✅ 沒有要注意的")
    for code, why, names in found:
        more = f" …還有 {len(names) - SHOW} 張" if len(names) > SHOW else ""
        print(f"   ⚠️ {code} {why}:{len(names)} 張")
        print(f"      {'、'.join(names[:SHOW])}{more}")
    return found


def add_new_terms(exports):
    """把各份匯出檔的 new_terms 寫回用語表第 7 節對應那一行。回傳實際加了哪些。"""
    voc = vocab.load()
    want = {c: [] for c in vocab.CATS}
    for d in exports:
        nt = d.get("new_terms") if isinstance(d.get("new_terms"), dict) else {}
        for c in vocab.CATS:
            for t in nt.get(c) or []:
                t = str(t).strip()
                if not t or re.search(r"[\s|、,，]", t):
                    print(f"   ⏭ 跳過「{t}」:裡面有空白或分隔符號,不能當一個詞")
                    continue
                if t not in voc[c] and t not in want[c]:
                    want[c].append(t)
    if not any(want.values()):
        return {}
    text = open(vocab.VOCAB_FILE, encoding="utf-8").read()
    added = {}
    for c, terms in want.items():
        if not terms:
            continue
        m = re.search(rf"^(\*\*{c}[:：]\*\*\s*)(.+?)(\s*…[^\n]*)?$", text, re.M)
        if not m:
            print(f"   ❌ VOCAB_FILE 第七節找不到「{c}」那一行,{'、'.join(terms)} 沒有寫回去")
            continue
        body = m.group(2).rstrip()
        new_line = m.group(1) + body + "、" + "、".join(terms) + (m.group(3) or "")
        text = text[:m.start()] + new_line + text[m.end():]
        added[c] = terms
    tmp = vocab.VOCAB_FILE + ".tmp"
    open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, vocab.VOCAB_FILE)
    # 寫完馬上用審片頁同一支讀回來,確認每個詞都讀得到(讀不到 = 審片頁的按鈕會少)
    back = vocab.load()
    for c, terms in added.items():
        lost = [t for t in terms if t not in back[c]]
        if lost:
            print(f"   ❌ 寫進去了但讀不回來:{c} {'、'.join(lost)} —— 請檢查 VOCAB_FILE 第七節那一行")
    return added


def main():
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not files:
        print(__doc__)
        sys.exit(1)
    voc, sec = vocab.load(), sop_section()
    exports, batches, bad = [], {}, 0
    for f in files:
        d = load_export(f)
        if d is None:
            bad += 1
            continue
        exports.append(d)
        lint_one(f, d, voc, sec)
        if d.get("batch"):
            batches.setdefault(d["batch"], []).append(os.path.basename(f))

    if len(batches) > 1:
        print("   ⚠️ ⑥ 這幾份的批次名不一樣。如果是同一趟,在 Darktable 會分成好幾堆:")
        for b, fs in batches.items():
            print(f"      {b}:{'、'.join(fs)}")

    if "--add-new-terms" in sys.argv:
        added = add_new_terms(exports)
        for c, terms in added.items():
            print(f"   ✅ 固定用語表「{c}」收進:{'、'.join(terms)}")

    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
