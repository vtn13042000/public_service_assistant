# As built — components and the processing pipeline from input to output

Companion to `architecture.md` (the pre-implementation spec, kept unchanged). This document describes the system **as implemented on 2026-10-10**
(release v0.1), names the real modules, and lists where the build deviates from the spec and why. Read this to understand what happens to a
question; read `docs/06_rubric/CONCEPTS.md` for what each technique is and why it was chosen.

---

## 1. Component inventory

```
                 OFFLINE (build time)                                   ONLINE (per question)
 raw pages/PDF ─▶ parse_* ─▶ canonical records (JSON) ─▶ validate      question ─▶ LangGraph app ─▶ one of 5 outcomes
                                   │                                               │  reads
                     ┌─────────────┴─────────────┐                                 ├─ SQLite  data/app.db   (facts)
                     ▼                           ▼                                 ├─ Chroma  data/chroma   (text, bge-m3) + BM25
              build_db.py ─▶ SQLite      build_index.py ─▶ Chroma+BM25             ├─ SearxNG 127.0.0.1:8080 (web, allowlisted)
              (same precedence, same chunk ids, same procedure ids)                └─ Ollama  127.0.0.1:11434 (qwen3.5 / qwen3.6 / bge-m3)
                                                                                   every node ─▶ LangFuse 127.0.0.1:3000
```

| Layer | Module(s) | Responsibility | Not allowed to |
|---|---|---|---|
| Data acquisition | `scripts/crawl_bca_portal.py`, `scripts/parse_bca_portal.py`, `scripts/fetch_moj.py`, `scripts/moj_fetch_portal.py`, `scripts/parse_moj.py`, `scripts/moj_parse_daklak.py` | fetch text sources politely, parse into the canonical record (one JSON shape shared by every procedure, `docs/03_design/data-model.md` §1) with provenance (where and when each fact was fetched) | guess a field; OCR scans |
| Validation | `data/schema/procedure_record.schema.json`, `scripts/validate_records.py` | enforce field names/types; warn on smells | — |
| Relational store | `src/db.py` (loader), `scripts/build_db.py`, `data/variants.yaml` | one canonical record → `procedures`, `required_documents`, `fees`, `agencies`, `sources`, `procedures_fts` (FTS5 full-text index on titles); `--docs` adds the cleaned depth documents → `documents` (210), `document_sections` (332), `document_procedures` (857) (corpus v2; 57 procedures as before); precedence (which source wins when two describe the same procedure) moj-portal > bca-portal > daklak; Đắk Lắk fee rows always kept; `variant_of` (marks sibling variants of one procedure, e.g. with / without a foreign element) from config; unit-less processing times filled from the provincial source with their own provenance id | run while `data/.RUNLOCK` exists |
| Vector + lexical store | `src/ingest.py`, `scripts/build_index.py`, `scripts/sync_index.py`, `data/synonyms.yaml` | one chunk per section per procedure, prefixed `[Thủ tục: …] [Mục: …]`, plus one chunk per document section per linked procedure, prefixed `[Thủ tục: …] [Văn bản: …] [Mục: …]` (corpus v2: 2,429 chunks = 572 procedure + 1,857 document; v1 had 572); metadata `procedure_id, section, kind, source_id, variant_of` (+ `doc_id, doc_title, original_version` on document chunks); bge-m3 embeddings (each chunk turned into 1,024 numbers so that similar meaning gives nearby numbers) in Chroma, a vector database (telemetry, i.e. usage reporting, off); BM25 (keyword scoring) built in memory from the stored texts, statistics per chunk kind so resolution sees procedure chunks only | drift from the DB (reads records through `src.db.read_records` + `select_records`) |
| Tools | `src/tools/db.py`, `src/tools/rag.py`, `src/tools/web.py` | return `Evidence` records (`src/evidence.py`) with a trust tier (how far a piece of evidence may be trusted): `db` > `corpus` > `web_official` > `web_other` | DB: accept LLM SQL · RAG: return chunks without ids · Web: supply a fact |
| Models | `src/llm.py` | `get_llm()` qwen3.5 (narrative, rewrite; thinking off, `num_ctx` 16384 = the most tokens one call can hold); `get_structured_llm()` qwen3.5 schema-constrained (the reply is forced into a fixed JSON format) via `/api/generate` (scope/intent classifier); `get_structured_judge()` qwen3.6 (in-graph ISREL/ISSUP verdicts, i.e. "is this chunk relevant?" / "is this sentence supported?"; also the RAGAS judge); `get_embeddings()` bge-m3; all localhost. Injected (passed in from outside, so tests can swap in fakes) as `Deps.llm / classifier / judge` (`src/nodes.py`) | call a cloud API |
| Agent | `src/state.py`, `src/nodes.py`, `src/graph.py`, `src/self_rag.py`, `src/render.py`, `src/refusal.py`, `src/prompts/*.txt` | the pipeline in §2 | — |
| Baseline | `src/baseline/` | the first version (the starting system that came with the task), same `build_graph` signature, for comparison | — |
| Interface | `src/cli.py` | `--variant`, `--preset v1\|v2\|v3` (guardrailed runs the named flag set from `src/presets.py`, default v3; the output, JSON and trace name the preset), `--locality`, `--procedure` (after a clarify), `--json` | — |
| Observability | `src/tracing.py`, `infra/langfuse/` | one trace (the full record of one run) per question, one span (one timed step inside it) per node with decision metadata, tags `variant=`, `testset_id=` | — |
| Evaluation | `eval/run_variant.py`, `eval/safety.py`, `eval/ragas_run.py`, `eval/injection.py`, `eval/report.py` | run a variant over a test set under `data/.RUNLOCK`; safety matrix; RAGAS (a standard library that scores RAG answers) with the local judge; adversarial injection via dependency injection; report | touch `src/` |

