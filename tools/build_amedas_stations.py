"""地域気象観測所一覧(ame_master.pdf)から data/amedas_stations.json を作る。

入力: 気象庁 https://www.jma.go.jp/jma/kishou/know/amedas/ame_master.pdf
      （pdftotext -layout で作ったテキスト、または PDF 自体。PDF は pdftotext が必要）
使い方: python3 tools/build_amedas_stations.py ame_master.pdf
標準ライブラリのみ（PDFの場合は外部コマンド pdftotext を呼ぶ）。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

LINE = re.compile(r"^(\S+)\s+(\d{5})\s+(官|四|三|雨|雪)\s+(\S+)\s+(\S+)\s+(\S+)")


def to_text(path):
    if path.suffix.lower() == ".pdf":
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                              text=True, check=True).stdout
    return path.read_text(encoding="utf-8")


def main():
    src = Path(sys.argv[1])
    seen, out = set(), []
    for line in to_text(src).splitlines():
        m = LINE.match(line)
        if not m or m.group(2) in seen:
            continue
        seen.add(m.group(2))
        sub, no, kind, name, kana, label = m.groups()
        out.append({"amdno": no, "kind": kind, "name": name, "kana": kana,
                    "label": label, "subprefecture": sub})
    dst = Path(__file__).resolve().parent.parent / "data" / "amedas_stations.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)}地点を書き出しました: {dst}")


if __name__ == "__main__":
    main()
