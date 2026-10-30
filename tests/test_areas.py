import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jnav.areas import pick, resolve  # noqa: E402


class TestAreas(unittest.TestCase):
    def test_確定する地名(self):
        for q, office in [("那覇", "471000"), ("石垣", "474000"), ("東京", "130000"),
                          ("広島", "340000"), ("札幌", "016000"), ("鹿児島", "460100")]:
            with self.subTest(q=q):
                self.assertEqual(pick(q)["office_code"], office)

    def test_地区に分割された市(self):
        # 2026-10-30 の area.json 更新で「横浜市」などが「横浜市北部/南部」に分割された
        for q, office in [("横浜市", "140000"), ("相模原市", "140000"), ("長野市", "200000"), ("富山市", "160000")]:
            with self.subTest(q=q):
                self.assertEqual(pick(q)["office_code"], office)

    def test_曖昧な地名は確定しない(self):
        for q in ["府中", "伊達", "北海道"]:
            with self.subTest(q=q):
                self.assertIsNone(pick(q))
                self.assertGreaterEqual(len({c["office_code"] for c in resolve(q)}), 2)

    def test_見つからない(self):
        self.assertEqual(resolve("存在しない町xyz"), [])
        self.assertEqual(resolve(""), [])

    def test_ひらがな(self):
        self.assertEqual(pick("なはし")["office_code"], "471000")


if __name__ == "__main__":
    unittest.main()
