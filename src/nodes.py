"""Graph nodes (architecture.md §5). Each node is a thin function state -> partial state.

Nodes call tools / self_rag / render / refusal and write only the fields they own. Routing lives in
the edge functions in `graph.py`. `make_nodes(deps)` closes over injected dependencies so tests can
pass fakes (tests/fakes.py) and the CLI passes the real tools.

Fail-closed (L6): every node runs inside `_guarded`; an exception is appended to `errors` and every
later node becomes a no-op until an edge routes to `refuse_redirect(system_error)`. Two tool calls are
deliberately non-fatal and say so in state: `web_lookup` (already on the refusal path) and `web_check`
(notice-only; a failure adds the generic verify-at-counter notice instead).
"""
from __future__ import annotations

import contextvars
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from langchain_core.runnables import RunnableConfig

from src import render, self_rag
from src.families import load_family_nouns, nouns_in, title_has
from src.refusal import build_refusal
from src.self_rag import load_prompt, message_text

# ---------------------------------------------------------------- tunable constants (one place; see STATUS.md)

# resolve_procedure: score = LEX_WEIGHT * lexical(hint, title) + (1 - LEX_WEIGHT) * rrf_norm
RESOLVE = {
    "lex_weight": 0.6,    # weight of title-token F1 (absolute scale) vs normalised RRF rank score (relative scale)
    "core_floor": 0.75,   # top candidate's hint-word coverage (see `coverage`) below this → none → web_lookup
    "lex_floor": 0.34,    # (kept for the plain-marker root check) full title-token F1 floor
    "gap": 0.08,          # a non-sibling within this of the top → clarify
    "sibling_gap": 0.25,  # a variant_of sibling within this of the top → clarify (w-tools: KS-01 ranks under KS-02)
    "max_options": 4,     # candidates shown in a clarify prompt
    "k": 5,               # candidates from each source
    "f2_rule": None,      # round 2, item 1 (flag, default off): "distinguishing_words" → see `choose`
    "base_title_preference": False,  # audit finding 1 (flag, default off): see `choose` and `qualifier_said`
    "head_noun_guard": False,  # owner trace c26ce7e9 (flag, default off; v5 candidate): see `_head_noun_filter`
}
F2_RULES = (None, "distinguishing_words")
SCOPE_GATES = (None, "in_scope")  # Round-4 item (c), flag: "in_scope" → an in-scope question always reaches the resolver
# the prompt's own out-of-scope definition: a personal eligibility verdict ("tôi có được … không", "có đủ điều kiện …"),
# accent-folded and with chat spellings (đc, ko, hok). Such a question keeps the out_of_scope route under scope_gate.
_ELIGIBILITY = re.compile(r"\bco\b[^,.;?!]{0,40}?\b(duoc|dc)\s+(khong|ko|k|kg|hok|hong)\b|\bco du dieu kien\b")
# words that pick the plain (root) variant of a family, e.g. "khai sinh trong nước, lần đầu" → KS-01 not KS-02/KS-03
PLAIN_MARKERS = ("trong nuoc", "lan dau", "thong thuong", "dung han")
# a sibling whose title adds one of these (and the hint does not) is a different action, not a hidden variant:
# "đăng ký thường trú" never means "xóa đăng ký thường trú"; "đăng ký khai sinh" never means "đăng ký lại khai sinh"
ACTION_WORDS = frozenset("xoa lai doi cham dut ghi gia han tach sao trich luc huy thay cai chinh bo sung giam sat".split())
# words shared by many titles; ignored by the "none" floor so "nhập tịch … công dân Việt Nam … nước ngoài" does not
# match "ghi vào Sổ hộ tịch việc kết hôn của công dân Việt Nam … nước ngoài" (accent-folded)
# (not "doi": folded "đổi" is the action of "cấp đổi"; not "can": folded "căn" of "căn cước")
GENERIC = frozenset("""thu tuc dang ky cong dan viet nam nguoi cho cua va co yeu to nuoc ngoai thuc hien tai cap
    voi viec da duoc trong o la cac nhung khu vuc bien gioi ho so giay to theo lam lan dau bao nhieu gi
    the nao dau xin nop mat lau phai khong toi minh hay hoi muon thi ai khi
    cuc canh sat quan ly hanh chinh an bo phong so uy ban nhan xa huyen tinh trung uong""".split())
CHUNKS_K = 5              # corpus chunks per gather_evidence
STALE_DAYS = 180          # freshness: oldest retrieved_at older than this → web_check
MAX_REWRITES = 1          # iteration ≤ 1 (architecture.md §4)
CITATION_PARSE = "tolerant"  # ROUND-2 item 8 (default on after a held-out pass with no regression; "strict" = v1): repairs citation format in the narrative (self_rag.normalize_citations)
RRF_K = 60                # src/tools/rag.py RRF constant; max RRF score of 2 lists = 2/(RRF_K+1)
# ROUND-4: procedures no longer performed (procedure_id → {status, since, basis, notice_doc_id, notice_url, redirect})
PROCEDURE_STATUS_PATH = Path(__file__).resolve().parents[1] / "data" / "procedure_status.yaml"


def load_procedure_status(path: Path | str = PROCEDURE_STATUS_PATH) -> dict[str, dict]:
    """The discontinued-procedure table; a missing file means none. Only `status: discontinued` entries are kept."""
    p = Path(path)
    if not p.exists():
        return {}
    import yaml
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {str(k): dict(v) for k, v in data.items() if (v or {}).get("status") == "discontinued"}

# eval ablations (w-eval request, lead-approved); default None = full guardrailed graph
#   no_resolve:   L1 off — rank-1 RAG candidate is trusted (no thresholds, no clarify) and corpus retrieval is
#                 not filtered by procedure_id (db rows still come from that rank-1 id, the only way to get rows)
#   llm_support:  L4 code checks off — every cited claim (db: included) is judged by the LLM; premise polarity
#                 check and the finalize code re-check are off too, so the ablation is not masked
ABLATIONS = (None, "no_resolve", "llm_support")

INTENT_SECTION = {"documents": "required_documents", "fee": "fees", "agency": "agency", "time": "processing_time",
                  "steps": ["steps", "submission_method"], "general": None, "update": None}


