"""Crawl procedure detail pages from the Ministry of Public Security DVC portal (dichvucong.bocongan.gov.vn).

The portal is server-rendered; robots.txt only restricts Googlebot/AdsBot from /tttl/.
Raw HTML -> data/raw/dvc/bca-portal/<matt>.html, one line per fetch -> data/raw/dvc/bca-portal/index.jsonl.
Re-runnable: a matt already in index.jsonl with status 200 is skipped (never fetched twice).

Usage: uv run python scripts/crawl_bca_portal.py [--lists] [--dry-run]
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dvc" / "bca-portal"
INDEX = RAW / "index.jsonl"
BASE = "https://dichvucong.bocongan.gov.vn"
LIST_URL = BASE + "/bocongan/bothutuc?linh_vuc={code}"
DETAIL_URL = BASE + "/bocongan/bothutuc/tthc?matt={matt}"
UA = "AI5013-UniversityProject-PublicServicesAssistant/0.1 (student research crawler)"
DELAY_S = 4.0
CAP = 20

FIELDS = {"QL_CU_TRU": "Đăng ký, quản lý cư trú", "CAP_CCCD": "Cấp, quản lý căn cước"}

# Target procedures (matt = the portal's internal id; mã TTHC is read from the page by the parser).
# Chosen from the two listing pages (11 entries each, single page) for the families in the brief.
TARGETS = {
    "QL_CU_TRU": [
        26360,  # Đăng ký thường trú
        26356,  # Đăng ký tạm trú
        26345,  # Gia hạn tạm trú
        26348,  # Xóa đăng ký thường trú
        26552,  # Xóa đăng ký tạm trú
        26351,  # Khai báo tạm vắng
        26497,  # Xác nhận thông tin về cư trú
        26499,  # Tách hộ
        26492,  # Khai báo thông tin về cư trú đối với người chưa đủ điều kiện đăng ký thường trú, tạm trú
    ],
    "CAP_CCCD": [
        26052,   # Cấp thẻ căn cước cho người từ đủ 14 tuổi trở lên (cấp tỉnh)
        26054,   # Cấp thẻ căn cước cho người từ đủ 14 tuổi trở lên (cấp trung ương)
        26094,   # Cấp đổi thẻ căn cước (cấp tỉnh)
        26099,   # Cấp đổi thẻ căn cước (cấp trung ương)
        26093,   # Cấp lại thẻ căn cước (cấp tỉnh)
        26096,   # Cấp lại thẻ căn cước (cấp trung ương)
        57013,   # Cấp thẻ căn cước cho người dưới 14 tuổi (cấp tỉnh)
        122156,  # Cấp thẻ căn cước cho người dưới 14 tuổi (Công an cấp xã)
        26092,   # Cấp xác nhận số CMND 09 số, số định danh cá nhân (cấp tỉnh)
    ],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_index() -> list[dict]:
    if not INDEX.exists():
        return []
    return [json.loads(line) for line in INDEX.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_index(row: dict) -> None:
    with INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


class Fetcher:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.last = 0.0
        self.count = 0

    def get(self, url: str) -> requests.Response:
        wait = DELAY_S - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        r = self.s.get(url, timeout=60)
        self.last = time.monotonic()
        self.count += 1
        return r


def page_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    h = soup.select_one(".tthc-title, h1.title, .page-title")
    for it in soup.select(".tthc-list-item"):
        if it.select_one(".item-title") and it.select_one(".item-title").get_text(strip=True) == "Mã thủ tục":
            body = it.select_one(".tthc-panel-collapse")
            code = body.get_text(strip=True) if body else None
            return code
    return h.get_text(" ", strip=True) if h else None


def save(fetcher: Fetcher, url: str, path: Path, extra: dict) -> dict:
    r = fetcher.get(url)
    body = r.content
    path.write_bytes(body)
    row = {"url": url, "fetched_at": now_iso(), "status": r.status_code,
           "sha256": hashlib.sha256(body).hexdigest(), "file": str(path.relative_to(ROOT)), **extra}
    append_index(row)
    return row


def list_titles(html: str) -> dict[int, str]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[int, str] = {}
    for a in soup.find_all("a", href=re.compile(r"matt=\d+")):
        m = int(re.search(r"matt=(\d+)", a["href"]).group(1))
        out.setdefault(m, a.get_text(" ", strip=True))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lists", action="store_true", help="re-fetch the two listing pages (otherwise use cached ones)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "_lists").mkdir(exist_ok=True)
    fetcher = Fetcher()
    index = load_index()

    titles: dict[int, tuple[str, str]] = {}
    for code in TARGETS:
        lp = RAW / "_lists" / f"{code}.html"
        if args.lists or not lp.exists():
            if args.dry_run:
                print("would fetch", LIST_URL.format(code=code))
                continue
            save(fetcher, LIST_URL.format(code=code), lp, {"kind": "list", "linh_vuc": code})
        for matt, t in list_titles(lp.read_text(encoding="utf-8")).items():
            titles[matt] = (code, t)

    done = {r["matt"] for r in index if r.get("kind") == "detail" and r.get("status") == 200}
    n_detail = len(done)
    for code, matts in TARGETS.items():
        for matt in matts:
            if matt in done:
                continue
            if n_detail >= CAP:
                print(f"cap {CAP} reached; stopping")
                break
            url = DETAIL_URL.format(matt=matt)
            title = titles.get(matt, (code, None))[1]
            if args.dry_run:
                print("would fetch", url, title)
                continue
            row = save(fetcher, url, RAW / f"{matt}.html",
                       {"kind": "detail", "matt": matt, "linh_vuc": code, "title": title})
            if row["status"] == 200:
                row_code = page_title((RAW / f"{matt}.html").read_text(encoding="utf-8", errors="replace"))
                print(f"{matt} {row['status']} {row_code} {title}")
                n_detail += 1
            else:
                print(f"{matt} HTTP {row['status']} — stopping on non-200", file=sys.stderr)
                return 1
    print(f"requests this run: {fetcher.count}; detail pages total: {n_detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
