#!/bin/bash
# 週次のリンク検査。NGがあればmacOS通知を出す。結果は reports/link_check_YYYYMMDD.json に残る。
cd "$(dirname "$0")" || exit 1
/usr/bin/python3 tools/check_links.py --notify