@dataclass
class Deps:
    llm: Any                                  # chat model: narrative (draft_answer) and rewrite_query
    rag: Any                                  # has retrieve(query, procedure_id, section, k) and resolve_candidates(query, k)
    db: Any                                   # has search_titles, get_procedure, get_required_documents, get_fees, get_agency
    web: Callable | None = None               # web_search(query) -> list[Evidence]
    judge: Any = None                         # ISREL/ISSUP: structured factory (src.llm.get_structured_judge) or chat model; defaults to llm
    classifier: Any = None                    # assess_need: structured factory (src.llm.get_structured_llm); defaults to judge
    today: date | None = None                 # injected for freshness tests
    trace: Callable[..., None] = lambda *a, **k: None   # set_span_metadata hook
    config: dict = field(default_factory=dict)

    def __post_init__(self):
        self.judge = self.judge or self.llm
        self.classifier = self.classifier or self.judge
        self.resolve = {**RESOLVE, **self.config.get("resolve", {})}
        if "f2_rule" in self.config:
            self.resolve["f2_rule"] = self.config["f2_rule"]
        if "base_title_preference" in self.config:
            self.resolve["base_title_preference"] = bool(self.config["base_title_preference"])
        if "head_noun_guard" in self.config:
            self.resolve["head_noun_guard"] = bool(self.config["head_noun_guard"])
        if self.resolve["head_noun_guard"]:
            self.resolve["family_nouns"] = load_family_nouns()
        if self.resolve["f2_rule"] not in F2_RULES:
            raise ValueError(f"unknown f2_rule {self.resolve['f2_rule']!r}; expected one of {F2_RULES}")
        self.stale_days = self.config.get("stale_days", STALE_DAYS)
        # ROUND-2 item 2: v2 prompt (no example citation id to copy) is the default; "v1" reproduces the first draft
        self.draft_prompt = {"v2": "draft_answer", "v1": "draft_answer_v1"}[self.config.get("draft_prompt", "v2")]
        self.story_rewrite = bool(self.config.get("story_rewrite", False))  # ROUND-2 item 5 (P22), default off
        self.citation_parse = self.config.get("citation_parse", CITATION_PARSE)  # ROUND-2 item 8
        if self.citation_parse not in ("strict", "tolerant"):
            raise ValueError(f"unknown citation_parse {self.citation_parse!r}; expected 'strict' or 'tolerant'")
        self.ablation = self.config.get("ablation")
        self.scope_gate = self.config.get("scope_gate")
        self.citation_repair = self.config.get("citation_repair")  # Round-4 item (d): "tier" (needs citation_parse tolerant)
        if self.citation_repair not in (None, "tier"):
            raise ValueError(f"unknown citation_repair {self.citation_repair!r}; expected None or 'tier'")
        if self.scope_gate not in SCOPE_GATES:
            raise ValueError(f"unknown scope_gate {self.scope_gate!r}; expected one of {SCOPE_GATES}")
        # ROUND-4 (safety, no flag): config may inject the table (tests); otherwise data/procedure_status.yaml
        self.procedure_status = self.config["procedure_status"] if "procedure_status" in self.config \
            else load_procedure_status()
        if self.ablation not in ABLATIONS:
            raise ValueError(f"unknown ablation {self.ablation!r}; expected one of {ABLATIONS}")


# The RunnableConfig LangGraph passes to the running node, so the trace hook can find the node's span
# (src.tracing.set_span_metadata(config, ...)). Context-local, so concurrent graph runs do not mix.
CURRENT_CONFIG: contextvars.ContextVar[dict | None] = contextvars.ContextVar("CURRENT_CONFIG", default=None)


def _guarded(name: str, fn: Callable[[dict], dict], *, run_on_error: bool = False):
    def node(state: dict, config: RunnableConfig = None) -> dict:  # no functools.wraps: LangGraph must see `config`
        if state.get("errors") and not run_on_error:
            return {}
        token = CURRENT_CONFIG.set(config)
        try:
            return fn(state)
        except Exception as exc:  # noqa: BLE001 — fail closed on anything (L6)
            return {"errors": list(state.get("errors") or []) + [f"{name}: {type(exc).__name__}: {exc}"]}
        finally:
            CURRENT_CONFIG.reset(token)
    node.__name__ = name
    return node


# ---------------------------------------------------------------- helpers

def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _tokens(s: str) -> list[str]:
    return re.findall(r"\w+", _fold(s))


_TITLE_PREFIX = re.compile(r"^\s*th[uủ]\s*t[uụ]c\s+", re.I)  # real titles start with "Thủ tục …"; it carries no signal


def lexical(hint: str, title: str, ignore: frozenset = frozenset()) -> float:
    """Token-set F1 between hint and title (accent-folded): an absolute 0..1 score. `ignore` drops generic words."""
    a = set(_tokens(_TITLE_PREFIX.sub("", hint))) - ignore
    b = set(_tokens(_TITLE_PREFIX.sub("", title))) - ignore
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    p, r = inter / len(b), inter / len(a)
    return 2 * p * r / (p + r)


def _locality(state: dict) -> str | None:
    return state.get("locality") or (state.get("need") or {}).get("locality")


NOTICE_WINDOW_DAYS = 365  # no source date on the record: only changes that took effect within this window
NOTICE_SHOWN = 2           # newest notices printed; the rest are counted ("và N văn bản khác")
_INSTRUMENT = re.compile(r"\b\d{1,4}/\d{4}/[A-ZĐ0-9-]+", re.I)  # "120/2025/NĐ-CP", "116/2026/TT-BCA"


def record_date(evidence: list, pid: str) -> date | None:
    """The procedure record's own source date (sources.effective_date, e.g. the Đắk Lắk annex "hiệu lực 2026-01-08").
    moj/bca rows carry none (only retrieved_at, which says when we fetched, not what the page reflects)."""
    ds = [_parse_date(e.get("effective_date")) for e in evidence
          if e.get("tier") == "db" and e.get("evidence_id", "").startswith(f"db:procedures:{pid}:")]
    ds = [d for d in ds if d]
    return max(ds) if ds else None


def notice_applies(n: dict, today: date, rec_date: date | None, legal_text: str = "") -> bool:
    """A change notice is shown when it is in force (effective_date ≤ today) and newer than what the record reflects:
    later than the record's source date, or, with no source date, within NOTICE_WINDOW_DAYS. A notice whose instrument
    number the record's legal basis already cites is reflected by the record and not shown."""
    d = _parse_date(n.get("effective_date"))
    if not d or d > today or not n.get("title") or not n.get("url"):
        return False
    if rec_date is not None and d <= rec_date:
        return False
    if rec_date is None and (today - d).days > NOTICE_WINDOW_DAYS:
        return False
    nums = {m.upper() for m in _INSTRUMENT.findall(n["title"])}
    return not (nums and nums <= {m.upper() for m in _INSTRUMENT.findall(legal_text)})


