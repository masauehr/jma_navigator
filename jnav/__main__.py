"""使い方: python3 -m jnav "明日の那覇の天気" """
import json
import sys

from .navigate import guide

if __name__ == "__main__":
    q = " ".join(sys.argv[1:])
    print(json.dumps(guide(q), ensure_ascii=False, indent=2))
