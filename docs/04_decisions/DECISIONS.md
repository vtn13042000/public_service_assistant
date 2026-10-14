# Decision log

One entry per choice you might have to defend. Format: context → decision → consequences → alternatives rejected.
Keep entries short; link to the design doc that elaborates. Date each one.

---

## D-001 — Use `qwen3.5` instead of the guidance's `qwen2.5:7b` (2026-10-10)

**Context.** Guidance names `qwen2.5:7b`; the machine has `qwen3.5` (9.7B, Q4_K_M: a 4-bit compressed version of the model weights, so it fits in GPU memory), `qwen3.6`, `gpt-oss`, and 61 GB free on `/home`.
**Decision.** Generator/reflector = `qwen3.5` with thinking disabled (the model does not write hidden step-by-step reasoning before answering), `num_ctx=16384` (how many tokens the model reads at once), `temperature=0` (always pick the most likely word, so runs are repeatable). Judge = `qwen3.6`.
**Amended 2026-10-10 (as built).** qwen3.5 = scope/intent classifier, narrative generator, query rewrite; qwen3.6 = the in-graph relevance/support judge AND the RAGAS judge (see CONCEPTS C4, R6). The reflection verdicts therefore run on the larger model; consequence for evaluation independence is stated in R3 §5.
**Consequences.** Must disclose the substitution; must disable thinking for determinism and latency; must confirm with the professor (Q2).
**Rejected.** Pulling `qwen2.5:7b` (disk, and no evidence it is better); using `qwen3.6` as generator (slower cold start, VRAM pressure alongside the judge).

## D-002 — "Self-RAG-style" prompted reflection, not trained reflection tokens (2026-10-10)

**Context.** The original Self-RAG fine-tunes (retrains the weights of) the generator to emit `Retrieve/ISREL/ISSUP/ISUSE` tokens (special words meaning: should I search? is this passage relevant? is my sentence supported by it? is the answer useful?). We have off-the-shelf Ollama models and no fine-tuning budget.
**Decision.** Separate structured-output calls (the model must answer in a fixed JSON form, e.g. {relevant: yes/no}) per reflection point, with programmatic checks replacing the LLM where the fact is structured. Name it honestly in the report.
**Consequences.** More LLM calls per question (measure); each decision is inspectable and testable; code can override the LLM.
**Rejected.** Pretending a single `supported` flag is Self-RAG; downloading a Self-RAG checkpoint (not available via Ollama, English-centric).

## D-003 — Templated parameterised SQL instead of free-form Text-to-SQL (2026-10-10)

