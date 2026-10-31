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
        # 府県は警報・注意報のページ（予報区の発表状況）。map.html の areaCode は無視され全国の地図になるため使わない
        self.assertIn("warning/#area_type=offices&area_code=471000", r["url"])
        self.assertNotIn("map.html", r["url"])

    def test_地名がなければ全国(self):
        r = guide("警報は出ている？", item_id="warning_map")
        self.assertEqual((r["scope"], r["url"]), ("japan", "https://www.jma.go.jp/bosai/map.html#contents=warning"))

    def test_名護市の警報で府県を選ぶと沖縄本島地方(self):
        r = guide("名護市の警報", item_id="warning_map", scope="offices")
        self.assertEqual((r["status"], r["scope"], r["place"]), ("ok", "offices", "沖縄本島地方"))
        self.assertIn("area_code=471000", r["url"])

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
        self.assertEqual([s["value"] for s in scopes_of(by["warning_map"])], ["japan", "centers", "offices", "class20s"])
        self.assertEqual([s["value"] for s in scopes_of(by["forecast_short"])], ["offices", "class20s"])  # 地方は全国の予報に戻るため非対応
        self.assertEqual([s["value"] for s in scopes_of(by["early_warning"])], ["centers", "offices"])  # 市町村・一次細分は全国地図に戻る
        self.assertEqual([s["label"] for s in scopes_of(by["warning_map"])], ["全国", "地方", "府県", "市町村"])

    def test_地方の単位(self):
        # 利用者が示したURLと同じ: 沖縄地方 = 011100（予報区 沖縄本島・大東島・宮古島・八重山をまとめた単位）
        r = guide("名護市の警報", item_id="warning_map", scope="centers")
        self.assertEqual((r["status"], r["scope"], r["place"]), ("ok", "centers", "沖縄地方"))
        self.assertEqual(r["url"], "https://www.jma.go.jp/bosai/warning/#area_type=centers&area_code=011100&lang=ja")

    def test_地方名が書かれていれば地方の単位(self):
        r = guide("東北地方の警報", item_id="warning_map")
        self.assertEqual((r["scope"], r["place"]), ("centers", "東北地方"))
        self.assertIn("area_code=010200", r["url"])

    def test_地名がなければ地方を選んでもらう(self):
        r = guide("警報は？", item_id="warning_map", scope="centers")
        self.assertEqual(r["status"], "need_place")
        self.assertEqual(len(r["candidates"]), 11)
        self.assertTrue(all("center_code" in c for c in r["candidates"]))

    def test_地方に対応するページ(self):
        for iid, frag in [("warning_timeline", "warning_timeline/#area_type=centers&area_code=011100"),
                          ("early_warning", "probability/#area_type=centers&area_code=011100"),
                          ("information", "information/#area_type=centers&area_code=011100")]:
            with self.subTest(iid=iid):
                self.assertIn(frag, guide("沖縄の" + iid, item_id=iid, scope="centers")["url"])

    def test_北海道は北海道地方になる(self):
        # 「北海道」は8つの予報区にまたがるが、すべて北海道地方（010100）に属する
        for scope in (None, "centers"):
            with self.subTest(scope=scope):
                r = guide("北海道の警報", item_id="warning_map", scope=scope)
                self.assertEqual((r["status"], r["scope"], r["place"]), ("ok", "centers", "北海道地方"))
                self.assertIn("area_type=centers&area_code=010100", r["url"])
        self.assertEqual(guide("道内の警報", item_id="warning_map", scope="centers")["place"], "北海道地方")
        self.assertIn("probability/#area_type=centers&area_code=010100", guide("北海道の早期注意情報", item_id="early_warning")["url"])

    def test_北海道の府県は8予報区すべてを選べる(self):
        for item, scope in (("warning_map", "offices"), ("forecast_short", None)):
            with self.subTest(item=item):
                r = guide("北海道の天気", item_id=item, scope=scope)
                self.assertEqual(r["status"], "need_place")
                self.assertEqual(len(r["candidates"]), 8)  # 以前は6件で切れて、選べない予報区があった
                self.assertEqual(len({c["office_code"] for c in r["candidates"]}), 8)

    def test_複数の地方にまたがる地名は地方も聞き返す(self):
        r = guide("府中の警報", item_id="warning_map", scope="centers")
        self.assertEqual(r["status"], "need_place")
        self.assertEqual({c["office_code"] for c in r["candidates"]}, {"130000", "340000"})  # 東京都・広島県

    def test_天気予報は地方に対応しない(self):
        r = guide("沖縄の天気", item_id="forecast_short", scope="centers")
        self.assertEqual(r["scope"], "offices")  # 非対応の単位は無視して地名から決める

    def test_予報は市町村でも開く(self):
        r = guide("明日の那覇市の天気", item_id="forecast_short", scope="class20s")
        self.assertIn("forecast/#area_type=class20s&area_code=4720100", r["url"])


if __name__ == "__main__":
    unittest.main()
