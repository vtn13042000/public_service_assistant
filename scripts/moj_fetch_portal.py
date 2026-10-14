"""Fetch MOJ portal TTHC detail pages for the given mã TTHC (cached; see fetch_moj.py).

Usage: uv run python scripts/moj_fetch_portal.py 1.001193 2.000528 ...
Saves data/raw/moj/portal/<mã>.html and logs to data/raw/moj/index.jsonl.
"""
import sys
import urllib3

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from fetch_moj import fetch  # noqa: E402

URL = "https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-{code}.html"

if __name__ == "__main__":
    urllib3.disable_warnings()
    for code in sys.argv[1:]:
        rec = fetch(URL.format(code=code), name=f"portal/{code}.html", note="MOJ portal TTHC detail")
        print(code, rec["status"], rec["sha256"][:12])