def change_notices(deps: Deps, pid: str | None, today: date, evidence: list | None = None) -> list[dict]:
    """Linked change_notice documents that apply (`notice_applies`), newest first, from the db `documents` table via
    `db.get_change_notices(pid)` → [{doc_id, title, effective_date, url}]. A db without that query (corpus v1) or a
    failing one yields none: the notice is extra, the answer path does not depend on it."""
    fn = getattr(deps.db, "get_change_notices", None)
    if not pid or fn is None:
        return []
    try:
        rows = fn(pid) or []
    except Exception:  # noqa: BLE001 — notice-only lookup
        return []
    evidence = evidence or []
    rec = record_date(evidence, pid)
    legal = " ".join(e.get("text") or "" for e in evidence if e.get("evidence_id") == f"db:procedures:{pid}:legal_basis")
    out = [{k: r.get(k) for k in ("doc_id", "title", "effective_date", "url")} for r in rows
           if notice_applies(r, today, rec, legal)]
    return sorted(out, key=lambda r: r["effective_date"], reverse=True)


def _vn_date(s: str | None) -> str:
    d = _parse_date(s)
    return d.strftime("%d/%m/%Y") if d else (s or "không rõ")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None


# ---------------------------------------------------------------- nodes

def make_nodes(deps: Deps) -> dict[str, Callable[[dict], dict]]:
    """name -> node function, all wrapped fail-closed."""

    def assess_need(state):
        need = self_rag.assess_need(deps.classifier, state["query"])
        dropped = None
        if need.get("premise") and premise_invented(need["premise"], state["query"]):  # safety rule, no flag (ROUND-4 (g))
            dropped, need = need["premise"], {**need, "premise": None}
        gate = scope_gate(deps, need, state["query"])
        if gate == "opened":  # retrieve=false is only for greetings / questions about the assistant, which are not in scope
            need = {**need, "retrieve": True}
        # metadata key "config" is swallowed by the LangFuse span update (all fields lost), hence graph_config
        deps.trace("assess_need", need=need, preset=state.get("preset"), graph_config=deps.config, scope_gate=gate,
                   premise_dropped=dropped)
        return {"need": need, "iteration": state.get("iteration", 0), "errors": list(state.get("errors") or [])}

    def resolve_procedure(state):
        need = state.get("need") or {}
        if state.get("procedure_id"):  # caller already chose (clarify follow-up / CLI --procedure)
            rows = deps.db.get_procedure(state["procedure_id"])
            if not rows:
                return {"procedure_id": None, "candidates": [], "route": "none"}
            title = rows[0]["structured"].get("title")
            return {"candidates": [{"procedure_id": state["procedure_id"], "title": title, "score": 1.0, "chosen": "preset"}],
                    "route": "one"}
        hint = need.get("procedure_hint") or state["query"]
        if deps.ablation == "no_resolve":
            top = deps.rag.resolve_candidates(hint, k=1)
            if not top:
                return {"candidates": [], "procedure_id": None, "route": "none"}
            return {"candidates": top, "procedure_id": top[0]["procedure_id"], "route": "one"}
        cands = score_candidates(deps, hint, state["query"])
        decision, chosen = choose(cands, deps.resolve, hint, query=state["query"], intent=need.get("intent"))
        if decision == "none":  # rescue: titles whose specific words all occur in the user's own words
            rescued = [{**c, "core": 1.0, "rescued": True} if title_in_query(c, state["query"]) else c for c in cands]
            if any(c.get("rescued") for c in rescued):
                cands = rescued
                decision, chosen = choose(cands, deps.resolve, hint, query=state["query"], intent=need.get("intent"))
        story = None
        if decision == "none" and deps.story_rewrite:  # P22: one LLM call naming the procedure behind a story
            story = self_rag.story_rewrite(deps.classifier, state["query"])
            if story:
                cands2 = score_candidates(deps, story, state["query"])
                decision2, chosen2 = choose(cands2, deps.resolve, story, query=state["query"], intent=need.get("intent"))
                if decision2 != "none":  # same floor as any hint: an invented name matches no title
                    cands, decision, chosen, hint = cands2, decision2, chosen2, story
        out = {"candidates": cands, "procedure_id": None, "route": "none"}
        if decision == "one":
            out = {"candidates": cands, "procedure_id": chosen[0]["procedure_id"], "route": "one"}
            if chosen[0].get("assumed_over"):  # base_title_preference: the qualified siblings not chosen
                out["assumed_variants"] = chosen[0]["assumed_over"]
        elif decision == "tie":
            group = sibling_invariant(deps, chosen, need.get("intent"))
            if group:  # lead decision P1: same asked-for value across the whole variant group → answer for the top
                out = {"candidates": chosen, "procedure_id": chosen[0]["procedure_id"], "route": "one", "variant_group": group}
            else:
                out = {"candidates": chosen, "procedure_id": None, "route": "tie"}
        label = {"one": "resolved", "tie": "clarify", "none": "none"}[out["route"]]
        deps.trace("resolve_procedure", decision=label, sibling_invariant=bool(out.get("variant_group")),
                   assumed_variants=out.get("assumed_variants"),
                   procedure_id=out["procedure_id"], hint=hint, story_rewrite=story,
                   candidates=[{k: c.get(k) for k in ("procedure_id", "title", "score", "lexical", "core", "rrf", "family")}
                               for c in cands[:3]],
                   thresholds={k: deps.resolve[k] for k in ("core_floor", "gap", "sibling_gap", "lex_weight", "f2_rule",
                                                             "base_title_preference", "head_noun_guard")})
        return out

    def gather_evidence(state):
        pid = state["procedure_id"]
        intent = (state.get("need") or {}).get("intent", "general")
        db_rows = list(deps.db.get_procedure(pid)) + list(deps.db.get_agency(pid))
        if intent in ("documents", "agency", "general"):
            db_rows += deps.db.get_required_documents(pid)
        if intent in ("fee", "general", "update"):
            db_rows += deps.db.get_fees(pid)
        stopped = deps.procedure_status.get(pid)
        if stopped:  # ROUND-4: a discontinued procedure is never answered; keep the db rows for the agency in the refusal
            deps.trace("gather_evidence", discontinued=stopped)
            return {"db_results": db_rows, "documents": [], "evidence": db_rows,
                    "discontinued": {**stopped, "procedure_id": pid}}
        query = (state.get("sub_queries") or [state["query"]])[-1]
        chunks = deps.rag.retrieve(query, procedure_id=None if deps.ablation == "no_resolve" else pid,
                                   section=INTENT_SECTION.get(intent), k=CHUNKS_K)
        chunks = [c for c in chunks if c["tier"] != "web_other"]  # L2: web_other never graded
        return {"db_results": db_rows, "documents": chunks, "evidence": db_rows + chunks}

    def grade_relevance(state):
        if state.get("discontinued"):  # no model call: after_grade sends it to refuse_redirect
            return {"grades": {"relevance": {}, "usable": False, "discontinued": True}}
        chunks = state.get("documents") or []
        query = (state.get("sub_queries") or [state["query"]])[-1]
        verdicts = self_rag.grade_relevance(deps.judge, query, chunks)
        relevant = [c for c, ok in zip(chunks, verdicts) if ok]
        db_rows = state.get("db_results") or []
        intent = (state.get("need") or {}).get("intent", "general")
        block, gaps = render.render_block(intent, db_rows, _locality(state))
        grades = {"relevance": {c["evidence_id"]: ok for c, ok in zip(chunks, verdicts)},
                  "usable": bool(relevant) or bool(block)}
        deps.trace("grade_relevance", relevance=grades["relevance"], usable=grades["usable"])
        return {"grades": grades, "documents": relevant, "evidence": db_rows + relevant}

    def rewrite_query(state):
        need = state.get("need") or {}
        title = render.title_of(state.get("evidence") or []) or need.get("procedure_hint", "")
        prompt = load_prompt("rewrite_query").substitute(title=title, intent=need.get("intent", "general"),
                                                          query=state["query"])
        q = message_text(deps.llm.invoke(prompt)).splitlines()
        q = next((ln.strip() for ln in q if ln.strip()), "") or f"{title} {state['query']}"
        return {"sub_queries": list(state.get("sub_queries") or []) + [q], "iteration": state.get("iteration", 0) + 1}

    def draft_answer(state):
        need = state.get("need") or {}
        intent = need.get("intent", "general")
        evidence = state.get("evidence") or []
        block, gaps = render.render_block(intent, evidence, _locality(state))
        chunks = [e for e in evidence if e["tier"] == "corpus"]
        premise_line = render.render_premise(need.get("premise"), intent, evidence)
        if premise_line:  # numeric premise answered by code (F5); the LLM is told not to repeat it
            block = f"{premise_line}\n\n{block}" if block else premise_line
        premise = None if premise_line else need.get("premise")
        narrative = ""
        if chunks or premise:
            premise_rule = (f"- Người hỏi khẳng định: \"{premise}\". Câu ĐẦU TIÊN của bạn phải nói rõ nhận định đó ĐÚNG hay "
                            "KHÔNG ĐÚNG theo KHỐI CỐ ĐỊNH/TÀI LIỆU (bắt đầu bằng \"Đúng.\" hoặc \"Không.\") và có mã nguồn."
                            if premise else
                            "- Nhận định của người hỏi (nếu có) đã được trả lời trong KHỐI CỐ ĐỊNH; không nhắc lại." if premise_line else "")
            prompt = load_prompt(deps.draft_prompt).substitute(
                query=state["query"], title=render.title_of(evidence) or "", block=block or "(trống)",
                documents=self_rag._wrap_docs(chunks) or "(không có)", premise_rule=premise_rule)
            narrative = message_text(deps.llm.invoke(prompt))
            if deps.citation_parse == "tolerant":
                repairs: list = []
                narrative = self_rag.normalize_citations(narrative, (e["evidence_id"] for e in evidence),
                                                         repair=deps.citation_repair == "tier", repairs=repairs)
                deps.trace("draft_answer", citation_parse=deps.citation_parse, citation_repair=deps.citation_repair,
                           repaired_citations=repairs)
        parts = [narrative, block] if premise else [block, narrative]
        draft = "\n\n".join(p for p in parts if p.strip())
        return {"draft": draft, "block": block, "gaps": gaps, "premise_line": premise_line}

    def check_support(state):
        need = state.get("need") or {}
        intent = need.get("intent", "general")
        premise_line = state.get("premise_line")
        claims = self_rag.split_claims(state.get("draft") or "", block=state.get("block") or "",
                                       intent=intent, premise=None if premise_line else need.get("premise"))
        for c in claims:  # the code-rendered premise line still gets the polarity check
            if premise_line and c["text"] == premise_line.strip():
                c["origin"] = "premise"
        claims = self_rag.check_support(deps.judge, claims, state.get("evidence") or [], premise=need.get("premise"),
                                        code_checks=deps.ablation != "llm_support")
        if premise_line and deps.ablation != "llm_support":
            claims = [self_rag.premise_narrative_check(c, need["premise"], state.get("evidence") or []) for c in claims]
        # A missing asked-for element (no fee rows, no document rows) is a declared gap → answer_partial with the
        # agency as next step (testset T-002), not a claim; only unsupported *claims* can sink the answer.
        if intent == "steps" and not any(c["verdict"] == "supported" for c in claims):
            claims.append({"text": "Không có căn cứ về: trình tự thực hiện", "type": "core", "origin": "gap",
                           "evidence_ids": [], "kind": "steps", "verdict": "unsupported", "reason": "no supported step",
                           "synthetic": True})
        deps.trace("check_support", verdicts=[(c["text"][:60], c["type"], c["verdict"]) for c in claims])
        return {"claims": claims, "grades": {**(state.get("grades") or {}), "support": self_rag.support_summary(claims)}}

    def prune_claims(state):
        draft = state.get("draft") or ""
        pruned = []
        for c in state.get("claims") or []:
            if c["type"] == "minor" and c["verdict"] != "supported":
                draft = draft.replace(c["text"], "")
                pruned.append(self_rag.strip_cites(c["text"]))
        draft = "\n".join(ln.strip() for ln in draft.splitlines())
        draft = re.sub(r"\n{3,}", "\n\n", draft).strip()
        claims = [c for c in state.get("claims") or [] if not (c["type"] == "minor" and c["verdict"] != "supported")]
        deps.trace("prune_claims", pruned=pruned)
        return {"draft": draft, "pruned": pruned, "claims": claims}

    def freshness_check(state):
        need = state.get("need") or {}
        cited = {i for c in state.get("claims") or [] for i in c["evidence_ids"]}
        evs = [e for e in state.get("evidence") or [] if e["evidence_id"] in cited]
        dates = [d for d in (_parse_date(e.get("retrieved_at")) for e in evs) if d]
        oldest = min(dates) if dates else None
        today = deps.today or date.today()
        stale = oldest is None or (today - oldest).days > deps.stale_days
        touches_agency = any(e.get("section") == "agency" or (e.get("structured") or {}).get("name") for e in evs)
        reasons = [r for r, on in (("intent=update", need.get("intent") == "update"), ("stale", stale),
                                   ("agency", touches_agency)) if on]
        notices = change_notices(deps, state.get("procedure_id"), today, state.get("evidence") or [])
        if notices:
            reasons.append("change_notice")
        fresh = {"oldest_retrieved_at": oldest.isoformat() if oldest else None, "stale": stale,
                 "notice": bool(reasons), "reasons": reasons, "change_notices": notices}
        deps.trace("freshness_check", freshness=fresh)
        return {"freshness": fresh}

    def web_check(state):
        fresh = dict(state.get("freshness") or {})
        title = render.title_of(state.get("evidence") or []) or (state.get("need") or {}).get("procedure_hint", "")
        try:
            if deps.web is None:
                raise RuntimeError("no web tool configured")
            hits = [h for h in _web(deps, f"{title} thay đổi sửa đổi {(deps.today or date.today()).year}", official_only=True)
                    if h["tier"] == "web_official"]  # L2: web_other discarded
            ok = self_rag.grade_relevance(deps.judge, f"{title} có thay đổi, sửa đổi gì mới", hits) if hits else []
            hits = [h for h, r in zip(hits, ok) if r]
            fresh["web_links"] = [h.get("source_url") for h in hits[:3]]
        except Exception as exc:  # noqa: BLE001 — notice-only tool: degrade to the generic notice
            fresh["web_links"], fresh["web_error"] = [], f"{type(exc).__name__}: {exc}"
            hits = []
        deps.trace("web_check", freshness=fresh)
        return {"freshness": fresh, "web_results": hits}

    def web_lookup(state):
        hint = (state.get("need") or {}).get("procedure_hint") or state["query"]
        try:
            if deps.web is None:
                raise RuntimeError("no web tool configured")
            hits = [h for h in _web(deps, f"thủ tục {hint}", site="dichvucong.gov.vn") if h["tier"] == "web_official"]
            if not hits:
                hits = [h for h in _web(deps, f"thủ tục {hint}", official_only=True) if h["tier"] == "web_official"]
            ok = self_rag.grade_relevance(deps.judge, f"trang chính thức về thủ tục {hint}", hits) if hits else []
            hits = [h for h, r in zip(hits, ok) if r]  # only a page graded relevant is linked in the refusal
            deps.trace("web_lookup", hits=[h.get("source_url") for h in hits[:3]])
            return {"web_results": hits}
        except Exception as exc:  # noqa: BLE001 — already on the refusal path; refuse without a link
            return {"web_results": [], "grades": {**(state.get("grades") or {}), "web_error": f"{type(exc).__name__}: {exc}"}}

    def finalize(state):
        violations = final_safety_violations(state, code_checks=deps.ablation != "llm_support")
        if state.get("discontinued"):  # unreachable through the edges; never answer a stopped procedure
            text, refusal = build_refusal(state, "not_in_corpus")
            return {"generation": text, "outcome": "refuse", "refusal": refusal}
        if violations:  # belt and braces: never emit an unsupported structured claim (non-negotiable)
            text, refusal = build_refusal(state, "insufficient_evidence", missing=["một số thông tin trong câu trả lời"],
                                          note="; ".join(violations))
            return {"generation": text, "outcome": "refuse", "refusal": refusal}
        evidence = state.get("evidence") or []
        cited = []
        for c in state.get("claims") or []:
            for i in c["evidence_ids"]:
                if i not in cited:
                    cited.append(i)
        citations = render.citation_list(evidence, cited)
        out = [state.get("draft") or ""]
        # Only gaps in what was asked are shown; pruned minor sentences were LLM extras nobody asked for, so they are
        # removed silently (kept in state.pruned and the trace). See STATUS "Decisions".
        missing = [f"{g['element']} ({g['detail']})" for g in state.get("gaps") or []]
        if missing:
            out.append("Không tìm thấy căn cứ về: " + "; ".join(missing) + ".")
        if citations:
            out.append("Nguồn:\n" + "\n".join(
                f"- [{c['evidence_id']}] {c['source_url'] or 'không rõ'} (ngày lấy {(c['retrieved_at'] or 'không rõ')[:10]}"
                + (f", hiệu lực {c['effective_date']}" if c.get("effective_date") else "") + ")" for c in citations))
        fresh = state.get("freshness") or {}
        if fresh.get("notice"):
            note = ("Lưu ý: thông tin có thể đã thay đổi (cơ quan tiếp nhận có thể đã thay đổi sau sắp xếp đơn vị hành chính 2025); "
                    "vui lòng xác nhận tại cơ quan tiếp nhận trước khi nộp hồ sơ.")
            if fresh.get("web_links"):
                note += " Trang chính thức có thể có cập nhật: " + ", ".join(fresh["web_links"])
            out.append(note)
        notices = fresh.get("change_notices") or []  # ROUND-4: newer than the record (code rule, no LLM)
        for n in notices[:NOTICE_SHOWN]:
            out.append(f"Lưu ý: thủ tục này có thay đổi theo «{n['title']}», hiệu lực {_vn_date(n['effective_date'])}; "
                       f"vui lòng kiểm tra lại trước khi nộp hồ sơ. Nguồn: {n['url']}")
        if len(notices) > NOTICE_SHOWN:
            out.append(f"và {len(notices) - NOTICE_SHOWN} văn bản khác (xem nguồn).")
        if state.get("variant_group"):
            out.append("Thông tin trên giống nhau cho cả nhóm thủ tục: " + "; ".join(state["variant_group"])
                       + " (theo dữ liệu từng thủ tục trong kho).")
        if state.get("assumed_variants"):
            title = next((c.get("title") for c in state.get("candidates") or []
                          if c.get("procedure_id") == state.get("procedure_id")), None) or state.get("procedure_id")
            out.append(f"Thông tin trên áp dụng cho «{title}». Nếu trường hợp của bạn là «"
                       + "» hoặc «".join(state["assumed_variants"]) + "», vui lòng hỏi lại và nêu rõ.")
        if (state.get("need") or {}).get("intent") == "agency":
            out.append("Việc bạn có đủ điều kiện hay không do cơ quan tiếp nhận xác định.")
        outcome = "answer_partial" if missing else "answer"
        deps.trace("finalize", outcome=outcome)
        return {"generation": "\n\n".join(p for p in out if p.strip()), "outcome": outcome, "citations": citations,
                "refusal": None}

    def clarify(state):
        text, refusal = build_refusal(state, "ambiguous")
        deps.trace("clarify", outcome="clarify", refusal_type="ambiguous")
        return {"generation": text, "outcome": "clarify", "refusal": refusal}

    def out_of_scope(state):
        text, refusal = build_refusal(state, "out_of_scope")
        deps.trace("out_of_scope", outcome="out_of_scope", refusal_type="out_of_scope")
        return {"generation": text, "outcome": "out_of_scope", "refusal": refusal}

    def refuse_redirect(state):
        rtype, missing, note = refusal_type(state)
        text, refusal = build_refusal(state, rtype, missing=missing, note=note)
        deps.trace("refuse_redirect", outcome="refuse", refusal_type=rtype)
        return {"generation": text, "outcome": "refuse", "refusal": refusal}

    fns = {
        "assess_need": assess_need, "resolve_procedure": resolve_procedure, "gather_evidence": gather_evidence,
        "grade_relevance": grade_relevance, "rewrite_query": rewrite_query, "draft_answer": draft_answer,
        "check_support": check_support, "prune_claims": prune_claims, "freshness_check": freshness_check,
        "web_check": web_check, "web_lookup": web_lookup, "finalize": finalize, "clarify": clarify,
        "out_of_scope": out_of_scope, "refuse_redirect": refuse_redirect,
    }
    return {n: _guarded(n, f, run_on_error=(n == "refuse_redirect")) for n, f in fns.items()}


