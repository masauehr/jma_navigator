"""気象庁ナビのローカルWebサーバー。標準ライブラリのみ。

画面(web/)を配り、POST /api/guide で質問→ガイド結果(JSON)を返す。
- 127.0.0.1 にだけ待ち受ける(外部からは届かない)。
- LLM版を使う場合も呼び出しはこのサーバー側で行う。画面側にキーや認証情報は置かない。
使い方: python3 server.py [--port 8765] [--llm]
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jnav.navigate import build_url, guide, load_catalog

WEB = Path(__file__).resolve().parent / "web"
MAX_BODY = 2048
MAX_QUESTION = 200
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8"}
# 画面に出す前に、リンク先が気象庁のドメインか確認する(サーバー側でも念のため)
ALLOWED_HOSTS = ("https://www.jma.go.jp/", "https://www.data.jma.go.jp/")

USE_LLM = False


def run_guide(question, pick=None):
    """pick は聞き返しの候補ボタンで選ばれた {"office_code":..} か {"amdno":..}。
    元の質問を解き直し、返ってきた候補に含まれる値だけを受け付けてURLを組み立てる。"""
    if USE_LLM:
        from jnav.llm import guide_llm
        result = guide_llm(question)
    else:
        result = guide(question)
    if pick and result.get("status") == "need_place":
        result = apply_pick(question, result, pick)
    url = result.get("url")
    if url and not url.startswith(ALLOWED_HOSTS):  # カタログ由来なので通常は起きない
        result = {"status": "no_match", "question": question}
    return result


def apply_pick(question, result, pick):
    key = next((k for k in ("office_code", "amdno") if k in pick), None)
    chosen = next((c for c in result.get("candidates", []) if key and c.get(key) == pick[key]), None)
    item = next((i for i in load_catalog() if i["id"] == result.get("item")), None)
    if not chosen or not item:
        return result
    url, missing = build_url(item, {key: chosen[key]})
    if missing:  # 年月などが足りない項目は、ここでは確定しない
        return result
    return {"item": item["id"], "title": item["title"], "category": item["category"],
            "status": "ok", "url": url, "verified": item["verified"],
            "place": chosen.get("office_name") or chosen.get("place")}


def shortcuts():
    """地域指定のいらない固定ページ(static)を、カテゴリ順の一覧にして返す。"""
    return [{"id": i["id"], "title": i["title"], "category": i["category"], "url": i["url"]}
            for i in load_catalog() if i["static"] and i["url"].startswith(ALLOWED_HOSTS)]


class Handler(BaseHTTPRequestHandler):
    server_version = "jnav"

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        # 外部リソースを読まない・インラインスクリプトを実行しない
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        # DNSリバインディング対策: Hostがローカルのものだけ受け付ける
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden"})
        path = self.path.split("?", 1)[0]
        if path == "/api/shortcuts":
            return self._send(200, shortcuts())
        name = "index.html" if path == "/" else path.lstrip("/")
        f = (WEB / name).resolve()
        if WEB.resolve() not in f.parents or not f.is_file() or f.suffix not in TYPES:
            return self._send(404, {"error": "not found"})
        self._send(200, f.read_bytes(), TYPES[f.suffix])

    def do_POST(self):
        if not self._host_ok() or self.path != "/api/guide":
            return self._send(403 if not self._host_ok() else 404, {"error": "not found"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(415, {"error": "json only"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= MAX_BODY:
                return self._send(413, {"error": "too large"})
            body = json.loads(self.rfile.read(n))
            question = str(body.get("question", "")).strip()
            pick = body.get("pick") if isinstance(body.get("pick"), dict) else None
        except (ValueError, AttributeError):
            return self._send(400, {"error": "bad request"})
        if not question or len(question) > MAX_QUESTION:
            return self._send(400, {"error": f"質問は1〜{MAX_QUESTION}文字で入力してください"})
        self._send(200, run_guide(question, pick))

    def log_message(self, fmt, *args):  # 質問文をログに残さない
        pass


def main():
    global USE_LLM
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--llm", action="store_true", help="項目選択にLLM(Claude Code CLI経由)を使う")
    args = ap.parse_args()
    USE_LLM = args.llm
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"http://127.0.0.1:{args.port}/ (LLM={'on' if USE_LLM else 'off'}) Ctrl+Cで終了")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
