"""気象台からのコメント（comments.py）のテスト。通信なし（取得関数を差し替える）。"""
import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jnav import comments  # noqa: E402

JST = comments.JST
# 気象庁の実際の形式（HTML断片）を小さくしたもの
SAMPLE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title></title></head>
<body style="font-family:monospace"><div class="ycomment_pub_date" style="margin-bottom: 2ex;">2026年10月30日(金)11時28分</div>
<p><span><tt>【警戒レベル相当情報の発表の見込み】</tt><br><tt>（レベル４危険警報）</tt><br><tt>・なし</tt><br><br>
<tt>★［警報・注意報のページ］は</tt><a href="https://www.jma.go.jp/bosai/warning/"><tt>こちら</tt></a><tt>で確認★</tt></span></p>
<script>alert(1)</script><p><tt>＜＜特記事項＞＞</tt><br><tt>雷に注意</tt></p></body></html>"""


class TestParse(unittest.TestCase):
    def test_発表日時と本文(self):
        pub, text = comments.parse(SAMPLE)
        self.assertEqual(pub, "2026年10月30日(金)11時28分")
        self.assertIn("【警戒レベル相当情報の発表の見込み】\n（レベル４危険警報）\n・なし", text)
        self.assertIn("★［警報・注意報のページ］はこちらで確認★", text)  # リンクの文字は残る
        self.assertIn("雷に注意", text)

    def test_スクリプトやタグは文字に出ない(self):
        _, text = comments.parse(SAMPLE)
        self.assertNotIn("alert", text)
        self.assertNotIn("<", text)
        self.assertNotIn("2026年10月30日", text)  # 発表日時は本文に混ぜない

    def test_空行は詰める(self):
        _, text = comments.parse("<p>a</p><br><br><br><p>b</p>")
        self.assertNotIn("\n\n\n", text)

    def test_発表日時の解析(self):
        self.assertEqual(comments.published_at("2026年10月30日(金)11時28分"), datetime.datetime(2026, 10, 30, 11, 28, tzinfo=JST))
        self.assertIsNone(comments.published_at("不明"))
        self.assertIsNone(comments.published_at("2026年13月40日 99時99分"))


class TestGet(unittest.TestCase):
    def setUp(self):
        comments.clear_cache()
        self.now = datetime.datetime(2026, 10, 30, 12, 0, tzinfo=JST)

    def test_取得して全文を返す(self):
        urls = []
        r = comments.get("471000", fetcher=lambda u: urls.append(u) or SAMPLE.encode(), now=self.now)
        self.assertEqual(urls, ["https://www.jma.go.jp/bosai/forecaster_comment/data/comments/471000.txt"])
        self.assertEqual((r["office_name"], r["published"], r["stale"]), ("沖縄気象台", "2026年10月30日(金)11時28分", False))
        self.assertEqual(r["age_hours"], 0.5)

    def test_古いと注意(self):
        r = comments.get("471000", fetcher=lambda u: SAMPLE.encode(), now=self.now + datetime.timedelta(hours=20))
        self.assertTrue(r["stale"])

    def test_予報区以外は取得しない(self):
        calls = []
        for bad in ["../../etc/passwd", "999999", "", "471000/../x", "http://evil"]:
            self.assertIsNone(comments.get(bad, fetcher=lambda u: calls.append(u) or b"x"))
        self.assertEqual(calls, [])

    def test_キャッシュ(self):
        n = []
        f = lambda u: n.append(u) or SAMPLE.encode()  # noqa: E731
        clk = [0.0]
        comments.get("471000", fetcher=f, now=self.now, clock=lambda: clk[0])
        clk[0] = 100
        comments.get("471000", fetcher=f, now=self.now, clock=lambda: clk[0])
        self.assertEqual(len(n), 1)   # TTL内は再取得しない
        clk[0] = 400
        comments.get("471000", fetcher=f, now=self.now, clock=lambda: clk[0])
        self.assertEqual(len(n), 2)

    def test_失敗はNoneで短く覚える(self):
        n = []

        def boom(u):
            n.append(u)
            raise OSError("down")
        clk = [0.0]
        self.assertIsNone(comments.get("471000", fetcher=boom, clock=lambda: clk[0]))
        self.assertIsNone(comments.get("471000", fetcher=boom, clock=lambda: clk[0]))
        self.assertEqual(len(n), 1)   # 連続アクセスで気象庁に負荷をかけない
        clk[0] = 60
        comments.get("471000", fetcher=boom, clock=lambda: clk[0])
        self.assertEqual(len(n), 2)

    def test_大きすぎる応答は使わない(self):
        self.assertIsNone(comments.get("471000", fetcher=lambda u: b"a" * (comments.MAX_BYTES + 1)))

    def test_本文が空ならNone(self):
        self.assertIsNone(comments.get("471000", fetcher=lambda u: b"<html><body></body></html>"))


if __name__ == "__main__":
    unittest.main()
