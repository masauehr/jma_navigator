"""server.py のテスト。127.0.0.1 の一時ポートで起動し、ローカル通信だけで確かめる。"""
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


def call(port, path, body=None, host=None, ctype="application/json"):
    headers = {"Content-Type": ctype}
    if host:
        headers["Host"] = host
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_index(self):
        code, body, h = call(self.port, "/")
        self.assertEqual(code, 200)
        self.assertIn("気象庁ナビ".encode(), body)
        self.assertIn("default-src 'self'", h["Content-Security-Policy"])

    def test_guide_ok(self):
        code, body, _ = call(self.port, "/api/guide", {"question": "明日の那覇の天気"})
        d = json.loads(body)
        self.assertEqual((code, d["status"]), (200, "ok"))
        self.assertTrue(d["url"].startswith("https://www.jma.go.jp/"))

    def test_guide_need_place_candidates(self):
        d = json.loads(call(self.port, "/api/guide", {"question": "府中の天気"})[1])
        self.assertEqual(d["status"], "need_place")
        self.assertGreaterEqual(len(d["candidates"]), 2)

    def test_candidate_pick_resolves(self):
        # 画面の候補ボタンは、候補の office_code を pick として送る
        d = json.loads(call(self.port, "/api/guide", {"question": "府中の天気", "pick": {"office_code": "130000"}})[1])
        self.assertEqual(d["status"], "ok")
        self.assertIn("area_code=130000", d["url"])

    def test_pick_outside_candidates_ignored(self):
        # 候補にない値は受け付けない(URLは任意の値で組み立てられない)
        d = json.loads(call(self.port, "/api/guide", {"question": "府中の天気", "pick": {"office_code": "999999"}})[1])
        self.assertEqual(d["status"], "need_place")

    def test_alternatives_and_refine(self):
        d = json.loads(call(self.port, "/api/guide", {"question": "沖縄の大雨の見通し"})[1])
        self.assertEqual(d["status"], "ok")
        self.assertIn("area_code=471000", d["url"])
        self.assertGreaterEqual(len(d["alternatives"]), 2)
        self.assertTrue(all(a["url"].startswith(server.ALLOWED_HOSTS) for a in d["alternatives"] if a.get("url")))
        # 「違う」: 却下した項目を除き、話題で絞って探し直す
        d2 = json.loads(call(self.port, "/api/guide", {"question": "沖縄の大雨の見通し", "exclude": [d["item"]],
                                                     "refine": {"when": "now"}})[1])
        self.assertNotEqual(d2.get("item"), d["item"])
        shown = [d2.get("item")] + [a["item"] for a in d2.get("alternatives", [])]
        self.assertNotIn(d["item"], shown)

    def test_choose_when_ambiguous(self):
        d = json.loads(call(self.port, "/api/guide", {"question": "雨が心配"})[1])
        self.assertEqual(d["status"], "choose")
        self.assertTrue(d["alternatives"] and d["choices"]["when"])

    def test_refine_input_sanitized(self):
        # 想定外のキー・型は無視され、エラーにならない
        d = json.loads(call(self.port, "/api/guide", {"question": "雨が心配", "refine": {"x": 1, "when": "future"},
                                                     "exclude": [1, 2]})[1])
        self.assertIn(d["status"], ("ok", "choose", "need_place"))

    def test_bad_requests(self):
        self.assertEqual(call(self.port, "/api/guide", {"question": ""})[0], 400)
        self.assertEqual(call(self.port, "/api/guide", {"question": "あ" * 201})[0], 400)
        self.assertEqual(call(self.port, "/api/guide", b"x" * 3000)[0], 413)
        self.assertEqual(call(self.port, "/api/guide", b"{}", ctype="text/plain")[0], 415)
        self.assertEqual(call(self.port, "/api/guide", b"not json")[0], 400)

    def test_healthz_and_noindex(self):
        code, body, h = call(self.port, "/healthz", host="anything.example")
        self.assertEqual((code, json.loads(body)), (200, {"ok": True}))
        self.assertIn("noindex", h["X-Robots-Tag"])
        self.assertIn(b"Disallow: /", call(self.port, "/robots.txt")[1])

    def test_public_host_rules(self):
        old = server.PUBLIC
        try:
            server.PUBLIC = True
            self.assertEqual(call(self.port, "/", host="jma-navigator.onrender.com")[0], 200)
            self.assertEqual(call(self.port, "/", host="evil.example")[0], 403)
            self.assertEqual(call(self.port, "/", host="onrender.com.evil.example")[0], 403)
        finally:
            server.PUBLIC = old
        self.assertEqual(call(self.port, "/", host="jma-navigator.onrender.com")[0], 403)  # 非公開時は不可

    def test_foreign_host_rejected(self):
        self.assertEqual(call(self.port, "/", host="evil.example")[0], 403)

    def test_no_path_traversal(self):
        self.assertEqual(call(self.port, "/../server.py")[0], 404)
        self.assertEqual(call(self.port, "/%2e%2e/server.py")[0], 404)

    def test_shortcuts_are_jma_only(self):
        items = json.loads(call(self.port, "/api/shortcuts")[1])
        self.assertGreater(len(items), 5)
        self.assertTrue(all(i["url"].startswith(server.ALLOWED_HOSTS) for i in items))


class RateLimiterTest(unittest.TestCase):
    def test_limit_and_window(self):
        rl = server.RateLimiter(limit=3, window=60)
        self.assertTrue(all(rl.allow("a", now=t) for t in (0, 1, 2)))
        self.assertFalse(rl.allow("a", now=3))
        self.assertTrue(rl.allow("b", now=3))      # 別IPは別枠
        self.assertTrue(rl.allow("a", now=61))     # 窓が過ぎたら再び許可

    def test_memory_bounded(self):
        rl = server.RateLimiter(limit=1, window=10, max_ips=5)
        for i in range(50):
            rl.allow(f"ip{i}", now=100 + i)
        self.assertLessEqual(len(rl.hits), 6)


if __name__ == "__main__":
    unittest.main()
