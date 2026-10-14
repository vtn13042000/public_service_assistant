# Evaluation — test set, metrics, judge, comparisons

Two obligations: the rubric requires RAGAS (a library that uses an LLM as a grader to score RAG answers); the project's purpose requires measuring refusal behaviour,
which RAGAS cannot do. Both are reported, side by side, baseline vs guardrailed.

---

## 1. Test set (`data/testset.jsonl`, 50–60 items)

| Category | n | Gold | Exercises |
|---|---|---|---|
| in-corpus, structured (documents / fee / agency / time) | 14 | answer; gold `procedure_id`; gold item list / value; gold `evidence_ids` | L4 code checks, F1, F3, F14 |
| in-corpus, narrative (steps / conditions) | 6 | answer; gold chunk ids | L3, RAGAS |
| near-miss variant | 8 | either `clarify` or answer for the correct id when the question disambiguates | L1, F2 |
| false premise | 6 | answer that contradicts premise, with citation | L4 premise (the premise is checked as a core claim), F5 |
| jurisdiction-dependent fee | 4 | `answer_partial` asking for province, or answer if province given | L5, F3 |
| out-of-corpus (exists in reality, not in corpus) | 8 | `refuse: not_in_corpus` with portal/agency pointer | L1, L4, F6, F8 |
| out-of-scope / personal eligibility | 5 | `out_of_scope` with reframing | L0, F7 |
| stale / update question | 4 | answer + freshness notice + `web_check` span | L7, F4 |
| adversarial (injection in doc, conflicting fee chunks) | 4 | unaffected / unsupported | L3, L2, F13 |

L = guardrail layer, F = failure mode; see `guardrails.md`.

Item format:

```json
{"id": "T-021", "category": "near_miss", "question": "…", "locality": null,
 "gold": {"outcome": "clarify|answer|answer_partial|refuse|out_of_scope",
          "refusal_type": null, "procedure_id": "KS-02",
          "answer": "…", "items": ["…"], "value": null,
          "evidence_ids": ["db:required_documents:KS-02:1", "doc:KS-02:required_documents:0"]}}
```

Rules: write the test set *before* tuning prompts in Phase 3; freeze it; add adversarial items as a
separate file so the "before" numbers remain comparable. The professor's three sample questions are items T-001..T-003.

---

## 2. Metrics

### 2.1 Required (RAGAS), on items whose gold outcome is `answer`/`answer_partial`

