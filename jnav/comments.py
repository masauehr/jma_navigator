"""気象台からのコメントの取得。標準ライブラリのみ。

出どころ: https://www.jma.go.jp/bosai/forecaster_comment/data/comments/{予報区コード}.txt
（気象庁の「あなたの街の防災情報」の「気象台からのコメント」と同じデータ。HTMLの断片で、発表日時と本文が入っている）

方針:
- 予報官の文章は要約・言い換えをせず、全文をそのまま文字として返す（HTMLは文字に変換。画面にHTMLは埋め込まない）。
- URLは、area.json の予報区コードに一致したものからだけ組み立てる（任意のURLは取得しない）。
- 気象庁への負荷を抑えるため、予報区ごとに数分キャッシュする。取得できなければ None。
- 発表から時間が経ったものは stale を立てて、画面で「最新ではない可能性」を示す。
"""
import datetime
import re
import threading
import time
import urllib.request
from html.parser import HTMLParser

from .areas import _load

BASE = "https://www.jma.go.jp/bosai/forecaster_comment/data/comments/"
UA = "jma_navigator/1.0 (+https://github.com/masauehr/jma_navigator; personal, cached)"
TTL = 300          # 成功した取得を使い回す秒数
FAIL_TTL = 30      # 失敗を使い回す秒数（連続アクセスで気象庁に負荷をかけない）
MAX_BYTES = 200_000
TIMEOUT = 8
STALE_HOURS = 12   # これを超えて古いときは注意を出す
JST = datetime.timezone(datetime.timedelta(hours=9))

_cache = {}
_lock = threading.Lock()
MAX_CACHE = 100


class _Text(HTMLParser):
    """HTML断片 → 文字。改行は br / p / div で入れる。script・style は捨てる。"""

    BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.pub, self._skip, self._in_pub = [], [], 0, False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "title"):
            self._skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag in self.BLOCK:
            self.parts.append("\n")
            if tag == "div" and "ycomment_pub_date" in (dict(attrs).get("class") or ""):
                self._in_pub = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "title"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")
            if tag == "div":
                self._in_pub = False

    def handle_data(self, data):
        if self._skip:
            return
        (self.pub if self._in_pub else self.parts).append(data)


def parse(raw_html):
    """HTML断片 → (発表日時の文字列, 本文)。本文の空行は最大1行に詰める。"""
    p = _Text()
    p.feed(raw_html)
    p.close()
    text = "".join(p.parts)
    text = re.sub(r"[ \t　]+\n", "\n", text)       # 行末の空白
    text = re.sub(r"\n{3,}", "\n\n", text).strip()      # 連続する空行
    return "".join(p.pub).strip(), text


def published_at(pub):
    """「2026年10月30日(金)11時28分」→ datetime(JST)。読めなければ None。"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2})時(\d{1,2})分", pub or "")
    if not m:
        return None
    y, mo, d, h, mi = map(int, m.groups())
    try:
        return datetime.datetime(y, mo, d, h, mi, tzinfo=JST)
    except ValueError:
        return None


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if not r.geturl().startswith(BASE):  # 別の場所に飛ばされたら使わない
            return None
        return r.read(MAX_BYTES + 1)


def get(office_code, fetcher=_fetch, now=None, clock=time.monotonic):
    """予報区の気象台コメントを返す。取得できなければ None。

    戻り値: {"office_code","office_name","published","text","age_hours","stale"}
    """
    offices = _load()["offices"]
    if office_code not in offices:  # URLの組み立てに使うのは、辞書にある予報区コードだけ
        return None
    t = clock()
    with _lock:
        hit = _cache.get(office_code)
        if hit and t - hit[0] < (TTL if hit[1] else FAIL_TTL):
            return hit[1]
    result = None
    try:
        raw = fetcher(f"{BASE}{office_code}.txt")
        if raw and len(raw) <= MAX_BYTES:
            pub, text = parse(raw.decode("utf-8", "replace"))
            if text:
                dt = published_at(pub)
                now = now or datetime.datetime.now(JST)
                age = round((now - dt).total_seconds() / 3600, 1) if dt else None
                result = {"office_code": office_code, "office_name": offices[office_code].get("officeName", ""),
                          "published": pub, "text": text, "age_hours": age,
                          "stale": age is None or age > STALE_HOURS}
    except Exception:  # 通信失敗・404・文字化けなど。画面では「取得できませんでした」と案内する
        result = None
    with _lock:
        if len(_cache) >= MAX_CACHE:
            _cache.clear()
        _cache[office_code] = (t, result)
    return result


def clear_cache():
    with _lock:
        _cache.clear()
