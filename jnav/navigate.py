"""質問文 → ガイド結果（カタログ項目の選択・地名解決・URL組み立て）。標準ライブラリのみ。

Phase1のベースライン: LLMなし（キーワード照合）。LLM版との比較用に残す。
URLは必ずカタログのテンプレートから組み立て、自由記述では作らない。
"""
import json
import re
from datetime import date
from pathlib import Path

from .amedas import find_stations, nearest, wanted_element
from .areas import all_centers, center_of, find_centers, resolve
from .stations import find_station
from . import tides

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
    """質問文中の部分文字列から地名を探し、候補のリストを返す（曖昧なら複数 office）。

    - 1つの予報区に決まる語（「東京」「札幌」）があれば、それを優先する。
      「東京の府中市」「北海道の札幌」のように、広い語や同名の語が混じっても絞り込める。
    - 決まる語が複数の予報区に分かれる（「那覇と東京」）、または全て曖昧なら、聞き返し用に候補を返す。
    - ひらがなだけの語は、かなの前方一致（score 60）も認める（「おおさか」）。
    """
    def collect(min_score, min_len, kana_only):
        found = {}
        for n in range(6, min_len - 1, -1):
            for i in range(len(question) - n + 1):
                frag = question[i:i + n]
                if frag in found or not re.search(r"[一-龥ぁ-んァ-ヶ]", frag):
                    continue
                if kana_only and not re.fullmatch(r"[ぁ-ん]+", frag):
                    continue
                cands = [c for c in resolve(frag) if c["score"] >= min_score]
                if cands:
                    found[frag] = cands
        return found

    frags = collect(80, 2, False)
    if not frags:  # 見つからないときだけ、ひらがな3字以上のかな前方一致を試す（ノイズ防止）
        frags = collect(60, 3, True)
    if not frags:
        return []
    unique = {}
    for frag, cands in frags.items():
        offices = {c["office_code"] for c in cands}
        if len(offices) == 1:
            unique[next(iter(offices))] = cands
    if len(unique) == 1:
        return next(iter(unique.values()))
    if len(unique) > 1:
        return [c for cs in unique.values() for c in cs]  # 異なる地域が混在: 聞き返す
    longest = max(frags, key=len)
    return frags[longest]


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


SCOPE_LABEL = {"japan": "全国", "centers": "地方", "offices": "府県", "class20s": "市町村"}
SCOPES = tuple(SCOPE_LABEL)


def scopes_of(item):
    """項目が対応する地域の単位を [{"value","label"}] で返す（なければ空）。"""
    su = item.get("scope_urls") or {}
    return [{"value": k, "label": SCOPE_LABEL[k]} for k in SCOPES if k in su]


def build_scoped(item, scope, values):
    """地域の単位ごとのURLテンプレートに値を埋める。足りない値があれば (None, missing)。"""
    url = item["scope_urls"][scope]
    missing = [k for k in re.findall(r"\{(\w+)\}", url) if k not in values]
    if missing:
        return None, missing
    for k, v in values.items():
        url = url.replace("{" + k + "}", str(v))
    return url, []


def _cities(cands, min_score):
    """候補のうち市町村(class20s)を、コード重複なしで返す。"""
    seen, out = set(), []
    for c in cands:
        if c.get("level") == "class20s" and c["score"] >= min_score and c["code"] not in seen:
            seen.add(c["code"])
            out.append(c)
    return out


