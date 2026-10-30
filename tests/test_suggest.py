"""suggest（複数候補・絞り込み）のテスト。通信なし。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jnav.suggest import _topic_hits, _when_hits, rank, suggest  # noqa: E402


class TestSuggest(unittest.TestCase):
    def test_地名があれば地域指定できるページが本命(self):
        r = suggest("沖縄の大雨の見通し")
        self.assertIn(r["item"], ("early_warning", "warning_timeline"))
        self.assertIn("area_code=471000", r["url"])
        shown = {r["item"]} | {a["item"] for a in r["alternatives"]}
        self.assertTrue({"early_warning", "warning_timeline"} <= shown)  # どちらも案内に出る

    def test_地名がなければ全国版が本命で地域が要るページは聞き返し(self):
        r = suggest("大雨の見通し")
        self.assertEqual((r["item"], r["scope"]), ("warning_timeline", "japan"))
        alt = {a["item"]: a for a in r["alternatives"]}
        self.assertEqual(alt["early_warning"]["status"], "need_place")
        self.assertNotIn("url", alt["early_warning"])

    def test_話題だけなら本命を決めず選択肢を出す(self):
        r = suggest("雨が心配")
        self.assertEqual(r["status"], "choose")
        self.assertNotIn("item", r)
        self.assertGreaterEqual(len(r["alternatives"]), 3)

    def test_却下した項目は出ない(self):
        r = suggest("沖縄の大雨の見通し", exclude=["early_warning", "warning_timeline"])
        shown = [r.get("item")] + [a["item"] for a in r["alternatives"]]
        self.assertNotIn("early_warning", shown)
        self.assertNotIn("warning_timeline", shown)

    def test_絞り込みで時間軸が効く(self):
        past = suggest("気温", refine={"when": "past"})
        self.assertIn(past["item"], ("past_data_search", "past_data_menu", "record_ranking"))

    def test_今年の冬の今は未来(self):
        r = suggest("今年の冬は寒い？")
        self.assertIn(r["item"], ("monthly_forecast", "three_month_forecast"))

    def test_該当なしは選択肢つき(self):
        r = suggest("ラーメンの作り方")
        self.assertEqual(r["status"], "no_match")
        self.assertTrue(r["choices"]["topic"])

    def test_海と出かける前の確認を拾う(self):
        q = "今日の夕方、名護市の海に行きたいけど、天気は大丈夫？"
        self.assertTrue({"sea", "safety", "weather"} <= _topic_hits(q))
        self.assertTrue({"now", "future"} <= _when_hits(q))
        r = suggest(q)
        self.assertEqual((r["item"], r["scope"]), ("forecast_short", "class20s"))
        self.assertIn("area_code=4720900", r["url"])
        self.assertIn("warning_map", [a["item"] for a in r["alternatives"]])  # 警報・注意報の確認も案内する

    def test_津波は波浪の話題にしない(self):
        self.assertNotIn("wave", _topic_hits("津波が心配"))
        self.assertIn("wave", _topic_hits("高波が心配"))

    def test_夕方や夜はこれから(self):
        self.assertIn("future", _when_hits("夕方の雨"))
        self.assertIn("future", _when_hits("今夜の天気"))

    def test_点数の順(self):
        scores = [s for s, _, _ in rank("明日の那覇の天気")]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
