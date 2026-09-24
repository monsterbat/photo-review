#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""照片審查台的自我測試 —— 不需要隨身硬碟,也不碰任何真的照片。

它自己造一批合成照片與一份假的紀錄檔,跑完整條流程,最後把造的東西刪乾淨。

為什麼要有:這個工具會刪照片、會改總表。以前沒有測試,每次改完只能靠「看起來還好」。
現在改完跑一次,壞掉的地方當場現形。

用法:
    python3 tests/test_photo_review.py          # 全部
    python3 tests/test_photo_review.py -v       # 連每一項的名字都印出來
"""
import csv
import re
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def make_jpeg(path, size=(64, 48)):
    """用 macOS 內建的 sips 造一張真的 JPG,不必裝任何套件。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    src = "/System/Library/CoreServices/DefaultDesktop.heic"
    if os.path.exists(src):
        r = subprocess.run(["sips", "-s", "format", "jpeg", "-Z", str(max(size)),
                            src, "--out", path],
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(path):
            return path
    # 退路:寫一張最小的合法 JPG(1x1,灰底)
    with open(path, "wb") as f:
        f.write(bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000ffdb004300"
            + "08" * 64
            + "ffc2000b080001000101011100ffc40014000100000000000000000000000000000009"
            + "ffda0008010100000001d2cf20ffd9"))
    return path


