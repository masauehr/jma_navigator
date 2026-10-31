"""地方（地方予報区）と予報区の対応の点検。通信なし（気象庁の画面での確認結果を期待値に使う）。"""
import collections
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jnav import areas  # noqa: E402
from jnav.navigate import guide  # noqa: E402

# 2026-10-31 に、気象庁の「警報・注意報」ページ（area_type=centers）で確認した、各地方に含まれる予報区の数と名前
OFFICIAL = {
    "010100": ("北海道地方", ["宗谷地方", "上川・留萌地方", "網走・北見・紋別地方", "十勝地方", "釧路・根室地方", "胆振・日高地方", "石狩・空知・後志地方", "渡島・檜山地方"]),
    "010200": ("東北地方", ["青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"]),
    "010300": ("関東甲信地方", ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", "山梨県", "長野県"]),
    "010400": ("東海地方", ["岐阜県", "静岡県", "愛知県", "三重県"]),
    "010500": ("北陸地方", ["新潟県", "富山県", "石川県", "福井県"]),
    "010600": ("近畿地方", ["滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"]),
    "010700": ("中国地方（山口県を除く）", ["鳥取県", "島根県", "岡山県", "広島県"]),
    "010800": ("四国地方", ["徳島県", "香川県", "愛媛県", "高知県"]),
    "010900": ("九州北部地方（山口県を含む）", ["山口県", "福岡県", "佐賀県", "長崎県", "熊本県", "大分県"]),
    "011000": ("九州南部・奄美地方", ["宮崎県", "鹿児島県（奄美地方除く）", "奄美地方"]),
    "011100": ("沖縄地方", ["沖縄本島地方", "大東島地方", "宮古島地方", "八重山地方"]),
}


class TestCenterDictionary(unittest.TestCase):
    def setUp(self):
        self.area = areas._load()

    def test_気象庁の画面と一致(self):
        self.assertEqual(set(self.area["centers"]), set(OFFICIAL))
        for code, (name, offices) in OFFICIAL.items():
            with self.subTest(center=name):
                c = self.area["centers"][code]
                self.assertEqual(c["name"], name)
                # 並び順は問わず、含まれる予報区が気象庁の画面と同じか（辞書の並びは気象庁の画面と一部違う）
                self.assertEqual(sorted(self.area["offices"][o]["name"] for o in c["children"]), sorted(offices))

    def test_全予報区がちょうど1つの地方に属する(self):
        count = collections.Counter(o for c in self.area["centers"].values() for o in c["children"])
        self.assertEqual(set(count), set(self.area["offices"]))
        self.assertEqual({v for v in count.values()}, {1})
        for oc, o in self.area["offices"].items():
            self.assertIn(oc, self.area["centers"][o["parent"]]["children"])

    def test_予報区から地方を引ける(self):
        self.assertEqual(areas.center_of("471000"), ("011100", "沖縄地方"))
        self.assertEqual(areas.center_of("350000"), ("010900", "九州北部地方（山口県を含む）"))  # 山口県
        self.assertEqual(areas.center_of("460100"), ("011000", "九州南部・奄美地方"))          # 奄美

    def test_地方コードと予報区コードは重なるが区別される(self):
        # 011000 は「宗谷地方（予報区）」でもあり「九州南部・奄美地方（地方）」でもある
        self.assertEqual(self.area["offices"]["011000"]["name"], "宗谷地方")
        self.assertEqual(self.area["centers"]["011000"]["name"], "九州南部・奄美地方")
        r = guide("奄美の警報", item_id="warning_map", scope="centers")
        self.assertIn("area_type=centers&area_code=011000", r["url"])
        r = guide("宗谷地方の警報", item_id="warning_map", scope="offices")
        self.assertIn("area_type=offices&area_code=011000", r["url"])


class TestCenterAliases(unittest.TestCase):
    def center(self, q, scope="centers"):
        r = guide(q + "の警報", item_id="warning_map", scope=scope)
        return r["status"], r.get("place"), r

    def test_通称(self):
        for q, name in [("関東", "関東甲信地方"), ("東北", "東北地方"), ("東海", "東海地方"), ("北陸", "北陸地方"),
                        ("近畿", "近畿地方"), ("関西", "近畿地方"), ("四国", "四国地方"), ("沖縄", "沖縄地方"),
                        ("九州北部", "九州北部地方（山口県を含む）"), ("九州南部", "九州南部・奄美地方"), ("奄美", "九州南部・奄美地方"),
                        ("北海道", "北海道地方"), ("中国", "中国地方（山口県を除く）")]:
            with self.subTest(q=q):
                st, place, _ = self.center(q)
                self.assertEqual((st, place), ("ok", name))

    def test_九州は2つの地方の候補(self):
        st, _, r = self.center("九州")
        self.assertEqual(st, "need_place")
        self.assertEqual({c["center_code"] for c in r["candidates"]}, {"010900", "011000"})

    def test_市町村名は予報区から地方を決める(self):
        self.assertEqual(self.center("北九州市")[1], "九州北部地方（山口県を含む）")   # 「九州」の語に引きずられない
        self.assertEqual(self.center("東海村")[1], "関東甲信地方")                      # 茨城県の東海村（東海地方ではない）
        self.assertEqual(self.center("東海市")[1], "東海地方")

    def test_通称だけで地方の単位が既定になる(self):
        self.assertEqual(guide("関東の警報", item_id="warning_map")["scope"], "centers")
        self.assertEqual(guide("東海市の警報", item_id="warning_map")["scope"], "class20s")  # 市名が書かれていれば市町村

    def test_地方名で府県を選ぶと地方内の予報区から選ぶ(self):
        r = guide("沖縄地方の警報", item_id="warning_map", scope="offices")
        self.assertEqual(r["status"], "need_place")
        self.assertEqual([c["place"] for c in r["candidates"]], ["沖縄本島地方", "大東島地方", "宮古島地方", "八重山地方"])
        r = guide("北海道地方の警報", item_id="warning_map", scope="offices")
        self.assertEqual(len(r["candidates"]), 8)
        # 予報区名も書かれていれば、それに決まる
        r = guide("沖縄地方の八重山地方の警報", item_id="warning_map", scope="offices")
        self.assertEqual((r["status"], r["place"]), ("ok", "八重山地方"))
        self.assertIn("area_type=offices&area_code=474000", r["url"])

    def test_沖縄地方の画面と同じ4予報区(self):
        # 気象庁「沖縄地方の警報・注意報」（2026-10-31確認）に並ぶ4つ
        self.assertEqual([n for _, n in areas.center_offices("011100")], ["沖縄本島地方", "大東島地方", "宮古島地方", "八重山地方"])

    def test_山口県の注記(self):
        self.assertIn("山口県は含まれません", self.center("中国")[2]["note"])
        self.assertIn("九州北部地方に含まれます", self.center("山口県")[2]["note"])
        self.assertNotIn("note", self.center("福岡県")[2])
        self.assertNotIn("note", self.center("北九州市")[2])


if __name__ == "__main__":
    unittest.main()
