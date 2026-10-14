"""Round 4: fetch depth documents for the hộ tịch family into data/raw/moj/docs/ (cached, indexed by fetch_moj).

Usage: uv run python scripts/moj_docs_fetch.py NAME=URL [NAME=URL ...]
NAME is the file name under data/raw/moj/docs/. Prints status, size and sha256 for each.
"""
import sys

import urllib3

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from fetch_moj import fetch  # noqa: E402

urllib3.disable_warnings()

if __name__ == "__main__":
    for arg in sys.argv[1:]:
        name, url = arg.split("=", 1)
        try:
            r = fetch(url, name=f"docs/{name}", note="round4")
            print(r["status"], r["sha256"][:12], r["content_type"], name)
        except Exception as e:  # keep going; report
            print("ERR", type(e).__name__, str(e)[:120], name)