**Context.** Rubric requires a database tool; guidance's skeleton leaves `route_sql` as TODO. Text-to-SQL (the LLM writes the database query itself) by a 10B model on Vietnamese column names is error-prone, and a wrong-but-valid query produces a confident wrong fee.
**Decision.** Fixed, parameterised functions (fixed query text; the user's words are passed in as values, never as code) `search_titles`, `get_procedure`, `get_required_documents` (named `get_documents` in this decision as first written), `get_fees`, `get_agency`, `get_source`; the LLM chooses the *intent*, code chooses the query.
**Consequences.** DB answers are deterministic and verifiable by string match (enables L4 code checks). Less "agentic" looking; justify by the guardrail requirement.
**Rejected.** LLM-generated SQL with read-only connection (read-only prevents damage, not wrong answers).

## D-004 — Resolve one procedure before retrieving details (2026-10-10)

**Context.** Variant blending (F2: mixing the paperwork of two sibling procedures, e.g. khai sinh vs khai sinh có yếu tố nước ngoài) is the most frequent dangerous failure observed in naive RAG on procedure corpora.
**Decision.** `resolve_procedure` is deterministic (BM25 (keyword-match score) + dense (embedding-similarity) search over titles/summaries, with confidence and gap thresholds: the top match must score high enough and clearly beat the runner-up); detail retrieval is filtered by the resolved id; ties go to `clarify`.
**Consequences.** Adds a terminal and an ablation; thresholds must be tuned and reported.
**Rejected.** Relying on the relevance grader alone (it sees chunks, not procedure identity).

## D-005 — Partial answers are allowed; blended answers are not (2026-10-10)

**Context.** The skeleton refuses the whole answer on `supported != fully`, which drives over-refusal (F9). The professor wants refusal *over fabrication*, not refusal over everything.
**Decision.** Claim-level verdicts; minor unsupported claims are removed and listed as "không tìm thấy căn cứ"; core unsupported claims → refuse-redirect.
**Consequences.** Needs a core/minor classification per claim (the user's asked-for fact type is core; `premise` is always core).
**Rejected.** All-or-nothing refusal.

## D-006 — Web search is for redirection and freshness, never for facts (2026-10-10)

**Context.** Rubric requires web search; description says "fallback khi corpus không có hoặc lỗi thời". Unvetted snippets would bypass every other guardrail.
**Decision.** Allowlist (only these domains are accepted: `dichvucong.gov.vn`, `*.gov.vn`, secondary legal sites as `web_other` for links only). Web evidence can support a "this may have changed, see link" notice or a redirect link, never a document item, fee, agency or deadline.
**Consequences.** Web path is visibly weaker; explain the trust-tier reasoning (evidence is ranked: our database > official site > other site) in the report.
**Rejected.** Feeding web results into generation as the skeleton does.

## D-007 — Section-based chunking with procedure/section prefix (2026-10-10)

**Context.** Skeleton uses 700/100 character splitting (cut text every 700 characters, with 100 characters repeated between pieces); guardrails need section metadata.
**Decision.** One chunk per section per procedure, prefixed with title and section, metadata `procedure_id`/`section`/`source_id`.
**Consequences.** Enables intent-to-section evidence gathering and the F2 mitigation; cheap ablation vs 700/100.
**Rejected.** Character splitting (loses structure).

## D-008 — CLI + LangFuse is the demo; no web UI (2026-10-10)

**Context.** The professor's stated expectation is understanding structure and interactions, not a deployable product.
**Decision.** `scripts/demo.py` runs the six walkthrough cases; LangFuse shows the internals live. *(As built 2026-10-10: `scripts/demo.py` was not written; the cases run through `src/cli.py` and `tests/e2e/test_walkthroughs.py`. A demo script is still owed for the demo bullet.)*
**Consequences.** Time goes to guardrails and evaluation.
**Rejected.** Streamlit/Gradio front end (fine as a stretch goal after Phase 4 exit test passes).

## D-009 — LangFuse self-hosted via Docker (2026-10-10, pending Q4)

**Context.** Rubric says "vận hành hoàn toàn nội bộ"; LangFuse cloud would send prompts and retrieved text off-premise.
**Decision.** Self-host with `docker compose`, volumes under `/home/student02`.
**Consequences.** One more service to run; traces stay local.
**Rejected.** LangFuse cloud (unless the professor says it is acceptable; then still prefer local).

## D-010 — English identifiers in schema, code and metadata; Vietnamese data (2026-10-10)

**Context.** The guidance's sample schema uses Vietnamese table/column names (`thu_tuc`, `ho_so`, `le_phi`…). The user's requirement: the *data* is Vietnamese; the structure and codebase behind it need not be.
**Decision.** All tables, columns, section ids, state fields, evidence ids and function names are English. Content strings stay Vietnamese verbatim. A mapping table (`data-model.md` §2) shows one-to-one correspondence to the guidance schema and goes in the report.
**Consequences.** Code reads consistently (no mixed `get_fees` / `le_phi`); user-facing text and chunk prefixes remain Vietnamese; the loader test asserts every guidance field has a populated English counterpart (traceability row D2).
**Rejected.** Mirroring the guidance names (mixed-language code, no semantic gain).

## D-011 — Conduct evidence is a deliverable alongside the demo (2026-10-10)

**Context.** The rubric reads as design and discipline requirements plus "demo + báo cáo". A working demo does not prove conditional routing, correct Self-RAG, local-only operation, or honest evaluation; the defence will ask how each was met and verified.
**Decision.** Every rubric row carries design evidence and conduct evidence (`rubric-traceability.md`); nothing is "done" without a test or measurement; the test set is frozen before prompt tuning; the report puts Method before Results; baseline/ablation/final runs are reproducible with one command each.
**Consequences.** Some time moves from features to tests and bookkeeping; `journal.md` and `DECISIONS.md` are kept current, not reconstructed at the end.
**Rejected.** Demo-first, document-later.

## D-012 — Primary data source is the ministries' "Quyết định công bố TTHC", not the portal (2026-10-10)

**Context.** Worker w-dvc established that `dichvucong.gov.vn` is a client-side app whose robots.txt forbids the asset bundle; `csdl.dichvucong.gov.vn` sits behind a login; provincial portals (HCM, Đà Nẵng) expose a JSON API that needs an OAuth token obtainable only via a client secret embedded in public JS; `thuvienphapluat.vn` serves a Cloudflare challenge. Evidence in `data/raw/dvc/EVIDENCE.md`.
**Decision.** Use the legally authoritative publications (Bộ Tư pháp for hộ tịch; Bộ Công an for căn cước/cư trú), issued after 2025-07-01, as the primary corpus. No headless browser against robots-disallowed paths; no use of scraped client secrets to pass a 401, even though a browser does the same, because it circumvents an access control and this project is about trustworthy systems.
**Consequences.** Source is cleaner and carries explicit effective dates, but some files are scanned PDFs → an OCR step (reading text out of scanned images; tesseract + Vietnamese data) with page-level provenance. Provincial fee rows are not available → fees that vary by province are modelled as `jurisdiction="theo tỉnh"` and answered partially. The portal's inaccessibility is itself a report finding (freshness/redirect design must point users to the portal rather than mirror it).
**Rejected.** Playwright against the SPA; token-from-bundle API access; abandoning web sources entirely (web search for update detection stays).
**Amendment (as built, 2026-10-10).** The procedure content came from the ministries' own **portal pages** (`moj.gov.vn` procedure pages, `dichvucong.bocongan.gov.vn`), which are text; the decision texts used are 1833/QĐ-BTP part I (agencies) and the Đắk Lắk 33/QĐ-UBND annex. The OCR step was dropped under the owner's text-only rule (scanned decisions are out of scope). Đắk Lắk fee rows do exist, taken from the provincial annex; most say only "theo HĐND tỉnh" (set by the provincial council; the council resolutions are named in the annex's legal basis, not in the rows), and two carry an amount (8.000 đồng, the national fee). Province-dependent fees are therefore answered as "set by the provincial council" with the source, or with the amount when a row has one. The no-circumvention rule stands unchanged. Source list: `data/README.md`, `docs/03_design/data-model.md` §5.

## D-013 — Data-model changes from the schema review (2026-10-10)

**Context.** Worker w-tools' review of `data-model.md` found 12 gaps (fields dropped by the DB, no ordering/quantity text, optional provenance id, no FTS table for the promised BM25 search, ambiguous fee semantics, path inconsistencies).
**Decision.** All accepted: `procedures` gains `channels`, `legal_basis`, `conditions`; `required_documents` gains `position`, `quantity_text`; `source.source_id` required and per (document, procedure) with optional `locator`; `sources.kind`; `procedures_fts` (FTS5, SQLite's built-in full-text search); `fees: []` means unknown and known-free must be explicit; paths `data/processed/<source>/<id>.json`, queries in `src/tools/db.py`, loader in `src/db.py`. w-tools applies the doc edits under a scoped exception.
**Consequences.** Parsers must emit the new fields; the loader is the single reader both DB and index use.
**Rejected.** Leaving the DB thinner than the record and relying on RAG for channels/legal basis.

## D-014 — Self-hosted SearxNG is the primary web backend; chinhphu.vn allowlisted as official (2026-10-10)

**Context.** Public engines throttle this host (fresh probe: DuckDuckGo 1/5 queries answered, Bing 0/2), so the DuckDuckGo-first web tool was not demo-safe. The professor's stack list names "SearxNG nội bộ" as an option.
**Decision.** Run SearxNG (a self-hosted search engine that forwards the query to public engines) in Docker on 127.0.0.1:8080 (`infra/searxng/`), chain `searxng,duckduckgo,bing`; allowlist, cache, spacing and the "web is for redirection/freshness, never facts" rule (D-006) unchanged. Add `chinhphu.vn` (Government portal incl. xaydungchinhsach/baochinhphu) as `web_official`.
**Consequences.** Probe 5/5 queries return allowlisted results; only 2/5 had a *.gov.vn hit before the chinhphu.vn addition. Inside SearxNG only DuckDuckGo and Bing respond (Google denies, Brave rate-limits); documented in R4 §5. SearxNG's outbound calls remain the single sanctioned external traffic (R6).
**Rejected.** Paid search APIs (Tavily etc.; external dependency, key management); relying on DuckDuckGo alone.

---

Template for new entries:

```
## D-015 — Base-title preference among tied sibling procedures (2026-10-10)

**Context.** The independent audit found the professor's first sample question ("Hồ sơ đăng ký khai sinh gồm những gì?") ending in a clarify between
"đăng ký khai sinh" and "đăng ký khai sinh lưu động" in every variant. The qualifier-only rule (ignore a sibling that differs only by a qualifier the user did
not say) had been switched off for the documents intent, to protect against variant blending (F2) where document lists differ most; and the function word
"có" in a question matched the qualifier "có yếu tố nước ngoài".
**Decision.** Among tied siblings, drop every title that is another tied title plus a qualifier the user did not say, for every intent, even when the base ranks
below its qualified sibling. A qualifier counts as said only when its content words appear in the hint or the question; function words and question words never
count. The answer ends with a line naming the procedure answered and the sibling to ask about if it applies. Behind `base_title_preference` (default off; on in
variant v3) so earlier variants stay reproducible.
**Consequences.** Held-out: two clarifies become correct answers, no new unsafe or wrong-procedure answers; frozen: the professor's row 1 is answered (this gain is
selection, since the item motivated the change). Residual risk accepted: a user whose situation implies a variant without naming it ("con sinh ở Hàn Quốc")
receives the base list plus the naming line instead of a question.
**Rejected.** Patching T-001 alone; subtracting the generic-word list proposed by the audit (it contains "nước ngoài" and "biên giới", so a user saying "người
nước ngoài" would wrongly get the base list).

## D-016 — Named presets shared by product and evaluation; v3 is the live default (2026-10-10)

> Superseded in part: the live default moved to v4 at 15:36Z (D-016 mechanism unchanged) and to v5 at 19:29Z, see D-017.

**Context.** After Rounds 2 and 3 the evaluation runner defined its variants as flag literals, while the CLI and the web UI ran on code defaults that matched
neither the release flags (v1) nor the recommended configuration (v3). A demo or an audit probe would therefore have measured a configuration no table reports.
**Decision.** One module, `src/presets.py`, defines v1, v2, v3 and baseline (graph flags and environment); the CLI and the web UI resolve `guardrailed` to v3
unless `--preset` says otherwise; the evaluation runner imports the same sets; every run records its preset in the state, the LangFuse tags and the output;
a test fails if the presets drift from the documented flag sets or from the runner.
**Consequences.** The product and the numbers describe the same configuration by construction. Older variants stay reproducible by name.
**Rejected.** Changing code defaults flag by flag (no single place to read the configuration from; drift between product and evaluation remains possible).

## D-017 — v5 (v4 + family-noun guard) is the live default; one current product, no version labels in the UI, slides or demo (2026-10-10 19:29Z)

**Context.** The owner's own question ("đăng ký khai sinh để điền tên cha có cần phải có giấy kết hôn …") was answered by the live app from the wrong
procedure (đăng ký kết hôn) in three of three probes: the short title was fully covered by the words "giấy kết hôn", and after the premise post-check removed
the invented fee premise no narrative was drafted, so the rows of the wrong procedure passed every later check. The question is in no test set.
**Decision.** The resolver's family-noun guard (a candidate whose title family is not the family the question names first cannot win; two families named with
neither first → ask; no family named → untouched; the two-family clarify only between candidates above the coverage floor) is on in preset v5, the live default
since 19:29Z. Measured twice officially: the first pass lost one correct refusal to a defect in the clarify branch, fixed; the re-run (REPORT.md "Round 5
variant v5", 19:18:37Z) differs from v4 on no frozen, held-out or adversarial item. The owner also ruled that the product shows one current version: no preset
or version label in the app UI, the slides or the demo text; evaluation tables, round logs and `src/presets.py` keep the names.
**Consequences.** The owner's question resolves to đăng ký khai sinh (3/3 probes) at four model calls instead of two; test-set numbers unchanged; documents
that named the live default were updated the same evening; older presets remain reproducible by name.
**Rejected.** Staying on v4 with the case documented as a known wrong-sibling failure (would have shown a wrong answer on the owner's own demo question);
switching without the official re-run (the first pass had a real defect).

## D-0XX — <title> (<date>)
**Context.**
**Decision.**
**Consequences.**
**Rejected.**
```
