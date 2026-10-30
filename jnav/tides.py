"""潮位観測所の解決。標準ライブラリのみ。

データは data/tide_stations.json（気象庁 /bosai/tidelevel/const/tide_area.json から作成。166局）。
観測所は「市町村(class20)→沿岸区分(class30)→観測所」の階層で、URLには area_code(市町村)・point_code(観測所)・
class30s(沿岸区分)の3つが要る。地名から観測所を決め、決められないときは同じ予報区の観測所を候補にする。
"""
import json
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data" / "tide_stations.json"
_cache = None
MAX_CANDIDATES = 8


def _load():
    global _cache
    if _cache is None:
        _cache = json.loads(_DATA.read_text(encoding="utf-8"))
    return _cache


def _candidate(st, office_name=""):
    """画面の候補ボタン用の辞書。station_code などは URL の組み立てにそのまま使う。"""
    label = st["name"] + (f"（{st['type']}）" if st["type"] and st["type"] != "気象庁" else "")
    return {"station_code": st["code"], "place": label, "area_code": st["area_code"],
            "class30_code": st["class30"], "office_code": st["office_code"], "office_name": office_name,
            "area": st["area_name"]}


def find(question, city_codes=(), office_code=None, office_name=""):
    """観測所を探す。戻り値: (確定した観測所 or None, 候補のリスト)。

    1. 質問に観測所名が書かれていれば、それ(長い名前を優先)。
    2. 質問の市町村に観測所があれば、その観測所。
    3. なければ、同じ予報区の観測所を候補として返す（確定しない）。
    """
    stations = _load()
    named = [s for s in stations if len(s["name"]) >= 2 and s["name"] in question]
    if named:
        best = max(len(s["name"]) for s in named)
        named = [s for s in named if len(s["name"]) == best]
        if len(named) == 1:
            return named[0], []
        return None, [_candidate(s, office_name) for s in named[:MAX_CANDIDATES]]
    in_city = [s for s in stations if s["area_code"] in set(city_codes)]
    if len(in_city) == 1:
        return in_city[0], []
    pool = in_city or ([s for s in stations if s["office_code"] == office_code] if office_code else [])
    return None, [_candidate(s, office_name) for s in pool[:MAX_CANDIDATES]]
