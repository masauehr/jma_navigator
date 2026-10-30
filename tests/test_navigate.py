import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import date  # noqa: E402

from jnav.navigate import guide, parse_year_month  # noqa: E402


class TestGuide(unittest.TestCase):
    def test_url確定(self):
        r = guide("明日の那覇の天気を知りたい")
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["url"].endswith("area_code=471000"))

    def test_地名なしの静的ページ(self):
        r = guide("台風の進路")
        self.assertEqual((r["status"], r["item"]), ("ok", "typhoon"))

    def test_曖昧な地名は聞き返し(self):
        self.assertEqual(guide("府中の天気予報")["status"], "need_place")

    def test_過去データ_地点なしは聞き返し(self):
        self.assertEqual(guide("去年の8月の気温")["status"], "need_place")

    def test_過去データ_url確定(self):
        r = guide("2025年8月の那覇の気温")
        self.assertEqual(r["status"], "ok")
        self.assertIn("daily_s1.php?prec_no=91&block_no=47936&year=2025&month=8", r["url"])

    def test_アメダス現在値(self):
        r = guide("石垣島の今の気温は")
        self.assertEqual(r["status"], "ok")
        self.assertIn("amdno=94081", r["url"])

    def test_アメダス_同名は聞き返し(self):
        r = guide("府中の今の気温")
        self.assertEqual(r["status"], "need_place")
        self.assertEqual({c["area"] for c in r["candidates"]}, {"東京", "広島"})

    def test_アメダス_観測しない要素は注意(self):
        r = guide("渡名喜の今の気温")  # 渡名喜は雨量のみ
        self.assertEqual(r["status"], "ok")
        self.assertIn("気温を観測していません", r["note"])

    def test_アメダス_積雪用番号は除外(self):
        self.assertIn("amdno=62078", guide("大阪の今の気温")["url"])

    def test_県名つきで同名を絞り込む(self):
        self.assertIn("amdno=67326", guide("広島の府中市の今の気温")["url"])  # 広島県の府中
        self.assertTrue(guide("東京の府中市の天気")["url"].endswith("area_code=130000"))

    def test_ひらがな地名(self):
        self.assertTrue(guide("おおさかの天気")["url"].endswith("area_code=270000"))

    def test_沖縄の離島はprec_no91(self):
        self.assertIn("prec_no=91&block_no=47918", guide("2025年8月の石垣島の気温")["url"])

    def test_年月の解析(self):
        t = date(2026, 10, 27)
        self.assertEqual(parse_year_month("去年の8月", t), (2025, 8))
        self.assertEqual(parse_year_month("先月", t), (2026, 9))
        self.assertEqual(parse_year_month("12月", t), (2025, 12))
        self.assertEqual(parse_year_month("2024年3月", t), (2024, 3))
        self.assertEqual(parse_year_month("先月", date(2026, 1, 5)), (2025, 12))

    def test_台風は経路図へ(self):
        for q in ["台風の進路", "台風経路図", "台風情報"]:
            with self.subTest(q=q):
                r = guide(q)
                self.assertEqual((r["item"], r["status"]), ("typhoon", "ok"))
                self.assertEqual(r["url"], "https://www.jma.go.jp/bosai/map.html#contents=typhoon")

    def test_大雨の見通しと早期注意情報(self):
        self.assertEqual(guide("大雨の見通し")["item"], "warning_timeline")
        self.assertEqual(guide("全国の早期注意情報")["item"], "early_warning_map")
        self.assertEqual(guide("早期注意情報")["item"], "early_warning")  # 地域が要る→聞き返し
        r = guide("那覇の早期注意情報")
        self.assertEqual((r["item"], r["status"]), ("early_warning", "ok"))
        self.assertIn("area_code=471000", r["url"])

    def test_該当なし(self):
        self.assertEqual(guide("ラーメンの作り方")["status"], "no_match")


if __name__ == "__main__":
    unittest.main()
