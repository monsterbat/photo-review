# Example controlled vocabulary ／ 範例用語表

This file feeds the tag buttons on the review page. Copy it, edit it, and point
`config.local.json` → `vocab_file` at your copy.

這份檔案決定審片頁上會出現哪些標籤按鈕。複製一份、改成自己的,
再把 `config.local.json` 的 `vocab_file` 指過去就好。

## Why a fixed list ／ 為什麼要有固定清單

Free typing splits one idea into many tags: `Tokyo` / `tokyo` / `東京` end up as
three different things, and a search for one misses the other two.
A short list you pick from keeps the library searchable.

自由打字會讓同一件事裂成好幾個標籤(`Tokyo` / `tokyo` / `東京`),
查其中一個就漏掉另外兩個。從固定清單裡點選,整個照片庫才搜得動。

## 7. 固定用語表 ／ The vocabulary

Four axes. Each photo can take any number of tags from any axis.
四個軸,一張照片可以在任何一個軸上掛任意多個標籤。

| 軸 Axis | 問題 It answers | 例 |
|---|---|---|
| **作品** Series | 這張屬於哪個活動或作品? | 演唱會、球賽 |
| **用途** Purpose | 為什麼留這張? | 旅遊、登山 |
| **地點** Place | 在哪裡拍的? | 東京、京都 |
| **主題** Subject | 畫面裡有什麼? | 夜景、貓 |

**作品:** 演唱會、球賽、展覽、電影、舞台劇、市集

**用途:** 旅遊、登山、美食、風景精選、生活、紀念、周邊

**地點:** 東京、新宿、京都、大阪、台北、高雄、富士山

**主題:** 人物、風景、夜景、花、櫻花、貓、建築、街景、車站、神社、拉麵、咖啡

## How it grows ／ 這張表怎麼長大

Start with the list above. When you photograph something new, type the new term
on the review page, then run:

先用上面這批。拍到新東西就在審片頁上打新的詞,然後跑:

```bash
python3 lint.py <your-export.json> --add-new-terms
```

It writes the new terms back into this file, so the next session offers them as
buttons. `落地.command` runs it for you.

它會把新的詞寫回這個檔,下一次就會變成按鈕。`落地.command` 會自動幫你跑。

**To remove or rename a term, edit this file directly.** Renaming a term that is
already on photos also needs `rename_tag.py`, which rewrites the CSV and the
Darktable sidecars so nothing is left pointing at the old name.

**要刪掉或改名,直接編輯這個檔。** 如果那個詞已經標在照片上,改名還要再跑
`rename_tag.py`,它會把 CSV 與 Darktable 的 `.xmp` 一起改掉,不會留下舊名字。
