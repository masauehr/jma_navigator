"""リンク検査と辞書の鮮度点検。標準ライブラリのみ。

検査内容:
  1. カタログの全URL(プレースホルダ付きは代表値で埋める)に HTTP で到達できるか
     ※ #以降(ハッシュ)はサーバーに送られない。bosai系SPAは「土台のページが存在するか」までしか見えない。
       表示内容の確認はブラウザ実機で行う(catalog.json の verified と note を参照)。
  2. bosai系の裏にあるJSON(予報・警報のデータ)が取れるか(SPAの中身が生きている目安)
  3. data/area.json・data/amedastable.json が気象庁の原本と一致するか(鮮度点検)

方針: 気象庁サーバーへの負荷を避けるため、1.5秒間隔・リトライなし・1回の実行で約30リクエスト。
使い方:
  python3 tools/check_links.py            # 検査して reports/ にJSONを書き、NGがあれば終了コード1
  python3 tools/check_links.py --notify   # NG時にmacOS通知も出す(launchd用)
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "jma_navigator-linkcheck/0.1 (personal; low-frequency)"
INTERVAL = 1.5
TIMEOUT = 20

# プレースホルダの代表値(那覇・沖縄本島)。到達確認だけが目的
SAMPLE = {
    "office_code": "471000", "area_code": "472000", "station_code": "NH", "class30_code": "471010",
    "prec_no": "91", "block_no": "47936", "year": "2026", "month": "9", "amdno": "91197",
}

# 裏のJSON(SPAの中身が生きているかの目安)
BACKING = [
    ("予報JSON", "https://www.jma.go.jp/bosai/forecast/data/forecast/471000.json"),
    ("警報JSON", "https://www.jma.go.jp/bosai/warning/data/warning/471000.json"),
    ("アメダス最新時刻", "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"),
]

# 辞書と原本の対応(ローカル, 原本URL)
FRESHNESS = [
    ("data/area.json", "https://www.jma.go.jp/bosai/common/const/area.json"),
    ("data/amedastable.json", "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"),
]


def fetch(url):
    """URLを取得して (HTTPステータス, 本文bytes) を返す。通信失敗は (0, エラー文字列のbytes)。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:  # 名前解決失敗・タイムアウトなど
        return 0, str(e).encode("utf-8", "replace")


def fill(url):
    """プレースホルダを代表値で埋め、ハッシュ(#以降)を除く。"""
    url = re.sub(r"\{(\w+)\}", lambda m: SAMPLE.get(m.group(1), "1"), url)
    return url.split("#", 1)[0]


def check_catalog(items, fetcher, sleep):
    results, done = [], {}
    for it in items:
        url = fill(it["url"])
        if url not in done:  # 同じURLは1回だけ(ハッシュ違いの重複を省く)
            sleep()
            status, _ = fetcher(url)
            done[url] = status
        status = done[url]
        results.append({"kind": "catalog", "id": it["id"], "url": url, "status": status, "ok": status == 200})
    return results


def check_backing(fetcher, sleep):
    out = []
    for name, url in BACKING:
        sleep()
        status, body = fetcher(url)
        out.append({"kind": "backing", "id": name, "url": url, "status": status, "ok": status == 200 and len(body) > 0})
    return out


def check_freshness(fetcher, sleep, root=ROOT):
    out = []
    for local, url in FRESHNESS:
        sleep()
        status, body = fetcher(url)
        rec = {"kind": "freshness", "id": local, "url": url, "status": status, "ok": False}
        if status == 200:
            try:
                same = json.loads(body.decode("utf-8")) == json.loads((root / local).read_text(encoding="utf-8"))
                rec["ok"] = same
                rec["detail"] = "原本と一致" if same else "原本と差分あり(辞書の再取得を検討)"
            except (ValueError, OSError) as e:
                rec["detail"] = f"比較できません: {e}"
        out.append(rec)
    return out


def run(fetcher=fetch, sleep=lambda: time.sleep(INTERVAL), root=ROOT):
    items = json.loads((root / "catalog.json").read_text(encoding="utf-8"))["items"]
    return check_catalog(items, fetcher, sleep) + check_backing(fetcher, sleep) + check_freshness(fetcher, sleep, root)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true", help="NG時にmacOS通知を出す")
    args = ap.parse_args()
    results = run()
    ng = [r for r in results if not r["ok"]]
    now = datetime.datetime.now()
    report = {"checked_at": now.isoformat(timespec="seconds"), "total": len(results), "ng": len(ng), "results": results}
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"link_check_{now:%Y%m%d}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in results:
        print("OK " if r["ok"] else "NG ", r["kind"], r["id"], r["status"], r.get("detail", ""))
    print(f"{len(results)}件を検査 / NG {len(ng)}件")
    if ng and args.notify:
        msg = f"jma_navigator: NG {len(ng)}件 ({', '.join(r['id'] for r in ng[:3])})"
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "リンク検査"'], check=False)
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