# ---------------------------------------------------------------- resolve_procedure scoring (pure, tested)

def _num(s: str) -> set[str]:
    return {n.replace(".", "").replace(",", "").lstrip("0") or "0" for n in re.findall(r"\d[\d.,]*\d|\d", s or "")}


def premise_invented(premise: str, query: str) -> bool:
    """Premise post-check (ROUND-4 item (g), safety rule, no flag): a premise is something the user asserts. One that carries a number the question does not
    contain was not asserted by the user (owner trace c26ce7e9: "lệ phí đăng ký khai sinh là 50.000đ", the prompt's own
    example, for a question that names no fee), so it is dropped. Numbers compare without separators or leading zeros."""
    return bool(_num(premise) - _num(query))


def scope_gate(deps: Deps, need: dict, query: str) -> str | None:
    """Round-4 item (c), flag `scope_gate: "in_scope"`. The classifier sometimes answers in_scope=true with retrieve=false
    and an empty hint (T-022, T-027, the CMND probe), which after_assess routes to out_of_scope. Under the flag an in-scope
    question is opened to the resolver, whose coverage floor stays the safety net; a personal eligibility question
    (`_ELIGIBILITY`, the prompt's own definition) is kept closed. Returns "opened" | "kept_eligibility" | None (no change)."""
    if deps.scope_gate != "in_scope" or not need.get("in_scope") or need.get("retrieve"):
        return None
    return "kept_eligibility" if _ELIGIBILITY.search(_fold(query)) else "opened"


