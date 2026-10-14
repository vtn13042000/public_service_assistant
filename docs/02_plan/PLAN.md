# PLAN — Project 5: Trợ lý dịch vụ công / thủ tục hành chính (Self-RAG)

Course: AI5013 (Agents). Duration: 4 weeks per the professor's roadmap. Prepared 2026-10-10.
Sources: `docs/00_sources/description.md`, `docs/00_sources/guidance.md`, `docs/01_context/HARDWARE.md`.

---

## 0. How this plan differs from the earlier sample plan

The sample plan (`docs/01_context/sample_plan.md`) is a competent engineering sprint, and parts of it
are reused here (environment checks, model assignment, repo layout). What it lacks for a master's
final project:

| Sample plan | This plan |
|---|---|
| Guardrail (a rule outside the model that keeps it from answering unsafely) is a Week-3 feature after a "baseline" (the simplest version, kept only for comparison) is built. | Guardrail is the project. The baseline exists only to be measured against and to show *why* it fails. |
| Refusal = "not enough evidence, contact the agency". | Refusal must still help the citizen: name the receiving agency, link the official procedure page, say exactly what is and is not known. The professor wrote "từ chối **/ chuyển tuyến**", not just "từ chối". |
| All checks are LLM judgments (`supported: fully`). | Deterministic checks wherever the fact is structured (fees, document lists, agency names come from the DB and are string-matched). The LLM judges only narrative claims. |
| Evaluation = RAGAS (a standard library that scores RAG answers with a judge model). | RAGAS is required and will be reported, but it cannot measure the thing the project is about. A refusal/answer confusion matrix (a table of expected vs actual outcome) and a per-item hallucination rate (share of listed items not in the source) are added, and over-refusal (declining a question we could answer) is penalised. |
| 20 daily checklists. | 4 phases, each with a question to answer, an exit test, and a report artifact. A thin end-to-end slice runs in week 1. |
| Generic data notes. | Names the specific hazards of Vietnamese procedure data: procedure variants, province-set fees, the 2025 two-tier local-government reorganisation that changed receiving agencies, stale portal pages. |
| Operations noise (firewall, lockfile policy). | Dropped. Not graded, not the point. |

---

## 1. What the professor is actually grading

### 1.1 Rubric (verbatim from `description.md`) → what we must show