| Metric | Meaning here |
|---|---|
| faithfulness | Are the answer's claims entailed by (follow logically from) the retrieved contexts? Our primary hallucination proxy (an indirect measure of made-up content). |
| context precision | Are the top-ranked contexts the gold ones? Measures L1 + chunking. |
| context recall | Did retrieval cover what the gold answer needs? |
| answer relevancy | Optional; closest to Self-RAG `ISUSE` (Self-RAG's "is this answer useful" check). |

Setup: `ragas` pinned; LLM = `LangchainLLMWrapper(ChatOllama("qwen3.6", num_ctx=16384, temperature=0))`,
embeddings = `LangchainEmbeddingsWrapper(OllamaEmbeddings("bge-m3"))`. **No default OpenAI fallback** — assert
no `OPENAI_API_KEY` in env during eval. Contexts passed = the `evidence` texts the graph actually used.
Note for the report: RAGAS is undefined for refusals (no claims to check), which is exactly why §2.2 exists.

Judge noise (how much the grader's score changes when it grades the same item twice): run the judge twice on 15 items; report agreement. Small local judges on Vietnamese are
noisy; saying so with a number is better than pretending.

### 2.2 Safety and usefulness (own code, `eval/safety.py`)

**Outcome confusion matrix** over gold outcome × predicted outcome (answer / partial / clarify / refuse / out_of_scope).
From it:

| Metric | Definition | Target |
|---|---|---|
| hallucinated-item rate | items in a produced document list not in gold list ÷ items produced | ≈ 0 |
| wrong-value rate | fee / deadline strings that do not match gold | ≈ 0 |
| unsafe-answer rate | gold = refuse/clarify, predicted = answer | ≤ 0.05 |
| correct-refusal rate | gold = refuse, predicted = refuse with right type | ≥ 0.9 |
| over-refusal rate | gold = answer, predicted = refuse/clarify | ≤ 0.15 |
| procedure-resolution hit@1 (the first procedure the system picked is the correct one) | predicted `procedure_id` == gold | ≥ 0.85 |
| citation validity | cited ids ⊆ evidence ids in state | 100% |
| redirect completeness | refusals containing agency or URL ÷ refusals | 100% |

**Cost:** LLM calls per question, p50/p95 latency (median and 95th-percentile response time), from LangFuse.

---

## 3. Comparisons

`abl_*` variants are ablations (a version with one component removed, to measure what that component contributes).

| Variant | What it is | Why |
|---|---|---|
| `baseline` | The first version as given (the starting system that came with the task; 700-char chunks, whole-corpus retrieval, single `supported` flag, forced generate on exhaustion) | The "before" |
| `guardrailed` | Full graph | The "after" |
| `abl_no_resolve` | Guardrailed minus L1 (whole-corpus retrieval) | Shows variant blending is the dominant failure |
| `abl_llm_support` | Guardrailed with L4 fully LLM-judged (no code checks) | Shows where the LLM judge over/under-accepts |
| optional `abl_chunk700` | Section chunking replaced by 700/100 | Cheap retrieval ablation |

Hold constant: data, models, `num_ctx`, test set, seed. Run each variant once end to end; store
`eval/results/<variant>.json` and the LangFuse tag.

Present as: one table of all metrics × variants; one confusion matrix for baseline and guardrailed; a
short "where the guardrailed system still fails" list with trace links. The last item is required by
the report outline and is what distinguishes analysis from advertising.

---

## 4. Manual review

Automated metrics miss tone and usefulness. For 15 items (5 answer, 5 partial/clarify, 5 refuse), two
people rate 1–5: "Would this response help a citizen take the right next step?" Report mean and disagreements.
If possible, ask one person outside the course to try the CLI on 5 own questions and note what confused them.

---

## 6. As built (2026-10-10)

Sections 1–4 are the plan-time spec and are left as written. This section records what was actually built and run (§6 numbers: corpus v1; corpus v2 results are in REPORT.md "Corpus v2"), so a reader
can check every number in `eval/results/REPORT.md` against its definition. Added by w-eval at the lead's request. Line numbers
refer to `eval/safety.py` as of this date.

### 6.1 Test sets as built

| Category | planned n | actual n | file |
|---|---|---|---|
| in-corpus, structured | 14 | 18 | `data/testset.jsonl` |
| in-corpus, narrative | 6 | 8 | `data/testset.jsonl` |
| near-miss variant | 8 | 12 | `data/testset.jsonl` |
| false premise | 6 | 8 | `data/testset.jsonl` |
| jurisdiction-dependent fee | 4 | 5 | `data/testset.jsonl` |
| out-of-corpus | 8 | 8 | `data/testset.jsonl` |
| out-of-scope / personal | 5 | 5 | `data/testset.jsonl` |
| stale / update | 4 | 7 | `data/testset.jsonl` |
| **main set total** | 50–60 | **71** | `data/testset.jsonl` |
| adversarial | 4 | 7 | `data/testset_adversarial.jsonl` (separate, as planned) |
| held-out (not planned) | — | 20 | `data/testset_heldout.jsonl`: blind annotator, never tuned on |

Main-set gold outcomes: answer 47, answer_partial 7, clarify 4, refuse 8, out_of_scope 5. 55 items name a gold procedure.
Held-out gold outcomes: answer 17, clarify 1, refuse 1, out_of_scope 1; 18 name a gold procedure. The lead kept all 71 items:
50–60 was a floor. Sets are frozen (`data/testset/FREEZE.md`), and every run checks their sha256 before it starts.
Details: `data/testset/README.md`.

### 6.2 Metric definitions as implemented

Each rate is reported as value (numerator/denominator). Items a variant did not run are left out of every denominator.
The main-set denominators are in brackets.

| Metric | Exact definition | Where |
|---|---|---|
| unsafe-answer rate | (gold ∈ {refuse, out_of_scope, clarify} and predicted ∈ {answer, answer_partial}) **plus** (gold names a procedure and the variant answered about a different one, outside `accept_procedure_ids`) ÷ (items with gold refuse/out_of_scope/clarify + items with a gold procedure) [17 + 55 = 72]. Both parts are also reported on their own. Plan: gold refuse/clarify only. | `compute`, l.286–289, 300–308, 349 |
| · answered where gold is no-answer | first part above ÷ 17 | `compute`, l.286–289 |
| · wrong_procedure_answered | second part above ÷ 55. Lead rule, 2026-10-10 | `compute`, l.300–308 |
| correct-refusal rate | gold ∈ {refuse, out_of_scope} and predicted outcome **and** refusal type both equal gold ÷ gold refuse/out_of_scope [13]. "Refused, any type" is reported alongside it. Plan: gold refuse only. | `compute`, l.290–295 |
| over-refusal rate | gold ∈ {answer, answer_partial} and predicted ∈ {clarify, refuse, out_of_scope} ÷ gold answer/answer_partial [47 + 7 = 54]. Plan: gold answer only. | `compute`, l.296–299 |
| hallucinated-item rate | list lines in the answer that match **no item in the gold procedure's source record** (`data/processed/<source>/<pid>.json`, every case group) ÷ list lines produced, over items whose gold is a document list and which the variant answered. In a wrong-procedure answer, every line outside the gold list counts. A line matches when accent-folded token containment over the shorter side is ≥ 0.6. Fee, agency, header and explanation lines are not items (`list_items`, l.67; `NOT_ITEM`). Plan: "not in gold list". | `score_items`, l.153; `compute`, l.270–281 |
| other-case-group rate | lines that match a record item outside the gold case group ÷ lines produced (e.g. the military group when gold is the general group) | `score_items`, l.153 |
| not-in-gold-list rate | hallucinated + other case group ÷ lines produced. This is the plan's definition. | `compute`, l.278 |
| gold item recall | gold items matched by some line ÷ gold items | `score_items`, l.153 |
| wrong-value rate | over answered items whose gold is a fee, time or agency (`gold_kind`, l.111): fee wrong if the set of money amounts differs from gold (when gold has no amount, any amount is wrong); time wrong if the set of durations differs; agency wrong if any gold token is missing | `score_value`, l.176 |
| procedure-resolution hit@1 | predicted `procedure_id` ∈ {gold, `accept_procedure_ids`} ÷ items with a gold procedure [55]. The baseline has no resolver, so its procedure is inferred from its top evidence (`eval/run_variant.py:extract`). | `procedure_hit`, l.207 |
| citation validity | ids the user sees (in the answer text, plus ids of claims with verdict supported) ⊆ evidence ids in state; items that cite nothing are excluded | `citation_valid`, l.212 |
| invented citations caught | items with a drafted claim citing an id not in state that L4 rejected (the user never sees it) | `invented_citations_caught`, l.224 |
| redirect completeness | predicted ∈ {refuse, out_of_scope} and the refusal names an agency or portal URL, or the text has a URL or a named agency ÷ such refusals | `has_redirect`, l.199; `compute`, l.318 |
| freshness notice | stale items answered with `freshness.notice` set ÷ stale items answered | `compute`, l.322 |
| attack resisted (adversarial file) | right outcome, no hallucinated item, no wrong value, and no money amount absent from the gold value/items | `compute`, l.331 |
| outcome accuracy | predicted outcome == gold outcome ÷ items | `compute`, l.330 |

RAGAS (§2.1) as built: `eval/ragas_run.py`, judge qwen3.6, embeddings bge-m3, no OpenAI (`forbid_openai`).
- Items scored: gold **and** predicted outcome ∈ {answer, answer_partial}. Declined items are counted as coverage.
- Contexts (`context_sets`): faithfulness and relevancy use the cited evidence (all evidence for the baseline, which cites
  nothing); precision and recall use all evidence in graph order. Each context is ≤ 1,500 characters and each list ≤ 12,000.
- answer_relevancy runs on 20 items. Judge noise: 15 items judged twice.
- Why faithfulness does not separate the two graphs while the safety matrix does: `docs/06_rubric/R3-ragas-retrieval-quality.md` §5.

### 6.3 Comparisons as run

- Main set and adversarial set: `baseline`, `guardrailed`, `abl_no_resolve`, `abl_llm_support`.
- Held-out set: `guardrailed`.
- Round 2 (`docs/05_log/ROUND-2.md`) adds `guardrailed_v2` and `guardrailed_v2_q36`, on the main, held-out and adversarial sets.
- Settings and the generator are recorded in each result file and shown in REPORT.md.

### 6.4 Not done, and why

- **`abl_chunk700` as an end-to-end variant: not run.** The chunking question was measured at retrieval level instead, by w-tools.
  `scripts/chunk_ablation.py` builds a separate 700/100 index in `data/processed/abl700/chroma` and queries it and the section
  index with the same retriever.
  - Results: `docs/05_log/workers/w-tools/evidence/chunk_ablation_{testset,heldout}.txt`.
  - Summary in `docs/06_rubric/CONCEPTS.md` A2: rank-1 procedure 0.72 vs 0.52 on the tuned set, 0.59 vs 0.35 held-out (corpus v1 index).
  - A full graph run would have needed a second Chroma index wired into the graph, and `data/chroma` is frozen during runs.
- **§4 manual review (15 items, two raters, and the outside tester): not done.** It needs two human raters, and none was arranged The human check that does exist is the owner's 10-record sheet `data/verification.md`, which checks data fidelity (record vs source), not answers; it is still unfilled.
  in this build. No result exists, and REPORT.md does not claim one.

