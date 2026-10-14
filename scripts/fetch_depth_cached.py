"""Polite cached fetch for Round-4 depth documents (w-dvc, BRIEF-8 Part 3).

Usage: uv run python scripts/fetch_depth_cached.py URL [URL ...]
Each URL is fetched once (cache hit = no request), ≥ 4 s between requests, our named UA, no auth, no JS.
Raw bytes go to data/raw/dvc/depth/<host>/<safe-name>; one line per fetch is appended to data/raw/dvc/depth/index.jsonl
(url, fetched_at UTC, status, content_type, bytes, sha256, path). Prints the index line.
"""
import hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests, urllib3

urllib3.disable_warnings()
UA = "AI5013-UniversityProject-PublicServicesAssistant/0.1 (student research crawler)"
ROOT = Path("data/raw/dvc/depth")
INDEX = ROOT / "index.jsonl"
DELAY = 4.5


def cached() -> dict:
    out = {}
    if INDEX.exists():
        for line in INDEX.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("status") == 200:
                    out[r["url"]] = r
    return out


def safe_name(url: str) -> str:
    p = urlparse(url)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", (p.path + ("_" + p.query if p.query else "")).strip("/"))[:160] or "index"
    return name


def main(urls):
    seen = cached()
    last = 0.0
    for u in urls:
        if u in seen:
            print(json.dumps(seen[u] | {"cache": True}, ensure_ascii=False)); continue
        wait = DELAY - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.time()
        try:
            r = requests.get(u, headers={"User-Agent": UA}, timeout=60, verify=False)
        except Exception as e:  # network errors are logged, not retried
            rec = {"url": u, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "ERR", "error": str(e)[:200]}
        else:
            b = r.content
            path = ROOT / urlparse(u).netloc / safe_name(u)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b)
            rec = {"url": u, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": r.status_code,
                   "content_type": r.headers.get("content-type", ""), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(),
                   "path": str(path), "final_url": r.url}
        with INDEX.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(json.dumps(rec, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
