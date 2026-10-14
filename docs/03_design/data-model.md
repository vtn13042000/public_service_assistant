# Data model — canonical record, DB schema, chunking, provenance, acquisition

---

## 1. Canonical procedure record (one JSON per procedure, `data/processed/<source>/<id>.json`, e.g. `data/processed/moj/1.004873.json`)

The canonical record is the one standard JSON shape every source is converted into.

```json
{
  "procedure_id": "KS-01",            // illustrative; real ids are the national mã TTHC, e.g. "1.001193", and source ids like "moj-portal#1.001193"
  "title": "Đăng ký khai sinh",
  "variant_of": null,
  "field": "Hộ tịch",
  "level": "cấp xã",
  "jurisdiction": "toàn quốc",
  "receiving_agency": "UBND cấp xã nơi cư trú của cha hoặc mẹ",
  "channels": ["trực tiếp", "trực tuyến toàn trình"],
  "required_documents": [
    {"item": "Tờ khai đăng ký khai sinh theo mẫu", "quantity": 1, "quantity_text": "01 bản", "mandatory": true, "note": null},
    {"item": "Giấy chứng sinh", "quantity": 1, "quantity_text": null, "mandatory": true, "note": "nếu không có: văn bản xác nhận của người làm chứng…"}
  ],
  "steps": ["…", "…"],
  "fees": [{"value": "miễn lệ phí", "condition": "đăng ký đúng hạn", "jurisdiction": "toàn quốc"},
           {"value": "theo HĐND tỉnh", "condition": "đăng ký quá hạn", "jurisdiction": "theo tỉnh"}],
  "processing_time": "ngay trong ngày làm việc; nếu nhận hồ sơ sau 15 giờ thì ngày làm việc tiếp theo",
  "legal_basis": ["Luật Hộ tịch 2014", "Nghị định 123/2015/NĐ-CP", "…"],
  "conditions": "…",
  "raw_text": "…full cleaned text…",
  "source": {
    "source_id": "moj-1234/QD-BTP#KS-01",
    "url": "https://moj.gov.vn/…",
    "locator": "Mục I.3, tr. 12",
    "title": "…",
    "retrieved_at": "2026-10-15",
    "effective_date": "2025-07-01",
    "content_hash": "sha256:…"
  }
}
```

`variant_of` links siblings (variants of the same procedure, e.g. normal vs foreign-element; KS-02 `variant_of: "KS-01"`) so `resolve_procedure` can present them together in a clarify prompt.

Field rules (both parsers follow these; `data/schema/procedure_record.schema.json` enforces the structural ones):

- **Required:** `procedure_id`, `title`, `field`, `required_documents`, `source.source_id`, `source.url`, `source.retrieved_at`. Everything else may be `null`.
- **`quantity` / `quantity_text`:** `quantity` is an integer or `null`; `quantity_text` is the source's wording verbatim (`"01 bản chính và 01 bản sao"`, `"02 bản"`), or `null`. When the wording is not a single count, set `quantity: null` and keep the wording in `quantity_text`.
- **`source_id` is per (document, procedure):** `"<doc-id>#<procedure_id>"`, e.g. `"moj-1234/QD-BTP#1.004873"` or `"dvc-hanoi#1.004873"`. `source.url` is the URL of the document or page; the optional `source.locator` says where in it the procedure is (`"Mục I.3, tr. 12"`).
- **Unknown is not free:** `fees: []` or `null` means *unknown*. A source that states "không" / "miễn" must yield an explicit entry `[{"value": "miễn lệ phí", "condition": …, "jurisdiction": …}]`. Likewise `fee_summary` and `agency_summary` (§2) are `NULL` when there are no rows and never default to free or to any agency.

---

## 2. SQLite schema — English identifiers, Vietnamese data

Convention (D-010): all table, column, section and code identifiers are English; all *content* (titles,
document items, agency names, fee text, legal basis) is Vietnamese exactly as in the source. The
professor's schema semantics are preserved one-to-one; the mapping table below goes in the report so a
grader can see the equivalence at a glance.

