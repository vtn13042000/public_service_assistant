"""Self-RAG-style reflection (guardrails.md §3): retrieve? → relevant? → supported?

Pure functions that take an LLM and return verdicts. They make no routing decisions; the edge
functions in `graph.py` read the verdicts and choose the next node.

| Self-RAG token | function            | how                                                          |
|----------------|---------------------|--------------------------------------------------------------|
| Retrieve       | `assess_need`       | one structured LLM call                                      |
| ISREL          | `grade_relevance`   | one batched structured call; parse failure → irrelevant      |
| ISSUP          | `check_support`     | per claim: `db:` cites by code, `doc:` cites by LLM, uncited → unsupported |

Fail-closed everywhere: a reply that does not parse is never read as "relevant" or "supported".
Transport errors (Ollama down, timeout) are *not* swallowed here; they propagate so the node
wrapper can route to `refuse_redirect(system_error)`.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from string import Template
from typing import Literal

from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, Field, ValidationError

from src.evidence import Evidence, can_support

PROMPTS = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> Template:
    return Template((PROMPTS / f"{name}.txt").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- structured LLM calls

class Need(BaseModel):
    in_scope: bool
    retrieve: bool
    intent: Literal["documents", "fee", "agency", "time", "steps", "general", "update"] = "general"
    procedure_hint: str = ""
    locality: str | None = None
    premise: str | None = None


class RelevanceItem(BaseModel):
    idx: int
    relevant: bool
    reason: str = ""


class Relevance(BaseModel):
    items: list[RelevanceItem] = Field(default_factory=list)


class Support(BaseModel):
    relevant: bool = True
    supported: Literal["fully", "partial", "no"]
    reason: str = ""


class ReflectionParseError(ValueError):
    """The LLM's reply could not be parsed into the expected structure."""


_THINK = re.compile(r"<think>.*?</think>", re.S)
_CJK = re.compile(r"[\u3000-\u9fff\uac00-\ud7af\uf900-\ufaff]+")


def message_text(msg) -> str:
    """Text of an LLM reply with any <think> block removed."""
    content = getattr(msg, "content", msg)
    if isinstance(content, list):  # content blocks
        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return _THINK.sub("", str(content)).strip()


