"""check_links のテスト。通信せず、偽の取得関数で動作を確かめる。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check_links as cl  # noqa: E402


class FillTest(unittest.TestCase):
    def test_placeholder_and_hash(self):
        u = cl.fill("https://x/a.php?prec_no={prec_no}&block_no={block_no}#h=1")
        self.assertEqual(u, "https://x/a.php?prec_no=91&block_no=47936")

    def test_no_placeholder(self):
        self.assertEqual(cl.fill("https://x/bosai/forecast/#area_type=offices"), "https://x/bosai/forecast/")


class RunTest(unittest.TestCase):
    def _root(self, local_area):
        d = Path(tempfile.mkdtemp())
        (d / "data").mkdir()
        (d / "catalog.json").write_text(json.dumps({"items": [
            {"id": "a", "url": "https://x/p/#h={office_code}"},
            {"id": "b", "url": "https://x/p/#other"},  # ハッシュ違いでも同じURL→1回だけ取得
            {"id": "c", "url": "https://x/gone"},
        ]}), encoding="utf-8")
        (d / "data" / "area.json").write_text(json.dumps(local_area), encoding="utf-8")
        (d / "data" / "amedastable.json").write_text("{}", encoding="utf-8")
        return d

    def test_results(self):
        calls = []

        def fake(url):
            calls.append(url)
            if url.endswith("/gone"):
                return 404, b""
            if url.endswith("area.json"):
                return 200, json.dumps({"v": 2}).encode()
            if url.endswith("amedastable.json"):
                return 200, b"{}"
            return 200, b"x"

        res = cl.run(fetcher=fake, sleep=lambda: None, root=self._root({"v": 1}))
        by = {r["id"]: r for r in res}
        self.assertTrue(by["a"]["ok"] and by["b"]["ok"])
        self.assertFalse(by["c"]["ok"])
        self.assertEqual(calls.count("https://x/p/"), 1)
        self.assertFalse(by["data/area.json"]["ok"])      # 原本と差分
        self.assertTrue(by["data/amedastable.json"]["ok"])  # 原本と一致

    def test_connection_error(self):
        res = cl.run(fetcher=lambda u: (0, b"timeout"), sleep=lambda: None, root=self._root({}))
        self.assertTrue(all(not r["ok"] for r in res))


if __name__ == "__main__":
    unittest.main()