```sql
CREATE TABLE sources (                      -- provenance, one row per (document, procedure)
  source_id      TEXT PRIMARY KEY,          -- "<doc-id>#<procedure_id>"
  kind           TEXT,                      -- moj_decision | bca_decision | ministry_portal_page | provincial_decision
                                            -- | national_db_page | provincial_portal_page | other
  url            TEXT,                      -- URL of the document / page
  locator        TEXT,                      -- where in the document, e.g. "Mục I.3, tr. 12"
  title          TEXT,
  retrieved_at   TEXT,                      -- ISO date the content was fetched
  effective_date TEXT,                      -- ISO date the procedure version took effect, if stated
  content_hash   TEXT);

CREATE TABLE procedures (                   -- ≙ guidance.thu_tuc
  id              TEXT PRIMARY KEY,         -- "KS-01"
  title           TEXT,                     -- ≙ ten          (Vietnamese)
  field           TEXT,                     -- ≙ linh_vuc     ("Hộ tịch")
  fee_summary     TEXT,                     -- ≙ le_phi       (human-readable summary; see fees table)
  agency_summary  TEXT,                     -- ≙ co_quan      (human-readable summary; see agencies table)
  processing_time TEXT,                     -- ≙ thoi_gian_xu_ly (source wording kept verbatim)
  processing_time_source_id TEXT,           -- source the processing_time came from (see fallback rule below)
  level           TEXT,                     -- cấp xã / cấp tỉnh / trung ương
  variant_of      TEXT,                     -- sibling grouping for clarify prompts
  channels        TEXT,                     -- JSON array, e.g. ["trực tiếp", "trực tuyến toàn trình"]
  legal_basis     TEXT,                     -- JSON array of legal instruments
  conditions      TEXT,
  source_id       TEXT REFERENCES sources(source_id));

CREATE VIRTUAL TABLE procedures_fts USING fts5(  -- BM25 over title for search_titles
  title, content='procedures', content_rowid='rowid');

CREATE TABLE required_documents (           -- ≙ guidance.ho_so
  procedure_id TEXT REFERENCES procedures(id),
  position     INTEGER,                     -- order in the source list (loader assigns from array order, 1-based)
  item         TEXT,                        -- ≙ thanh_phan   (Vietnamese)
  quantity     INTEGER,                     -- ≙ so_luong
  quantity_text TEXT,                       -- source wording verbatim, e.g. "01 bản chính và 01 bản sao"
  mandatory    INTEGER,                     -- ≙ bat_buoc
  note         TEXT,
  source_id    TEXT);
CREATE INDEX idx_reqdoc_procedure ON required_documents(procedure_id);

CREATE TABLE fees (                         -- fees are multi-valued and jurisdiction-dependent
  procedure_id TEXT REFERENCES procedures(id),
  value        TEXT,                        -- "miễn lệ phí" | "theo HĐND tỉnh" | "50.000 đồng"
  condition    TEXT,                        -- "đăng ký đúng hạn"
  jurisdiction TEXT,                        -- "toàn quốc" | province name | "theo tỉnh"
  source_id    TEXT);

CREATE TABLE agencies (                     -- agency as a row so it can be cited, dated, and replaced
  procedure_id   TEXT REFERENCES procedures(id),
  name           TEXT,                      -- "UBND cấp xã nơi cư trú của cha hoặc mẹ"
  jurisdiction   TEXT,
  effective_date TEXT,                      -- proxy: the record's source.effective_date (no separate agency date)
  source_id      TEXT);

CREATE TABLE documents (                    -- non-procedure documents (ROUND-4): legal articles, forms, fee resolutions, …
  id             TEXT PRIMARY KEY,          -- doc_id, e.g. "legal:123-2015-ND-CP:dieu-16"
  kind           TEXT NOT NULL,             -- legal_text | form | fee_resolution | guidance | change_notice
  title          TEXT NOT NULL,
  issuer         TEXT,                      -- "Chính phủ", "HĐND tỉnh Đắk Lắk", …
  effective_date TEXT,
  jurisdiction   TEXT,                      -- province for fee_resolution / provincial guidance; NULL = national
  url            TEXT NOT NULL,
  retrieved_at   TEXT NOT NULL,
  sha256         TEXT NOT NULL,             -- of the fetched raw bytes
  link_method    TEXT,                      -- legal_basis | procedure_code | doc_links | manual | named | instrument_scope
  original_version INTEGER,                 -- legal_text: 1 = original wording of an article since amended
  amended_by     TEXT,                      -- JSON array of amending instruments
  notes          TEXT);

CREATE TABLE document_sections (            -- one row per điều / form part / heading, after cleaning
  doc_id   TEXT NOT NULL REFERENCES documents(id),
  position INTEGER NOT NULL,                -- 1-based order in the document
  heading  TEXT NOT NULL,
  text     TEXT NOT NULL,
  PRIMARY KEY (doc_id, position));

CREATE TABLE document_procedures (          -- which procedures a document is about
  doc_id       TEXT NOT NULL REFERENCES documents(id),
  procedure_id TEXT NOT NULL REFERENCES procedures(id),
  PRIMARY KEY (doc_id, procedure_id));
CREATE INDEX idx_docproc_procedure ON document_procedures(procedure_id);
```