def score_candidates(deps: Deps, hint: str, query: str = "") -> list[dict]:
    """Union of DB title search and RAG summary candidates, scored on one scale, with variant families."""
    cfg = deps.resolve
    by_id: dict[str, dict] = {}
    rrf_max = 2 / (RRF_K + 1)
    for c in deps.rag.resolve_candidates(hint, k=cfg["k"]):
        by_id[c["procedure_id"]] = {"procedure_id": c["procedure_id"], "title": c["title"],
                                    "rrf": min(1.0, c["score"] / rrf_max)}
    for e in deps.db.search_titles(hint):
        r = e.get("structured") or {}
        pid = r.get("id") or e.get("procedure_id")
        if pid and pid not in by_id:
            by_id[pid] = {"procedure_id": pid, "title": r.get("title"), "rrf": 0.0}
    expand = getattr(deps.rag, "expand_query", lambda q: q)  # w-tools synonyms (CCCD → thẻ căn cước, …)
    expanded, expanded_q = expand(hint), (expand(query) if query else "")
    out = []
    for pid, c in by_id.items():
        rows = deps.db.get_procedure(pid)
        if not rows:  # ROUND-4: only procedures are candidates; a legal-text or guidance id has no procedures row
            continue
        r = rows[0].get("structured") or {}
        c["title"] = c["title"] or r.get("title") or pid
        c["family"] = r.get("variant_of") or pid
        c["lexical"] = round(lexical(hint, c["title"]), 4)
        z = deps.scope_gate == "in_scope"  # Round-4 (c): "9" == "09"
        c["core"] = round(max(coverage(hint, c["title"], expanded, zeros=z), coverage(query, c["title"], expanded_q, zeros=z)), 4) \
            if query else round(coverage(hint, c["title"], expanded, zeros=z), 4)
        c["field"] = r.get("field")
        c["score"] = round(cfg["lex_weight"] * c["lexical"] + (1 - cfg["lex_weight"]) * c["rrf"], 4)
        out.append(c)
    return sorted(out, key=lambda c: -c["score"])


