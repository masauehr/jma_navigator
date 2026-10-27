"""地域気象観測所一覧(ame_master.pdf)から data/amedas_stations.json を作る。

入力: 気象庁 https://www.jma.go.jp/jma/kishou/know/amedas/ame_master.pdf
      （pdftotext -layout で作ったテキスト、または PDF 自体。PDF は pdftotext が必要）
      data/amedastable.json（原本: https://www.jma.go.jp/bosai/amedas/const/amedastable.json）
      があれば、緯度経度・標高・観測要素・「アメダス画面で開ける地点か」を足す。
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


# elems(8桁)の読み方。種類別の集計とPDFの観測種目との突き合わせによる推定:
#   0=気温 1=降水量 2=風向風速 3=風速 4=日照(1観測/2推計) 5=積雪 6=湿度 7=気圧
ELEM_NAMES = ["気温", "降水量", "風", None, "日照", "積雪", "湿度", "気圧"]


def observed(elems):
    return [n for n, c in zip(ELEM_NAMES, elems) if n and c != "0"]


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
    table_path = Path(__file__).resolve().parent.parent / "data" / "amedastable.json"
    table = json.loads(table_path.read_text(encoding="utf-8")) if table_path.exists() else {}
    for o in out:
        t = table.get(o["amdno"])
        o["in_viewer"] = t is not None
        if t:
            o["lat"] = round(t["lat"][0] + t["lat"][1] / 60, 4)
            o["lon"] = round(t["lon"][0] + t["lon"][1] / 60, 4)
            o["alt"] = t["alt"]
            o["observes"] = observed(t["elems"])
    dst = Path(__file__).resolve().parent.parent / "data" / "amedas_stations.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)}地点を書き出しました: {dst}")


if __name__ == "__main__":
    main()