Record → DB, one rule per line:

- Every §1 field is stored except `steps` and `raw_text`. Those two are RAG-only: they reach the answer through chunks (§3).
- `jurisdiction` reaches the DB as `agencies.jurisdiction`.
- `agencies` has one row, built from `receiving_agency`. Its `effective_date` is the record's `source.effective_date`, used as a proxy.
- `procedures_fts` is an external-content FTS5 table (the search index stores only pointers; the text stays in `procedures`).
  The loader populates it (`'rebuild'`) after inserting `procedures`.
- The loader is `scripts/build_db.py` (shared code in `src/db.py`).
- `sources.kind` is filled from the `source_id` prefix: `moj-portal` ministry_portal_page, other `moj-…` moj_decision,
  `bca-portal` ministry_portal_page, other `bca-…` bca_decision, `daklak-…` provincial_decision,
  `dvc`/`dvc-national` national_db_page, other `dvc-…` provincial_portal_page; anything else `other`.
- Fee rows from the Đắk Lắk source (`data/processed/daklak/`) are always loaded as extra `fees` rows with `jurisdiction = "Đắk Lắk"`
  and their own `source_id`. This holds even when another source wins the procedure row; they are not duplicated when Đắk Lắk wins.
- `processing_time` fallback: if the winning source's value is empty or a bare number (`^\s*\d+\s*$`, e.g. moj pages that say only "5"),
  the loader takes the first source, in precedence order, whose `processing_time` for that procedure is longer.
  It records that source in `processing_time_source_id`; otherwise `processing_time_source_id` is the winner's `source_id`.
- The index uses the same `processing_time` value.

Mapping to the guidance's schema (put this table in the report, section Data):

| Guidance (`guidance.md`) | Ours | Note |
|---|---|---|
| `thu_tuc.id / ten / linh_vuc` | `procedures.id / title / field` | same semantics |
| `thu_tuc.le_phi` | `procedures.fee_summary` + `fees` rows | summary kept for compatibility; rows are what `check_support` verifies against |
| `thu_tuc.co_quan` | `procedures.agency_summary` + `agencies` rows | same pattern; rows carry `effective_date` because this field changed in 2025 |
| `thu_tuc.thoi_gian_xu_ly` | `procedures.processing_time` | source wording verbatim (keeps "ngày làm việc") |
| `ho_so.thu_tuc_id / thanh_phan / so_luong / bat_buoc` | `required_documents.procedure_id / item / quantity / mandatory` | plus `note`, `source_id` |
| `idx_hoso_tt` | `idx_reqdoc_procedure` | |
| — | `sources` | added: provenance |
| — | `procedures.channels / legal_basis / conditions`, `procedures_fts` | added: stored for tools; FTS5 for `search_titles` |

Templated queries (`src/tools/db.py`; the loader lives separately in `src/db.py`), all read-only (`mode=ro`), all parameterised (fixed query text; user words are passed in as values, never as code):

- `search_titles(q) -> [(id, title, score)]` (BM25 over `title`; each hit carries a `variant_group` field, the caller groups)
- `get_procedure(id)`, `get_required_documents(id)`, `get_fees(id, jurisdiction=None)`, `get_agency(id)`, `get_source(source_id)`

**Documents (ROUND-4, corpus v2).** Non-procedure documents (`legal_text`, `form`, `fee_resolution`, `guidance`, `change_notice`;
shape `data/schema/document_record.schema.json`) are collected into `data/processed_docs/<kind>/` and cleaned by `scripts/clean_documents.py` into
`data/clean_docs/<kind>/` (report `data/clean_docs/CLEAN_REPORT.md`). `src.db.build(docs=…)` / `scripts/build_db.py --docs` loads them into `documents`,
`document_sections` (one row per article / form part / heading, in order) and `document_procedures` (links to loaded procedures only; a document
linked to none is skipped with a note). `sha256` is the raw fetched file (articles cut from one law share it); de-duplication uses `doc_id`,
the cleaned text hash `text_sha256` and (kind, title). Without `--docs` the three tables exist and are empty (corpus v1). `original_version` / `amended_by` mark a legal article or form whose wording has since
been amended; its chunks start with `[Văn bản gốc – đã sửa đổi] `. The builders' run lock guards only the shared `data/app.db` and `data/chroma/`
next to `data/.RUNLOCK`, so copies (`data/app_v2.db`, `data/chroma_v2`) can be built while a run holds the lock (PROTOCOL, "Shared artifacts lock").

