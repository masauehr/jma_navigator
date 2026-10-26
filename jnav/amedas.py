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
        # 積雪の深さ用の観測所（種類が雪、または番号下3桁が900以上）は、
        # 同名・同管内に気温などを観測する地点があれば除く（同じ地名が二重に出るのを防ぐ）
        def is_snow(x):
            return x["kind"] == "雪" or int(x["amdno"][2:]) >= 900

        keep = {(x["name"], x["subprefecture"]) for x in raw if not is_snow(x)}
        _cache = [x for x in raw if not is_snow(x) or (x["name"], x["subprefecture"]) not in keep]
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
