"""全国観測値ランキング（日別）の案内のテスト。通信なし（日付は固定）。"""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jnav import navigate  # noqa: E402
from jnav.navigate import guide, parse_rank_date, today_jst  # noqa: E402
from jnav.suggest import suggest  # noqa: E402

TODAY = date(2026, 10, 30)


class TestRankDate(unittest.TestCase):
    def test_相対と絶対の日付(self):
        f = lambda q: parse_rank_date(q, TODAY)  # noqa: E731
        self.assertEqual(f("今日の最高気温ランキング"), TODAY)
        self.assertEqual(f("最高気温ランキング"), TODAY)                       # 指定なしは今日
        self.assertEqual(f("昨日のランキング"), date(2026, 10, 29))
        self.assertEqual(f("一昨日のランキング"), date(2026, 10, 28))
        self.assertEqual(f("10月28日の最低気温ランキング"), date(2026, 10, 28))
        self.assertEqual(f("28日のランキング"), date(2026, 10, 28))
        self.assertEqual(f("12月25日のランキング"), date(2025, 12, 25))        # 未来の日付は昨年扱い
        self.assertEqual(f("31日のランキング"), TODAY)  # 今月はまだ31日でなく、先月(9月)にも31日はない → 今日

    def test_日数の表現は日付として読まない(self):
        self.assertEqual(parse_rank_date("3日間のランキング", TODAY), TODAY)
        self.assertEqual(parse_rank_date("3日前のランキング", TODAY), TODAY)

    def test_日本時間の今日(self):
        # サーバーがUTCでも、日本時間の日付を使う（UTC 10/29 20:00 = JST 10/30 05:00）
        class FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 29, 20, 0, tzinfo=__import__("datetime").timezone.utc).astimezone(tz)
        with mock.patch.object(navigate, "datetime", FakeDT):
            self.assertEqual(today_jst(), date(2026, 10, 30))


class TestRankGuide(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(navigate, "today_jst", return_value=TODAY)
        p.start()
        self.addCleanup(p.stop)

    def test_今日は日付つきページ(self):
        r = suggest("今日の最高気温ランキングを教えて")
        self.assertEqual(r["item"], "rank_daily")
        self.assertEqual(r["url"], "https://www.data.jma.go.jp/stats/data/mdrr/rank_daily/data1030.html")
        self.assertEqual(r["place"], "10月30日（今日）")

    def test_次点に一覧ページが必ず出る(self):
        r = suggest("今日の最高気温ランキングを教えて")
        first = r["alternatives"][0]
        self.assertEqual(first["item"], "rank_daily_index")
        self.assertEqual(first["url"], "https://www.data.jma.go.jp/stats/data/mdrr/rank_daily/index.html")

    def test_昨日と日付指定(self):
        self.assertTrue(suggest("昨日の最高気温ランキング")["url"].endswith("data1029.html"))
        r = suggest("10月28日の最低気温ランキング")
        self.assertTrue(r["url"].endswith("data1028.html"))
        self.assertEqual(r["place"], "10月28日（一昨日）")
        self.assertEqual(guide("10月24日の最高気温ランキング", item_id="rank_daily")["place"], "10月24日")

    def test_掲載期間外は一覧ページと理由(self):
        r = guide("10月1日の最高気温ランキング", item_id="rank_daily")
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["url"].endswith("rank_daily/index.html"))
        self.assertIn("最近1週間分", r["note"])

    def test_歴代や観測史上は日別ランキングにしない(self):
        for q in ["歴代の最高気温ランキング", "観測史上1位の気温"]:
            with self.subTest(q=q):
                r = suggest(q)
                self.assertEqual(r["item"], "record_ranking")
                shown = [r["item"]] + [a["item"] for a in r["alternatives"]]
                self.assertNotIn("rank_daily", shown)
                self.assertNotIn("rank_daily_index", shown)

    def test_一覧だけを聞く(self):
        self.assertEqual(suggest("ランキングの一覧")["item"], "rank_daily_index")
        self.assertEqual(suggest("ランキングを見たい")["item"], "rank_daily_index")


if __name__ == "__main__":
    unittest.main()