Decision: no free-form Text-to-SQL. Reason and alternatives in `DECISIONS.md` D-003.

---

## 3. Chunking — by section, not by character count

The first version splits at 700 characters. Procedure pages have natural sections, and the guardrail
needs to know which section a chunk came from (a fee sentence inside a steps chunk is a smell). So:

- One chunk (a piece of text stored in the vector index and retrieved as one unit) per section per procedure. Section ids (English, used in metadata and evidence ids):
  `required_documents`, `steps`, `submission_method`, `fees`, `agency`, `processing_time`, `conditions`, `legal_basis`,
  and `summary` (title + 2-line summary, used by `resolve_procedure`).
- Sections longer than ~900 tokens (≈600 Vietnamese words; a token is a word-piece the model counts) are sub-split with overlap (the end of one
  piece is repeated at the start of the next, so no sentence is lost), keeping the section tag.
- Metadata on every chunk: `procedure_id`, `section`, `source_id`, `retrieved_at`, `tier="corpus"`.
- Each chunk's *text* is prefixed in Vietnamese, because that is what the embedding (a number vector that represents meaning, used for similarity search) and the LLM read:
  `"[Thủ tục: <title>] [Mục: <Vietnamese section label>] "`. The English section id lives in metadata only.
  (This prefix alone reduces variant blending measurably; record the before/after in `journal.md`.)
- Section labels (`src/ingest.py:SECTION_LABELS`) and the record fields each section is built from:

  | Section id | Vietnamese label (prefix) | Built from |
  |---|---|---|
  | `summary` | Tóm tắt | `title`, `field`, `level`, `jurisdiction`, `receiving_agency` |
  | `required_documents` | Thành phần hồ sơ | `required_documents[]` (item, quantity_text/quantity, mandatory, note), numbered |
  | `steps` | Trình tự thực hiện | `steps[]`, "Bước i: …" |
  | `submission_method` | Cách thức thực hiện | `channels[]` |
  | `fees` | Phí, lệ phí | the same fee rows the DB loads (incl. Đắk Lắk extras) |
  | `agency` | Cơ quan thực hiện | `receiving_agency` (+ `jurisdiction`) |
  | `processing_time` | Thời hạn giải quyết | `processing_time` |
  | `conditions` | Yêu cầu, điều kiện | `conditions` |
  | `legal_basis` | Căn cứ pháp lý | `legal_basis[]` |

- An empty section produces no chunk (in particular, unknown fees produce no `fees` chunk; unknown is not free).
- The index builder must read records via `src.db.read_records` + `src.db.select_records`, so the index and the DB use the same records and the same source precedence.
- **Document chunks (ROUND-4).** Each section of a cleaned document becomes one chunk per linked procedure (sub-split like procedure sections), prefix
  `"[Thủ tục: <procedure title>] [Văn bản: <document title>] [Mục: <section heading>] "`, id `doc:<procedure_id>:<section>:<8 hex of doc_id>-<i>`.
  Metadata adds `kind`, `doc_id`, `doc_title` (procedure chunks have `kind = "procedure_page"`). `section` deliberately reuses the procedure section ids (no new ids) so the
  evidence contract (`src/evidence.py:SECTIONS`) and the graph's intent filters (`src/nodes.py:INTENT_SECTION`) apply unchanged: `legal_text`, `change_notice` → `legal_basis`; `form` → `required_documents`;
  `fee_resolution` → `fees`; `guidance` → `steps`. Tier stays `corpus`: a document may support a narrative claim, never replace a DB row for a number.
  `resolve_candidates` ranks procedures over `procedure_page` chunks only, so a law cited by many procedures cannot pull one up. Its BM25 term statistics
  are computed over `procedure_page` chunks only (`src/tools/rag.py:_bm25_for`), so adding documents cannot shift resolution through word rarity either.
- To apply record or document changes without a full re-embed, `scripts/sync_index.py` (`src/ingest.py:sync_index`) deletes, embeds or re-labels only the
  chunks that differ from what a full build would produce.

Compare in Phase 2: section chunking vs 700/100 character chunking on context precision — a cheap, reportable ablation.

---

## 4. Provenance rules

