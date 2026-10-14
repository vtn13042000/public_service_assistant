"""AgentState — the graph's typed state (architecture.md §3).

The professor's fields (guidance.md A1) are kept with their names so the skeleton in `src/baseline/`
runs on the same state; our fields are added below them. Rule: a node writes only the fields it owns;
edge functions read state and return a label.
"""
from __future__ import annotations

from typing import TypedDict

from src.evidence import Evidence


class AgentState(TypedDict, total=False):
    # professor's fields (guidance.md A1)
    query: str
    sub_queries: list[str]
    documents: list[dict]          # corpus evidence
    db_results: list[dict]         # db evidence
    web_results: list[dict]        # web evidence
    grades: dict
    route: str
    iteration: int
    generation: str                # the final user-facing text (answer, clarify or refusal)
    # added (architecture.md §3)
    need: dict          # {"retrieve": bool, "intent": "documents|fee|agency|time|steps|general|update",
                        #  "procedure_hint": str, "locality": str|None, "premise": str|None, "in_scope": bool}
    candidates: list[dict]         # [{procedure_id, title, score}] from resolve_procedure
    procedure_id: str | None
    evidence: list[Evidence]       # merged, graded, tiered
    draft: str
    claims: list[dict]             # [{text, type, evidence_ids, verdict: supported|unsupported|unknown}]
    outcome: str                   # answer | answer_partial | clarify | refuse | out_of_scope
    refusal: dict | None           # {"type": …, "agency": …, "portal_url": …, "missing": [...]}
    freshness: dict | None         # {"oldest_retrieved_at": …, "notice": bool}
    errors: list[str]
    # added by w-graph (not in architecture.md §3; see docs/05_log/workers/w-graph/STATUS.md)
    locality: str | None           # caller-supplied province (CLI --locality); overrides need.locality
    block: str                     # code-rendered structured block (render.py), fixed text inside `draft`
    gaps: list[dict]               # [{element, kind: missing|needs_input, detail}] from render.py
    pruned: list[str]              # claim texts removed by prune_claims
    citations: list[dict]          # [{evidence_id, source_url, retrieved_at}] for finalize
    premise_line: str | None       # code-rendered verdict on a numeric premise (render.render_premise)
    variant_group: list[str] | None  # titles when a tie was resolved by the sibling-invariant shortcut (lead P1)
    discontinued: dict | None      # ROUND-4: data/procedure_status.yaml entry when the resolved procedure has stopped
    preset: str | None             # named flag set this run used (src/presets.py); set by the caller (CLI / web)
    assumed_variants: list[str] | None  # qualified sibling titles set aside by base_title_preference (audit finding 1)


INTENTS = ("documents", "fee", "agency", "time", "steps", "general", "update")
OUTCOMES = ("answer", "answer_partial", "clarify", "refuse", "out_of_scope")
REFUSAL_TYPES = ("out_of_scope", "ambiguous", "not_in_corpus", "insufficient_evidence", "system_error")
