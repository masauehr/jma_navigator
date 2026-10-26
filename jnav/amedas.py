"""アメダス観測所の検索。データは data/amedas_stations.json（地域気象観測所一覧PDF由来）。

観測所番号(amdno)5桁だけで bosai/amedas のページが開く。標準ライブラリのみ。
"""
import json
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data" / "amedas_stations.json"
_cache = None


def _load():
    global _cache
    if _cache is None:
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
        # 積雪専用(雪)の地点は、同名・同管内に気温などを観測する地点があれば除く
        keep = {(s["name"], s["subprefecture"]) for s in raw if s["kind"] != "雪"}
        _cache = [s for s in raw if s["kind"] != "雪" or (s["name"], s["subprefecture"]) not in keep]
    return _cache


def find_stations(question):
    """質問文に含まれる観測所名で最も長く一致するものを全て返す（同名の別地点も含む）。"""
    best_len, found = 0, []
    for s in _load():
        n = len(s["name"])
        if n >= 2 and s["name"] in question:
            if n > best_len:
                best_len, found = n, [s]
            elif n == best_len:
                found.append(s)
    return found
