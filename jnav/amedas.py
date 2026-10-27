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
        # アメダス画面(amedastable.json)に載っている地点だけを使う。
        # 積雪の深さ用の観測所（種類が雪・番号下3桁900以上）は載っておらず、リンクが開けない
        _cache = [x for x in raw if x.get("in_viewer")]
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


# 質問文の語 → 観測要素。その要素を観測しない地点なら案内に注意を付ける
MEASURES = [("気温", "気温"), ("何度", "気温"), ("風", "風"), ("降水", "降水量"), ("雨", "降水量"),
            ("日照", "日照"), ("湿度", "湿度"), ("気圧", "気圧")]


def wanted_element(question):
    for kw, elem in MEASURES:
        if kw in question:
            return elem
    return None


def nearest(lat, lon, n=3, need=None):
    """緯度経度に近い観測所をn件返す（近い順）。need に観測要素名を渡すと、それを観測する地点に限る。

    距離は緯度経度の簡易計算（km）。戻り値: [(距離km, 観測所), ...]
    """
    import math
    out = []
    for st in _load():
        if need and need not in st.get("observes", []):
            continue
        dy = (st["lat"] - lat) * 111.0
        dx = (st["lon"] - lon) * 111.0 * math.cos(math.radians(lat))
        out.append((round(math.hypot(dx, dy), 1), st))
    out.sort(key=lambda x: x[0])
    return out[:n]
