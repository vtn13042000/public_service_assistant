"""The evidence record: the one shape every tool returns (architecture.md §2).

Grading, citation and support checking never care which tool produced the evidence; they read
`tier` and `evidence_id`. Tier ordering and the minimum tier per claim type follow guardrails.md §2 (L2).
"""
from __future__ import annotations

import hashlib
from typing import Literal, TypedDict

Tier = Literal["db", "corpus", "web_official", "web_other"]


class Evidence(TypedDict):
    evidence_id: str        # "db:required_documents:KS-01:3" | "doc:KS-01:required_documents:2" | "web:…"
    tier: Tier
    procedure_id: str | None
    section: str | None     # required_documents | steps | submission_method | fees | agency | processing_time | conditions | legal_basis | summary
    text: str               # what the LLM sees
    structured: dict | None # for db tier: the row (fee value, document item, agency name, …)
    source_url: str | None
    retrieved_at: str | None
    effective_date: str | None


# Highest trust first: db > corpus > web_official > web_other.
TIERS: tuple[Tier, ...] = ("db", "corpus", "web_official", "web_other")
TIER_RANK: dict[str, int] = {t: len(TIERS) - i for i, t in enumerate(TIERS)}  # db=4 … web_other=1

SECTIONS = (
    "required_documents", "steps", "submission_method", "fees", "agency",
    "processing_time", "conditions", "legal_basis", "summary",
)

# guardrails.md §2 L2: the weakest tier that may support each claim type.
MIN_TIER: dict[str, Tier] = {
    "document_item": "db",
    "fee": "db",
    "agency": "db",
    "deadline": "db",
    "steps": "corpus",
    "conditions": "corpus",
    "legal_basis": "corpus",
    "update_notice": "web_official",
}


def tier_at_least(tier: str, minimum: str) -> bool:
    """True if `tier` is as trusted as `minimum` or more. Unknown tiers are never enough."""
    return TIER_RANK.get(tier, 0) >= TIER_RANK[minimum] > 0


def can_support(tier: str, claim_type: str) -> bool:
    """Whether evidence of `tier` may support a claim of `claim_type` (L2).

    Unknown claim types fall back to `corpus` (fail closed: web never supports an unclassified fact).
    `web_other` supports nothing; it is discarded before grading.
    """
    if tier == "web_other":
        return False
    return tier_at_least(tier, MIN_TIER.get(claim_type, "corpus"))


def sort_by_tier(evidence: list[Evidence]) -> list[Evidence]:
    """Stable sort, most trusted tier first."""
    return sorted(evidence, key=lambda e: -TIER_RANK.get(e["tier"], 0))


def db_id(table: str, procedure_id: str, row: int | str) -> str:
    """`db:<table>:<procedure_id>:<row>`; `row` is the 1-based position (or index) inside that procedure."""
    return f"db:{table}:{procedure_id}:{row}"


def doc_id(procedure_id: str, section: str, i: int) -> str:
    """`doc:<procedure_id>:<section>:<i>`; `i` is the chunk index within that section."""
    return f"doc:{procedure_id}:{section}:{i}"


def web_id(url: str) -> str:
    """`web:<12 hex>`; a stable hash of the URL, so ids stay short and contain no `:`/`]` from the URL."""
    return "web:" + hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:12]


def make_evidence(
    evidence_id: str,
    tier: Tier,
    text: str,
    *,
    procedure_id: str | None = None,
    section: str | None = None,
    structured: dict | None = None,
    source_url: str | None = None,
    retrieved_at: str | None = None,
    effective_date: str | None = None,
) -> Evidence:
    """Build a validated Evidence record (raises ValueError on a bad tier/section/id prefix or empty text)."""
    if tier not in TIER_RANK:
        raise ValueError(f"unknown tier {tier!r}")
    if section is not None and section not in SECTIONS:
        raise ValueError(f"unknown section {section!r}")
    expected = {"db": "db:", "corpus": "doc:", "web_official": "web:", "web_other": "web:"}[tier]
    if not evidence_id.startswith(expected):
        raise ValueError(f"evidence_id {evidence_id!r} does not match tier {tier!r} (expected prefix {expected!r})")
    if not text or not text.strip():
        raise ValueError("evidence text is empty")
    return Evidence(
        evidence_id=evidence_id,
        tier=tier,
        procedure_id=procedure_id,
        section=section,
        text=text.strip(),
        structured=structured,
        source_url=source_url,
        retrieved_at=retrieved_at,
        effective_date=effective_date,
    )