class Sandbox(unittest.TestCase):
    """每個測試自己一個臨時資料夾,設定用環境變數指過去。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="photo_review_test_")
        self.camera = os.path.join(self.tmp, "Camera")
        self.notes = os.path.join(self.tmp, "notes")
        os.makedirs(self.camera, exist_ok=True)
        os.makedirs(self.notes, exist_ok=True)
        self.env = dict(os.environ)
        self.env.update({
            "PHOTO_REVIEW_CAMERA_ROOT": self.camera,
            "PHOTO_REVIEW_NOTES_DIR": self.notes,
            "PHOTO_REVIEW_VOCAB_FILE": os.path.join(ROOT, "vocab.example.md"),
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, *args):
        r = subprocess.run([sys.executable, *args], cwd=ROOT, env=self.env,
                           capture_output=True, text=True)
        return r


class TestConfig(Sandbox):
    def test_環境變數蓋得過設定檔(self):
        r = self.run_tool("-m", "photo_review.config")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(self.camera, r.stdout)
        self.assertIn("環境變數", r.stdout)

    def test_沒有任何設定也不會爆掉(self):
        env = {k: v for k, v in self.env.items() if not k.startswith("PHOTO_REVIEW_")}
        env.pop("SC_CAMERA_ROOT", None)
        env.pop("SC_SSD_ROOT", None)
        r = subprocess.run([sys.executable, "-m", "photo_review.config"], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_個人設定不會被當成範例帶出去(self):
        """config.local.json 是私人的:⛔ 不准在公開版的白名單裡,而且要明確排除。"""
        pub = os.path.join(ROOT, "public", "publish.json")
        if not os.path.exists(pub):
            self.skipTest("還沒做公開版設定")
        spec = json.loads(read_text(pub))
        self.assertNotIn("config.local.json", spec.get("include", []),
                         "個人設定不該出現在 include")
        self.assertIn("config.local.json", spec.get("exclude", []),
                      "個人設定要明確寫進 exclude,⛔ 不要只靠 include 沒列到")

    def test_公開版帶得出去的檔裡沒有個人資料(self):
        """照 publish.json 的 include 挑檔,逐檔掃一次禁詞。"""
        import fnmatch
        pub = os.path.join(ROOT, "public", "publish.json")
        if not os.path.exists(pub):
            self.skipTest("還沒做公開版設定")
        spec = json.loads(read_text(pub))
        # 禁詞清單住在 publish.json(那份不會被帶上去),測試只負責照著掃。
        banned = list(spec.get("forbidden", []))
        taken = []
        for pat in spec.get("include", []):
            for path in sorted(pathlib.Path(ROOT).rglob("*")):
                name = os.path.relpath(path, ROOT)
                if path.is_file() and (fnmatch.fnmatch(name, pat)
                                       or fnmatch.fnmatch(path.name, pat)):
                    taken.append(name)
        self.assertTrue(taken, "include 應該要挑得到檔")
        bad = []
        for name in taken:
            if os.path.basename(name) == "test_photo_review.py":
                continue
            for i, line in enumerate(read_text(os.path.join(ROOT, name)).splitlines(), 1):
                for word in banned:
                    if word in line:
                        bad.append(f"{name}:{i} 出現「{word}」")
        self.assertEqual(bad, [], "公開版會帶出去的檔裡有這些:\n" + "\n".join(bad))


class TestVocab(Sandbox):
    def test_範例用語表讀得出四類(self):
        r = self.run_tool("-m", "photo_review.vocab")
        self.assertEqual(r.returncode, 0, r.stderr)
        for cat in ("作品", "用途", "地點", "主題"):
            self.assertIn(cat, r.stdout)

    def test_範例用語表是示範規模不是誰的真實清單(self):
        """範例只要夠示範就好。一個軸膨脹到幾十個詞,通常代表有人把自己的真實清單貼進來了。

        ⛔ 這裡刻意不列「不可以出現哪些詞」—— 那份名單本身就是個人資料。
           真正的把關在產線上版的時候逐檔掃禁詞。
        """
        env = dict(os.environ)
        env["PHOTO_REVIEW_VOCAB_FILE"] = os.path.join(ROOT, "vocab.example.md")
        sys.path.insert(0, ROOT)
        r = subprocess.run([sys.executable, "-m", "photo_review.vocab"], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for line in r.stdout.splitlines():
            cat, _, rest = line.partition("(")
            n = int(rest.split(")")[0])
            self.assertGreaterEqual(n, 3, f"「{cat}」只有 {n} 個詞,示範不出這個軸在做什麼")
            self.assertLessEqual(n, 15, f"「{cat}」有 {n} 個詞 —— 範例不該這麼長,是不是貼了真實清單?")

    def test_讀不到用語表也不會爆掉(self):
        env = dict(self.env)
        env["PHOTO_REVIEW_VOCAB_FILE"] = os.path.join(self.tmp, "不存在.md")
        r = subprocess.run([sys.executable, "-m", "photo_review.vocab"], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestGenerate(Sandbox):
    def test_掃出照片並產出審片頁(self):
        folder = os.path.join(self.camera, "20260101_測試")
        for i in range(3):
            make_jpeg(os.path.join(folder, f"IMG_{i:04d}.jpg"))
        out = os.path.join(self.tmp, "out")
        r = self.run_tool("-m", "photo_review.review.generate", folder, "--out-dir", out, "--no-open", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        pages = [f for f in os.listdir(out) if f.endswith(".html")]
        self.assertTrue(pages, "應該要產出至少一頁審片頁")
        html = read_text(os.path.join(out, pages[0]))
        self.assertIn("IMG_0000.jpg", html)
        # 產出的頁面只該指向這次的沙盒,⛔ 不該夾帶任何家目錄或外接硬碟的路徑。
        stray = [m for m in re.findall(r"/(?:Users|Volumes|home)/[^\"'\s<>]+", html)
                 if not m.startswith(self.tmp)]
        self.assertEqual(stray, [], f"審片頁裡夾帶了沙盒以外的路徑:{stray[:3]}")

    def test_空資料夾不會產出壞頁面(self):
        folder = os.path.join(self.camera, "空的")
        os.makedirs(folder, exist_ok=True)
        out = os.path.join(self.tmp, "out")
        r = self.run_tool("-m", "photo_review.review.generate", folder, "--out-dir", out, "--no-open", "--yes")
        self.assertNotEqual((r.returncode, r.stdout.strip()), (0, ""),
                            "空資料夾要講話,不能靜悄悄")


class TestApply(Sandbox):
    def _export(self, photo, **kw):
        data = {"photos": [dict({"path": photo, "name": os.path.basename(photo),
                                 "stars": 4, "tags": ["用途|風景精選"],
                                 "note": "測試", "delete": False}, **kw)]}
        p = os.path.join(self.tmp, "export.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return p

    def test_預設是乾跑不會動到檔案(self):
        photo = make_jpeg(os.path.join(self.camera, "20260101_測試", "IMG_0001.jpg"))
        r = self.run_tool("-m", "photo_review.land.apply", self._export(photo))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(photo), "乾跑不該動到照片")
        self.assertFalse(os.path.exists(os.path.join(self.notes, "照片日記總表.csv")),
                         "乾跑不該寫總表")

    def test_加了apply才寫進總表(self):
        photo = make_jpeg(os.path.join(self.camera, "20260101_測試", "IMG_0002.jpg"))
        r = self.run_tool("-m", "photo_review.land.apply", self._export(photo), "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        diary = os.path.join(self.notes, "照片日記總表.csv")
        self.assertTrue(os.path.exists(diary), "--apply 之後總表要出現")
        rows = read_csv(diary)
        self.assertEqual(len(rows), 1)
        self.assertTrue(os.path.exists(photo), "沒標刪除的照片不該被動到")


class TestRenameTag(Sandbox):
    HEAD = ["review日期", "資料夾", "檔名", "星等", "顏色", "標籤", "心得", "路徑"]

    def _diary(self, tag):
        path = os.path.join(self.notes, "照片日記總表.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(self.HEAD)
            w.writerow(["2026-01-01", "20260101_測試", "a.jpg", "4", "", tag,
                        "這裡提到舊名字", os.path.join(self.camera, "a.jpg")])
        return path

    def test_預設只預覽不改檔(self):
        path = self._diary("地點|舊名")
        before = read_text(path)
        r = self.run_tool("-m", "photo_review.library.rename_tag", "地點|舊名", "地點|新名")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_text(path), before)

    def test_apply只改標籤欄不碰心得(self):
        path = self._diary("地點|舊名")
        r = self.run_tool("-m", "photo_review.library.rename_tag", "地點|舊名", "地點|新名", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = read_csv(path)[0]
        self.assertEqual(row["標籤"], "地點|新名")
        self.assertIn("舊名字", row["心得"], "心得是使用者自己寫的話,一個字都不該碰")


class TestNoPersonalDataInCode(unittest.TestCase):
    """守門員:以後誰再把個人路徑寫回程式裡,這一項會當場叫。"""

    def test_程式碼裡沒有寫死的個人路徑(self):
        # 認「形狀」不認名單:任何寫死的家目錄或外接硬碟路徑都算。
        # ⛔ 不要在這裡列某台機器的使用者名稱或硬碟名 —— 那本身就是個人資料。
        hardcoded = re.compile(r"[\"'](?:/Users/|/home/|/Volumes/)[^\"'\s]+")
        bad = []
        # ⛔ 走整棵樹,不是只看根目錄那一層 —— 白名單只會告訴你名單上有誰。
        here = os.path.abspath(__file__)
        for path in sorted(pathlib.Path(ROOT).rglob("*.py")):
            if os.path.abspath(path) == here or ".venv" in path.parts:
                continue
            name = os.path.relpath(path, ROOT)
            for i, line in enumerate(read_text(str(path)).splitlines(), 1):
                m = hardcoded.search(line)
                # 系統內建的東西不算(例:macOS 的預設桌布,測試拿它造圖用)
                if m and not m.group(0).startswith(('"/System/', "'/System/")):
                    bad.append(f"{name}:{i} 寫死了 {m.group(0)}")
        self.assertEqual(bad, [], "路徑要寫在 config.local.json,不要寫回程式:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
