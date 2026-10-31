"""地域名 → 気象庁の地域コード(office_code)の解決。標準ライブラリのみ。

データは data/area.json（気象庁 /bosai/common/const/area.json の写し）。
階層: centers → offices(府県予報区) → class10s(一次細分) → class15s → class20s(市町村)。
LLMに推測させず、ここで決定論的に候補を出す。候補が複数なら呼び出し側が聞き返す。
"""
import json
import re
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data" / "area.json"
_SUFFIX = re.compile(r"(市|町|村|区|県|府|都|地方)$")

_cache = None


def _load():
    global _cache
    if _cache is None:
        _cache = json.loads(_DATA.read_text(encoding="utf-8"))
    return _cache


def _office_of(area, level, code):
    """class20s/class15s/class10s のコードから所属する office のコードを返す。"""
    while level != "offices":
        parent = area[level][code]["parent"]
        level = {"class20s": "class15s", "class15s": "class10s", "class10s": "offices"}[level]
        code = parent
    return code


def _norm(s):
    return s.strip().replace("　", "").replace(" ", "")


def resolve(query):
    """地名から候補のリストを返す。

    戻り値: [{"office_code","office_name","place","level","score"}]（score降順・重複除去）
    候補が1件なら確定、複数なら聞き返し対象。
    """
    q = _norm(query)
    if not q:
        return []
    area = _load()
    found = {}

    def add(level, code, entry, score):
        office = _office_of(area, level, code)
        key = (office, entry["name"])
        if key not in found or found[key]["score"] < score:
            found[key] = {
                "office_code": office,
                "office_name": area["offices"][office]["name"],
                "place": entry["name"],
                "code": code,
                "level": level,
                "score": score,
            }

    # 「北海道」は予報区が複数に分かれ名前に含まれないため、コード先頭01の全予報区を候補にする
    if q in ("北海道", "道内"):
        for code, e in area["offices"].items():
            if code.startswith("01"):
                add("offices", code, e, 100)

    for level in ("class20s", "class15s", "class10s", "offices"):
        for code, e in area[level].items():
            name = e["name"]
            kana = e.get("kana", "")
            stem = _SUFFIX.sub("", name)
            if q == name:
                score = 100
            elif q == stem and len(stem) >= 2:
                score = 90
            elif name.startswith(q) and name[len(q):len(q) + 1] in ("市", "町", "村", "区") and len(q) >= 2:
                score = 90  # 「伊達」→「伊達市伊達」のように、市町村名+旧町名の形
            elif q.endswith("市") and len(q) >= 3 and name.startswith(q):
                score = 90  # 「横浜市」→「横浜市北部」のように、市が地区に分割された形
            elif kana and q == kana:
                score = 80
            elif kana and len(q) >= 2 and kana.startswith(q) and re.fullmatch(r"[ぁ-ん]+", q):
                score = 60
            elif len(q) >= 2 and q in name:
                score = 50
            else:
                continue
            add(level, code, e, score)
    return sorted(found.values(), key=lambda r: -r["score"])


def pick(query):
    """確定できれば1件、できなければ None（聞き返し用に resolve を使う）。

    最高スコアの候補が、同じ office に属するものだけなら確定とみなす。
    """
    cands = resolve(query)
    if not cands:
        return None
    top = cands[0]["score"]
    offices = {c["office_code"] for c in cands if c["score"] == top}
    if len(offices) == 1:
        return next(c for c in cands if c["score"] == top)
    return None


def center_of(office_code):
    """予報区コード → (地方コード, 地方名)。例: 471000 → ("011100", "沖縄地方")。"""
    area = _load()
    code = area["offices"][office_code]["parent"]
    return code, area["centers"][code]["name"]


def find_centers(question):
    """質問に地方名（「東北地方」など。括弧書きは除く）が書かれていれば [(コード, 名前)] を返す。"""
    out = []
    for code, e in _load()["centers"].items():
        base = e["name"].split("（")[0]
        if base in question:
            out.append((code, e["name"]))
    return out


def all_centers():
    return [(code, e["name"]) for code, e in _load()["centers"].items()]


def center_name(code):
    return _load()["centers"][code]["name"]