- Nothing enters the DB or the index without `source_id`, `url`, `retrieved_at`.
- DB and index are built from the same record set: both read via `src.db.read_records` + `src.db.select_records`.
- `content_hash` (a fingerprint of the page; if it changes, the page changed) lets a re-scrape detect change; changed records get a new `retrieved_at` and the old chunk ids are deleted (rebuild DB and index together, always).
- `effective_date` is filled when the page or the legal basis states it; otherwise `null` and the answer says "ngày lấy dữ liệu" instead.

---

## 5. Acquisition — decide in week 1

The professor's own note says: do not let every group scrape from scratch; a packaged 50–200 document corpus plus a sample SQLite may be provided. **Ask first** (`questions-for-professor.md` Q1).

If not provided, in order of preference:

1. **Ministry of Justice "Quyết định công bố thủ tục hành chính" (lĩnh vực hộ tịch)** — the legally authoritative publication, a single PDF/DOC with every procedure in a fixed structure (tên, trình tự, cách thức, thành phần hồ sơ, thời hạn, đối tượng, cơ quan, lệ phí, căn cứ). Cleanest to parse into the canonical record; one `source_id` per decision, `effective_date` explicit. Search `moj.gov.vn` / `thuvienphapluat.vn` for the latest one issued after the 2025 reorganisation.
2. **dichvucong.gov.vn procedure detail pages** — authoritative and the professor's suggested source, but the portal is JavaScript-heavy; check whether detail pages are fetchable server-side or expose a JSON endpoint before committing. Rate-limit (≥2 s), ≤100 pages, store raw HTML.
3. **Provincial DVC portals** for province-specific fee rows (only if time allows; otherwise `jurisdiction="theo tỉnh"` and the fee answer becomes partial).

Whatever the source, hand-verify 10 random records field by field and keep the verification sheet in `data/verification.md`; it is evidence for the report's data section.

Target: 30–60 procedures with at least these families represented, because the test set depends on them:
khai sinh (≥3 variants), kết hôn (≥2), khai tử, nhận cha-mẹ-con, thay đổi/cải chính hộ tịch, cấp bản sao trích lục, xác nhận tình trạng hôn nhân, CCCD cấp mới/cấp lại/đổi, đăng ký thường trú/tạm trú.

**Sources actually used (build of 2026-10-10).** The national portal dichvucong.gov.vn was not reachable server-side.
The corpus therefore comes from three sources, in this precedence:

1. `data/processed/moj/` — 37 hộ tịch procedures from moj.gov.vn's server-rendered procedure pages
   (`source_id` `moj-portal#<mã>`, kind `ministry_portal_page`). Their `receiving_agency` is taken from Quyết định 1833/QĐ-BTP
   Phần I (cited in `source.locator`).
2. `data/processed/bca-portal/` — 18 căn cước and cư trú procedures from dichvucong.bocongan.gov.vn
   (`bca-portal#<mã>`, `ministry_portal_page`).
3. `data/processed/daklak/` — 39 hộ tịch procedures from the annex of Quyết định 33/QĐ-UBND of Đắk Lắk
   (`daklak-33/QD-UBND#<mã>`, `provincial_decision`). 37 of these overlap with moj, so they add Đắk Lắk fee rows
   and a `sources` row but not the procedure row; 2 are Đắk Lắk-only.

- Result: 57 unique procedures (Hộ tịch 39, căn cước 9, cư trú 9); all target families above are present.
- Conflicts are in `data/processed/CONFLICTS.md`; cross-source differences are in `data/processed/SOURCE_DIFF.md`.
- The 10-record check sheet is `data/verification.md`.

**Depth documents (corpus v2, live since 2026-10-10).** 210 non-procedure documents linked to the 57 procedures, collected by w-moj (hộ tịch, 143)
and w-dvc (Bộ Công an families, 67) into `data/processed_docs/<kind>/`, cleaned into `data/clean_docs/` (210 kept, 0 skipped). By kind (documents / sections):
`legal_text` 143 / 143 (articles of the laws, decrees and circulars cited in `legal_basis`), `form` 27 / 47, `change_notice` 21 / 56, `guidance` 18 / 85,
`fee_resolution` 1 / 1. Loaded as `documents` 210, `document_sections` 332, `document_procedures` 857, and indexed as 1,857 document chunks
(2,429 in all). Counts, hashes and the build: `data/README.md` "Corpus v2". Corpus v1 (procedures only, 572 chunks) is kept as `data/app_v1.db` / `data/chroma_v1`.
