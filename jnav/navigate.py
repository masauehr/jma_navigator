"""質問文 → ガイド結果（カタログ項目の選択・地名解決・URL組み立て）。標準ライブラリのみ。

Phase1のベースライン: LLMなし（キーワード照合）。LLM版との比較用に残す。
URLは必ずカタログのテンプレートから組み立て、自由記述では作らない。
"""
import json
import re
from datetime import date
from pathlib import Path

from .amedas import find_stations, nearest, wanted_element
from .areas import resolve
from .stations import find_station

_CATALOG = Path(__file__).resolve().parent.parent / "catalog.json"


def load_catalog():
    return json.loads(_CATALOG.read_text(encoding="utf-8"))["items"]


def select_item(question, items=None):
    """意図キーワード（intents/title）の一致の長さで最良の項目を返す。なければ None。"""
    items = items or load_catalog()
    best, best_score = None, 0
    for it in items:
        score = 0
        for kw in it["intents"] + [it["title"]]:
            if kw in question:
                score += len(kw)
        if score > best_score:
            best, best_score = it, score
    return best


def extract_place(question):
    """質問文中の部分文字列から地名を探す。見つかった候補リストを返す（曖昧なら複数 office）。"""
    best = []
    best_len = 0
    for n in range(6, 1, -1):
        for i in range(len(question) - n + 1):
            frag = question[i:i + n]
            if not re.search(r"[一-龥ぁ-んァ-ヶ]", frag):
                continue
            cands = [c for c in resolve(frag) if c["score"] >= 80]
            if cands and n > best_len:
                best, best_len = cands, n
        if best:
            break
    return best


def parse_year_month(question, today=None):
    """「去年の8月」「2025年3月」「先月」「今月」などから (year, month) を返す。分からない要素は None。"""
    today = today or date.today()
    year = month = None
    m = re.search(r"(\d{4})年", question)
    if m:
        year = int(m.group(1))
    elif "一昨年" in question:
        year = today.year - 2
    elif "去年" in question or "昨年" in question:
        year = today.year - 1
    elif "今年" in question:
        year = today.year
    m = re.search(r"(\d{1,2})月", question)
    if m and 1 <= int(m.group(1)) <= 12:
        month = int(m.group(1))
    elif "先月" in question:
        month = today.month - 1 or 12
        year = year or (today.year if today.month > 1 else today.year - 1)
    elif "今月" in question:
        month = today.month
        year = year or today.year
    if month and year is None:
        year = today.year if month <= today.month else today.year - 1
    return year, month


def build_url(item, values):
    """テンプレートへ値を埋める。足りない params があれば missing に返す。"""
    missing = [k for k, spec in item["params"].items()
               if not spec.get("optional") and k not in values]
    if missing:
        return None, missing
    url = item["url"]
    for k in item["params"]:
        url = url.replace("{" + k + "}", str(values.get(k, "")))
    return url, []


def guide(question, item_id=None, place_text=None):
    """質問に対するガイド結果を辞書で返す。status: ok / need_place / need_more / no_match

    item_id / place_text を渡すと、項目選択・地名抽出をその値で置き換える（LLM版が使う）。
    項目の選択以外（地域解決・URL組み立て）は常に決定論的で、LLMはURLを作らない。
    """
    if item_id is not None:
        item = next((i for i in load_catalog() if i["id"] == item_id), None)
    else:
        item = select_item(question)
    if item is None:
        return {"status": "no_match", "question": question}
    place_q = place_text or question
    result = {"item": item["id"], "title": item["title"], "category": item["category"]}
    values = {}
    if "office_code" in item["params"]:
        cands = extract_place(place_q)
        offices = {c["office_code"] for c in cands}
        if len(offices) != 1:
            return {**result, "status": "need_place", "candidates": [
                {"office_code": c["office_code"], "office_name": c["office_name"], "place": c["place"]}
                for c in cands[:6]]}
        values["office_code"] = cands[0]["office_code"]
        result["place"] = f'{cands[0]["office_name"]}'
    if "amdno" in item["params"]:
        sts = find_stations(place_q)
        if not sts:
            return {**result, "status": "need_place", "hint": "アメダス観測所名（例: 石垣島、伊是名）が必要です"}
        if len(sts) > 1:
            return {**result, "status": "need_place", "candidates": [
                {"amdno": x["amdno"], "place": x["name"], "area": x["subprefecture"]} for x in sts[:6]]}
        values["amdno"] = sts[0]["amdno"]
        result["place"] = sts[0]["name"]
        elem = wanted_element(question)
        if elem and elem not in sts[0]["observes"]:
            near = nearest(sts[0]["lat"], sts[0]["lon"], 1, need=elem)
            hint = f'{sts[0]["name"]}は{elem}を観測していません。'
            if near:
                hint += f'最寄りで観測する地点は{near[0][1]["name"]}（約{near[0][0]}km）です。'
            result["note"] = hint
    if "prec_no" in item["params"]:
        st = find_station(place_q)
        if st is None:
            return {**result, "status": "need_place", "hint": "気象官署の地点名（例: 那覇、東京）が必要です。アメダス地点は未対応"}
        year, month = parse_year_month(question)
        values.update(prec_no=st["prec_no"], block_no=st["block_no"])
        if year and month:
            values.update(year=year, month=month)
        result["place"] = st["name"]
        if not st["verified"]:
            result["note"] = "prec_noは推定値です。開けない場合は気象庁の地点選択ページから選んでください"
    url, missing = build_url(item, values)
    if missing:
        return {**result, "status": "need_more", "missing": missing}
    return {**result, "status": "ok", "url": url, "verified": item["verified"]}
