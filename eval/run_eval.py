"""評価セット(eval/questions.json)で guide() の正答率を測る。標準ライブラリのみ。

使い方: python3 eval/run_eval.py [--engine keyword|llm] [--model haiku|sonnet]
正解の判定: status が一致し、期待する item / office_code / amdno / block_no / 年月が一致すること。
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from jnav.navigate import guide  # noqa: E402


def check(exp, got, today):
    """不一致の理由のリストを返す（空なら正解）。"""
    why = []
    if got.get("status") != exp["status"]:
        why.append(f'status {got.get("status")} != {exp["status"]}')
        return why
    if exp["status"] == "no_match":
        return why
    if exp["item"] and got.get("item") != exp["item"]:
        why.append(f'item {got.get("item")} != {exp["item"]}')
    url = got.get("url", "")
    for key, pat in (("office_code", r"[aA]rea_?[cC]ode=(\d+)"), ("amdno", r"amdno=(\d+)"),
                     ("block_no", r"block_no=(\d+)"), ("year", r"year=(\d+)"), ("month", r"month=(\d+)")):
        if key in exp:
            want = exp[key]
            if want == "LY":
                want = today.year - 1
            m = re.search(pat, url)
            if not m or m.group(1) != str(want):
                why.append(f"{key} {m.group(1) if m else None} != {want}")
    return why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="keyword", choices=["keyword", "llm"])
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    qs = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    if a.limit:
        qs = qs[:a.limit]
    if a.engine == "llm":
        from jnav.llm import guide_llm
        fn = lambda q: guide_llm(q, model=a.model)  # noqa: E731
    else:
        fn = guide
    ok, today, results = 0, date.today(), []
    for e in qs:
        got = fn(e["q"])
        why = check(e, got, today)
        ok += not why
        results.append({"q": e["q"], "ok": not why, "why": why, "got": got})
        if why:
            print(f'NG {e["q"]}  → {"; ".join(why)}')
    print(f"{a.engine}{'/' + a.model if a.engine == 'llm' else ''}: {ok}/{len(qs)}")
    out = ROOT / "eval" / f"result_{a.engine}{'_' + a.model if a.engine == 'llm' else ''}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
