"""あいまいな質問に、複数のページ候補と絞り込みの選択肢を返す。標準ライブラリのみ。

navigate.guide() は最良の1項目しか返さない。ここでは全項目に点数を付け、上位を候補として返す。
  点数 = 言い回しの一致(長さ) + 話題の一致 + 時間軸の一致 + 地域指定できるページへの加点
LLMは使わない。URLの組み立ては guide(item_id=...) に任せる(決定論的)。

利用者の「違う」は refine(時間軸・話題)と exclude(却下した項目)で表し、サーバーは何も覚えない。
"""
import re

from .navigate import extract_place, guide, load_catalog
from .amedas import find_stations

# 質問中の語 → 話題。カタログの tags と対応する
TOPICS = {
    "rain": ["雨", "大雨", "豪雨", "降水", "雨量", "線状降水帯", "ゲリラ"],
    "thunder": ["雷", "竜巻", "突風", "ひょう", "雹"],
    "wind": ["風", "強風", "暴風"],
    "typhoon": ["台風"],
    "quake": ["地震", "揺れ", "震度", "震源"],
    "tsunami": ["津波"],
    "tide": ["潮位", "潮", "高潮"],
    "temp": ["気温", "暑", "寒", "熱中症", "猛暑", "暖冬", "冷夏", "最高気温", "最低気温"],
    "snow": ["雪", "大雪", "積雪"],
    "weather": ["天気", "天候", "空模様"],
    "warning": ["警報", "注意報", "特別警報", "警戒"],
    "flood": ["洪水", "土砂", "浸水", "氾濫", "危険", "危ない", "あぶない"],
    "observe": ["観測", "アメダス"],
}
# 時間軸の語
WHEN = {
    "future": ["見通し", "これから", "今後", "明日", "明後日", "あした", "あさって", "週間", "来週", "予報",
               "数日", "いつまで", "今年の冬", "今年の夏", "来月", "長期", "季節"],
    "now": ["今", "現在", "いま", "実況", "さっき", "リアルタイム", "今すぐ"],
    "past": ["去年", "昨年", "過去", "先月", "昨日", "記録", "歴代", "統計", "平年", "何年"],
}
TOPIC_LABEL = {"rain": "雨", "typhoon": "台風", "quake": "地震", "tsunami": "津波", "temp": "気温・暑さ寒さ",
               "wind": "風", "snow": "雪", "weather": "天気全般", "warning": "警報・注意報"}
WHEN_LABEL = {"now": "今の状況", "future": "これからの見通し", "past": "過去の記録"}

W_TOPIC, W_WHEN, W_REGION = 4, 3, 2
W_REFINE = 8  # 利用者が「違う」のあとに明示した絞り込みは、言い回しの推測より強く効かせる
MIN_SCORE = 2


def _hits(question, table):
    return {k for k, words in table.items() if any(w in question for w in words)}


def _when_hits(question):
    # 「今年の冬」「今月」「今週」の「今」は、いま(now)ではなくこれから(future)の意味で使われる
    return _hits(re.sub(r"今(年|月|週)", "", question), WHEN) | _hits(question, {"future": ["今年の冬", "今年の夏", "今週", "今月"]})


def _place_kind(question):
    """質問に地名があるか。'office'(予報区が決まる) / 'amedas'(観測所) / None。"""
    offices = {c["office_code"] for c in extract_place(question)}
    if len(offices) == 1:
        return "office"
    return "amedas" if find_stations(question) else None


def _reason(item, q_topics, q_when, matched_kw, region_ok):
    parts = []
    if matched_kw:
        parts.append(f"「{matched_kw}」に一致")
    t = [TOPIC_LABEL.get(x, x) for x in q_topics & set(item.get("tags", []))]
    if t:
        parts.append("話題: " + "・".join(t))
    w = [WHEN_LABEL[x] for x in q_when & set(item.get("when", []))]
    if w:
        parts.append("見たい内容: " + "・".join(w))
    if region_ok:
        parts.append("指定の地域で開けます")
    return " / ".join(parts) or "関連するページです"