def _guide_scoped(item, result, place_q, scope):
    """全国・地方・府県・市町村のうち、選んだ（または地名から決めた）単位でURLを組み立てる。"""
    su = item["scope_urls"]
    scopes = scopes_of(item)
    cands = extract_place(place_q)
    offices = {c["office_code"] for c in cands}
    office = next(iter(offices)) if len(offices) == 1 else None
    # 質問に市町村名そのもの（「那覇市」）が書かれているか。略称（「那覇」「沖縄」）は別に扱う
    exact_cities = [c for c in _cities(cands, 90) if c["place"] in place_q] if office else []
    loose_cities = _cities(cands, 90) if office else []
    named_centers = find_centers(place_q)  # 「東北地方」のように地方名が書かれているか

    def ask(hint=None, candidates=None):
        r = {**result, "scopes": scopes, "status": "need_place", "scope": want}
        if candidates is not None:
            r["candidates"] = candidates
        if hint:
            r["hint"] = hint
        return r

    def office_candidates():
        return [{"office_code": c["office_code"], "office_name": c["office_name"], "place": c["place"]}
                for c in cands[:6]]

    def center_candidates(pool):
        return [{"center_code": code, "place": name, "office_name": ""} for code, name in pool]

    want = scope if scope in su else None
    if want is None:  # 地名の粒度から単位を決める
        if named_centers and "centers" in su:
            want = "centers"
        elif not cands:
            want = "japan" if "japan" in su else None
        elif office is None:
            return ask(candidates=office_candidates())
        elif exact_cities and "class20s" in su:
            want = "class20s"
        else:
            want = next((k for k in ("offices", "japan", "class20s") if k in su), None)
        if want is None:
            return ask(hint="地名（例: 那覇、東京）を入れてください")
    if want == "japan":
        values = {}
    elif want == "centers":
        if len(named_centers) > 1:
            return ask(candidates=center_candidates(named_centers))
        if named_centers:
            code, name = named_centers[0]
        elif office:
            code, name = center_of(office)
        elif cands:  # 地名が複数の予報区にまたがる: まず地域を決めてもらう
            return ask(candidates=office_candidates())
        else:
            return ask(candidates=center_candidates(all_centers()), hint="どの地方ですか？")
        values = {"center_code": code}
        result["place"] = name
    elif want == "offices":
        if office is None:
            return ask(candidates=office_candidates() if cands else None,
                       hint=None if cands else "府県・地方の名前（例: 沖縄、東京）を入れてください")
        values = {"office_code": office}
        result["place"] = cands[0]["office_name"]
        result["office_code"] = office
    else:  # class20s
        if office is None:
            return ask(candidates=office_candidates() if cands else None,
                       hint=None if cands else "市町村名（例: 那覇市）を入れてください")
        pool = exact_cities
        if len(pool) != 1:  # 略称や複数一致のときは、市町村を選んでもらう（黙って決めない）
            pool = exact_cities or loose_cities
            if not pool:
                return ask(hint="市町村名（例: 那覇市）を入れてください。府県の名前だけでは市町村を決められません")
            return ask(candidates=[{"office_code": office, "office_name": c["office_name"], "place": c["place"],
                                    "class20_code": c["code"]} for c in pool[:6]])
        values = {"office_code": office, "class20_code": pool[0]["code"]}
        result["office_code"] = office
        result["place"] = f'{pool[0]["office_name"]} {pool[0]["place"]}'
    url, missing = build_scoped(item, want, values)
    if missing:
        return {**result, "scopes": scopes, "status": "need_more", "missing": missing, "scope": want}
    return {**result, "scopes": scopes, "status": "ok", "url": url, "verified": item["verified"], "scope": want}


def _guide_tide(item, result, place_q):
    """潮位観測所: 観測所名→市町村→同じ予報区の順に決め、決まらなければ観測所を候補にする。"""
    cands = extract_place(place_q)
    offices = {c["office_code"] for c in cands}
    office = next(iter(offices)) if len(offices) == 1 else None
    office_name = cands[0]["office_name"] if office else ""
    city_codes = [c["code"] for c in _cities(cands, 90)] if office else []
    st, near = tides.find(place_q, city_codes, office, office_name)
    if st is None:
        if not near:
            return {**result, "status": "need_place",
                    "hint": "潮位観測所のある地名（例: 那覇、石垣、東京）を入れてください。全国166局を探せます"}
        return {**result, "status": "need_place", "candidates": near,
                "hint": "お住まいの市町村に観測所がないときは、近い観測所を選んでください"}
    url, missing = build_url(item, {"area_code": st["area_code"], "station_code": st["code"], "class30_code": st["class30"]})
    return {**result, "status": "ok", "url": url, "verified": item["verified"], "place": f'{st["name"]}（{st["area_name"]}）'}


def guide(question, item_id=None, place_text=None, scope=None):
    """質問に対するガイド結果を辞書で返す。status: ok / need_place / need_more / no_match

    item_id / place_text を渡すと、項目選択・地名抽出をその値で置き換える（LLM版が使う）。
    項目の選択以外（地域解決・URL組み立て）は常に決定論的で、LLMはURLを作らない。
    """
    if place_text:
        # LLMが取り出した地名で解決し、曖昧なときは質問全体（「東京の府中市」の県名など）で絞り直す
        r = _guide(question, item_id, place_text, scope)
        if r.get("status") == "need_place":
            r2 = _guide(question, item_id, None, scope)
            if r2.get("status") != "need_place":
                return r2
        return r
    return _guide(question, item_id, None, scope)


def _guide(question, item_id, place_text, scope=None):
    if item_id is not None:
        item = next((i for i in load_catalog() if i["id"] == item_id), None)
    else:
        item = select_item(question)
    if item is None:
        return {"status": "no_match", "question": question}
    place_q = place_text or question
    result = {"item": item["id"], "title": item["title"], "category": item["category"]}
    values = {}
    if item.get("scope_urls"):
        return _guide_scoped(item, result, place_text or question, scope)
    if "station_code" in item["params"]:
        return _guide_tide(item, result, place_text or question)
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
            narrowed = [x for x in sts if x["subprefecture"] in place_q]  # 「広島の府中」のような県名つき
            if len(narrowed) == 1:
                sts = narrowed
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
