"""ページカタログ(catalog.json)の構造検査。標準ライブラリのみ。

検査内容: 必須キー・ID重複・URL内プレースホルダと params の一致。
使い方: python3 tools/validate_catalog.py
"""
import json
import re
import sys
from pathlib import Path

REQUIRED = ["id", "category", "title", "intents", "url", "params", "verified", "static"]


def main():
    path = Path(__file__).resolve().parent.parent / "catalog.json"
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    errors, seen = [], set()
    for it in items:
        iid = it.get("id", "?")
        for k in REQUIRED:
            if k not in it:
                errors.append(f"{iid}: 必須キー {k} がありません")
        if iid in seen:
            errors.append(f"{iid}: ID重複")
        seen.add(iid)
        holders = set(re.findall(r"\{(\w+)\}", it.get("url", "")))
        params = set(it.get("params", {}))
        if holders != params:
            errors.append(f"{iid}: URLの{{}}={sorted(holders)} と params={sorted(params)} が不一致")
        if it.get("static") and holders:
            errors.append(f"{iid}: static=true なのにプレースホルダがあります")
        if not it["url"].startswith("https://"):
            errors.append(f"{iid}: URLはhttpsにしてください")
    for e in errors:
        print("NG", e)
    print(f"{len(items)}件を検査 / エラー {len(errors)}件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
