import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jnav.navigate import guide  # noqa: E402


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

    def test_過去データは観測所辞書が未整備のため不足を返す(self):
        r = guide("去年の8月の気温")
        self.assertEqual(r["status"], "need_more")
        self.assertIn("prec_no", r["missing"])

    def test_該当なし(self):
        self.assertEqual(guide("ラーメンの作り方")["status"], "no_match")


if __name__ == "__main__":
    unittest.main()
