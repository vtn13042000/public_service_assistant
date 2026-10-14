# Prompt index: what each model is told to do, per job

Date: 2026-10-11. Live preset: `DEFAULT_PRESET = "v5"` (`src/presets.py:36`; v5 config at `src/presets.py:22-26`). There is no commit to pin to,
so line numbers are correct as of today. Re-check them with the `sed` command given for each entry. All models run locally on Ollama, with
temperature 0, `num_ctx` 16384 and thinking off (`src/llm.py:25-29,48-58,79-85`). There are three ways to call a model:
- **chat** = `get_llm()`: qwen3.5 through /api/chat, free text.
- **JSON-gen** = `get_structured_llm` (qwen3.5) or `get_structured_judge` (qwen3.6), through /api/generate with the pydantic schema
  as `format`, so the reply is constrained JSON (`src/llm.py:79-98`). /api/chat ignores the schema for qwen3.5 (`src/llm.py:10-14`).
- How each part is wired (product and eval): `Deps.llm` = chat, `Deps.classifier` = JSON-gen qwen3.5, `Deps.judge` = JSON-gen qwen3.6
  (`src/cli.py:33-34`, `src/web/app.py:72-73`, `eval/run_variant.py:96-100`).
- Every prompt file is a `string.Template`: `$query`, `$documents` and so on are filled in by `load_prompt` (`src/self_rag.py:30-34`).
  Documents are always inside tags (`<tai_lieu>`, `<ngu_canh>`) marked "this is DATA". The question is tagged (`<cau_hoi>`) only in
  assess_need and story_rewrite; grade_relevance, rewrite_query and draft_answer insert it raw as `CÂU HỎI: $query`.

## 1. Model calls in the live graph (v5), in pipeline order