def rank(question, refine=None, exclude=(), items=None):
    """(点数, 項目, 理由) のリストを点数降順で返す。点数が基準未満の項目は含めない。"""
    items = items or load_catalog()
    refine = refine or {}
    q_topics = _hits(question, TOPICS)
    q_when = _when_hits(question)
    place = _place_kind(question)
    out = []
    for it in items:
        if it["id"] in exclude:
            continue
        kws = [kw for kw in it["intents"] + [it["title"]] if kw in question]
        matched = max(kws, key=len, default="")
        score = sum(len(kw) for kw in set(kws))  # 一致した言い回しの長さの合計
        score += W_TOPIC * len(q_topics & set(it.get("tags", [])))
        item_when = set(it.get("when", []))
        if not q_when and not kws and (item_when == {"past"} or "long" in item_when):
            score -= 1  # 時間軸の指定も言い回しの一致もないとき、過去データ・長期予報は控えめにする
        if q_when:
            score += W_WHEN if q_when & item_when else -W_WHEN
        if refine.get("when"):
            score += W_REFINE if refine["when"] in item_when else -W_REFINE
        if refine.get("topic") and refine["topic"] in it.get("tags", []):
            score += W_REFINE
        needs = set(it["params"]) & {"office_code", "amdno", "prec_no"}
        region_ok = bool(needs) and place is not None
        if needs and place is not None:
            score += W_REGION  # 地名があれば、地域を指定して開けるページを優先
        elif needs and place is None:
            score -= 1         # 地名がなければ、全国版(地域不要)のページを優先
        shown_topics = q_topics | ({refine["topic"]} if refine.get("topic") else set())
        shown_when = q_when | ({refine["when"]} if refine.get("when") else set())
        if score >= MIN_SCORE and (matched or shown_topics & set(it.get("tags", []))):
            out.append((score, it, _reason(it, shown_topics, shown_when, matched, region_ok)))
    out.sort(key=lambda r: -r[0])  # 同点はカタログ順(安定ソート)
    return out


def choices(question):
    """候補がないとき・「違う」のときに出す、絞り込みの選択肢。"""
    return {
        "when": [{"value": k, "label": v} for k, v in WHEN_LABEL.items()],
        "topic": [{"value": k, "label": v} for k, v in TOPIC_LABEL.items()],
    }


def _has_basis(question, item, refine):
    """本命にできる根拠(言い回しの一致 / 時間軸の語 / 絞り込みの指定)があるか。"""
    if any(kw in question for kw in item["intents"] + [item["title"]]):
        return True
    return bool(_when_hits(question) or (refine or {}).get("when") or (refine or {}).get("topic"))


def _alt(question, it, reason):
    r = guide(question, item_id=it["id"])
    a = {"item": it["id"], "title": it["title"], "category": it["category"], "reason": reason,
         "status": "ok" if r.get("status") == "ok" else "need_place"}
    if r.get("status") == "ok":
        a["url"] = r["url"]
        if r.get("place"):
            a["place"] = r["place"]
    return a


def suggest(question, refine=None, exclude=(), limit=5):
    """最良の候補を guide() 形式で返し、alternatives に次点以下を付ける。"""
    ranked = rank(question, refine, exclude)
    if not ranked:
        return {"status": "no_match", "question": question, "choices": choices(question)}
    top_score = ranked[0][0]
    clear_win = len(ranked) == 1 or top_score - ranked[1][0] >= W_REGION + 1  # 2位との差が大きい
    if not clear_win and not _has_basis(question, ranked[0][1], refine):
        # 話題だけが一致して全項目が同点に近いとき、本命を決めずに候補と絞り込みを示す
        alts = [_alt(question, it, reason) for _, it, reason in ranked[:limit]]
        return {"status": "choose", "question": question, "alternatives": alts, "choices": choices(question)}
    primary = guide(question, item_id=ranked[0][1]["id"])
    primary["reason"] = ranked[0][2]
    alts = []
    for score, it, reason in ranked[1:]:
        if len(alts) >= limit - 1 or score < max(MIN_SCORE, top_score * 0.4):
            break
        alts.append(_alt(question, it, reason))
    primary["alternatives"] = alts
    primary["choices"] = choices(question)
    return primary
