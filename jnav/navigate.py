"""質問文 → ガイド結果（カタログ項目の選択・地名解決・URL組み立て）。標準ライブラリのみ。

Phase1のベースライン: LLMなし（キーワード照合）。LLM版との比較用に残す。
URLは必ずカタログのテンプレートから組み立て、自由記述では作らない。
"""
import json
import re
from pathlib import Path

from .areas import resolve

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


def guide(question):
    """質問に対するガイド結果を辞書で返す。status: ok / need_place / need_more / no_match"""
    item = select_item(question)
    if item is None:
        return {"status": "no_match", "question": question}
    result = {"item": item["id"], "title": item["title"], "category": item["category"]}
    values = {}
    if "office_code" in item["params"]:
        cands = extract_place(question)
        offices = {c["office_code"] for c in cands}
        if len(offices) != 1:
            return {**result, "status": "need_place", "candidates": [
                {"office_code": c["office_code"], "office_name": c["office_name"], "place": c["place"]}
                for c in cands[:6]]}
        values["office_code"] = cands[0]["office_code"]
        result["place"] = f'{cands[0]["office_name"]}'
    url, missing = build_url(item, values)
    if missing:
        return {**result, "status": "need_more", "missing": missing}
    return {**result, "status": "ok", "url": url, "verified": item["verified"]}