def choose(cands: list[dict], cfg: dict, hint: str = "", *, query: str = "", intent: str | None = None
           ) -> tuple[str, list[dict]]:
    """'one' | 'tie' | 'none' plus the chosen candidate(s).

    none: the top candidate's hint-word coverage (`coverage`) is below core_floor (if a lower-ranked candidate
          clears it within sibling_gap of the top score, that candidate is judged instead). Absolute floor:
          fused RRF has no absolute scale and dense cosine overlaps between in- and out-of-corpus questions.
    tie:  among candidates that also clear core_floor —
          a variant_of sibling within sibling_gap whose title the hint does not tell apart from the top's
          (the hint has none of the top's title tokens that the sibling lacks, e.g. "lại", "nước ngoài";
          with f2_rule="distinguishing_words": the hint ∪ query lacks any one of them, ROUND-2 item 1),
          or a same-field neighbour within gap. Unrelated candidates never cause a clarify.
    one:  otherwise; or the family root when the hint says "trong nước / lần đầu / thông thường"
          and the tie is only among that family's variants.
    """
    if not cands:
        return "none", []
    if cfg.get("head_noun_guard") and cfg.get("family_nouns"):
        guarded = _head_noun_filter(cands, cfg["family_nouns"], hint, cfg["core_floor"])
        if guarded and guarded[0] == "tie":
            return guarded
        if guarded:
            cands = guarded[1]
    top = cands[0]
    if top.get("core", top["lexical"]) < cfg["core_floor"]:
        best = max(cands, key=lambda c: c.get("core", c["lexical"]))
        if best.get("core", best["lexical"]) < cfg["core_floor"] or top["score"] - best["score"] > cfg["sibling_gap"]:
            return "none", []
        top = best  # a lower-ranked candidate is the real lexical match; judge the tie around it
    ok = [c for c in cands if c is not top and c.get("core", c["lexical"]) >= cfg["core_floor"]]
    folded = " ".join(_tokens(hint))
    if any(m in folded for m in PLAIN_MARKERS):
        root = next((c for c in [top] + ok if c["procedure_id"] == top["family"]), None)
        others = [c for c in ok if c["family"] != top["family"] and top["score"] - c["score"] <= cfg["gap"]]
        if root and not others:
            return "one", [root]
    fam = {top["family"], top["procedure_id"]}
    hint_t = set(_tokens(hint)) | set(_tokens(query))  # the hint drops places ("ở công an tỉnh"); the query keeps them
    base_pref = bool(cfg.get("base_title_preference"))
    said = [_tokens(hint), _tokens(query)]

    def is_close(c: dict) -> bool:
        if {c["family"], c["procedure_id"]} & fam:  # sibling: close unless the user's words tell them apart
            top_t = set(_tokens(_TITLE_PREFIX.sub("", top["title"])))
            c_t = set(_tokens(_TITLE_PREFIX.sub("", c["title"])))
            distinct = top_t - c_t
            if cfg.get("f2_rule") == "distinguishing_words":  # F2 candidate A: all of the top's own words, not one
                discriminates = bool(distinct) and distinct <= hint_t
            else:
                discriminates = bool(distinct & hint_t)
            if base_pref and c_t < top_t:  # the top is this sibling plus a qualifier: told apart only if it is said
                discriminates = qualifier_said(c["title"], top["title"], said)
            other_action = bool(((c_t - top_t) & ACTION_WORDS) - hint_t)
            # the sibling only adds a qualifier the user did not say (lưu động, khu vực biên giới, …): the user means
            # the top — except for document lists, where a wrong variant is the most harmful blend (F2) → still ask
            if base_pref:  # every intent; the qualifier counts as said only by its own words (`qualifier_said`)
                qualifier_only = top_t < c_t and not qualifier_said(top["title"], c["title"], said)
            else:
                qualifier_only = top_t < c_t and not ((c_t - top_t) & hint_t) and intent != "documents"
            return (abs(top["score"] - c["score"]) <= cfg["sibling_gap"] and not discriminates and not other_action
                    and not qualifier_only)
        same_field = c.get("field") and c.get("field") == top.get("field")
        return bool(same_field) and abs(top["score"] - c["score"]) <= cfg["gap"]

    close = [c for c in ok if is_close(c)]
    if base_pref:
        return _base_preference(top, close, ok + [cands[0]], cfg, said)
    if close:
        return "tie", ([top] + close)[: cfg["max_options"]]
    return "one", [top]


