# From the data to the retrieval — why the assistant is built the way it is

**What.** This page lists the properties of our data that shaped the product, and for each one the processing step or retrieval
mechanism we built because of it. It ends with the procedure we follow to build the corpus (§3), and with how a question meets
that data at run time (§4).
**Who it is for.** Anyone who asks "why not just put the pages in a vector store and ask a model?"

## 1. The data decides the design

A public-service answer is a checklist: which documents, which fee, which office, how long. Each item has to be exactly right,
because a wrong item costs the citizen a wasted trip (PLAN.md §2). Our sources are official pages and legal texts.
They come in several versions. Their procedures look alike. Their facts sit in lists and values, not prose. They lag behind the
law, and they are written in a different Vietnamese from the one people type. A generic RAG pipeline (retrieval-augmented
generation: search for text, then have a model write from it) ignores all of this, and each property it ignores turns into a
failure we can name. So we did not start from a pipeline and fill it with data. We started from the data, and each property
below led to one processing step or one retrieval mechanism.

## 2. Properties of the data, what each breaks, what we built

### 2.1 One procedure, several records
- **Property.** The same procedure appears in more than one official source. One example is the national ministry page for a
  hộ tịch (civil-status) procedure plus the Đắk Lắk provincial decision that sets its fee and deadline locally. In total there
  are **94 source records for 57 procedures** (`data/README.md` "Corpus v2"; data-collection.md §5).
- **What it breaks if ignored.** Two records give two answers. If a fee is set by the province and the answer doesn't say which
  province, the answer is misleading even though the number is in the corpus (PLAN.md §2, "Fees differ by province").
- **What we built.** One **canonical record** per source in a single shape (data-model.md §1). Every record is keyed by the
  official procedure code (*mã TTHC*), so all versions share **one procedure id**. Each fee row carries its **jurisdiction**
  ("toàn quốc" for national, "Đắk Lắk" for the provincial annex, or "theo tỉnh" when the amount is set by each province). `scripts/build_db.py --prefer` decides which source fills each field and writes any
  disagreement to `data/processed/CONFLICTS.md`. The database and the index read the same selection, through
  `src/db.py:211` `read_records` and `src/db.py:337` `select_records`.

### 2.2 Look-alike siblings
- **Property.** Different procedures share most of their title words. *Đăng ký khai sinh* (birth registration) has 12 members
  in its family: the ordinary one, the one with a foreign element, re-registration, and others (`data/variants.yaml`). There
  are 10 such families.
- **What it breaks if ignored.** Meaning search (dense retrieval) returns chunks from several siblings, and the model blends
  their document lists (PLAN.md §2, the first hazard). A sibling's chunk is in the top 5 for about 70 % of questions, whether
  chunks are cut by section or by 700 characters (journal.md, 07:45 entry). Without procedure resolution, unsafe answers rise from
  1 to 23 of 72 (ablation `eval/results/abl_no_resolve.json`).
- **What we built.** **Procedure resolution in code, before any retrieval of facts.** The `resolve_procedure` node scores the
  candidates and applies fixed rules: *none*, *tie* or *one* (as-built-pipeline.md §2, step 2). Sibling groups come from
  `data/variants.yaml`. Family nouns are word pairs found in every member's title, such as "khai sinh" or "kết hôn". They are
  derived from the titles into `data/family_nouns.json` (`src/families.py:50`) and they check that the chosen procedure belongs to
  the family the user named (`src/nodes.py:689`). When two siblings fit equally, the assistant **asks the user to choose**
  (the outcome *clarify*) instead of guessing.

### 2.3 The facts live in fields, not in prose
- **Property.** The answer's key facts are lists and values: the required documents (341 rows), the fees (218), the agency
  (55), and the deadline as written (for example "05 ngày làm việc").
- **What it breaks if ignored.** If a model rewrites a list, it adds or drops items. The first version invented 37 % of its
  document items. Character windows also cut a document list in half, or put a fee sentence inside a "steps" chunk.
- **What we built: two homes for the same record.**
  - **SQLite, `data/app.db`, for the structured query.** Code looks up a procedure id and reads its rows. Every number and item
    in an answer is copied from those rows, verbatim, with a `[db:…]` citation (`src/render.py`; as-built-pipeline.md §2, step 5).
  - **The index, `data/chroma`, for the meaning query.** It holds the section texts. bge-m3 vectors and BM25 are fused by rank
    (§2.6) to answer "which procedure is this?" and "which passages explain it?". Resolution ranks over procedure-page chunks only.
  - Both are built from **the same record selection by the same loader** (`src/db.py:211` `read_records`, `:337`
    `select_records`), so they can't disagree about a procedure.