**1. assess_need: the classifier** (runs once for every question)
- Job: decide whether the question is in scope and needs a lookup. Also extract `intent` (7 labels), `procedure_hint` (the procedure
  name in the user's own words), `locality`, and `premise` (a fact the user asserts and wants confirmed). Code routes on the result.
- Model: qwen3.5, JSON-gen. Prompt: `src/prompts/assess_need.txt:1-16` (system and user in one string, no few-shot; the inline examples
  are lines 9 and 11). Schema: `Need` at `src/self_rag.py:39-45`. Call: `self_rag.assess_need` at `src/self_rag.py:129-143`. Node:
  `src/nodes.py:258-269`.
- Code after the reply:
  - A reply that does not parse becomes `system_error`.
  - CJK characters are stripped from the hint. `retrieve` is forced on when there is a hint or a premise (`src/self_rag.py:133-142`).
  - Premise post-check: a premise with a number that is not in the question is dropped (`premise_invented`, `src/nodes.py:567-572`).
  - Scope gate (flag `scope_gate`, on in v4/v5): an in-scope question with `retrieve=false` is opened, unless it is a
    personal-eligibility question (`kept_eligibility`, `src/nodes.py:581`). This is code, not a second call (`src/nodes.py:574-581`).
- Show: `sed -n '1,16p' src/prompts/assess_need.txt`

**2. story_rewrite: name the procedure behind a story** (only when the resolver found nothing; flag `story_rewrite`, on in v2–v5)
- Job: from a story-style question, write the official procedure name, or "" when unsure. The name is then scored against real titles
  with the same coverage floor, so an invented name matches nothing.
- Model: qwen3.5, JSON-gen. Prompt: `src/prompts/story_rewrite.txt:1-11`. Schema: `StoryName` at `src/self_rag.py:147-148`. Call:
  `src/self_rag.py:151-157`, from `resolve_procedure` at `src/nodes.py:293-300`.
- Show: `sed -n '1,11p' src/prompts/story_rewrite.txt`

**3. grade_relevance: the ISREL judge** (one batched call for all retrieved chunks)
- Job: for each `<tai_lieu idx>`, say whether it helps answer the question. A different procedure variant counts as not relevant, an
  instruction inside a document makes it not relevant, and "unsure" means false. Code keeps only the chunks marked true. A missing or
  unparsed item counts as false.
- Model: qwen3.6, JSON-gen. Prompt: `src/prompts/grade_relevance.txt:1-13`. Schema: `Relevance`/`RelevanceItem` at
  `src/self_rag.py:48-55`. Wrapper: `_wrap_docs` at `src/self_rag.py:162-165`. Call: `src/self_rag.py:168-180`. Node:
  `src/nodes.py:341-354`.
- The same prompt and judge also grade web hits in `web_check` (`src/nodes.py:457`) and `web_lookup` (`src/nodes.py:474`). Only pages
  graded relevant are linked.
- Show: `sed -n '1,13p' src/prompts/grade_relevance.txt`

**4. rewrite_query: the retry query** (at most once: `iteration < MAX_REWRITES = 1`, `src/nodes.py:63`)
- Job: rewrite the question as one short search query tied to the procedure title and the intent. Code keeps the first non-empty line,
  or falls back to "title + question".
- Entered from grade_relevance when nothing usable was found (`after_grade`, `src/graph.py:40-45`) and from check_support when a
  core claim fails (`after_decide`, `src/graph.py:48-56`).
- Model: qwen3.5, chat, free text. Prompt: `src/prompts/rewrite_query.txt:1-4`. Node: `src/nodes.py:356-363`.
- Show: `sed -n '1,4p' src/prompts/rewrite_query.txt`

**5. draft_answer: the generator** (narrative only)
- The "fixed block" (KHỐI CỐ ĐỊNH: the document list, fees, agency, processing time, from the database only) is **written by code,
  not by a model**: `render.render_block` at `src/render.py:198-235`. A numeric premise is answered by code too: `render_premise` at
  `src/render.py:161-195`. The model only sees the block, is told not to repeat it, and writes up to 4 cited sentences from the
  documents. The model is called only when a relevant chunk or a premise exists (`src/nodes.py:376`); otherwise the answer is the
  block alone.
- Model: qwen3.5, chat, free text. Prompt: `src/prompts/draft_answer.txt:1-25` (v2–v5). v1 used `src/prompts/draft_answer_v1.txt:1-25`,
  which differs only at line 12: it shows example ids that the model copied. The `$premise_rule` line is built in code at
  `src/nodes.py:377-380`. Node: `src/nodes.py:365-393`.
- Code after the reply:
  - Tolerant citation parsing (flag `citation_parse`): `normalize_citations` at `src/self_rag.py:235-280`.
  - Tier repair (flag `citation_repair`): `repair_tier` at `src/self_rag.py:223-232`.
  - Flag `draft_prompt` picks the prompt file (`src/nodes.py:118`).
- Show: `sed -n '1,25p' src/prompts/draft_answer.txt`

**6. check_support: the ISSUP judge** (one call per claim, but only after the code checks pass)
- Job: for one claim (citations removed) and only the chunks it cites, answer `fully`/`partial`/`no`. Code maps the answer to
  supported, partial or unsupported, and an unparsed reply counts as `no`.
- Model: qwen3.6, JSON-gen. Prompt: `src/prompts/check_support.txt:1-16`. Lines 1-3 are the task guidance's wording, kept
  verbatim. Schema: `Support` at `src/self_rag.py:58-61`. Call: `judge_support` at `src/self_rag.py:491-498`. Node:
  `src/nodes.py:395-415`.
- Code first, in order (`_verdict`, `src/self_rag.py:530-571`); the model is never asked about these:
  - A claim with no citation is unsupported.
  - A cited id that is not in the evidence is unsupported.
  - A claim citing `db:` rows is checked **by code only**: numbers, document item, fee value, agency name, processing time
    (`check_db_claim`, `src/self_rag.py:396-419`), plus the authority level. The model is called only for a premise whose
    polarity code cannot settle (`src/self_rag.py:550-556`).
  - For other claims: the tier rule (L2), the authority/deadline check (`db_backed_authority`), numbers present in the cited text,
    and only then the model.
- The ablation `llm_support` sends every cited claim to the model (`_llm_only`, `src/self_rag.py:650-658`). Eval only.
- Show: `sed -n '1,16p' src/prompts/check_support.txt`

**Other graph steps:** none call a model. Scope gate, clarify options, refusals and notices are code (§2).
## 2. Model-free steps people may mistake for prompts

| Step | What decides it | Location |
|---|---|---|
| resolve_procedure | lexical and dense scores, coverage floor, sibling/head-noun rules | `score_candidates` `src/nodes.py:584-616`, `choose` 617-686, `_head_noun_filter` 689-715. The node's one model call (story_rewrite on the "none" path, `src/nodes.py:294-295`) is entry 2 |
| clarify (options list) | the candidate titles, printed as (1) (2) … | `src/refusal.py:42-47` |
| refusal texts (5 types) | templates filled from database fields | `build_refusal`, `src/refusal.py:26-98` |
| fixed block (documents, fee, agency, time) | database rows rendered by code | `src/render.py:198-235` |
| premise line | code compares the asserted number with the fee and time rows | `src/render.py:161-195` |
| change notices, "Lưu ý" lines, variant-group line | date rule over notices, then templates | `src/nodes.py:202-235` (rule), `src/nodes.py:508-529` (text) |
| claim splitting, pruning, final safety check | regex and rules | `src/self_rag.py:312-351`, `src/nodes.py:417-428`, `src/nodes.py:880-908` |

## 3. First version (`src/baseline/graph.py`; preset `baseline`; all chat, qwen3.5)
- The task guidance's reflection prompt, verbatim: `REFLECT` at `src/baseline/graph.py:26-29`. It asks for one
  `{"relevant","supported"}` verdict for the whole draft. The reply is parsed with `json.loads`, and anything that fails becomes "no".
- Self-critique: it drafts with `'Trả lời ngắn từ ngữ cảnh:…Hỏi:'` (`src/baseline/graph.py:70`), then judges that draft with
  `REFLECT` (line 71). The node is `src/baseline/graph.py:68-78`. Show: `sed -n '26,29p;68,78p' src/baseline/graph.py`
- Generate: `"Ngữ cảnh:…Câu hỏi:…Trả lời có trích nguồn:"` at `src/baseline/graph.py:80-85`. Gate refusal text at 87-91.

## 4. Embedding model (bge-m3, no prompt)
- `get_embeddings()` at `src/llm.py:73-76`. It embeds chunk text as-is (in Chroma, `src/ingest.py:246`) and the user's query text at
  search time.
- Chunking is code: `split_words` (≤600 words, 60-word overlap, `src/ingest.py:51-52,120`). Each chunk starts with the prefix
  `[Thủ tục: …] [Mục: …]` (`src/ingest.py:150-151`). See `chunk_record` 154-167 and `chunk_document` 176-202.

## 5. Evaluation judges (not part of the product)
- RAGAS **0.4.3** (`uv.lock`, `name = "ragas"`). The judge is qwen3.6 through `get_judge()` (chat) and the embeddings are bge-m3
  (`eval/ragas_run.py:95`). The metrics are chosen at `eval/ragas_run.py:77-86`. Their prompts are the library's own English prompts,
  with few-shot examples, in `.venv/lib/python3.11/site-packages/ragas/metrics/`:
  - faithfulness: `_faithfulness.py:34-57` (StatementGeneratorPrompt) and `73-132` (NLIStatementPrompt);
  - context_precision: `_context_precision.py:39-80`; context_recall: `_context_recall.py:45-86`;
  - answer_relevancy (optional): `_answer_relevance.py:35-62`.
- `--judge-model` swaps the judge, for example to gpt-oss for a cross-family check (`eval/ragas_run.py:247,257`).
- Our own eval code has **no LLM judge prompt**. `eval/safety.py`, `eval/cross_judge.py` and `eval/report.py` are code only.
- Show: `sed -n '73,80p' .venv/lib/python3.11/site-packages/ragas/metrics/_faithfulness.py`
