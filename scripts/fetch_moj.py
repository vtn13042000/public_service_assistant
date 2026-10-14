"""Polite cached fetcher for w-moj (legal publications).

Usage:
  uv run python scripts/fetch_moj.py URL [--so-hieu X] [--ngay YYYY-MM-DD] [--name FILE] [--note TEXT]

Every response is cached under data/raw/moj/ and logged to data/raw/moj/index.jsonl
(url, fetched_at, status, sha256, so_hieu, ngay, path). A URL already in the index is never re-fetched.
Respects robots.txt and waits >= 2 s between requests to the same host.
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "moj"
INDEX = RAW_DIR / "index.jsonl"
UA = "AI5013-StudentProject/0.1 (university course project; public-services assistant research; contact via course)"
DELAY_S = 2.5
_last_hit: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def load_index() -> dict[str, dict]:
    if not INDEX.exists():
        return {}
    out = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["url"]] = rec
    return out


def robots_ok(url: str) -> bool:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=20, verify=False)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                rp.parse([])  # no robots.txt -> allowed
            _robots[base] = rp
        except requests.RequestException:
            _robots[base] = None
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(UA, url)


def safe_name(url: str) -> str:
    p = urlparse(url)
    tail = Path(p.path).name or "index"
    tail = re.sub(r"[^A-Za-z0-9._-]+", "_", tail)[-80:]
    h = hashlib.sha256(url.encode()).hexdigest()[:10]
    return f"{p.netloc}_{h}_{tail}"


def fetch(url: str, so_hieu: str | None = None, ngay: str | None = None,
          name: str | None = None, note: str | None = None) -> dict:
    idx = load_index()
    if url in idx:
        return idx[url]
    if not robots_ok(url):
        raise SystemExit(f"robots.txt disallows {url}")
    host = urlparse(url).netloc
    wait = DELAY_S - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60, verify=False)
    _last_hit[host] = time.time()
    body = r.content
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / (name or safe_name(url))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    rec = {
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": r.status_code,
        "sha256": hashlib.sha256(body).hexdigest(),
        "content_type": r.headers.get("content-type"),
        "so_hieu": so_hieu,
        "ngay": ngay,
        "path": str(path.relative_to(RAW_DIR.parent.parent.parent)),
        "note": note,
    }
    with INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--so-hieu")
    ap.add_argument("--ngay")
    ap.add_argument("--name")
    ap.add_argument("--note")
    a = ap.parse_args()
    rec = fetch(a.url, a.so_hieu, a.ngay, a.name, a.note)
    print(json.dumps(rec, ensure_ascii=False))
    sys.exit(0 if rec["status"] == 200 else 1)