- **Chunking: by section, not by window.** The first version cut text every 700 characters. We make **one chunk per section per
  procedure**; the section ids are listed in data-model.md §3. An empty section yields no chunk, so an unknown fee produces no
  "fees" chunk. Each chunk carries a Vietnamese prefix, `[Thủ tục: …] [Mục: …]` (`src/ingest.py:150`), and its metadata:
  procedure id, section, source, retrieved date and tier. Document chunks reuse the same section ids. A section is cut only if
  it exceeds `MAX_WORDS = 600` (`src/ingest.py:51-52`; `split_words` `:120-147`): the cut falls on line boundaries, and about 60
  words are repeated across it. **Only 79 of 830 sections are cut** (44 of 498 procedure sections, 35 of 332 document sections).
  The remaining 77 % of the 2,429 chunks have no overlap; 548 come from cut sections. Hit@1 with section chunks is 0.72 against
  0.52 with 700-character chunks on the tuned set, and 0.59 against 0.35 on the blind set (journal.md, 07:45 entry). The model
  writes only the narrative, such as the steps.

### 2.4 Rules change and pages lag
- **Property.** On 2025-07-01 the district level was abolished. Even so, 12 of the 37 MOJ pages still say "xã, phường, thị
  trấn", and two still name "Phòng Tư pháp". The 2026 amendments (Luật 118/2025/QH15, NĐ 58/2026, TT 116/2026) aren't on the
  ministry pages yet. Procedure 2.001178 (confirmation of a 9-digit identity number) stopped on 2026-03-15
  (`data/README.md` §3).
- **What it breaks if ignored.** The answer sends the citizen to an office that no longer exists, or explains a procedure that
  is no longer performed (PLAN.md §2, "The receiving agency changed in 2025").
- **What we built.** The agency is taken from the 2025 decision 1833/QĐ-BTP, while the portal's outdated wording stays flagged in
  `raw_text`. There are 21 **change-notice** documents linked to the procedures they change. `data/procedure_status.yaml` lists
  discontinued procedures; one listed there always ends in a typed refusal with its date, decree and redirect (`src/nodes.py:70`).
  The `freshness_check` node adds a notice when the answer names an agency, when the record is old, or when a newer change notice
  is in force. **Every answer shows the date the data was retrieved** (RELEASE-v0.1.md §3).

### 2.5 The legal basis is cited by number, not quoted
- **Property.** A procedure page says "Luật Cư trú 68/2020, Điều 20" but doesn't quote the article. Conditions and exceptions
  live in that article, in the form's filling notes, or in a guidance page.
- **What it breaks if ignored.** The model either fills the gap from memory or says nothing about the condition that decides the
  case.
- **What we built.** There are **210 depth documents**: 143 legal articles, 27 forms, 21 change notices, 18 guidance pages and
  1 fee resolution. They are cut into 332 sections and linked to their procedures 857 times; each link records why it exists
  (`link_method`, data-collection.md §4 step 4). **Trust tiers** (`src/evidence.py:27`, `:53`) decide what each source may
  support. A number, document item, agency or deadline needs a database row. A step, condition or legal basis may rest on a
  corpus document. A web page from an official site may only support an "please check for updates" notice. A legal text that has
  since been amended carries the prefix `[Văn bản gốc – đã sửa đổi]` (original text, since amended).

### 2.6 Vietnamese as typed is not Vietnamese as published
- **Property.** People type "CCCD", "hộ khẩu" or "lấy chồng", often without accents. The titles say "căn cước", "đăng ký thường trú"
  and "kết hôn".
- **What it breaks if ignored.** The right procedure never ranks first, so the answer is about a neighbouring procedure, or the
  assistant refuses something it could answer.
