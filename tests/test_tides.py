"""潮位観測所の解決と、波のページの案内のテスト。通信なし。"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jnav.navigate import guide  # noqa: E402
from jnav.suggest import suggest  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data" / "tide_stations.json"


class TestTides(unittest.TestCase):
    def test_辞書は166局(self):
        st = json.loads(DATA.read_text(encoding="utf-8"))
        self.assertEqual(len(st), 166)
        self.assertEqual(len({s["code"] for s in st}), 166)
        self.assertTrue(all(s["office_code"] for s in st))

    def test_観測所名で確定し潮位ビューアと同じURLになる(self):
        # tide_viewer/js/config.js の那覇・石垣の値と一致
        r = guide("那覇の潮位", item_id="tide")
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["url"].endswith("area_type=class20s&area_code=4720100&point_code=209131&filter=0&class30s=47101100"))
        r = guide("石垣の満潮はいつ", item_id="tide")
        self.assertIn("area_code=4720700&point_code=209431&filter=0&class30s=47401100", r["url"])

    def test_観測所がない市町村は同じ地方の観測所を候補に(self):
        r = guide("名護市の潮位", item_id="tide")
        self.assertEqual(r["status"], "need_place")
        self.assertEqual({c["place"] for c in r["candidates"]}, {"沖縄（国土地理院）", "那覇", "中城湾港（港湾局）"})
        self.assertTrue(all("station_code" in c and "class30_code" in c for c in r["candidates"]))

    def test_地名がなければ聞き返し(self):
        r = guide("潮位", item_id="tide")
        self.assertEqual(r["status"], "need_place")
        self.assertIn("hint", r)

    def test_波のページ(self):
        r = suggest("波の高さを知りたい")
        self.assertEqual(r["item"], "wave_map")
        self.assertEqual(r["url"], "https://www.data.jma.go.jp/waveinf/tile/jp/index.html")
        self.assertIn("wave_coastal", [a["item"] for a in r["alternatives"]])

    def test_釣りと波では波浪図を案内(self):
        r = suggest("明日、石垣島で釣りに行くけど波は大丈夫？")
        shown = [r["item"]] + [a["item"] for a in r["alternatives"]]
        self.assertIn("wave_map", shown)
        self.assertIn("forecast_short", shown)

    def test_津波は波浪図ではない(self):
        r = suggest("津波が心配")
        self.assertEqual(r["item"], "tsunami")
        self.assertNotIn("wave_map", [a["item"] for a in r.get("alternatives", [])])


if __name__ == "__main__":
    unittest.main()
