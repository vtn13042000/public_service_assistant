"""RAG tool: hybrid retrieval (BM25 + bge-m3 dense) over the `corpus` collection, returning Evidence.

Metadata filters (`procedure_id`, `section`) are applied to both retrievers *before* fusion; the two
ranked lists are merged with reciprocal-rank fusion (RRF, k=60). BM25 is built in memory from the Chroma
collection on first use and rebuilt when the collection's chunk count changes.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from rank_bm25 import BM25Okapi

from src.evidence import Evidence, make_evidence
from src.ingest import PROCEDURE_KIND, ROOT, chroma_dir, open_store

RRF_K = 60
POOL = 30  # candidates taken from each retriever before fusion

_cache: dict = {}


def reset_cache() -> None:
    """Forget the open store and BM25 (tests, or after rebuilding the index in-process)."""
    _cache.clear()


def _strip_accents(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def tokenize(text: str) -> list[str]:
    """Lower-cased word tokens, each followed by its unaccented form when different, so a query typed
    without diacritics ('dang ky khai sinh') still matches 'đăng ký khai sinh'."""
    toks = re.findall(r"\w+", unicodedata.normalize("NFC", text.lower()))
    out = []
    for t in toks:
        out.append(t)
        u = _strip_accents(t)
        if u != t:
            out.append(u)
    return out


# P20: synonym expansion of the BM25 query (dense query unchanged). Env RAG_SYNONYMS=0 turns the default off.
SYNONYMS_DEFAULT = os.environ.get("RAG_SYNONYMS", "1") != "0"
SYNONYMS_PATH = Path(os.environ.get("SYNONYMS_PATH", ROOT / "data" / "synonyms.yaml"))


def _synonym_groups() -> list[list[str]]:
    if "synonyms" not in _cache:
        import yaml
        groups = []
        if SYNONYMS_PATH.exists():
            groups = [[str(x) for x in g] for g in yaml.safe_load(SYNONYMS_PATH.read_text(encoding="utf-8")).get("groups") or []]
        _cache["synonyms"] = groups
    return _cache["synonyms"]


def _norm_text(s: str) -> str:
    return _strip_accents(unicodedata.normalize("NFC", s.lower()))


def expand_query(query: str) -> str:
    """`query` plus the other terms of every synonym group that has a term in it (matched without diacritics)."""
    q = _norm_text(query)
    extra = []
    for group in _synonym_groups():
        if any(re.search(rf"(?<!\w){re.escape(_norm_text(term))}(?!\w)", q) for term in group):
            extra += [term for term in group if term not in extra]
    return query + (" " + " ".join(extra) if extra else "")


# ROUND-2 item 4: chat-abbreviation normalisation ("đk" -> "đăng ký", "15t" -> "15 tuổi"), applied to the BM25 *and*
# the dense query text. Off by default; env RAG_ABBREV=1 turns it on. Entries: data/abbreviations.yaml.
ABBREV_DEFAULT = os.environ.get("RAG_ABBREV", "0") == "1"
ABBREV_PATH = Path(os.environ.get("ABBREV_PATH", ROOT / "data" / "abbreviations.yaml"))


def _abbreviations() -> tuple[dict[str, str], list[tuple[re.Pattern, str]]]:
    if "abbrev" not in _cache:
        import yaml
        cfg = yaml.safe_load(ABBREV_PATH.read_text(encoding="utf-8")) if ABBREV_PATH.exists() else {}
        words = {unicodedata.normalize("NFC", str(k).lower()): str(v) for k, v in (cfg.get("words") or {}).items()}
        pats = [(re.compile(a, re.IGNORECASE), b) for a, b in cfg.get("patterns") or []]
        _cache["abbrev"] = (words, pats)
    return _cache["abbrev"]


def normalize_abbrev(query: str) -> str:
    """`query` with whole-token chat abbreviations replaced by their full form (data/abbreviations.yaml)."""
    words, pats = _abbreviations()
    q = unicodedata.normalize("NFC", query)
    for pat, rep in pats:
        q = pat.sub(rep, q)
    return re.sub(r"\w+", lambda m: words.get(m.group(0).lower(), m.group(0)), q)


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal-rank fusion of ranked id lists -> [(id, score)] best first (ties: first-seen order)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking, 1):
            scores[i] = scores.get(i, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


def _state(path: Path | None = None):
    path = Path(path or chroma_dir())
    st = _cache.get(str(path))
    if st is None:
        st = {"store": open_store(path)}
        _cache[str(path)] = st
    coll = st["store"]._collection
    n = coll.count()
    if st.get("n") != n:
        got = coll.get(include=["documents", "metadatas"])
        st.update(n=n, ids=got["ids"], docs=got["documents"], metas=got["metadatas"],
                  bm25=BM25Okapi([tokenize(d) for d in got["documents"]]) if n else None,
                  has_kind=any("kind" in m for m in got["metadatas"]), bm25_kind={})  # corpus-v1 indexes carry no `kind`
    return st


def _bm25_for(st: dict, kind) -> "BM25Okapi":
    """BM25 whose term statistics (IDF, average length) come from the chunks of `kind` only, scoring every chunk
    (others get 0). With kind=None, the whole collection. Without this, adding documents to the index would change
    the procedure-only ranking used by resolution through IDF alone (measured on corpus v2: held-out hit@1 0.82 -> 0.59)."""
    if kind is None:
        return st["bm25"]
    key = (kind,) if isinstance(kind, str) else tuple(sorted(kind))
    cache = st.setdefault("bm25_kind", {})
    if key not in cache:
        idx = [i for i, m in enumerate(st["metas"]) if m.get("kind") in key]
        sub = BM25Okapi([tokenize(st["docs"][i]) for i in idx]) if idx else None

        class _Scatter:
            def get_scores(self, q):
                out = [0.0] * st["n"]
                if sub is not None:
                    for i, v in zip(idx, sub.get_scores(q)):
                        out[i] = v
                return out
        cache[key] = _Scatter()
    return cache[key]


def _match(meta: dict, procedure_id, section, kind=None) -> bool:
    def ok(key, want):
        return want is None or meta.get(key) in ([want] if isinstance(want, str) else want)
    return ok("procedure_id", procedure_id) and ok("section", section) and ok("kind", kind)


def _chroma_filter(procedure_id, section, kind=None) -> dict | None:
    conds = []
    for key, want in (("procedure_id", procedure_id), ("section", section), ("kind", kind)):
        if want is not None:
            conds.append({key: want} if isinstance(want, str) else {key: {"$in": list(want)}})
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


def _ranked(query: str, procedure_id, section, pool: int, path=None, expand: bool | None = None,
            abbrev: bool | None = None, kind=None) -> tuple[list[str], list[str], dict]:
    """(bm25 ids, dense ids, {id: (text, metadata)}) for the filtered candidate set.
    `expand` (default SYNONYMS_DEFAULT) applies synonym expansion to the BM25 query only.
    `abbrev` (default ABBREV_DEFAULT) normalises chat abbreviations first, for both rankers.
    `kind` restricts to chunk kinds (e.g. "procedure_page"); ignored on an index without `kind` metadata (corpus v1,
    where every chunk is a procedure page)."""
    if ABBREV_DEFAULT if abbrev is None else abbrev:
        query = normalize_abbrev(query)
    st = _state(path)
    if not st["n"]:
        return [], [], {}
    if not st["has_kind"]:
        kind = None
    allowed = [i for i, m in enumerate(st["metas"]) if _match(m, procedure_id, section, kind)]
    if not allowed:
        return [], [], {}
    expand = SYNONYMS_DEFAULT if expand is None else expand
    scores = _bm25_for(st, kind).get_scores(tokenize(expand_query(query) if expand else query))
    bm25_idx = sorted((i for i in allowed if scores[i] > 0), key=lambda i: -scores[i])[:pool]
    bm25_ids = [st["ids"][i] for i in bm25_idx]
    dense = st["store"].similarity_search_with_score(query, k=min(pool, len(allowed)),
                                                     filter=_chroma_filter(procedure_id, section, kind))
    dense_ids = [doc.id for doc, _ in dense]
    info = {st["ids"][i]: (st["docs"][i], st["metas"][i]) for i in allowed}
    return bm25_ids, dense_ids, info


def retrieve(query: str, procedure_id: str | list[str] | None = None, section: str | list[str] | None = None,
             k: int = 5, expand: bool | None = None, abbrev: bool | None = None) -> list[Evidence]:
    """Top-k corpus chunks for `query` as Evidence (tier `corpus`), hybrid BM25 + dense with RRF.

    `procedure_id` / `section` (a value or a list) restrict the candidates before fusion.
    `expand`: synonym expansion of the BM25 query (default on; env RAG_SYNONYMS=0).
    `abbrev`: chat-abbreviation normalisation of both queries (default off; env RAG_ABBREV=1).
    """
    bm25_ids, dense_ids, info = _ranked(query, procedure_id, section, max(POOL, 4 * k), expand=expand, abbrev=abbrev)
    out = []
    for cid, _score in rrf([bm25_ids, dense_ids])[:k]:
        text, m = info[cid]
        out.append(make_evidence(cid, "corpus", text, procedure_id=m["procedure_id"], section=m["section"],
                                 source_url=m.get("source_url"), retrieved_at=m.get("retrieved_at"),
                                 effective_date=m.get("effective_date")))
    return out


RESOLVE_MODES = ("fused", "summary")
# "fused" (default, P18): RRF of the summary-chunk procedure ranking and the all-chunk procedure ranking.
# "summary": the original behaviour (summary chunks only), kept for the eval ablation; env RAG_RESOLVE_MODE overrides the default.
RESOLVE_MODE = os.environ.get("RAG_RESOLVE_MODE", "fused")


def _procedure_ranking(fused: list[tuple[str, float]], info: dict) -> list[str]:
    """Chunk ranking -> procedure_ids in order of their best chunk."""
    return list(dict.fromkeys(info[cid][1]["procedure_id"] for cid, _ in fused))


def resolve_candidates(query: str, k: int = 5, mode: str | None = None, expand: bool | None = None,
                       abbrev: bool | None = None) -> list[dict]:
    """Candidate procedures for `query`: [{procedure_id, title, score}] best first. Used by `resolve_procedure`.

    mode "summary": rank procedures by their `summary` chunk (hybrid BM25 + dense, RRF).
    mode "fused" (default): RRF of that ranking and the procedure ranking from all chunks (each procedure placed
    at its best chunk), so wording that only appears in a body section (e.g. "hộ khẩu") still finds the procedure.
    `score` is the final RRF score (comparable within one call only). `expand`, `abbrev`: as in `retrieve`.
    """
    mode = mode or RESOLVE_MODE
    if mode not in RESOLVE_MODES:
        raise ValueError(f"mode must be one of {RESOLVE_MODES}")
    pool = max(POOL, 4 * k)
    # Resolution ranks procedures by their own pages only (ROUND-4): a legal article or guidance page cited by
    # many procedures must not pull a procedure up.
    b, d, info = _ranked(query, None, "summary", pool, expand=expand, abbrev=abbrev, kind=PROCEDURE_KIND)
    rankings = [_procedure_ranking(rrf([b, d]), info)]
    if mode == "fused":
        b, d, all_info = _ranked(query, None, None, max(50, 10 * k), expand=expand, abbrev=abbrev, kind=PROCEDURE_KIND)
        rankings.append(_procedure_ranking(rrf([b, d]), all_info))
        info = {**all_info, **info}
    titles = {m["procedure_id"]: m["title"] for _, m in info.values()}
    return [{"procedure_id": pid, "title": titles[pid], "score": round(score, 6)}
            for pid, score in rrf(rankings)[:k]]