def parse_json(text: str, model: type[BaseModel]) -> BaseModel | None:
    """First JSON object in `text` validated against `model`; None on any failure."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return model.model_validate(json.loads(text[start:end + 1]))
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None


def _bind_json(llm, model: type[BaseModel]):
    """Ask Ollama for schema-constrained JSON when the model is a ChatOllama; other models get the prompt only."""
    if "Ollama" in type(llm).__name__:
        return llm.bind(format=model.model_json_schema())
    return llm


def _factory(llm):
    """A structured-output factory `schema -> Runnable(prompt -> schema instance)`, if `llm` provides one.

    Accepted: `src.llm.get_structured_judge` / `get_structured_llm` themselves (plain callables: Ollama
    /api/generate with the schema as `format`, the only constrained path on Ollama 0.30.8 — see w-infra
    STATUS), or any object with a `.structured(schema)` method (tests/fakes.py)."""
    if hasattr(llm, "structured"):
        return llm.structured
    if callable(llm) and not hasattr(llm, "invoke"):
        return llm
    return None


def structured_call(llm, prompt: str, model: type[BaseModel]) -> BaseModel | None:
    """One LLM call parsed into `model`. Transport errors propagate; parse failures return None."""
    factory = _factory(llm)
    if factory is not None:
        try:
            out = factory(model).invoke(prompt)
        except (ValidationError, json.JSONDecodeError, OutputParserException):
            return None
        if isinstance(out, model):
            return out
        return parse_json(message_text(out), model) if not isinstance(out, BaseModel) else None
    reply = _bind_json(llm, model).invoke(prompt)
    return parse_json(message_text(reply), model)


# ---------------------------------------------------------------- Retrieve (L0)

def assess_need(llm, query: str) -> dict:
    """`need` dict (architecture.md §3). Raises ReflectionParseError if the reply does not parse:
    without a parsed need there is no safe default, so the graph refuses with `system_error`."""
    out = structured_call(llm, load_prompt("assess_need").substitute(query=query), Need)
    if out is None:
        raise ReflectionParseError("assess_need: unparseable reply")
    need = out.model_dump()
    # qwen3.5 sometimes leaks CJK into the hint (observed: "đăng ký常住户口"); keep Vietnamese/Latin text only
    need["procedure_hint"] = re.sub(r"\s+", " ", _CJK.sub(" ", need.get("procedure_hint") or "")).strip()
    if need["in_scope"] and (need["procedure_hint"] or need.get("premise")):
        need["retrieve"] = True  # a named procedure or an asserted fact always needs evidence (observed: qwen3.5 said false)
    for k in ("locality", "premise"):
        if isinstance(need.get(k), str) and not need[k].strip():
            need[k] = None
    return need



class StoryName(BaseModel):
    procedure_name: str = ""


def story_rewrite(llm, query: str) -> str:
    """ROUND-2 item 5 (P22): one call naming the official procedure behind a story-style question.
    Parse failure or no name → "" (the resolver keeps its "none"); the name still has to clear the same
    lexical coverage floor against real titles, so an invented name cannot create a match."""
    out = structured_call(llm, load_prompt("story_rewrite").substitute(query=query), StoryName)
    name = "" if out is None else _CJK.sub(" ", out.procedure_name or "")
    return re.sub(r"\s+", " ", name).strip()


# ---------------------------------------------------------------- ISREL (L3)

def _wrap_docs(evidence: list[Evidence]) -> str:
    return "\n".join(
        f'<tai_lieu idx="{i}" id="{e["evidence_id"]}">\n{e["text"]}\n</tai_lieu>' for i, e in enumerate(evidence)
    )


def grade_relevance(llm, query: str, evidence: list[Evidence]) -> list[bool]:
    """One batched call; one bool per evidence item. Missing, duplicated-false or unparseable → False."""
    if not evidence:
        return []
    prompt = load_prompt("grade_relevance").substitute(query=query, documents=_wrap_docs(evidence))
    out = structured_call(llm, prompt, Relevance)
    verdicts = [False] * len(evidence)
    if out is None:
        return verdicts
    for item in out.items:
        if 0 <= item.idx < len(evidence) and item.relevant is True:
            verdicts[item.idx] = True
    return verdicts


# ---------------------------------------------------------------- claims

_CITE = re.compile(r"\[((?:db|doc|web):[^\]]+)\]")
_LIST_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-•*])\s+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_NEGATION = re.compile(r"^\W*(không|sai|chưa đúng|chưa chính xác|tùy trường hợp)\b|không phải|không đúng|chưa đúng|chưa chính xác", re.I)

# keyword classes for claims that do not cite a db row (L2 claim types, evidence.MIN_TIER keys)
_KIND_PATTERNS = [
    ("fee", re.compile(r"lệ phí|\bphí\b|đồng\b|\bvnđ\b|\d\s*đ\b|miễn phí", re.I)),
    ("deadline", re.compile(r"ngày làm việc|thời hạn|thời gian giải quyết|\d+\s*(ngày|giờ|tháng)\b", re.I)),
    ("agency", re.compile(r"\bubnd\b|ủy ban|uỷ ban|\bsở\b|\bbộ (tư pháp|công an|ngoại giao)|công an|cơ quan|bộ phận một cửa", re.I)),
    ("document_item", re.compile(r"tờ khai|giấy|bản sao|bản chính|hộ chiếu|căn cước|chứng minh|sổ hộ khẩu|văn bản", re.I)),
]
_SECTION_KIND = {
    "required_documents": "document_item", "fees": "fee", "agency": "agency", "processing_time": "deadline",
    "steps": "steps", "conditions": "conditions", "legal_basis": "legal_basis",
    "submission_method": "steps", "summary": "conditions",
}
CORE_NARRATIVE_INTENTS = {"steps", "general", "update"}
STRUCTURED_KINDS = {"fee", "agency", "document_item", "deadline"}


def cited_ids(text: str) -> list[str]:
    """Evidence ids cited in `text`; one bracket may hold several ids separated by , or ;."""
    ids: list[str] = []
    for group in _CITE.findall(text):
        for part in re.split(r"[;,]\s*", group):
            part = part.strip()
            if part and part not in ids:
                ids.append(part)
    return ids


# ROUND-2 item 8 (config citation_parse="tolerant"): repair citation FORMAT in the LLM narrative before claims are split.
# It never makes an id valid: every id that survives still has to exist in state (check_support rule 2, F11).
_LOOSE_CITE = re.compile(r"\[\s*(db|doc|web)\s*:\s*([^\]\n]*?)\s*\]", re.I)
EXAMPLE_IDS = frozenset({"doc:KS-01:steps:0", "db:fees:KS-01:1"})  # the ids shown as examples in draft_answer_v1.txt


def repair_tier(cid: str, known: set[str]) -> str | None:
    """Round-4 item (d): the gathered id that a citation with a wrong tier prefix or a dropped procedure id names.
    `[db:legal_basis:4e2497d4-0]` → `doc:1.001193:legal_basis:4e2497d4-0` when exactly one gathered id ends with the cited
    segments after the scheme (at least two, compared case-insensitively). None if ambiguous or nothing matches.
    The repaired id then goes through the same tier rule and support check as any other citation."""
    tail = [s.lower() for s in cid.split(":")[1:]]
    if len(tail) < 2 or cid in EXAMPLE_IDS:
        return None
    hits = [k for k in known if [s.lower() for s in k.split(":")[1:]][-len(tail):] == tail]
    return hits[0] if len(hits) == 1 else None


def normalize_citations(text: str, known_ids, *, repair: bool = False, repairs: list | None = None) -> str:
    """Tolerant citation parsing for the narrative:
    1. spacing/case variants `[ DB : fees:x:1 ]` → `[db:fees:x:1]` (an id is re-cased only to an id that exists);
    2. a copied prompt example id that is NOT in state is removed (the claim is then uncited and judged as such);
    3. a citation written after the full stop ("Câu một. [doc:a] Câu hai") moves back to the sentence before it,
       when that sentence has no citation of its own; a leading-citation style "[doc:a] Câu một." is left alone.
    4. with `repair` (flag citation_repair="tier"): an unknown id whose tail names exactly one gathered id is mapped to
       it (`repair_tier`); each (cited, repaired) pair is appended to `repairs`.
    Unknown ids other than the examples are kept, so they still fail as fabricated citations."""
    known = set(known_ids)
    by_lower = {k.lower(): k for k in known}

    def fix(m: re.Match) -> str:
        ids = []
        for part in re.split(r"\s*[;,]\s*", m.group(2)):
            part = re.sub(r"\s*:\s*", ":", part.strip())
            if not part:
                continue
            scheme = re.match(r"^(db|doc|web):", part, re.I)  # a later id in a group repeats its own scheme
            cid = f"{scheme.group(1).lower()}:{part[scheme.end():]}" if scheme else f"{m.group(1).lower()}:{part}"
            cid = cid if cid in known else by_lower.get(cid.lower(), cid)
            if cid in EXAMPLE_IDS and cid not in known:
                continue
            if repair and cid not in known:
                fixed = repair_tier(cid, known)
                if fixed:
                    if repairs is not None:
                        repairs.append((cid, fixed))
                    cid = fixed
            ids.append(cid)
        return f"[{', '.join(ids)}]" if ids else ""

    lines = []
    for line in text.splitlines():
        line = _LOOSE_CITE.sub(fix, line)
        out: list[str] = []
        for seg in _SENT_SPLIT.split(line.strip()) if line.strip() else []:
            lead = re.match(r"^((?:\[(?:db|doc|web):[^\]]+\]\s*)+)(.*)$", seg)
            if lead and out and not cited_ids(out[-1]) and lead.group(2).strip():
                prev = out[-1].rstrip()
                cites = lead.group(1).strip()
                out[-1] = f"{prev[:-1]} {cites}{prev[-1]}" if prev[-1:] in ".!?" else f"{prev} {cites}"
                seg = lead.group(2).strip()
            out.append(seg)
        lines.append(re.sub(r"[ \t]+([.!?,;])", r"\1", " ".join(out)))
    return "\n".join(lines)


def strip_cites(text: str) -> str:
    return re.sub(r"\s+", " ", _CITE.sub("", text)).strip()


def keyword_kind(text: str) -> str:
    """L2 claim type guessed from wording; 'general' if none matches."""
    for kind, pat in _KIND_PATTERNS:
        if pat.search(text):
            return kind
    return "general"


def _sentences(line: str) -> list[str]:
    parts = [p for p in _SENT_SPLIT.split(line.strip()) if p.strip()]
    out: list[str] = []
    carry = ""
    for p in parts:
        if out and not strip_cites(p):  # a segment that is only citations belongs to the sentence before it
            out[-1] = f"{out[-1]} {p}"
        elif not cited_ids(p) and len(p.split()) <= 3:  # "Không." / "Đúng." opens the next sentence
            carry = f"{carry} {p}".strip()
        else:
            out.append(f"{carry} {p}".strip())
            carry = ""
    if carry:
        out.append(carry)
    return out


def split_claims(draft: str, *, block: str = "", intent: str | None = None, premise: str | None = None) -> list[dict]:
    """Split a draft into claims at sentence / list-item level.

    Lines that belong to the code-rendered `block` are one claim each, always `core`.
    Narrative claims are `minor` unless the intent is answered by narrative (steps/general/update)
    and the claim is cited (an uncited sentence is unsupported anyway; as minor it is pruned, not fatal). When the user asserted a `premise`, the first narrative claim
    is the one that addresses it: type `core`, origin `premise`. If there is none, a synthetic
    unsupported core claim records that the premise was not addressed.
    Header lines that end with ':' and cite nothing are not claims.
    """
    block_lines = {ln.strip() for ln in block.splitlines() if ln.strip()}
    claims: list[dict] = []
    premise_done = premise is None
    for line in draft.splitlines():
        s = line.strip()
        if not s:
            continue
        if s in block_lines:
            if s.endswith(":") and not cited_ids(s):
                continue
            claims.append(_claim(s, "core", "block"))
            continue
        pieces = [s] if _LIST_ITEM.match(s) else _sentences(s)
        for p in pieces:
            if p.endswith(":") and not cited_ids(p):
                continue
            if not premise_done:
                claims.append(_claim(p, "core", "premise"))
                premise_done = True
                continue
            core = intent in CORE_NARRATIVE_INTENTS and bool(cited_ids(p))
            if core and intent in ("general", "update") and keyword_kind(p) in STRUCTURED_KINDS:
                core = False  # the code-rendered block already answers fee/agency/documents/deadline
            claims.append(_claim(p, "core" if core else "minor", "narrative"))
    if not premise_done:
        c = _claim(f"Nhận định của người hỏi chưa được trả lời: {premise}", "core", "premise")
        c["verdict"], c["reason"] = "unsupported", "premise not addressed in draft"
        c["synthetic"] = True
        claims.append(c)
    return claims


def _claim(text: str, ctype: str, origin: str) -> dict:
    return {"text": text, "type": ctype, "origin": origin, "evidence_ids": cited_ids(text),
            "kind": None, "verdict": "unknown", "reason": ""}


# ---------------------------------------------------------------- ISSUP (L4): code checks

def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", str(s)).lower().replace("uỷ", "ủy")
    s = re.sub(r"[“”\"'`]", "", s)
    return re.sub(r"\s+", " ", s).strip(" .;:,")


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers(text: str) -> set[str]:
    """Numbers in `text`, thousands separators removed and leading zeros dropped ("50.000" → "50000", "01" → "1")."""
    out = set()
    for m in _NUM.findall(text):
        d = re.sub(r"[.,]", "", m).lstrip("0") or "0"
        out.add(d)
    return out


def _claim_body(text: str) -> str:
    return _LIST_ITEM.sub("", strip_cites(text), count=1)


def _haystack(evs: list[Evidence]) -> str:
    parts: list[str] = []
    for e in evs:
        parts.append(e["text"])
        for v in (e.get("structured") or {}).values():
            if v is not None:
                parts.append(str(v))
        for k in ("retrieved_at", "effective_date", "procedure_id", "source_url"):
            if e.get(k):
                parts.append(str(e[k]))
    return " \n ".join(parts)


def check_db_claim(text: str, rows: list[Evidence]) -> tuple[bool, str]:
    """Programmatic check of a claim against the db rows it cites.

    - every number in the claim appears in a cited row (or its date/id fields);
    - a cited document row: its `item` is stated in the claim (`phrase_in`: all content tokens);
    - a cited fee row: its `value` is stated in the claim (`phrase_in`, fee rule);
    - a cited agency row: its `name` is stated in the claim (all content tokens);
    - a claim about "thời gian" citing a procedure row: its `processing_time` appears verbatim (F14).
    The claim passes the item/value/name test if at least one cited row of that kind matches.
    """
    body = _claim_body(text)
    nbody = norm(body)
    hay = _haystack(rows)
    missing = numbers(body) - numbers(hay)
    if missing:
        return False, f"numbers not in cited rows: {sorted(missing)}"
    for key, label in (("item", "document item"), ("value", "fee value"), ("name", "agency name")):
        vals = [str(r["structured"][key]) for r in rows if (r.get("structured") or {}).get(key)]
        if vals and not any(phrase_in(v, body, fee=(key == "value")) for v in vals):
            return False, f"{label} of cited row not in claim"
    pts = [str(r["structured"]["processing_time"]) for r in rows if (r.get("structured") or {}).get("processing_time")]
    if pts and "thời gian" in nbody and not any(phrase_in(p, body) for p in pts):
        return False, "processing_time not in claim"
    return True, "matches cited db rows"


# token-level phrase matching for the code checks: accent-folded, abbreviations expanded, "01" == "1"
_ABBREV = {"hdnd": "hoi dong nhan dan", "ubnd": "uy ban nhan dan", "tt": "thong tu", "nd": "nghi dinh",
           "cccd": "can cuoc cong dan", "cmnd": "chung minh nhan dan", "qd": "quyet dinh"}
_STOP = frozenset("theo so cua va la duoc do cho voi tai trong mot cac nhung ve thi".split())


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower()).replace("đ", "d")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _content_tokens(s: str) -> set[str]:
    out: set[str] = set()
    for t in re.findall(r"\w+", _fold(s)):
        for u in _ABBREV.get(t, t).split():
            u = (u.lstrip("0") or "0") if u.isdigit() else u
            if u not in _STOP:
                out.add(u)
    return out


def phrase_in(phrase: str, claim: str, *, fee: bool = False) -> bool:
    """Does `claim` state `phrase`? Verbatim (normalised) or every content token present (abbreviations
    expanded, accents folded, leading zeros dropped). Fee values also pass when all their numbers are in
    the claim and ≥ 75% of their tokens are ("TT 281/2016" for "Thông tư số 281/2016/TT-BTC").
    Document items and agency names need every content token: a near-miss item must fail."""
    if norm(phrase) in norm(claim):
        return True
    p, c = _content_tokens(phrase), _content_tokens(claim)
    if not p or p <= c:
        return bool(p)
    if fee and numbers(phrase) and numbers(phrase) <= numbers(claim):
        return len(p & c) / len(p) >= 0.75
    return False


def premise_consistent(claim_text: str, premise: str, rows: list[Evidence]) -> tuple[bool | None, str]:
    """Polarity check for a premise claim when the premise contains numbers.

    The premise is true iff all its numbers appear in the cited rows. A true premise must not be
    negated in the claim; a false one must be. Returns None when the premise has no numbers
    (left to the LLM judgment)."""
    pnums = numbers(premise)
    if not pnums:
        return None, "premise has no numbers"
    true = pnums <= numbers(_haystack(rows))
    negates = bool(_NEGATION.search(strip_cites(claim_text)))
    if true and negates:
        return False, "premise matches the record but the claim denies it"
    if not true and not negates:
        return False, "premise contradicts the record but the claim does not say so"
    return True, f"premise is {'true' if true else 'false'} per record; claim agrees"


_VERDICT_WORD = re.compile(r"^\W*(đúng|không|sai|chưa đúng|phải)\b", re.I)


def premise_narrative_check(c: dict, premise: str, evidence: list[Evidence]) -> dict:
    """When the premise was answered by code, a narrative sentence that also opens with a verdict word
    ("Đúng…", "Không…") must agree with the record (polarity check against the fee/time rows)."""
    if c.get("origin") != "narrative" or c.get("verdict") != "supported" or not _VERDICT_WORD.search(strip_cites(c["text"])):
        return c
    rows = [e for e in evidence if e["tier"] == "db" and e.get("section") in ("fees", "processing_time")]
    ok, reason = premise_consistent(c["text"], premise, rows)
    return {**c, "verdict": "unsupported", "reason": reason} if ok is False else c


# ---------------------------------------------------------------- ISSUP: the hybrid check

def judge_support(llm, claim_text: str, evs: list[Evidence]) -> tuple[str, str]:
    """LLM judgment of one claim against the cited chunks only. Parse failure → 'no'."""
    ctx = "\n\n".join(f"[{e['evidence_id']}]\n{e['text']}" for e in evs)
    prompt = load_prompt("check_support").substitute(ctx=ctx, claim=strip_cites(claim_text))
    out = structured_call(llm, prompt, Support)
    if out is None:
        return "no", "unparseable judge reply"
    return out.supported, out.reason


def check_support(llm, claims: list[dict], evidence: list[Evidence], *, premise: str | None = None,
                  code_checks: bool = True) -> list[dict]:
    """Fill `verdict` (supported | partial | unsupported), `kind` and `reason` on every claim.

    Order of rules for one claim:
    1. no citation → unsupported (uncited factual claims are never trusted);
    2. a cited id not present in `evidence` → unsupported (fabricated citation, F11);
    3. `db:` cites present → code check against those rows (+ premise polarity);
    4. otherwise the claim type (from the cited section, or wording for web) must be supportable by
       the cited tier (L2); a claim that names an authority or a deadline must also agree with the
       procedure's db rows, and never rests on an amended original legal text (`db_backed_authority`);
       then numbers must appear in the cited text; then one LLM judgment
       against those chunks only: fully → supported, partial → partial, no → unsupported.
    `code_checks=False` (ablation llm_support): rules 1–2 kept, every cited claim (db: included) goes to the
    LLM judgment against its cited evidence; no code check, no premise polarity, no tier check.
    """
    by_id = {e["evidence_id"]: e for e in evidence}
    out: list[dict] = []
    for c in claims:
        c = dict(c)
        if c.get("synthetic"):
            out.append(c)
            continue
        verdict, kind, reason = _verdict(llm, c, by_id, premise) if code_checks else _llm_only(llm, c, by_id)
        c.update(verdict=verdict, kind=kind, reason=reason)
        out.append(c)
    return out


def _verdict(llm, c: dict, by_id: dict, premise: str | None) -> tuple[str, str, str]:
    ids = c["evidence_ids"]
    if not ids:
        return "unsupported", keyword_kind(c["text"]), "no citation"
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        return "unsupported", keyword_kind(c["text"]), f"cited ids not in evidence: {unknown}"
    evs = [by_id[i] for i in ids]
    db_rows = [e for e in evs if e["tier"] == "db"]
    is_premise = c.get("origin") == "premise" and premise

    if db_rows:
        kind = _SECTION_KIND.get(db_rows[0].get("section") or "", keyword_kind(c["text"]))
        ok, reason = check_db_claim(c["text"], db_rows)
        if not ok:
            return "unsupported", kind, reason
        if kind == "agency":  # an agency claim citing its row next to an old legal chunk must not add "cấp huyện"
            ok, lreason = authority_level_ok(c["text"], evs, by_id)  # (document items name issuers: not checked)
            if not ok:
                return "unsupported", kind, lreason
        if is_premise:
            pol, preason = premise_consistent(c["text"], premise, db_rows)
            if pol is False:
                return "unsupported", kind, preason
            if pol is None:
                verdict, jreason = judge_support(llm, c["text"], db_rows)
                return _map(verdict), kind, f"premise judged by LLM: {jreason}"
            return "supported", kind, f"{reason}; {preason}"
        return "supported", kind, reason

    sec = evs[0].get("section") or ""
    kind = _SECTION_KIND.get(sec, "conditions") if evs[0]["tier"] == "corpus" else keyword_kind(c["text"])
    if not all(can_support(e["tier"], kind) for e in evs):
        return "unsupported", kind, f"tier {[e['tier'] for e in evs]} cannot support a {kind} claim (L2)"
    ok, areason = db_backed_authority(c["text"], evs, by_id)
    if not ok:
        return "unsupported", kind, areason
    missing = numbers(_claim_body(c["text"])) - numbers(_haystack(evs))
    if missing:
        return "unsupported", kind, f"numbers not in cited text: {sorted(missing)}"
    verdict, jreason = judge_support(llm, c["text"], evs)
    return _map(verdict), kind, f"LLM: {jreason}"


# ROUND-4 guard: corpus v2 adds the originally issued legal articles (marked AMENDED_MARK), written before the 2025
# two-tier reform moved district (cấp huyện) powers to the commune. Authority and deadline facts come from db rows only.
AMENDED_MARK = "[Văn bản gốc – đã sửa đổi]"
_AUTHORITY = re.compile(r"\bubnd\b|ủy ban|uỷ ban|\bsở\b|(?<!cán )\bbộ (tư pháp|công an|ngoại giao)|công an|cơ quan|bộ phận một cửa"
                        r"|phòng tư pháp|chủ tịch|cấp (xã|huyện|tỉnh)|\b(nộp|gửi|tiếp nhận|giải quyết)\b[^.;]{0,40}\btại\b", re.I)
_DEADLINE = _KIND_PATTERNS[1][1]
# administrative levels named in a text; "thị xã" is district level, so it is removed before the commune test
_LEVELS = (("huyen", re.compile(r"cấp huyện|\bhuyện\b|\bquận\b|thị xã|phòng tư pháp", re.I)),
           ("xa", re.compile(r"cấp xã|\bxã\b|\bphường\b|thị trấn", re.I)),
           ("tinh", re.compile(r"cấp tỉnh|\btỉnh\b|thành phố trực thuộc trung ương|\bsở\b", re.I)),
           ("tw", re.compile(r"trung ương|(?<!cán )\bbộ (tư pháp|công an|ngoại giao)\b|\bcục\b", re.I)))


_DENIED = re.compile(r"(chứ\s+)?không\s+phải(\s+là)?\s+[^,.;]*?(?=\s+mà\b|[,.;]|$)", re.I)


def levels(text: str) -> set[str]:
    """Administrative levels (xa / huyen / tinh / tw) named in `text`."""
    out = set()
    for name, pat in _LEVELS:
        t = re.sub(r"thị xã", " ", text, flags=re.I) if name == "xa" else text
        if pat.search(t):
            out.add(name)
    return out


def _procedure_db_rows(evs: list[Evidence], by_id: dict) -> list[Evidence]:
    pids = {e.get("procedure_id") for e in evs}
    return [e for e in by_id.values() if e["tier"] == "db" and e.get("procedure_id") in pids]


def authority_level_ok(text: str, evs: list[Evidence], by_id: dict) -> tuple[bool, str]:
    """Every administrative level the claim names for an authority must occur in the procedure's db agency rows or db
    summary row ("Cấp thực hiện: cấp tỉnh"). Used for corpus cites and for claims citing a db agency row (one citing that
    row next to an old legal chunk must not slip "cấp huyện" through). A mention without a level ("bộ phận một cửa") passes."""
    body = _claim_body(text)
    asserted = _DENIED.sub(" ", body)  # "… là UBND cấp xã chứ không phải Sở Tư pháp": the denied level is not claimed
    named = levels(asserted) if _AUTHORITY.search(body) else set()
    if not named:
        return True, ""
    ref = " ".join(e["text"] for e in _procedure_db_rows(evs, by_id)
                   if e.get("section") == "agency" or e.get("evidence_id", "").endswith(":summary"))
    if not ref:
        return False, "authority level named but no db agency/summary row to check it against"
    if named - levels(ref):
        return False, f"authority level {sorted(named - levels(ref))} not in db agency row"
    return True, ""


def db_backed_authority(text: str, evs: list[Evidence], by_id: dict) -> tuple[bool, str]:
    """A narrative claim citing corpus/web text that names an authority, place of submission or deadline.

    - never supported by an amended original legal text (chunk text carries AMENDED_MARK);
    - authority: every administrative level it names (xã / huyện / tỉnh / trung ương) must occur in the procedure's db
      agency rows or its db summary row ("Cấp thực hiện"); no such row → fail; a mention without a level goes to the judge;
    - deadline: its numbers must occur in the procedure's db processing_time row (no such row → fail).
    Claims that name neither pass unchanged. No flag: this is a safety rule (ROUND-4 guard)."""
    body = _claim_body(text)
    authority, deadline = bool(_AUTHORITY.search(body)), bool(_DEADLINE.search(body))
    if not (authority or deadline):
        return True, ""
    if any(AMENDED_MARK in (e.get("text") or "") for e in evs):
        return False, "authority/deadline cited to an amended original legal text (db rows only)"
    ok, reason = authority_level_ok(text, evs, by_id)
    if not ok:
        return False, reason
    rows = _procedure_db_rows(evs, by_id)
    if deadline:
        ptime = " ".join(e["text"] for e in rows if e.get("evidence_id", "").endswith(":processing_time"))
        if not ptime:
            return False, "deadline named but no db processing_time row to check it against"
        if numbers(body) - numbers(ptime):
            return False, f"deadline numbers {sorted(numbers(body) - numbers(ptime))} not in db processing_time row"
    return True, ""


def _llm_only(llm, c: dict, by_id: dict) -> tuple[str, str, str]:
    ids = c["evidence_ids"]
    if not ids:
        return "unsupported", keyword_kind(c["text"]), "no citation"
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        return "unsupported", keyword_kind(c["text"]), f"cited ids not in evidence: {unknown}"
    verdict, jreason = judge_support(llm, c["text"], [by_id[i] for i in ids])
    return _map(verdict), keyword_kind(c["text"]), f"LLM only (ablation): {jreason}"


def _map(v: str) -> str:
    return {"fully": "supported", "partial": "partial"}.get(v, "unsupported")


def support_summary(claims: list[dict]) -> str:
    """'all_supported' | 'minor_unsupported' | 'core_unsupported' — what `after_decide` reads."""
    bad = [c for c in claims if c.get("verdict") != "supported"]
    if any(c["type"] == "core" for c in bad):
        return "core_unsupported"
    if bad:
        return "minor_unsupported"
    return "all_supported"