def _head_noun_filter(cands: list[dict], nouns: dict, hint: str, floor: float = 0.0) -> tuple[str, list[dict]] | None:
    """head_noun_guard (flag): a candidate whose title lacks the procedure family the hint names must not win over one that
    has it, however well its short title is covered ("… khai sinh … giấy kết hôn" must not resolve to "Đăng ký kết hôn").
    Family nouns come from the titles (src/families.py). Returns None (no family named, or no candidate has it),
    ("cands", filtered) to keep only the named family's candidates, or ("tie", [a, b]) when the hint names two families
    and does not start with either (the first family noun is not among its first three words) → clarify between them.
    The clarify is offered only between candidates that clear the coverage floor; otherwise the list is filtered and the
    floor decides (T-053: a story_rewrite name listing several families must not turn "none" into a clarify)."""
    hits = nouns_in(hint, nouns)
    if not hits:
        return None
    groups: list[set[str]] = []  # one entry per named family: the family roots of its nouns, in order of first mention
    for _, n in hits:
        fams = set(nouns[n])
        g = next((g for g in groups if g & fams), None)
        if g is None:
            groups.append(fams)
        else:
            g |= fams
    members = [[c for c in cands if title_has(c["title"], {m for m, r in nouns.items() if set(r) & g})] for g in groups]
    cleared = [[c for c in m if c.get("core", c.get("lexical", 0)) >= floor] for m in members[:2]]
    if len(groups) > 1 and hits[0][0] > 2 and len(cleared) == 2 and cleared[0] and cleared[1]:
        return "tie", [cleared[0][0], cleared[1][0]]
    if not members[0]:  # no candidate of the first-named family: leave the list as it is
        return None
    return "cands", members[0]


def _base_preference(top: dict, close: list[dict], pool: list[dict], cfg: dict, said: list[list[str]]
                     ) -> tuple[str, list[dict]]:
    """base_title_preference (audit finding 1, flag): among the tied candidates, drop every title that is another tied
    sibling's title plus a qualifier the user did not say (the base may rank below its qualified sibling); one left →
    'one'. The chosen candidate carries `assumed_over`, the qualified sibling titles set aside, which finalize prints
    so the user can re-ask ("… lưu động"); nothing is chosen silently."""
    if close:
        tied = [top] + close
        kept = [c for c in tied if not any(_is_qualified(b, c, said) for b in tied if b is not c)]
        top, close = kept[0], kept[1:]
    if close:
        return "tie", ([top] + close)[: cfg["max_options"]]
    assumed = []
    for c in pool:
        if c is not top and c["title"] not in assumed and abs(top["score"] - c["score"]) <= cfg["sibling_gap"] \
                and _is_qualified(top, c, said):
            assumed.append(c["title"])
    return "one", [{**top, "assumed_over": assumed} if assumed else top]


# words any question uses to ask about a procedure ("hồ sơ", "giấy tờ") and function words inside qualifier phrases
# ("có yếu tố …", "tại khu vực …", "cho người …"): neither names a qualifier (audit finding 1, probe 06: "… có thay đổi gì")
FORM_WORDS = frozenset("ho so giay to thu tuc dang ky".split())
QUALIFIER_FUNCTION = frozenset("co cua tai o cho va voi la trong da duoc".split())


def qualifier_said(base_title: str, title: str, said: list[list[str]]) -> bool:
    """Does the user name a qualifier that `title` adds to `base_title`? Each run of title words not in the base
    ("lưu động", "có yếu tố nước ngoài tại khu vực biên giới") counts as said when the user's words (hint or question,
    accent-folded, in order) contain two of its content words side by side ("nước ngoài", "biên giới"), or its only
    content word ("lại"). Function words and FORM_WORDS never count, so "có" or "hồ sơ" in a question does not."""
    base = set(_tokens(_TITLE_PREFIX.sub("", base_title)))
    runs, cur = [], []
    for t in _tokens(_TITLE_PREFIX.sub("", title)):
        if t in base:
            runs, cur = (runs + [cur]) if cur else runs, []
        else:
            cur.append(t)
    runs = runs + [cur] if cur else runs
    words = {w for seq in said for w in seq}
    pairs = {p for seq in said for p in zip(seq, seq[1:])}
    for run in runs:
        content = [t for t in run if t not in QUALIFIER_FUNCTION]
        if len(content) == 1 and content[0] in words and content[0] not in FORM_WORDS:
            return True
        if any(p in pairs and not set(p) <= FORM_WORDS for p in zip(content, content[1:])):
            return True
    return False


def _is_qualified(base: dict, c: dict, said: list[list[str]]) -> bool:
    """`c` is a sibling whose title is `base`'s title plus words the user did not say (and no action word)."""
    if not {c["family"], c["procedure_id"]} & {base["family"], base["procedure_id"]}:
        return False
    b_t = set(_tokens(_TITLE_PREFIX.sub("", base["title"])))
    c_t = set(_tokens(_TITLE_PREFIX.sub("", c["title"])))
    return b_t < c_t and not ((c_t - b_t) & ACTION_WORDS) and not qualifier_said(base["title"], c["title"], said)


