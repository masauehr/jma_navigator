"""地域の単位（全国・府県・市町村）の選択のテスト。通信なし。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jnav.navigate import guide, scopes_of, load_catalog  # noqa: E402


class TestScope(unittest.TestCase):
    def test_市町村名があれば市町村の単位になる(self):
        r = guide("那覇市の警報は出ている？", item_id="warning_map")
        self.assertEqual((r["status"], r["scope"]), ("ok", "class20s"))
        self.assertIn("area_type=class20s&area_code=4720100", r["url"])

    def test_府県の名前なら府県の単位(self):
        r = guide("沖縄の警報は？", item_id="warning_map")
        self.assertEqual(r["scope"], "offices")
        self.assertIn("areaCode=471000", r["url"])

    def test_地名がなければ全国(self):
        r = guide("警報は出ている？", item_id="warning_map")
        self.assertEqual((r["scope"], r["url"]), ("japan", "https://www.jma.go.jp/bosai/map.html#contents=warning"))

    def test_単位を指定して切り替える(self):
        self.assertEqual(guide("那覇市の警報", item_id="warning_map", scope="offices")["scope"], "offices")
        self.assertEqual(guide("那覇市の警報", item_id="warning_map", scope="japan")["scope"], "japan")

    def test_略称で市町村を選ぶと黙って決めず確認する(self):
        r = guide("沖縄の警報", item_id="warning_map", scope="class20s")
        self.assertEqual(r["status"], "need_place")
        self.assertEqual([c["place"] for c in r["candidates"]], ["沖縄市"])
        self.assertIn("class20_code", r["candidates"][0])

    def test_市町村の指定に地名がない(self):
        r = guide("警報は出ている？", item_id="warning_map", scope="class20s")
        self.assertEqual(r["status"], "need_place")
        self.assertIn("hint", r)

    def test_対応する単位の一覧(self):
        by = {i["id"]: i for i in load_catalog()}
        self.assertEqual([s["value"] for s in scopes_of(by["warning_map"])], ["japan", "offices", "class20s"])
        self.assertEqual([s["value"] for s in scopes_of(by["forecast_short"])], ["offices", "class20s"])
        self.assertEqual(scopes_of(by["early_warning"]), [])  # 府県のみ（一次細分は全国地図に戻るため非対応）

    def test_予報は市町村でも開く(self):
        r = guide("明日の那覇市の天気", item_id="forecast_short", scope="class20s")
        self.assertIn("forecast/#area_type=class20s&area_code=4720100", r["url"])


if __name__ == "__main__":
    unittest.main()
