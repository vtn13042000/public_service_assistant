"""Adversarial fixtures (data/testset_adversarial.jsonl `fixture` field), test-only.

The production graph has no test hook: these wrappers sit around the real tools and are passed into `build_graph`
through its normal dependency injection (`eval/run_variant.py`). Each wrapper counts how often it actually delivered
the injected item, so a result can say whether the attack reached the graph at all.

    {"inject_chunk":    {"procedure_id", "section", "text"}}   extra corpus chunk ranked first by `retrieve`
    {"inject_evidence": {"kind": "web_other"|"web_official", "procedure_id", "text"}}   extra web result
    {"fault": "vector_store_raises"}                            `retrieve` and `resolve_candidates` raise
"""
from __future__ import annotations

from typing import Any

from src.evidence import doc_id, make_evidence, web_id

FAULTS = ("vector_store_raises",)
INJECTED_URL = "https://example.invalid/injected/{n}"
INJECTED_DATE = "2026-10-10"


class InjectionStats:
    def __init__(self) -> None:
        self.delivered = 0


def _wants(want: str | list[str] | None, value: str | None) -> bool:
    return want is None or value is None or (value == want if isinstance(want, str) else value in want)


class InjectingRetriever:
    """Wraps src.tools.rag. An injected chunk is prepended when the call's procedure/section filter admits it
    (an unfiltered whole-corpus call, as in the baseline, always admits it)."""

    def __init__(self, base: Any, chunk: dict | None = None, fault: str | None = None,
                 stats: InjectionStats | None = None) -> None:
        self.base, self.fault, self.stats = base, fault, stats or InjectionStats()
        self.chunk = None if chunk is None else make_evidence(
            doc_id(chunk["procedure_id"], chunk["section"], 9000), "corpus", chunk["text"],
            procedure_id=chunk["procedure_id"], section=chunk["section"],
            source_url=INJECTED_URL.format(n="chunk"), retrieved_at=INJECTED_DATE)

    def _check(self) -> None:
        if self.fault == "vector_store_raises":
            raise RuntimeError("vector store unavailable (injected fault)")

    def retrieve(self, query: str, procedure_id=None, section=None, k: int = 5, **kw):
        self._check()
        out = list(self.base.retrieve(query, procedure_id=procedure_id, section=section, k=k, **kw))
        if self.chunk and _wants(procedure_id, self.chunk["procedure_id"]) and _wants(section, self.chunk["section"]):
            self.stats.delivered += 1
            out = [self.chunk] + out[: max(k - 1, 0)]
        return out

    def resolve_candidates(self, query: str, *a, **kw):
        self._check()
        return self.base.resolve_candidates(query, *a, **kw)

    def __getattr__(self, name: str):
        return getattr(self.base, name)


class InjectingWeb:
    """Wraps `web_search`. The injected result is first; `official_only=True` drops a web_other injection
    exactly as the real tool drops any web_other result."""

    def __init__(self, base, evidence: dict, stats: InjectionStats | None = None) -> None:
        self.base, self.stats = base, stats or InjectionStats()
        kind = evidence.get("kind", "web_other")
        url = INJECTED_URL.format(n="web")
        self.ev = make_evidence(web_id(url), kind, evidence["text"], procedure_id=evidence.get("procedure_id"),
                                source_url=url, retrieved_at=INJECTED_DATE)

    def __call__(self, query: str, **kw):
        out = list(self.base(query, **kw)) if self.base else []
        if kw.get("official_only") and self.ev["tier"] != "web_official":
            return out
        self.stats.delivered += 1
        return [self.ev] + out


def apply_fixture(deps: dict, fixture: dict | None) -> tuple[dict, InjectionStats | None]:
    """New deps dict with the item's fixture applied, plus the delivery counter (None if no fixture)."""
    if not fixture:
        return deps, None
    unknown = set(fixture) - {"inject_chunk", "inject_evidence", "fault"}
    if unknown or fixture.get("fault") not in (None, *FAULTS):
        raise ValueError(f"unsupported fixture {fixture!r}")
    stats = InjectionStats()
    deps = dict(deps)
    if fixture.get("inject_chunk") or fixture.get("fault"):
        deps["retriever"] = InjectingRetriever(deps["retriever"], fixture.get("inject_chunk"), fixture.get("fault"), stats)
    if fixture.get("inject_evidence"):
        deps["web"] = InjectingWeb(deps.get("web"), fixture["inject_evidence"], stats)
    return deps, stats