- **What we built.**
  - **Normalisation.** Text is converted to one standard Unicode form (NFC) and lowercased (`src/tools/rag.py:38`, `:63-64`). Each token is
    indexed both with and without accents (`:30`).
  - **Synonym expansion.** `data/synonyms.yaml` turns everyday words into the official wording (`expand_query`, `:67`).
  - **Hybrid retrieval.** bge-m3 meaning search and BM25 keyword search are merged by rank with **reciprocal rank fusion**
    (RRF, k = 60: each list adds 1/(60 + rank); `:19`, `:102`). BM25 statistics come from procedure pages only (`:127`), so the
    1,857 document chunks can't push a procedure title down.
  - **Measured.** Procedure hit@1 on the tuned set rose from 0.69 (summaries only) to 0.76 (fused) to 0.81 (with synonyms). On
    the blind set it rose from 0.53 to 0.71 to 0.82 (`docs/05_log/workers/w-tools/STATUS.md:202-216`). The synonyms were
    written after we saw misses on the tuned set, so that set's number is optimistic. The blind set is the honest one.
  - **Measured and left off.** Chat-abbreviation expansion (`data/abbreviations.yaml`) brought no gain at the default retriever
    (`STATUS.md:64-66`).

### 2.7 The sources are hard to reach
- **Property.** The national portal dichvucong.gov.vn is a JavaScript application whose scripts are disallowed by its
  robots.txt. The national procedure database needs a login. Two ministry decisions are scans with no text layer
  (`data/README.md` §2; `data/raw/dvc/EVIDENCE.md`).
- **What it breaks if ignored.** Getting around these means bypassing an access control or guessing text from images. Either way,
  facts could enter the corpus that nobody can trace.
- **What we built.** We used the **ministry pages** (moj.gov.vn and dichvucong.bocongan.gov.vn). They are server-rendered,
  publish the same national procedures, and their robots.txt allows them. We took **text sources only, with no OCR**. Every
  fetched file has **provenance**: url, fetched_at, HTTP status and sha256, in an `index.jsonl` file next to it. Fetches are
  polite: at least 2 seconds per host, and each URL is fetched once.

### 2.8 A small corpus has to be trusted
- **Property.** There are 57 procedures and 304 documents. With so few, every wrong field shows up in an answer.
- **What it breaks if ignored.** A parsing error becomes a confident wrong answer. A rebuild in the middle of an evaluation
  changes the numbers being measured.
- **What we built.** Every record and document is checked against a JSON Schema: `scripts/validate_records.py` and
  `validate_documents.py` report 0 errors, and they list warnings ("smells"). Records were checked by hand against the raw
  pages (`data/processed/bca-portal/VERIFICATION.md`, 15/15 fields). The corpus and test sets are frozen with sha256 hashes
  (`data/testset/FREEZE.md`, `eval/records_v1.sha256`). Both build scripts refuse to run while `data/.RUNLOCK` exists
  (`scripts/build_db.py:15`, `src/db.py:22`).

## 3. The procedure we establish

Each step below names its script, what it refuses, and what it produces. The full description is in
`docs/08_handbook/PIPELINE.md` §2 and `docs/03_design/data-collection.md` §4.

1. **Fetch.** `crawl_bca_portal.py`, `fetch_moj.py`, `moj_fetch_portal.py`, `fetch_depth_cached.py`. Refuses: pages disallowed by
   robots.txt, login walls and scans. Produces: `data/raw/**` plus `index.jsonl` (url, time, status, sha256).
2. **Parse.** `parse_bca_portal.py`, `parse_moj.py`, `moj_parse_daklak.py`. Refuses to guess: an unknown field stays `null` or
   `[]`. Produces: `data/processed/<source>/<code>.json` canonical records.
3. **Clean.** `clean_documents.py`. Refuses: boilerplate, HTML remnants and duplicate sections. Produces: `data/clean_docs/` plus
   `CLEAN_REPORT.md`.
4. **Validate.** `validate_records.py`, `validate_documents.py`. Refuses: any record that breaks its schema. Produces: an error
   report (0 errors) and the smells.
5. **Load.** `build_db.py` (`--docs`). Refuses: to run under `data/.RUNLOCK`; when sources disagree, it records the conflict
   instead of merging silently. Produces: `data/app.db`.
6. **Chunk.** `src/ingest.py`. Refuses: empty sections, so an unknown fee produces no "fees" chunk (unknown is not free).
   Produces: section chunks with their prefixes.
7. **Embed and index.** `build_index.py` (`--docs`), `sync_index.py`. Refuses: to run under the lock. Produces: `data/chroma`, with
   2,429 chunks and the BM25 statistics per kind.
8. **Freeze.** `data/testset/FREEZE.md`, `eval/records_v1.sha256`. Refuses: edits to the test sets or the yardstick. Produces:
   hashes.