def coverage(hint: str, title: str, expanded: str | None = None, *, zeros: bool = False) -> float:
    """Share of the hint's specific words (accent-folded, GENERIC removed) that the title contains.

    A hint word that triggered a synonym group (data/synonyms.yaml via rag.expand_query) also counts as
    covered when any word of that group is in the title ("cccd" ~ "thẻ căn cước"). This is the absolute
    "is this procedure in the corpus" measure; dense cosine and fused RRF did not separate in- from
    out-of-corpus questions on the test set (w-graph STATUS).
    """
    fold = (lambda ws: {(w.lstrip("0") or "0") if w.isdigit() else w for w in ws}) if zeros else set  # zeros: "09" == "9"
    h = fold(_tokens(_TITLE_PREFIX.sub("", hint))) - GENERIC
    if not h:
        return 0.0
    t = fold(_tokens(_TITLE_PREFIX.sub("", title))) - GENERIC
    extra = set(_tokens((expanded or hint)[len(hint):]))
    syn_hit = bool(extra & t)
    covered = {w for w in h if w in t or (syn_hit and w in extra)}
    return len(covered) / len(h)


def _web(deps: Deps, query: str, **kw) -> list:
    """web_search with keyword options (site=, official_only=); a web tool without them gets the query only."""
    try:
        return deps.web(query, **kw)
    except TypeError:
        return deps.web(query)


def title_in_query(c: dict, query: str) -> bool:
    """All specific (non-GENERIC, ≥ 2) title words occur in the query: a story-style question that names the
    procedure ("… sinh ở Hàn Quốc …, đăng ký khai sinh ở đâu?") even when the extracted hint is noisy."""
    core = set(_tokens(_TITLE_PREFIX.sub("", c["title"]))) - GENERIC
    return len(core) >= 2 and core <= set(_tokens(query))


def contained_title(cands: list[dict], query: str) -> dict | None:
    """The candidate whose core title tokens (≥ 2) all appear in the query and that is the most specific such
    title; None if there is none or two equally specific ones (ambiguous → keep 'none')."""
    q = set(_tokens(query))
    hits = []
    for c in cands:
        core = set(_tokens(_TITLE_PREFIX.sub("", c["title"]))) - GENERIC
        if len(core) >= 2 and core <= q:
            hits.append((len(core), c))
    hits.sort(key=lambda h: -h[0])
    if not hits or (len(hits) > 1 and hits[0][0] == hits[1][0]):
        return None
    return hits[0][1]


def _invariant_value(deps: Deps, pid: str, intent: str):
    """Normalised value of the asked-for field for one procedure. Agency/time: None = no data, never invariant.
    Fees: () = no rows; identical absence across siblings is invariant and yields a declared fee gap."""
    n = self_rag.norm
    if intent == "fee":
        rows = deps.db.get_fees(pid)
        vals = sorted((n(r["structured"].get("value") or ""), n(r["structured"].get("condition") or ""),
                       n(r["structured"].get("jurisdiction") or "")) for r in rows)
        return tuple(vals)  # () = no fee rows: "unknown" for every sibling is also invariant (testset T-002)
    if intent == "agency":
        rows = deps.db.get_agency(pid)
        return tuple(sorted(n(r["structured"].get("name") or "") for r in rows)) or None
    if intent == "time":
        rows = deps.db.get_procedure(pid)
        return n((rows[0]["structured"] or {}).get("processing_time") or "") or None if rows else None
    return None


def sibling_invariant(deps: Deps, chosen: list[dict], intent: str | None) -> list[str] | None:
    """Titles of the variant group if every tied candidate is a sibling of the top and all share the same
    fee rows / agency / processing_time for the asked intent; else None. Document lists are never invariant."""
    if intent not in ("fee", "agency", "time") or len(chosen) < 2:
        return None
    top = chosen[0]
    fam = {top["family"], top["procedure_id"]}
    if not all({c["family"], c["procedure_id"]} & fam for c in chosen[1:]):
        return None
    values = [_invariant_value(deps, c["procedure_id"], intent) for c in chosen]
    if values[0] is None or any(v != values[0] for v in values[1:]):
        return None
    return [c["title"] for c in chosen]


# ---------------------------------------------------------------- refusal typing and the final safety net

def refusal_type(state: dict) -> tuple[str, list[str], str | None]:
    """Which of the five refusal types applies, from state only."""
    if state.get("errors"):
        return "system_error", [], "; ".join(state["errors"])
    if state.get("discontinued"):  # ROUND-4: still one of the five types; refusal["reason"] = "discontinued"
        return "not_in_corpus", [], None
    if not state.get("procedure_id"):
        return "not_in_corpus", [], (state.get("grades") or {}).get("web_error")
    # only declared elements (gaps, or the asked element): a draft claim never reaches the refusal text or `missing`
    # (owner trace c26ce7e9); the unsupported claims are kept in refusal["unsupported_claims"] by build_refusal
    missing = [g["element"] for g in state.get("gaps") or [] if g["kind"] == "missing"]
    if not missing:
        intent = (state.get("need") or {}).get("intent", "general")
        missing = [render.ASKED.get(intent, "nội dung bạn hỏi")]
    return "insufficient_evidence", [m for m in dict.fromkeys(missing) if m], None


_NUM_LINE = re.compile(r"\d")


def final_safety_violations(state: dict, code_checks: bool = True) -> list[str]:
    """Checks that must hold for anything that reaches finalize as an answer:
    no errors; every kept claim supported; every cited id exists in evidence; every block line cites a
    db row and passes the code check against it."""
    v = []
    if state.get("errors"):
        v.append("errors present")
    if state.get("discontinued"):
        v.append("discontinued procedure")
    ids = {e["evidence_id"] for e in state.get("evidence") or []}
    by_id = {e["evidence_id"]: e for e in state.get("evidence") or []}
    for c in state.get("claims") or []:
        if c.get("verdict") != "supported":
            v.append(f"unsupported claim kept: {c['text'][:60]}")
        for i in c.get("evidence_ids") or []:
            if i not in ids:
                v.append(f"citation not in evidence: {i}")
    for line in (state.get("block") or "").splitlines():
        s = line.strip()
        if not s or (s.endswith(":") and not self_rag.cited_ids(s)):
            continue
        rows = [by_id[i] for i in self_rag.cited_ids(s) if i in by_id and by_id[i]["tier"] == "db"]
        if not rows:
            v.append(f"structured line without db citation: {s[:60]}")
            continue
        ok, why = self_rag.check_db_claim(s, rows) if code_checks else (True, "")
        if not ok:
            v.append(f"structured line fails code check ({why}): {s[:60]}")
    return v
