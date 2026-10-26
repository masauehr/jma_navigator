"""過去データ検索(etrn)用の観測所辞書。標準ライブラリのみ。

対象は気象官署(daily_s1.php で開ける地点)。アメダス専用地点の block_no は未整備。
prec_no は観測所番号(obs_id)の先頭2桁から作った推定値で、verified=true の地点だけ
実際にページが開くことを確認済み(例: 石垣島は obs_id 先頭が94だが実際は91)。
"""
import json
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data" / "etrn_stations.json"
_cache = None


def _load():
    global _cache
    if _cache is None:
        _cache = json.loads(_DATA.read_text(encoding="utf-8"))
    return _cache


def find_station(question):
    """質問文に含まれる気象官署名を探す（長い名前を優先）。見つからなければ None。"""
    best = None
    for st in _load():
        if st["name"] in question and (best is None or len(st["name"]) > len(best["name"])):
            best = st
    return best