---

## 2. The online pipeline, input → output

State is `AgentState` (`src/state.py`): the professor's fields plus `need`, `candidates`, `procedure_id`, `evidence`, `draft`, `claims`, `outcome`,
`refusal`, `freshness`, `errors`. Every node is wrapped (`src/nodes.py:_guarded`, the fail-closed wrapper: an error can only end in a refusal): an exception writes `errors` and later nodes do nothing; every
conditional edge sends a state with `errors` to `refuse_redirect(system_error)`. `MAX_REWRITES = 1`.

| Step | Node | Reads → writes | Decision / tool / LLM | Next (edge) |
|---|---|---|---|---|
| 1 | `assess_need` | `query` → `need` {in_scope, retrieve, intent ∈ documents/fee/agency/time/steps/general/update, procedure_hint, locality, premise} | 1 structured call to the **classifier** (qwen3.5, Retrieve? — the Self-RAG check "does this need a lookup?" — + scope gate). Parse failure → error. | `after_assess`: `in_scope=false` or `retrieve=false` → `out_of_scope`; error → `refuse_redirect`; else → `resolve_procedure` |
| 2 | `resolve_procedure` | `need` → `candidates`, `procedure_id`, `route` | no LLM by default (the Round-2 `story_rewrite` flag, off by default, adds 1 classifier call on the none path). `db.search_titles` (FTS5) + `rag.resolve_candidates` (keyword BM25 and meaning-based dense rankings merged by position, over summary and all chunks, synonym expansion) → score = 0.6·title-token F1 (word overlap between hint and title) + 0.4·normalised rank. Rule (`RESOLVE`): hint-word coverage (share of the hint's specific words found in the title) of the top candidate < `core_floor` 0.75 → **none**; a `variant_of` sibling within `sibling_gap` 0.25 or a non-sibling within `gap` 0.08 → **tie**; tie among siblings whose asked fact is identical in the DB → **sibling-invariant** pick (the answer is the same whichever sibling is meant, so answer for the top one); else **one**. Span metadata: candidates[:3], scores, thresholds, decision. | `after_resolve`: one → `gather_evidence`; tie → `clarify`; none → `web_lookup`; error → `refuse_redirect` |
| 3 | `gather_evidence` | `procedure_id`, `need.intent` → `evidence` | always `db.get_procedure` + `get_agency`; by intent also `get_required_documents` / `get_fees(pid)` (all jurisdictions; `need.locality` is applied later in `render.py`) (tier `db`) + `rag.retrieve(query, procedure_id, section, k=5)` chunks (tier `corpus`). Always one procedure. | → `grade_relevance` |
| 4 | `grade_relevance` (ISREL) | `evidence` → `grades.usable` | 1 batched structured call (one call for all chunks) to the **judge** (qwen3.6) over the chunks, documents wrapped as data (so text inside them is not obeyed as instructions); unparseable → irrelevant. DB rows are not graded. | `after_grade`: usable (at least one relevant chunk, or a non-empty code-built block from DB rows) → `draft_answer`; nothing usable & iteration 0 → `rewrite_query`; else → `refuse_redirect(insufficient_evidence)` |
| 4a | `rewrite_query` | `query`, `procedure_id` → `query'`, `iteration+1` | 1 generator (qwen3.5) call | → `gather_evidence` (once) |
| 5 | `draft_answer` | `evidence`, `need` → `draft`, `claims` | `render.py` builds the structured block **by code** from `db` rows (document checklist, fee lines grouped by jurisdiction, agency, processing time verbatim, premise verdict) with `[db:…]` ids; 1 **generator** (qwen3.5) call writes the narrative around the fixed block with `[doc:…]` ids; `split_claims` cuts the draft into claims (one sentence each) and tags core (needed for the answer) vs minor (extra). | → `check_support` |
| 6 | `check_support` (ISSUP) | `claims`, `evidence` → `claims[].verdict`, `grades.support` | hybrid: `db:`-cited claims verified by code (item ⊂ row, number equality after normalisation, agency/unit verbatim); `doc:`-cited claims must respect the tier rule (`evidence.can_support`) then 1 structured **judge** (qwen3.6) verdict against the cited chunk only; uncited or fabricated-id claims → unsupported. | `after_decide`: all supported → `freshness_check`; minor unsupported → `prune_claims`; core unsupported & iteration 0 → `rewrite_query`; else → `refuse_redirect(insufficient_evidence)` |
| 6a | `prune_claims` | removes minor unsupported claims silently (tested: `test_L4_unsupported_minor_narrative_pruned_silently`) | no LLM | → `freshness_check` |
| 7 | `freshness_check` | `evidence`, `need` → `freshness` | no LLM: intent `update`, or oldest `retrieved_at` > 180 days, or the answer names an agency → notice needed | `after_freshness`: notice → `web_check`; else → `finalize` |
| 7a | `web_check` | → `freshness.web_links` | `web.web_search(official_only=True)` via SearxNG; only `web_official` hits kept, then 1 judge call grades them relevant; produces links + a verify-at-counter sentence, never a fact; failure → generic notice | → `finalize` |
| 2a | `web_lookup` (none path) | `need.procedure_hint` → `web_results` (`refuse_redirect` turns the first official hit into `refusal.portal_url`) | `web.web_search(site="dichvucong.gov.vn")`, falling back to any allowlisted official site, + 1 judge call to grade the hits; link only | → `refuse_redirect(not_in_corpus)` |
| T | `finalize` | → `generation`, `outcome` ∈ {answer, answer_partial} | code: block + narrative + citations list + freshness notice; `gaps` (asked facts with no row, e.g. fee not specified, province needed) produce the "Không tìm thấy căn cứ về: …" section and make the outcome `answer_partial`; `final_safety_violations` refuses if any kept claim is unsupported or a block line fails its code check | END |
| T | `clarify` | `candidates` → `generation`, `outcome=clarify` | lists ≤ 4 sibling/neighbour titles; the follow-up passes `--procedure <id>` | END |
| T | `refuse_redirect` | state → `generation`, `outcome=refuse`, `refusal.type` ∈ {not_in_corpus, insufficient_evidence, ambiguous, system_error} | `refusal.py` builds the text from state only: what was asked, what is confirmed, what is missing, agency from the DB and/or portal link, data date | END |
| T | `out_of_scope` | → `generation` | template: what the assistant covers; personal eligibility → the procedure's agency | END |

Model calls per question: classifier 1 (scope) + judge 1 (relevance) + generator 1 (narrative) + judge 1 per narrative claim (code handles `db:` claims) + generator 0–1 (rewrite) + judge 1 if `web_check`/`web_lookup` runs. Official run: mean 3.1, p50 3, p95 7 (p50 = median; p95 = 95 % of items need no more) (`eval/results/REPORT.md`). Three models are resident during a run (qwen3.5 6.2 GB, qwen3.6 24 GB split across both GPUs, bge-m3 0.7 GB at 16k context).
Measured on the frozen set: latency p50 7.4 s guardrailed vs 10.2 s baseline (means 8.8 vs 12.3 s) — refusing early is cheaper than forced generation.

### What the LLM is trusted to decide, and what it is not

| Trusted (judgment) | Not trusted (code decides) |
|---|---|
| scope/intent classification; relevance of a narrative chunk; support of a narrative claim by its cited chunk; phrasing of the narrative | which procedure; any number, document item, agency name or deadline in the answer; whether a claim cites existing evidence; whether the answer is complete enough to send; the refusal text |

---

## 3. The offline pipeline, source → store

1. **Fetch** (text only, ≥ 2–4 s spacing, robots respected (the site's robots.txt crawl rules), every response cached with sha256 (a content fingerprint) + timestamp in `index.jsonl`).
2. **Parse** into the canonical record: `procedure_id` = national mã TTHC; `source.source_id` = `<document>#<procedure_id>`; `quantity_text` verbatim; `fees: []` means unknown, known-free is explicit.
3. **Validate** against the JSON schema (94/94 valid).
4. **Load** (`build_db.py`): precedence per `procedure_id`; all sources recorded; Đắk Lắk fee rows kept as extra rows; `variant_of` from `data/variants.yaml`; FTS5 title index.
5. **Index** (`build_index.py`): section chunks with prefix and metadata, same records and precedence as the DB; 572 chunks. Corpus v2 adds the cleaned
   non-procedure documents (2429 chunks). Resolution's BM25 statistics are computed over procedure chunks only, so the documents do not move
   resolution. `sync_index.py` applies later changes by embedding only the chunks that differ.
6. **Freeze/lock**: both scripts refuse while `data/.RUNLOCK` exists (a live evaluation would otherwise be invalidated — it happened once).

---

## 4. The evaluation pipeline

`run_variant.py` takes the lock, builds the chosen variant (`guardrailed`, `baseline`, `abl_no_resolve`, `abl_llm_support` (ablations: one guardrail layer switched off), and the Round-2 variants `guardrailed_v2`, `guardrailed_v2_q36`; list in `VARIANTS`) through
`build_graph` dependency injection (so adversarial items can inject evidence without touching `src/`), runs every test item with LangFuse tags, and stores
outcome, answer, cited ids, evidence texts, claims and verdicts, latency, trace id. `safety.py` computes the confusion matrix (gold outcome vs produced outcome) and rates (unsafe-answer incl.
wrong-procedure, correct-refusal by type, over-refusal, hallucinated-item, wrong-value, hit@1 (right procedure ranked first), citation validity, redirect completeness, attack-resisted).
`ragas_run.py` scores answered items only, with the local qwen3.6 judge and bge-m3 embeddings, OpenAI disabled, and re-judges 15 items for noise.
`report.py` writes `eval/results/REPORT.md` from result files only.

---

## 5. Deviations from the spec (`architecture.md`) and why

| Spec | As built | Reason |
|---|---|---|
| Resolve by "top score ≥ τ and gap ≥ δ" | lexical hint-coverage floor + sibling/same-field tie rule + sibling-invariant shortcut | measured: bge-m3 cosine ranges for out-of-corpus (0.584–0.745) and answerable (0.528–0.931) questions overlap; fused RRF (reciprocal rank fusion: merging rankings by position) scores are near-constant |
| Fixed-size 700/100 chunks (professor's skeleton) | section chunks with title/section prefix | variant blending (F2: facts of two sibling procedures mixed in one answer); section metadata lets intent select fee/document chunks |
| One `supported` flag | claim-level hybrid verdicts, core vs minor, prune path | one flag either sinks correct lists or rescues invented fees; a scripted test with a fake model shows an LLM-only judge can accept an invented fee; the real-model ablation `llm_support` shows the other failure, over-rejection (over-refusal 14 → 32 of 54, unsafe unchanged 1/72) |
| Web → generate | web only in `web_lookup` (link) and `web_check` (notice) | snippets must never become facts (F10: an unverified web snippet stated as fact) |
| DuckDuckGo direct | SearxNG self-hosted first | public engines throttle this host (1/5 → 5/5 probe) |
| `with_structured_output` on chat | schema-constrained `/api/generate` path | Ollama ignores `format` on chat for these models (3/20 enum violations) |
| Processing time from the winning source | fallback to the provincial wording with its own provenance id when the winner is unit-less | 7 ministry pages give a bare number with no unit (3 of them "5") |
| Error edges per node | `_guarded` wrapper + `errors` check in every edge | fewer edges, same guarantee; tested with 8 injected failures |

---

## 6. Diagrams

- Compiled graph (generated, not drawn): `docs/06_rubric/assets/graph.mmd`.
- Outcome histogram of the v0.1 outcome pass: `docs/06_rubric/assets/outcomes_guardrailed_histogram.md`.
- Request walkthroughs (spec): `architecture.md` §6; real traces: ids in `docs/06_rubric/R1-langgraph-architecture.md` §4.
