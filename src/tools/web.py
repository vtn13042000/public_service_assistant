"""Web search tool: self-hosted SearxNG first, then DuckDuckGo / Bing via `ddgs`; allowlisted and normalised to Evidence
(architecture.md §1, guardrails.md L2/L7).

Backends (APP_WEB_BACKEND, default "searxng,duckduckgo,bing"; first non-empty answer wins):
  searxng     the local instance in infra/searxng (SEARXNG_URL, default http://127.0.0.1:8080), JSON API; it fans out to
              duckduckgo/bing/google/brave/startpage/mojeek itself, so one throttled engine does not empty the answer
  duckduckgo, bing   direct calls through the `ddgs` package (fallback when SearxNG is down)

Web results are never a source for structured facts. They feed `web_lookup` (find the official page when the
procedure is not in the corpus) and `web_check` (a "something may have changed" notice). Tiers come from
config/web_allowlist.txt: `dichvucong.gov.vn`, `*.gov.vn`, `chinhphu.vn`, `baochinhphu.vn` → web_official; `thuvienphapluat.vn`, `luatvietnam.vn`
→ web_other; any other host is dropped here.

Etiquette: ≥ 2 s between live searches (process-wide), every result list cached on disk under data/cache/web/
(one JSON per query + index.jsonl), so the same query is never sent twice (empty answers are not cached). Search errors raise WebSearchError;
the calling node decides whether that is fatal (web_lookup) or just means "no notice" (web_check).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.evidence import Evidence, Tier, make_evidence, web_id

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = ROOT / "config" / "web_allowlist.txt"
DEFAULT_ALLOWLIST: list[tuple[str, Tier]] = [
    ("dichvucong.gov.vn", "web_official"), ("*.gov.vn", "web_official"),
    ("chinhphu.vn", "web_official"), ("baochinhphu.vn", "web_official"),
    ("thuvienphapluat.vn", "web_other"), ("luatvietnam.vn", "web_other"),
]
MIN_INTERVAL_S = 2.0
REGION = "vn-vi"
SEARXNG_LANG = "vi-VN"
SEARXNG_MAX = 20  # one SearxNG page; the allowlist then drops most hosts, web_search caps the evidence at max_results

_lock = threading.Lock()
_last_call = 0.0


class WebSearchError(RuntimeError):
    pass


def cache_dir() -> Path:
    p = Path(os.environ.get("APP_WEB_CACHE", "data/cache/web"))
    return p if p.is_absolute() else ROOT / p


def load_allowlist(path: Path = ALLOWLIST_PATH) -> list[tuple[str, Tier]]:
    """`<pattern> <tier>` lines; `#` comments. Falls back to DEFAULT_ALLOWLIST if the file is missing."""
    if not path.is_file():
        return list(DEFAULT_ALLOWLIST)
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, tier = line.split()
        if tier not in ("web_official", "web_other"):
            raise ValueError(f"bad tier {tier!r} in {path}")
        rules.append((pattern.lower(), tier))
    return rules


def classify_url(url: str, rules: list[tuple[str, Tier]] | None = None) -> Tier | None:
    """Tier for a URL by host, or None (drop). Only http(s) URLs qualify."""
    u = urlparse(url)
    host = (u.hostname or "").lower().rstrip(".")
    if u.scheme not in ("http", "https") or not host:
        return None
    for pattern, tier in rules if rules is not None else load_allowlist():
        if pattern.startswith("*."):
            if host.endswith(pattern[1:]):
                return tier
        elif host == pattern or host.endswith("." + pattern):
            return tier
    return None


def _cache_key(query: str, max_results: int, backend: str) -> str:
    return hashlib.sha256(f"{backend}|{REGION}|{max_results}|{query}".encode("utf-8")).hexdigest()[:24]


def searxng_url() -> str:
    return os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080").rstrip("/")


def _searxng(query: str) -> list[dict]:
    """One SearxNG JSON query → [{title, href, body, engines}] (the ddgs result shape, plus SearxNG's engine list)."""
    try:
        r = httpx.get(f"{searxng_url()}/search", timeout=15,
                      params={"q": query, "format": "json", "language": SEARXNG_LANG, "safesearch": 0})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise WebSearchError(f"searxng: {type(e).__name__}: {e}") from e
    return [{"title": x.get("title", ""), "href": x.get("url", ""), "body": x.get("content", ""),
             "engines": x.get("engines", [])} for x in data.get("results", [])[:SEARXNG_MAX]]


def _search_live(query: str, max_results: int, backend: str, retries: int = 1) -> list[dict]:
    """One live search on one backend, spaced ≥ MIN_INTERVAL_S from the previous search (process-wide).

    The engines intermittently answer "No results found" for queries that do have results (soft throttling),
    so an empty answer is retried once after a longer pause; if it persists the result is [].
    """
    global _last_call
    from ddgs import DDGS

    for attempt in range(retries + 1):
        with _lock:
            wait = MIN_INTERVAL_S * (1 + 2 * attempt) - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                if backend == "searxng":
                    res = _searxng(query)
                else:
                    res = DDGS(timeout=10).text(query, region=REGION, max_results=max_results, backend=backend)
                if res:
                    return res
            except WebSearchError:
                raise
            except Exception as e:  # noqa: BLE001 — ddgs raises several types (rate limit, timeout, no results)
                if "no results" not in str(e).lower():
                    raise WebSearchError(f"{backend}: {type(e).__name__}: {e}") from e
            finally:
                _last_call = time.monotonic()
    return []


def backends() -> list[str]:
    """Backend chain, first non-empty answer wins. Default "searxng,duckduckgo,bing": the local SearxNG first
    (direct DuckDuckGo/Bing calls are throttled on this host, R4 §5). Override with APP_WEB_BACKEND."""
    return [b.strip() for b in os.environ.get("APP_WEB_BACKEND", "searxng,duckduckgo,bing").split(",") if b.strip()]


def raw_search(query: str, max_results: int = 8) -> dict:
    """Cached raw search: {"query", "fetched_at", "backend", "results": [{title, href, body}], "cached": bool}.

    Tries each backend in `backends()` until one returns results. Empty answers are not cached.
    """
    chain = backends()
    d = cache_dir()
    f = d / f"{_cache_key(query, max_results, ','.join(chain))}.json"
    if f.is_file():
        return {**json.loads(f.read_text(encoding="utf-8")), "cached": True}
    results, used, errors = [], None, []
    for b in chain:
        try:
            results = _search_live(query, max_results, b)
        except WebSearchError as e:
            errors.append(str(e))
            continue
        if results:
            used = b
            break
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not results:
        if errors and len(errors) == len(chain):
            raise WebSearchError("; ".join(errors))
        return {"query": query, "backend": None, "region": REGION, "max_results": max_results,
                "fetched_at": now, "results": [], "cached": False}
    rec = {"query": query, "backend": used, "region": REGION, "max_results": max_results,
           "fetched_at": now, "results": results}
    d.mkdir(parents=True, exist_ok=True)
    body = json.dumps(rec, ensure_ascii=False, indent=1)
    f.write_text(body, encoding="utf-8")
    with (d / "index.jsonl").open("a", encoding="utf-8") as idx:
        idx.write(json.dumps({"query": query, "backend": used, "file": f.name, "fetched_at": now, "n": len(results),
                              "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}, ensure_ascii=False) + "\n")
    return {**rec, "cached": False}


def _host_in(url: str, site: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    site = site.lower().lstrip("*.")
    return host == site or host.endswith("." + site)


def to_evidence(raw: dict, procedure_id: str | None = None, rules: list[tuple[str, Tier]] | None = None) -> list[Evidence]:
    """Allowlist + normalise raw results. Drops unlisted hosts and duplicate URLs; keeps search order."""
    rules = rules if rules is not None else load_allowlist()
    out, seen = [], set()
    for r in raw.get("results", []):
        url = (r.get("href") or r.get("url") or "").strip()
        tier = classify_url(url, rules)
        if tier is None or url in seen:
            continue
        seen.add(url)
        title, body = (r.get("title") or "").strip(), (r.get("body") or "").strip()
        text = "\n".join(x for x in (title, body) if x)
        if not text:
            continue
        out.append(make_evidence(
            web_id(url), tier, text, procedure_id=procedure_id,
            structured={"title": title, "url": url, "snippet": body, "domain": urlparse(url).hostname,
                        "query": raw.get("query")},
            source_url=url, retrieved_at=raw.get("fetched_at")))
    return out


def web_search(query: str, *, max_results: int = 8, site: str | None = None, official_only: bool = False,
               procedure_id: str | None = None) -> list[Evidence]:
    """Allowlisted web search → list[Evidence] with tier web_official / web_other.

    site: restrict the query, e.g. "dichvucong.gov.vn" (appends `site:`); official_only: drop web_other results.
    """
    q = f"{query} site:{site}" if site else query
    evs = to_evidence(raw_search(q, max_results=max_results), procedure_id=procedure_id)
    if site:  # not every backend honours `site:`; enforce it on the results
        evs = [e for e in evs if _host_in(e["source_url"], site)]
    if official_only:
        evs = [e for e in evs if e["tier"] == "web_official"]
    return evs[:max_results]