9. **Evaluate.** `eval/run_variant.py`, `safety.py`, `ragas_run.py`, `report.py`. Holds `data/.RUNLOCK` for the whole run, so nothing is rebuilt underneath it. Produces:
   `eval/results/REPORT.md`, with each number stamped with the corpus it was measured on.

## 4. How a question meets this data at run time

Full table: `docs/03_design/as-built-pipeline.md` §2.

1. **Resolve.** The code picks one procedure, or asks the user which one, before any facts are fetched (§2.2, §2.6).
2. **Gather.** The resolved procedure's own database rows, plus its own section chunks, filtered by `procedure_id` (§2.3).
3. **Add documents in tiers.** Linked legal texts, forms and notices are added as `corpus` evidence, never in place of a row
   (§2.5).
4. **Grade.** A judge model keeps only the relevant chunks. Each narrative sentence is then checked against the source it cites
   (§2.3, §2.5).
5. **Cite.** Facts are copied from rows with `[db:…]`, the narrative is written with `[doc:…]`, and the data date and any
   change notice are attached (§2.4).

## 5. How we measure the output

**(a) The safety matrix — our own code, `eval/safety.py`.** *What:* ten checks that read the **structured fields** the product
stores with every answer (`outcome`, `refusal_type`, `procedure_id`, `refusal.agency` / `portal_url`, cited ids;
`eval/run_variant.py:229`), not its prose. *Why:* a refusal is a valid outcome here, and documents, fees and deadlines must be
exact, which a similarity score cannot see. *How:*
1. **Unsafe answers.** Answering where the gold is no answer, or about another procedure (`outcome`, `procedure_id`).
2. **Correct refusals.** Both the outcome and the `refusal_type` must equal the gold. · 3. **Over-refusal.** The gold is an answer, but the product clarified or refused (`outcome`).
4. **Hallucinated document items.** A listed item in neither the gold list nor the source record (`item_match`).
5. **Gold items covered.** How many of the gold document items the answer lists. · 6. **Wrong fee or deadline values.** Amounts and (number, unit) pairs, compared with the gold (`score_value`).
7. **hit@1.** `procedure_id` equals the gold procedure. · 8. **Citation validity.** Every cited id is evidence the product actually retrieved (`cited_ids` ⊆ `state_evidence_ids`).
9. **Redirect completeness.** Every refusal names an agency or a portal link (`refusal.agency`, `portal_url`). · 10. **Exact outcome match.** The outcome equals the gold outcome.

**(b) RAGAS — the standard library, `eval/ragas_run.py`, run locally** (judge qwen3.6, embeddings bge-m3; no OpenAI client
can be built, `forbid_openai`). The judge is asked three things. **Faithfulness**: does each answer sentence follow from the evidence
it cites? **Context precision**: are the retrieved texts relevant and ranked high? **Context recall**: do they contain the reference
answer? Only answered items are scored, because a refusal has no claims to check (refusals are scored in (a)). One known
artifact: lines that code prints (source URL, data date, notices) count as unsupported claims, which lowers faithfulness. Judge
noise: 15 items were scored twice, and 93–100 % of the scores agreed within ±0.1.

| Frozen set, 71 questions (blind set: weakness only) | First version | Current configuration |
|---|---|---|
| Unsafe answers | 19 / 72 | **1 / 72** |
| Correct refusals, type matching | 0 / 13 | **13 / 13** |
| Over-refusal of answerable questions | 19 / 54 | 14 / 54 (blind: 8 / 17) |
| Hallucinated document items | 37 % (25 / 67) | **7 % (7 / 99)** |
| Wrong fee or deadline values | 6 / 16 | 3 / 23 |
| hit@1 | 38 / 55 | **46 / 55** (blind: 10 / 18) |
| Citation validity / redirect completeness | n/a / 0 of 27 | **47 / 47** / **25 / 25** |
| Exact outcome match | 35 / 71 | **51 / 71** |
| RAGAS faithfulness / precision / recall (answered items) | not run on this corpus | 0.50 / 0.26 / 0.89 * |

Source: `eval/results/REPORT.md` (2026-10-10, 19:18Z), §"Corpus v2" (first version) and §"Round 5 variant v5" (current).
\* RAGAS figures come from the earlier configuration on the same corpus (§"Corpus v2"), because the later runs checked safety
only. The first version has RAGAS on this corpus only for the blind set. Details: `docs/03_design/question-sets.md` §3,
`docs/06_rubric/R3-ragas-retrieval-quality.md`.
