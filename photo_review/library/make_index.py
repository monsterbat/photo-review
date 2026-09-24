#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生 output/index.html —— 照片審查台的首頁(一頁看完所有審片頁 + 進度)。

⚠️ 這支要在**照片正本看得到的那台電腦**上跑(見 DESIGN.md §2 的沙盒邊界)。
產出的 index.html 必須用 file:// 打開,⛔ 不可以掛在任何 http 伺服器上 ——
審片頁裡的照片是 file:// 開頭,從 http 頁面一律被瀏覽器擋掉 → 整頁破圖。

資料來源:
  · output/*.html            已經產生過的審片頁(分頁 _p2/_p3 會併回同一夾)
  · notes/照片庫總表.csv     全庫資料夾主索引(檔案數 = 分母)
  · notes/照片日記總表.csv   每張留用照一列
  · notes/照片Review_刪除log.csv  每張刪除照一列
  · 照片正本的資料夾(config.py 的 camera_root)   還沒產生審片頁的(找不到就跳過這段)
"""
import os, re, csv, html, collections, datetime

from photo_review import config

OUT = config.OUTPUT_DIR
NOTES = config.NOTES_DIR
MASTER = config.MASTER_CSV
DIARY = config.DIARY_CSV
DELLOG = config.DELLOG_CSV
CAMERA = config.CAMERA_ROOT
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif",
           ".cr2", ".cr3", ".arw", ".nef", ".dng", ".tif", ".tiff", ".raf", ".orf"}


def count_images(folder):
    """主索引沒收錄的資料夾(例如新拍的),直接數一次。只對「已經有審片頁」的夾做,不會掃全庫。"""
    n = 0
    try:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".previews"]
            for f in files:
                if not f.startswith("._") and os.path.splitext(f)[1].lower() in IMG_EXT:
                    n += 1
    except OSError:
        pass
    return n

PAGE_SUFFIX = re.compile(r"_p(\d+)$")
TEMPLATE = os.path.join(config.TEMPLATES_DIR, "template.html")
# 審片頁是「產生當下」把版面烤進去的 → 版面改過之後,舊頁不會自己長出新功能。
# 比 mtime 就知道哪些頁比版面舊 —— 否則加了新功能,舊頁面打開還是沒有。
TPL_MTIME = os.path.getmtime(TEMPLATE) if os.path.exists(TEMPLATE) else 0


def counter(path, col):
    if not os.path.exists(path):
        return collections.Counter()
    with open(path, encoding="utf-8-sig") as f:
        return collections.Counter(r[col] for r in csv.DictReader(f) if r.get(col))


def load_master():
    m = {}
    if not os.path.exists(MASTER):
        return m
    with open(MASTER, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                m[r["資料夾名"]] = int(r.get("檔案數", "0") or 0)
            except ValueError:
                m[r["資料夾名"]] = 0
    return m


def collect_pages():
    """output/*.html → {夾名: [檔名, …](第 1 頁在前)}"""
    groups = collections.defaultdict(list)
    if not os.path.isdir(OUT):
        return groups
    for fn in sorted(os.listdir(OUT)):
        if not fn.endswith(".html") or fn == "index.html":
            continue
        if fn.startswith("confirm_") or fn.startswith("multi_"):
            continue
        stem = fn[:-5]
        m = PAGE_SUFFIX.search(stem)
        base, n = (stem[:m.start()], int(m.group(1))) if m else (stem, 1)
        groups[base].append((n, fn))
    return {b: [fn for _, fn in sorted(v)] for b, v in groups.items()}


def pending_folders():
    """temp/ 裡躺著、還沒落地的匯出檔是哪幾夾。

    常見的困惑:明明評完也按了匯出,首頁卻寫「⬜ 還沒匯出過」
    ——「已落地」那兩個數字只有跑完落地(apply.py --apply)才會動,而他還沒按 2。
    話沒講錯,但**看的人只會覺得自己的東西不見了**。所以這一支把中間那個狀態撈出來。
    `已處理/` 底下的是落地完搬過去的,⛔ 不算。
    """
    import glob, json
    tmp = config.TEMP_DIR
    out = set()
    for f in glob.glob(os.path.join(tmp, "*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                root = (json.load(fh) or {}).get("root") or ""
        except Exception:
            continue
        if root:
            out.add(os.path.basename(root.rstrip("/")))
    return out


PENDING = set()


def row_html(name, pages, total, kept, deld):
    stale = bool(pages) and os.path.getmtime(os.path.join(OUT, pages[0])) < TPL_MTIME
    done = kept + deld
    pct = int(done * 100 / total) if total else 0
    # ⚠️ 這裡的「留用/刪除」是**已經匯出並落地**的數字(來自 notes 的 CSV)。
    #    瀏覽器裡剛評的進度存在 localStorage,這一頁讀不到 —— ⛔ 不要說成「還沒開始」。
    if total and done >= total:
        state, badge = "done", "✅ 已落地完成"
    elif done:
        state, badge = "half", "🟡 落地到一半"
    elif name in PENDING:
        state, badge = "half", "📤 <b>已匯出,等落地</b> — 回文字視窗按 <b>2</b>"
    else:
        state, badge = "new", "⬜ 還沒匯出過"
    label = ("再看一次 ▶" if name in PENDING else
             {"half": "接著評 ▶", "done": "再看一次 ▶"}.get(state, "開始評 ▶"))
    if stale:
        badge += " · <b class=\"stale\">⚠️ 舊版面,沒有標籤按鈕</b>"
    links = ""
    if pages:
        links = ('<a class="go" href="./%s">%s</a>' % (html.escape(pages[0]), label))
        if len(pages) > 1:
            extra = " ".join('<a class="pg" href="./%s">%d</a>' % (html.escape(p), i + 2)
                             for i, p in enumerate(pages[1:]))
            links += '<span class="pgs">分頁 %s</span>' % extra
    else:
        links = '<span class="none">還沒產生審片頁</span>'
    landed = "" if (state == "half" and not done) else f" · 已落地:留用 {kept} · 刪除 {deld}"
    return f"""<div class="row {state}" data-name="{html.escape(name.lower())}">
  <div class="nm">{html.escape(name)}<small>{badge}{landed}</small></div>
  <div class="bar"><i style="width:{pct}%"></i></div>
  <div class="cnt">{done} / {total or '?'} 張</div>
  <div class="act">{links}</div>
</div>"""


def main():
    global PENDING
    PENDING = pending_folders()
    pages = collect_pages()
    master = load_master()
    kept = counter(DIARY, "資料夾")
    deld = counter(DELLOG, "資料夾")

    on_disk = []
    if os.path.isdir(CAMERA):
        on_disk = sorted(d for d in os.listdir(CAMERA)
                         if os.path.isdir(os.path.join(CAMERA, d)) and not d.startswith("."))

    names = set(pages) | set(on_disk)
    half, done, todo_made, todo_new, pend = [], [], [], [], []
    for n in sorted(names):
        p = pages.get(n, [])
        t = master.get(n, 0)
        if not t and p and on_disk:            # 有審片頁但主索引沒收錄 → 現場數一次
            t = count_images(os.path.join(CAMERA, n))
        k, d = kept.get(n, 0), deld.get(n, 0)
        h = row_html(n, p, t, k, d)
        if t and (k + d) >= t:
            done.append(h)
        elif k + d:
            half.append(h)
        elif n in PENDING:
            pend.append(h)
        elif p:
            todo_made.append(h)
        else:
            todo_new.append(h)

    def sect(title, note, rows):
        if not rows:
            return ""
        return (f'<h2>{title} <span class="n">{len(rows)}</span></h2>'
                f'<p class="note">{note}</p>' + "\n".join(rows))

    stale_names = [n for n in sorted(names)
                   if pages.get(n) and os.path.getmtime(os.path.join(OUT, pages[n][0])) < TPL_MTIME]
    # 平常這裡會是空的:每次打開審查台,refresh.py 已經自動把舊版面換掉了。
    # 會留下來的只有「原始資料夾現在找不到」那種(硬碟沒插、資料夾搬走) → 誠實講,不假裝已更新。
    stale_warn = ("" if not stale_names else
        '<div class="warn">⚠️ 有 <b>%d</b> 個資料夾還是舊版面（沒有標籤按鈕）。'
        '原因是它們的原始照片資料夾現在找不到 —— 通常就是隨身硬碟沒插。'
        '插上去之後重開一次「照片審查台」，會自動換成新版面，'
        '<b>你打過的星等和心得不會不見</b>。</div>' % len(stale_names))

    ssd_warn = "" if on_disk else (
        '<div class="warn">⚠️ 找不到照片正本的資料夾（<code>%s</code>）。'
        '下面只列得出已經產生過審片頁的資料夾，而且點進去照片會是破的。'
        '把硬碟插上、或改 <code>config.local.json</code> 之後重跑一次「照片審查台」。</div>'
        % html.escape(CAMERA))

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    body = f"""<div class="wrap">
<h1>照片審查台</h1>
<p class="lead">這一頁是 <b>{stamp}</b> 產生的，就在你這台電腦上。點任何一列就進去評。</p>
{ssd_warn}
<div class="toolbar">
  <input id="q" placeholder="🔍 打幾個字找資料夾，例如「東京」「2024」">
  <div class="stat">全部 <b>{len(names)}</b> 夾</div>
  <div class="stat">已留 <b>{sum(kept.values())}</b> 張</div>
  <div class="stat">已刪 <b>{sum(deld.values())}</b> 張</div>
</div>
{stale_warn}
{sect('📤 已匯出，等落地', '評完也匯出了，只差最後一步：回「照片審查台」的文字視窗按 <b>2</b>。', pend)}
{sect('🟡 評到一半', '先把這些做完，接著評不會從頭開始。', half)}
{sect('⬜ 已經有審片頁', '點下去就能評（或接著評）。', todo_made)}
{sect('⬜ 還沒產生審片頁', '要評這些，回去雙擊「照片審查台」，'
         '在跳出來的<b>黑色文字視窗按 1</b> → 選資料夾。產生完就會出現在上面。', todo_new)}
{sect('✅ 已完成', '評完了。點進去還是可以改。', done)}
<div class="warn" style="background:#eef1f5;border-color:#dfe2e7;color:#555b64">
ℹ️ <b>這一頁看不到你剛剛評的東西，那不代表沒評。</b><br>
星等和標籤存在瀏覽器裡，只有走完最後一步才會出現在這裡。三個階段是：<br>
① 在審片頁上評 → ② 按右上角<b>匯出</b> → ③ 雙擊「照片審查台」<b>按 2 落地</b>。<br>
「已落地」那兩個數字，要做完 ③ 才會動。停在 ② 的資料夾會標成<b>「📤 已匯出，等落地」</b>。
</div>
<p class="foot">看不到照片？代表你是從網址（http://…）開這一頁的。這一頁只能用檔案的方式在你自己電腦上打開。</p>
</div>"""

    css = """
:root{color-scheme:light;--bg:#f4f5f7;--card:#fff;--ink:#191b1e;--dim:#555b64;
 --line:#dfe2e7;--blue:#1f4f9c;--green:#146c2e;--amber:#8a5300}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:"Helvetica Neue","PingFang TC","Noto Sans TC",sans-serif;font-size:15px;line-height:1.7}
.wrap{max-width:1020px;margin:0 auto;padding:26px 20px 90px}
h1{font-size:25px;margin:0 0 6px}
.lead{color:var(--dim);font-size:14px;margin:0 0 20px}
h2{font-size:17px;margin:34px 0 6px;padding-bottom:7px;border-bottom:2px solid var(--line)}
h2 .n{font-size:13px;color:var(--dim);font-weight:400}
.note{color:var(--dim);font-size:13px;margin:0 0 12px}
.warn{background:#fff5e2;border:1px solid #ecd6a5;color:var(--amber);
 border-radius:10px;padding:13px 16px;margin-bottom:18px;font-size:14px}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px}
#q{flex:1;min-width:220px;padding:11px 14px;border:1px solid var(--line);
 border-radius:9px;font-size:15px;font-family:inherit;background:var(--card)}
.stat{background:var(--card);border:1px solid var(--line);border-radius:9px;
 padding:11px 14px;font-size:13px;color:var(--dim);white-space:nowrap}
.stat b{color:var(--ink);font-size:16px}
.row{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:13px 16px;margin-bottom:8px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.row .nm{font-weight:600;min-width:210px;flex:1}
.row .nm small{display:block;font-weight:400;color:var(--dim);font-size:12px}
.bar{width:140px;height:8px;background:#e8eaee;border-radius:99px;overflow:hidden;flex:none}
.bar i{display:block;height:100%;background:var(--blue)}
.row.done .bar i{background:var(--green)}
.cnt{font-size:13px;color:var(--dim);width:105px;flex:none}
.act{flex:none;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
a.go{background:var(--blue);color:#fff;text-decoration:none;border-radius:8px;
 padding:9px 15px;font-size:14px;white-space:nowrap}
.row.done a.go{background:var(--green)}
.pgs{font-size:12px;color:var(--dim)}
a.pg{color:var(--blue);text-decoration:none;padding:0 3px}
.none{font-size:13px;color:var(--dim)}
.stale{color:#8a5300}
.foot{margin-top:34px;color:var(--dim);font-size:13px}
.hide{display:none}
code{background:#eceff3;border-radius:4px;padding:1px 5px;font-size:13px;
 font-family:ui-monospace,Menlo,monospace}
"""
    js = """
var q=document.getElementById('q');
q.addEventListener('input',function(){
  var v=q.value.trim().toLowerCase();
  document.querySelectorAll('.row').forEach(function(r){
    r.classList.toggle('hide', v && r.dataset.name.indexOf(v)<0);
  });
});
"""
    doc = ("<!DOCTYPE html>\n<html lang=\"zh-Hant\">\n<head>\n<meta charset=\"utf-8\">\n"
           "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
           "<title>照片審查台</title>\n<style>" + css + "</style>\n</head>\n<body>\n"
           + body + "\n<script>" + js + "</script>\n</body>\n</html>\n")

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "index.html")

    # ⛔ 在看不到照片正本的機器上寫檔 = 把另一台那份完整的蓋成縮水版。
    # 真的發生過:在看不到照片的機器上跑了一次,760 夾的首頁瞬間變成 10 夾 ——
    # 沒有任何錯誤訊息,看起來就像資料不見了。
    # index.html 本來就綁著本機的照片路徑,在看不到照片的機器上產的一定是壞的。
    if not on_disk and os.path.exists(path):
        import socket
        print("⛔ 沒偵測到隨身硬碟,而首頁已經存在 → 不覆蓋。")
        print(f"   (這台是 {socket.gethostname().split('.')[0]};要在照片正本看得到的那台跑才會完整)")
        return path

    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"✓ 首頁已更新:{path}")
    print(f"  {len(names)} 夾 · 評到一半 {len(half)} · 有頁沒評 {len(todo_made)} · "
          f"沒產生 {len(todo_new)} · 完成 {len(done)}")
    return path


if __name__ == "__main__":
    main()
