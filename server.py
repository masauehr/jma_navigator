"""気象庁ナビのローカルWebサーバー。標準ライブラリのみ。

画面(web/)を配り、POST /api/guide で質問→ガイド結果(JSON)を返す。
- 127.0.0.1 にだけ待ち受ける(外部からは届かない)。
- LLM版を使う場合も呼び出しはこのサーバー側で行う。画面側にキーや認証情報は置かない。
使い方: python3 server.py [--port 8765] [--llm]

公開モード(環境変数 JNAV_PUBLIC=1。Renderで使う):
- 0.0.0.0 で PORT 環境変数のポートを待ち受ける。LLM版は常に無効(サブスク枠・乱用対策)。
- Host は 127.0.0.1/localhost に加え、*.onrender.com と JNAV_ALLOWED_HOSTS(カンマ区切り)を許可。
- 検索エンジンに載せない(robots.txt・noindex)。URLを知っている人向け。
"""
import argparse
import collections
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jnav.navigate import build_url, load_catalog
from jnav.suggest import suggest

WEB = Path(__file__).resolve().parent / "web"
MAX_BODY = 2048
MAX_QUESTION = 200
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".txt": "text/plain; charset=utf-8"}
PUBLIC = os.environ.get("JNAV_PUBLIC") == "1"
EXTRA_HOSTS = tuple(h.strip() for h in os.environ.get("JNAV_ALLOWED_HOSTS", "").split(",") if h.strip())
RATE_LIMIT = 30      # 1分あたりの /api/guide の回数(IPごと)
RATE_WINDOW = 60

# 画面に出す前に、リンク先が気象庁のドメインか確認する(サーバー側でも念のため)
ALLOWED_HOSTS = ("https://www.jma.go.jp/", "https://www.data.jma.go.jp/")

USE_LLM = False


class RateLimiter:
    """IPごとの単純なスライディングウィンドウ。メモリ上のみ(再起動で消える)。"""

    def __init__(self, limit=RATE_LIMIT, window=RATE_WINDOW, max_ips=10000):
        self.limit, self.window, self.max_ips = limit, window, max_ips
        self.hits = {}
        self.lock = threading.Lock()

    def allow(self, ip, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            if len(self.hits) >= self.max_ips:  # 溜まりすぎたら古いIPを掃除
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < self.window}
                while len(self.hits) >= self.max_ips:  # それでも多ければ古い順に捨てる(上限を必ず守る)
                    self.hits.pop(next(iter(self.hits)))
            q = self.hits.setdefault(ip, collections.deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


LIMITER = RateLimiter()


def run_guide(question, pick=None, refine=None, exclude=()):
    """pick は聞き返しの候補ボタンで選ばれた {"office_code":..} か {"amdno":..}。
    refine は「違う」のあとの絞り込み {"when":..,"topic":..}、exclude は却下したページの項目ID。
    元の質問を解き直し、返ってきた候補に含まれる値だけを受け付けてURLを組み立てる。"""
    result = suggest(question, refine=refine, exclude=exclude)
    if USE_LLM:  # LLMは本命の項目選択だけを差し替える(次点以下はキーワード版のまま)
        from jnav.llm import guide_llm
        llm = guide_llm(question)
        if llm.get("status") != "no_match":
            llm["alternatives"] = [a for a in result.get("alternatives", []) if a["item"] != llm.get("item")]
            llm["choices"] = result.get("choices")
            result = llm
    if pick and result.get("status") == "need_place":
        alts, choices = result.get("alternatives"), result.get("choices")
        result = apply_pick(question, result, pick)
        if alts is not None and "alternatives" not in result:
            result["alternatives"], result["choices"] = alts, choices
    url = result.get("url")
    if url and not url.startswith(ALLOWED_HOSTS):  # カタログ由来なので通常は起きない
        result = {"status": "no_match", "question": question}
    for a in result.get("alternatives", []):
        if a.get("url") and not a["url"].startswith(ALLOWED_HOSTS):
            a.pop("url")
            a["status"] = "need_place"
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
    timeout = 10  # 遅い接続でスレッドを占有されないようにする

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        if PUBLIC:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        # 外部リソースを読まない・インラインスクリプトを実行しない
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        # DNSリバインディング対策: 許可したHostだけ受け付ける
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        if host in ("127.0.0.1", "localhost") or host in EXTRA_HOSTS:
            return True
        return PUBLIC and host.endswith(".onrender.com")

    def _client_ip(self):
        # 公開時はRenderのプロキシが付けたX-Forwarded-Forの末尾(最も信頼できる値)を使う
        if PUBLIC:
            xff = self.headers.get("X-Forwarded-For", "")
            if xff:
                return xff.split(",")[-1].strip()
        return self.client_address[0]

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":  # Renderのヘルスチェック用(Host検査の対象外)
            return self._send(200, {"ok": True})
        if not self._host_ok():
            return self._send(403, {"error": "forbidden"})
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
        if not LIMITER.allow(self._client_ip()):
            self.send_response(429)
            self.send_header("Retry-After", str(RATE_WINDOW))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(415, {"error": "json only"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= MAX_BODY:
                return self._send(413, {"error": "too large"})
            body = json.loads(self.rfile.read(n))
            question = str(body.get("question", "")).strip()
            pick = body.get("pick") if isinstance(body.get("pick"), dict) else None
            refine = body.get("refine") if isinstance(body.get("refine"), dict) else None
            exclude = [str(x) for x in body.get("exclude", [])][:10] if isinstance(body.get("exclude"), list) else []
            if refine:  # 許可した語彙だけ受け付ける
                refine = {k: v for k, v in refine.items() if k in ("when", "topic") and isinstance(v, str) and len(v) < 20}
        except (ValueError, AttributeError):
            return self._send(400, {"error": "bad request"})
        if not question or len(question) > MAX_QUESTION:
            return self._send(400, {"error": f"質問は1〜{MAX_QUESTION}文字で入力してください"})
        self._send(200, run_guide(question, pick, refine, exclude))

    def log_message(self, fmt, *args):  # 質問文をログに残さない
        pass


def main():
    global USE_LLM
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)))
    ap.add_argument("--llm", action="store_true", help="項目選択にLLM(Claude Code CLI経由)を使う(公開モードでは無効)")
    args = ap.parse_args()
    USE_LLM = args.llm and not PUBLIC
    bind = "0.0.0.0" if PUBLIC else "127.0.0.1"
    srv = ThreadingHTTPServer((bind, args.port), Handler)
    print(f"http://{bind}:{args.port}/ (public={PUBLIC}, LLM={'on' if USE_LLM else 'off'}) Ctrl+Cで終了", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