| Rubric line | What satisfies it | Where it will be evidenced |
|---|---|---|
| Kiến trúc LangGraph: nodes/edges/state rõ ràng, có conditional routing | A `StateGraph` (LangGraph's flowchart object: state = the shared record, nodes = steps, edges = which step follows) with typed state, ≥3 conditional edges (code that picks the next step from the state), bounded loops, ≥3 distinct terminal outcomes (answer / clarify / refuse-redirect) | `architecture.md`, graph diagram in report, LangFuse traces |
| Triển khai đúng kỹ thuật RAG nâng cao được gán (Self-RAG) | Reflection steps (the model checks its own work at fixed points) `retrieve?` → `relevant?` → `supported?` (and `useful?`), each a visible node/decision, with citations | `guardrails.md` §3, `self_rag.py`, traces |
| Chất lượng truy hồi: RAGAS (faithfulness, context precision/recall) | RAGAS run locally with an Ollama (local model server) judge, on a labelled test set, reported baseline vs guardrailed | `evaluation.md`, `eval/` results |
| Tích hợp đủ 3 loại tool (web search + database + RAG) | Each tool has a defined *role* and *trust level*, not just a call | `architecture.md` §2 |
| Trace được qua LangFuse | Every node, tool call, reflection verdict and refusal reason traced (recorded step by step in LangFuse); screenshots in report | Phase 1 (set up on day 1, not at the end) |
| Vận hành hoàn toàn nội bộ với Ollama | No cloud LLM anywhere, including the RAGAS judge; web search is the only outbound call | `HARDWARE.md`, `llm.py` |
| Demo hoạt động + báo cáo kỹ thuật | CLI demo covering the 3 terminal outcomes + report | Phase 4 |

Full line-by-line mapping: `rubric-traceability.md`.

### 1.2 The sentence that matters most

> **Thách thức chính:** Thiết kế guardrail an toàn; ưu tiên từ chối/chuyển tuyến hơn là bịa thông tin thủ tục.

Read it as three obligations:

1. **Never state a procedure fact (document item, fee, agency, deadline) that is not in retrieved official evidence.** This is a hard constraint, not a tendency.
2. **When evidence is missing, do not go silent — redirect.** The expected output in the professor's test set for the out-of-corpus case is "từ chối **+ chỉ dẫn cơ quan**".
3. **Do not hide behind refusal.** A system that refuses everything is trivially "safe" and useless. Over-refusal must be measured and reported as a failure mode, same as hallucination.

The project's intellectual content is the tension between (1) and (3), and the engineering content is
making (2) reliable when the LLM itself cannot be trusted to know when it is wrong.

### 1.3 The demo is not the deliverable; the conduct is

The rubric line is "Demo hoạt động **+ báo cáo kỹ thuật**", and the other six lines are design and
discipline requirements that a working demo does not prove. A grader at the defence will ask *how*
each requirement was met and *how we know*. So every rubric line needs two kinds of evidence:

| Kind | What it looks like | Where it accumulates |
|---|---|---|
| **Design evidence** — the requirement is met by construction | State/node/edge tables, trust-tier table (how far each tool's output may be trusted), schema, Self-RAG mapping | `docs/03_design/*` |
| **Conduct evidence** — we verified it, and we can show the verification | `pytest` results for each guardrail layer, LangFuse traces with variant tags, a test set frozen *before* prompt tuning, eval result files per variant, the decision log, the journal with observed failures and numbers, reproducible commands | `tests/`, LangFuse, `eval/results/`, `DECISIONS.md`, `journal.md`, `README.md` |

Rules that follow from this:

- Nothing is "done" without a test or a measurement that would fail if it were undone.
- Work in the order the design says, and when the order changes, log why. The defence can ask "why did you build X before Y".
- The report shows method before results: how the test set was built and frozen, how the judge was configured, how variants were held constant.
- Keep the baseline, ablation and final runs reproducible from one command each; graders may ask to see one run.

`rubric-traceability.md` has a column for each kind of evidence; a row is not complete until both are filled.

---

## 2. The real-world problem, stated honestly

The user is a citizen (or a ward clerk helping one) who needs to complete a procedure. What they
need is not a paragraph; it is a correct checklist, the right counter, the right fee, the right
timeline. Every wrong item costs them a wasted trip, a rejected file, or a missed deadline.
A chatbot that is 90% right is worse than the portal page, because the user cannot tell which 10% is wrong.

Hazards specific to this domain (each one becomes a test category in `evaluation.md`):

- **Procedure variants that look alike.** "Đăng ký khai sinh" exists as: thông thường; có yếu tố nước ngoài; đăng ký lại; kết hợp nhận cha-mẹ-con; lưu động; cho trẻ bị bỏ rơi. Dense retrieval (search by meaning, using embeddings) returns chunks (section-sized pieces of text) from several of them and the LLM blends their document lists. The guardrail must resolve *one* procedure before listing documents, or ask the user which one.
- **Fees differ by province.** Hộ tịch fees are set by provincial People's Councils (HĐND); many cases are fee-exempt. A fee answer without a jurisdiction qualifier is misleading even when the number is "in the corpus".
- **The receiving agency changed in 2025.** Vietnam reorganised local government (province mergers, abolition of the district level, effective 2025-07-01). Pages, PDFs and web results still name "UBND huyện" or former provinces. `cơ quan tiếp nhận` is therefore the *most volatile* field and the one where web search for updates matters most. (Verify the exact current state at build time; record in `journal.md`.)
- **Online vs in-person channels** (DVC trực tuyến toàn trình / một phần) have different document forms.
- **Users ask personal-case questions** ("mẹ Việt, bố Hàn, con sinh ở Seoul, đăng ký ở đâu?"). The assistant must map to a procedure and redirect, not perform legal determination.
- **Users assert false premises** ("Lệ phí khai sinh là 50.000đ phải không?"). The model's instinct is to agree.
- **Working days vs calendar days**, and "ngay trong ngày" edge cases, in processing times.

What "beneficial" therefore means here: the user leaves with (a) only facts that are traceable to an
official record, (b) an explicit list of what the assistant could not confirm, and (c) a next step
(agency name, portal link) even in the worst case.

---

## 3. Learning goals — what you should be able to explain at the defence

1. Why a LangGraph graph (explicit state, nodes, conditional edges) is a better home for guardrails than a prompt: every decision is inspectable, bounded and testable in isolation.
2. What Self-RAG is in the paper (trained reflection tokens: special words the model learns to emit to judge its own retrieval and output) versus what we implement (prompted reflection with structured output, i.e. separate prompts whose answers are forced into a fixed JSON format), and why the latter is the only option with off-the-shelf Ollama models. Say "Self-RAG-style reflection" in the report.
3. Where an LLM judgment is acceptable (relevance of a narrative chunk) and where it is not (whether a fee number matches the record), and how the architecture reflects that split.
4. Why the three tools have different *trust levels* and how evidence from each is allowed, or not allowed, to support each type of claim.
5. Why "refuse" is not one thing: out-of-scope, ambiguous, unresolved procedure, resolved-but-unsupported, stale. Each gets a different user-facing response.
6. What RAGAS measures, what it does not, and why faithfulness of a refusal is undefined.
7. The over-refusal / hallucination trade-off as a measured curve, not a slogan.
8. What a local 10B model (about 10 billion parameters) at `temperature=0` (no randomness: same input, same output) reliably does and does not do in Vietnamese (JSON compliance, agreement bias, blending of near-duplicates), with evidence from your traces.
9. For any rubric line, the process by which it was met and verified: which test, which trace, which eval file, which decision entry. "It works in the demo" is not an answer.

---

## 4. Scope decisions

**In scope**
- Domain: hộ tịch (civil registration) as the core, plus cư trú / CCCD if the professor's dataset or our scrape includes them (the professor's sample test set uses CCCD, so at least a few CCCD procedures should be present).
- Corpus: 30–60 procedure records (professor suggests 50–200; the lower end is enough to exhibit every hazard above, and leaves time for the guardrail work). Start with 8–10 for the vertical slice.
- Tools: Chroma (vector database) + bge-m3 (embedding model) (RAG), SQLite (DB), DuckDuckGo with a domain allowlist (only listed sites are used) (web).
- Interface: a CLI (`python -m src.cli "câu hỏi"`) and the LangFuse UI. That is the demo.
- Evaluation: RAGAS + custom safety metrics, baseline vs guardrailed, on a 50–60 item labelled set.

**Out of scope, explicitly**
- A web/mobile UI. The professor said the expectation is understanding structure, not deployment.
- Free-form Text-to-SQL (the model writes database queries itself). Templated, parameterised queries (fixed queries where only a value is filled in) are safer and sufficient; this is a defended decision (see `DECISIONS.md`).
- Multi-turn conversation memory beyond a single clarify → answer exchange.
- Fine-tuning any model.
- Covering all provinces' fee schedules. We model jurisdiction as a field and refuse to state a fee when jurisdiction is unknown and fees vary.

---

## 5. System at a glance

Detail in `docs/03_design/architecture.md`. One-paragraph version:

A question enters `assess_need`, which decides whether retrieval is needed at all (`retrieve?`) and
extracts intent (documents / fee / agency / time / steps / update) and procedure hints. `resolve_procedure`
pins the question to exactly one procedure id using the DB title table plus hybrid retrieval (keyword search and meaning search merged); if several
candidates tie, the graph exits to **clarify**; if none, it goes to `web_lookup` in redirect mode.
`gather_evidence` pulls DB rows (structured facts) and corpus chunks *filtered by that procedure id*
(narrative; corpus v2: procedure-page chunks plus chunks of the legal articles, forms, change notices and guidance linked to that procedure). `grade_relevance` (`relevant?`) drops noise. `draft_answer` writes with inline citations,
rendering structured facts from DB rows rather than from the LLM's memory. `check_support` (`supported?`)
splits the draft into claims: structured claims are string-checked against rows, narrative claims are
LLM-judged against the cited chunk. `decide` (as built: the conditional edge `after_decide`, not a node) then routes to **answer** (all supported), **answer with
explicit gaps** (minor claims removed and declared unknown), or **refuse-redirect** (core claim unsupported),
with one bounded rewrite loop. The receiving agency for the redirect comes from the DB, never from
generation. Every node writes to LangFuse.

The three tools and what each is trusted for:

| Tool | Trusted for | Not trusted for |
|---|---|---|
| SQLite (`procedures`, `required_documents`, `fees`, `agencies`, `sources`; corpus v2 adds `documents`, `document_sections`, `document_procedures`) | Fees, document lists, agency, processing time, procedure identity | Narrative steps, conditions |
| Chroma / bge-m3 over official text | Steps, conditions, legal basis, explanations; relevance grading | Being the sole support for a number or a list item (corpus v2: an amended original law text, marked `[Văn bản gốc – đã sửa đổi]`, never supports an authority or a deadline) |
| Web search (allowlisted `*.gov.vn`, secondary legal sites) | Detecting that something changed (corpus v2: dated change notices in the corpus do this too); finding the official page for an out-of-corpus procedure (redirect) | Supplying any document item or fee into an answer |

---

## 6. Guardrail strategy (summary)

Detail in `docs/03_design/guardrails.md`. Layers, outermost first:

- **L0 Scope gate** — not a procedure question / asks for legal judgment / personal data → scoped response, no retrieval.
- **L1 Procedure resolution** — one id or ask. Prevents variant blending, the most frequent and most dangerous error.
- **L2 Evidence tiers** (trust levels) — DB > official corpus text > allowlisted web > anything else (discarded). A claim type may only be supported by a tier at or above its minimum.
- **L3 Relevance reflection** (`relevant?`) — per chunk, structured JSON, fail-closed (an unreadable answer counts as "no", never as "yes") on parse error.
- **L4 Claim-level support** (`supported?`; a claim is one sentence of the draft) — hybrid programmatic/LLM; partial support yields a partial answer with declared gaps, not a blended one.
- **L5 Output constraints** — structured facts are rendered from rows by code; the LLM phrases around them. Citations must map to evidence ids that exist in state.
- **L6 Loop bounds & fail-closed** — `iteration ≤ 1` rewrite; any tool error, timeout or JSON failure routes to refuse-redirect, never to generate.
- **L7 Freshness** — every answer carries `retrieved_at` of its source; records older than a threshold or touching `cơ quan tiếp nhận` trigger `web_check` and an "verify at the counter" notice. Corpus v2: a linked change notice that is in force and newer than the record also triggers a notice, printed by code with its title, effective date and URL.

Refusal policy: five refusal types, each with a distinct response template that always includes a next step.

---

## 7. Evaluation strategy (summary)

Detail in `docs/03_design/evaluation.md`.

- **Test set (50–60 items)** across: in-corpus structured, in-corpus narrative, near-miss variant (a look-alike sibling procedure), false premise (the question asserts something wrong), jurisdiction-dependent, out-of-corpus, out-of-scope, stale/update. Each item has gold answer or gold refusal type, gold procedure id, gold source ids.
- **Required metrics:** RAGAS faithfulness (does the answer follow from the retrieved text?), context precision (is the retrieved text relevant?), context recall (does it contain what the gold answer needs?) (answer relevancy if stable), judge = `qwen3.6` local, embeddings = bge-m3.
- **Safety metrics:** answer/refuse confusion matrix (should-answer × did-answer); hallucinated-item rate for document lists; wrong-number rate for fees; procedure-resolution accuracy; over-refusal rate on answerable items.
- **Comparison:** the professor's skeleton as-is (baseline) vs. the guardrailed graph, same data, same models. Plus two ablations (the product with one layer switched off): no procedure resolution; LLM-only support check. These ablations are what make the report an analysis rather than a build log.
- **Cost:** latency and LLM calls per question, because reflection roughly doubles both.

---

## 8. Phases

Each phase has a *question it answers*, *what gets built*, an *exit test*, and the *report artifact* it produces.
Dates assume a start on 2026-10-13; adjust in `journal.md`.

### Phase 1 — Vertical slice & observe the baseline failing (week 1, 13–19 Oct)

*Question:* What does the professor's skeleton do, unmodified, on the professor's own three test questions and two near-miss questions, and where exactly does it go wrong?

Build:
- `uv` venv (Python 3.11), install `langgraph langchain-ollama langchain-chroma rank-bm25 ragas langfuse` + pins; record versions.
- `llm.py` per `HARDWARE.md` (qwen3.5, `num_ctx=16384`, `keep_alive=-1`, thinking off; `make_judge()` for qwen3.6). Verify 1024-dim embeddings.
- LangFuse self-hosted via Docker (`docker compose`), callback wired into `app.invoke` **from day 1**. Seeing the traces is how you learn the interactions.
- Data: decide source (professor-provided vs own) — see `data-model.md` §5 and `questions-for-professor.md`. Hand-curate 8–10 procedures (≥3 khai sinh variants, kết hôn, khai tử, 1–2 CCCD) into the canonical record format, load SQLite with the professor's schema, index with Chroma.
- The professor's skeleton (`state/nodes/graph/tools`) running end to end, plus their `self_critique`/`gate` as given.

Exit test: run the 3 professor questions + "Hồ sơ đăng ký khai sinh cho con có bố là người nước ngoài?" + "Lệ phí khai sinh là 50.000đ đúng không?". Save outputs and traces. Expect blended document lists, agreement with the false premise, and a dead-end refusal. **Write these failures up precisely** — they are the motivation section of the report.

Report artifact: §Motivation (observed baseline failures), §Environment.

### Phase 2 — Data at target size, tools with roles, test set v1 (week 2, 20–26 Oct)

*Question:* With 30–60 real records and a labelled test set, how good is retrieval alone, and which hazards from §2 actually show up in the data?

Build:
- Corpus to 30–60 records with provenance (`source_url`, `retrieved_at`, `effective_date`, content hash). Section-aware chunking (per `data-model.md`), metadata `procedure_id`, `section`.
- DB extended with `sources` (provenance), `fees` and `agencies` tables; templated read-only queries (`get_documents(pid)`, `get_fee(pid, province)`, `get_agency(pid)`, `search_titles(q)`).
- Web tool with domain allowlist and result normalisation into the same evidence record shape.
- Hybrid retrieval (BM25 keyword scoring + dense meaning search) for title/procedure resolution; measure hit@1/hit@3 (right procedure ranked first / in the top three) on the test set.
- Test set v1 (≥40 items) in `data/testset.jsonl` with gold fields.
- Baseline eval snapshot (skeleton graph) with RAGAS + safety matrix. Keep it; it is the "before".

Exit test: procedure-resolution hit@1 ≥ 0.85 on in-corpus items; every record traceable to a URL; baseline numbers recorded.

Report artifact: §Data, §Tools, §Baseline results.

### Phase 3 — The guardrailed graph (week 3, 27 Oct–2 Nov)

*Question:* Does each guardrail layer reduce a specific failure without raising over-refusal, and can we show that per layer?

Build, in this order, re-running the safety matrix after each step:
1. `assess_need` + scope gate (L0) and `resolve_procedure` with the clarify terminal (L1).
2. Evidence tiers and procedure-id-filtered retrieval (L2).
3. `grade_relevance` with structured output + fail-closed parsing (L3).
4. `draft_answer` with code-rendered structured facts and citations (L5).
5. `check_support` hybrid; partial-answer path; `refuse_redirect` with DB agency + portal link (L4).
6. Loop bounds, error routing (L6), freshness notice + `web_check` (L7).
7. Adversarial additions to the test set: false premise, personal-case, prompt-injection-in-document, conflicting fee across chunks.

Exit test: on the test set, hallucinated-item rate near 0 on document questions; correct-refusal rate on out-of-corpus ≥ 0.9; over-refusal on in-corpus ≤ 0.15; no path reaches `finalize` with an uncited structured claim (assert in a test).

Report artifact: §Architecture, §Guardrail design, §Per-layer results.

### Phase 4 — Evaluation, ablations, report, demo (week 4, 3–9 Nov)

*Question:* What did we learn about building a trustworthy LLM tool for this domain, with numbers?

Build:
- Final RAGAS run (local judge) + safety metrics, baseline vs guardrailed vs 2 ablations.
- Latency / calls-per-question table.
- Case studies: 2 correct answers, 1 partial answer with gaps, 1 clarify, 1 refuse-redirect, 1 remaining failure (be honest).
- `README.md` with reproduction commands; CLI demo script with the six case studies; LangFuse screenshots.
- Report (outline in §9). Defence rehearsal against §3.

Exit test: a fresh clone + `make demo` reproduces the six cases; the report answers every rubric line in `rubric-traceability.md`.

---

## 9. Technical report outline

1. Problem & why hallucinated procedures are worse than no answer (§2 of this plan, with the Phase-1 observed failures)
2. Requirements & rubric mapping
3. Data: sources, record model, provenance, hazards found
4. Architecture: state, nodes, edges, tool roles and trust tiers, graph diagram
5. Self-RAG-style reflection: what the paper does, what we do, the four reflection points
6. Guardrails: failure catalogue → layer → mechanism → test
7. Method: how the test set was built and frozen, judge configuration, what was held constant across variants, how guardrail tests are run
8. Evaluation: RAGAS, safety matrix, baseline/ablation comparison, latency
9. Case studies incl. a remaining failure
10. Limitations & what production would additionally need (jurisdiction coverage, freshness pipeline, human escalation)
11. Reproduction

---

## 10. Hardware mapping (from `HARDWARE.md`)

| Role | Model | Settings | Note |
|---|---|---|---|
| Generation, routing, reflection (as built: generation, classification and query rewrite only; reflection moved to `qwen3.6`, `src/llm.py`) | `qwen3.5` (9.7B Q4: weights stored in 4 bits to fit the GPU) | `temperature=0`, `num_ctx=16384`, `keep_alive=-1`, thinking off | ~80 tok/s; fits one GPU with room |
| RAGAS judge (as built: also the in-graph relevance/support judge) | `qwen3.6` (36B MoE: mixture of experts, only part of the model runs per word) | same, loaded only during eval (as built: resident during every run) | 23 GB; keep on the second GPU (as built: ~24 GB split across both GPUs) |
| Embeddings | `bge-m3` | default | 1024-dim |

Cautions carried over: always set `num_ctx` (the most tokens one call can hold; defaults to 262K and eats VRAM, the GPU's memory); `OLLAMA_NUM_PARALLEL=6` multiplies KV cache (memory the model keeps per request), so if OOM appears lower context first; `/home` is 96% full, put Chroma, LangFuse volumes and data under `/home/student02`. `qwen2.5:7b` from the guidance is not installed; `qwen3.5` substitutes (ask professor, see questions).

---

## 11. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Data acquisition eats week 1–2 (professor explicitly warns about this) | High | Vertical slice on 8–10 hand-curated records first; ask whether a dataset is provided; MoJ "Quyết định công bố TTHC" PDFs as a cleaner alternative source |
| 10B model does not reliably emit JSON for reflection | Medium | Use `with_structured_output` / `format="json"`; fail-closed on parse error; measure parse-failure rate |
| RAGAS version mismatch with the professor's snippet; local judge noisy on Vietnamese | High | Pin version, wrap Ollama LLM/embeddings explicitly, run judge twice on a sample to estimate noise, report it |
| Over-refusal makes the system useless | Medium | Over-refusal is a first-class metric from Phase 2; partial-answer path |
| Variant blending slips past relevance grading | High (it is the main failure) | L1 procedure resolution + id-filtered retrieval; dedicated near-miss test items |
| Agency field stale after 2025 reorganisation | High | Freshness notice; `web_check` restricted to gov.vn; never generate the agency name |
| Scope creep into UI | Medium | Out of scope by decision; CLI + LangFuse is the demo |

---

## 12. Immediate next actions

1. Send `questions-for-professor.md` (dataset provided? model substitution? report language? LangFuse cloud OK?).
2. Create the code skeleton beside `docs/` (`src/`, `scripts/`, `data/`, `tests/`) and the `uv` venv.
3. Stand up LangFuse locally and run the professor's skeleton on 8–10 hand-curated records.
4. Record the baseline failures in `journal.md` — Phase 1 exit.
