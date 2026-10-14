# Data collection — where the corpus comes from and how it is prepared

Draft, w-dvc, 2026-10-10 (BRIEF-8 Part 2). Numbers come from `data/README.md`, `data/app.db` (read-only) and the evidence files named in each section.

Terms used throughout:
- **corpus** — the collection of texts the assistant searches and quotes from.
- **procedure** (*thủ tục hành chính*, TTHC) — one official service, for example "đăng ký khai sinh" (birth registration).
- **mã TTHC** — the national procedure code (for example `1.001193`). It is the same code on every government site, so it is our `procedure_id`.
- **document** — one piece of text with its own source: a web address (URL), the date we downloaded it, and a **sha256** (a fingerprint of the exact
  bytes we downloaded, so anyone can check the file was not changed).
- **chunk** — a short passage cut from a document; the search engine looks up chunks, not whole documents.

---

## 1. What the brief suggests, and how we read it

**What.** The course brief names the national public-service portal, `dichvucong.gov.vn` (Cổng Dịch vụ công Quốc gia), as the corpus source: "cào một
nhóm thủ tục theo lĩnh vực" — collect one group of procedures from one field such as hộ tịch (civil status: birth, marriage, death records). The brief's
data note recommends a "minimal dataset" of about **50–200 documents** and warns that Vietnamese corpora "cần thêm bước làm sạch" — need an extra
cleaning step (`docs/00_sources/description.md` §Project 5 and "Lưu ý về dữ liệu"). The sample plan says the same: 50–200 official procedure records,
"confirm access rules … before scaling" (`docs/01_context/sample_plan.md`).

**Why it matters.** The portal is a suggestion of *where the official procedure text lives*, not a requirement to use one web address. What a grader
checks is that the content is official, current, traceable to a source, and large enough to test the system.

**How we read it.** (1) Use the same official procedure content, identified by the same national mã TTHC, from a place we are allowed to read.
(2) Count documents honestly and add depth until we sit inside 50–200 (Round 4, §6). (3) Make cleaning an explicit, documented step (§4).

## 2. Sources actually used, and why

**What.** Four official, text-based sources (`data/README.md` §1):

| Source | Publisher | What it gives | Records |
|---|---|---|---|
| `moj.gov.vn` procedure pages | Bộ Tư pháp (Ministry of Justice) | hộ tịch procedures: steps, documents, time, fees, legal basis | 37 |
| 1833/QĐ-BTP, Part I | Bộ Tư pháp | which office handles each hộ tịch procedure after the July 2025 local-government reform | feeds the 37 |
| 33/QĐ-UBND Đắk Lắk, annex (*phụ lục*) | Đắk Lắk provincial People's Committee | the same procedures as applied in one province: time, channel, fee rule | 39 |
| `dichvucong.bocongan.gov.vn` procedure pages | Bộ Công an (Ministry of Public Security) | căn cước (identity card, 9) and cư trú (residence registration, 9) procedures | 18 |

**Why these.** The national portal does not write procedures; it displays what each ministry publishes into the national procedure database
(CSDL TTHC). The ministries are the legal publishers, and their pages carry the **same mã TTHC**, so the content is the same official content under the same
key. The provincial annex adds what really varies by place (fees set by the provincial council, HĐND tỉnh). This is decision **D-012**
(`docs/04_decisions/DECISIONS.md`): use the ministries' official publications. Its **amendment** records what was actually built: the procedure text
came from the ministries' portal pages (text HTML), the decision texts used were 1833/QĐ-BTP Part I and the Đắk Lắk annex, and the planned OCR step was
dropped under the owner's text-only rule.

## 3. Access evidence and rejected directions

**What.** Before choosing, we tried the suggested portal and its neighbours, politely (our own named user agent, one request at a time, 2.5–4.5 s
apart, robots.txt obeyed). **robots.txt** is the file in which a website says which paths automated readers may fetch. **WAF** (web application firewall)
is a filter that blocks requests it does not like. Full record: `data/raw/dvc/EVIDENCE.md`, including the re-scout of 2026-10-10 11:40Z.

| Direction | What we found | Why rejected |
|---|---|---|
| `dichvucong.gov.vn` pages | Every allowed page, including procedure detail and "print" URLs, returns the same 5222-byte empty page (an **SPA**, single-page application: the text is filled in later by a script). That script sits under `/assets/`, which robots.txt forbids to every reader except Googlebot. The sitemap lists 61 section pages and no procedure page. | Reading it means running a forbidden script (rendering the SPA) — against robots.txt |
| `dichvucong.gov.vn` API, feeds | `/api…`, `/rss`, `/feed`, `/rss.xml`, `/sitemap_index.xml` → "Request Rejected … NDC WAF" | Getting past a firewall is circumvention |
| `csdl.dichvucong.gov.vn` (national database), `thutuc.dichvucong.gov.vn` | redirect to a login page, or HTTP 503 | **Login wall**: we have no account and a project crawler should not use one |
| `data.gov.vn` (open-data portal) | the name does not exist in DNS | Nothing to fetch |
| Provincial portals (HCM, Đà Nẵng) | a JSON API that answers 401 (not authorised) without a token; the token comes from a **client secret** (a password-like key) embedded in the site's public script | The lead ruled that using a scraped secret to pass a 401 is circumventing an access control |
| `thuvienphapluat.vn` | Cloudflare "Just a moment…" challenge, HTTP 403 | Not bypassed; also not an official publisher |
| Bộ Công an decisions 5230/QĐ-BCA-C06, 5860/QĐ-BCA-C06 | scanned PDFs with no text layer | Would need **OCR** (reading text out of page images); the owner's rule is text sources only |

**Why it matters.** The inaccessibility is itself a design input: the assistant never claims to mirror the national portal; when facts may be stale it
points the user to the portal (freshness and redirect guardrails).

## 4. The processing pipeline, fetch to index

**What.** Eight steps turn a web page into searchable, citable data. Steps 1–3 and 5–8 exist today for procedure pages; Round 4 adds the same steps for
the new document kinds (§6) and makes cleaning and linking explicit.

| Step | What happens | Today (procedure pages) | Round 4 (depth documents) |
|---|---|---|---|
| 1. Fetch | polite download, robots.txt checked, each response cached with URL, time and sha256 in an `index.jsonl` | `scripts/fetch_moj.py`, `moj_fetch_portal.py`, `crawl_bca_portal.py` | collectors (w-dvc, w-moj), same rules |
| 2. Clean | strip menus, headers, footers; normalise whitespace and Unicode (NFC, one standard way of storing Vietnamese accents); keep the Vietnamese wording verbatim | inside the parsers (`parse_moj.py`, `parse_bca_portal.py`, `moj_parse_daklak.py`): "whitespace cleanup only" | `scripts/clean_documents.py` (`data/processed_docs` → `data/clean_docs`) |
| 3. Segment | cut into sections | parsers emit one record per procedure with named sections (steps, documents, fees …) | legal texts by *điều/khoản* (article/clause), forms whole plus instructions, guidance by heading |
| 4. Link | attach each piece to the procedure(s) it is about | the mã TTHC on the page | each document lists its procedures in `procedure_ids`, with `link_method` saying how: `legal_basis` (the procedure's legal basis cites the text), `procedure_code` (the code or form code is on the page), `named` (the notice names the procedure), `instrument_scope` (the notice changes a text the procedure's legal basis cites), or `manual`; the reason is written in `notes` |
| 5. Validate | check every file against a JSON Schema (a machine-readable list of required fields and types) | `scripts/validate_records.py` on `data/schema/procedure_record.schema.json` (94/94 valid) | `scripts/validate_documents.py` on `data/schema/document_record.schema.json` |
| 6. De-duplicate | drop exact copies | one record per (source, mã); `build_db.py --prefer` picks which source fills each procedure; disagreements go to `data/processed/CONFLICTS.md` | by `doc_id`, by a hash of the cleaned section text, and by (kind, title); sha256 of the raw file is kept as provenance only; every skipped item listed with its reason |
| 7. Load | write to SQLite (the structured database the assistant reads exact numbers from) | `scripts/build_db.py` → `data/app.db` | new `documents`, `document_sections`, `document_procedures` tables, built on a copy (`data/app_v2.db`) |
| 8. Index | cut into chunks, embed them (turn text into number vectors with bge-m3) and store them in Chroma (the vector store) | `scripts/build_index.py` (`src/ingest.py`): one chunk per section, long sections split, prefix `[Thủ tục: …] [Mục: …]` | each document section becomes a chunk per linked procedure, with prefix `[Thủ tục: …] [Văn bản: …] [Mục: …]` (`build_index.py --docs`); later edits are applied with `scripts/sync_index.py`, which re-embeds only new or changed chunks. Procedure resolution computes its BM25 (keyword-match) statistics over procedure-page chunks only (per-kind BM25), so the many document chunks do not crowd out the procedure titles |

Both build scripts refuse to run while `data/.RUNLOCK` exists, so an evaluation in progress is never invalidated by a rebuild.

## 5. Counts today (corpus v1)

| What | Count | Source of the number |
|---|---|---|
| Procedures | **57** | `app.db` `procedures` |
| Fields | **3**: hộ tịch 39, căn cước 9, cư trú 9 | `app.db` `procedures.field` |
| Variant families (groups of sibling procedures, e.g. first issue / re-issue / replacement of the same card) | **10** | `app.db` distinct `variant_of` (from `data/variants.yaml`) |
| Source records | **94** = 55 ministry pages (37 MOJ + 18 BCA) + 39 Đắk Lắk annex sections | `app.db` `sources.kind`: `ministry_portal_page` 55, `provincial_decision` 39 |
| Required-document rows / fee rows / agency rows | 341 / 218 / 55 | `app.db` |
| Chunks in the search index | **572** | `build_index.py` run, recorded in `docs/03_design/as-built-pipeline.md` §3 |

So by the brief's measure we have 94 documents: inside 50–200, but only one page per procedure plus one provincial row each — wide, not deep.

**Round-4 depth documents (corpus v2, loaded and indexed).** Source: `data/README.md` "Corpus v2" (switched in 2026-10-10T12:32Z).
**210 documents** (legal_text 143, form 27, change_notice 21, guidance 18, fee_resolution 1), cut into **332 sections**, with **857 procedure links**
(document → procedure). They are loaded in `data/app.db` (= `data/app_v2.db`, sha256 `46c3f0d6…`; tables `documents`, `document_sections`,
`document_procedures`) and indexed in `data/chroma` (= `data/chroma_v2`): **2,429 chunks** in total (572 procedure-page chunks plus document chunks).
Corpus v1 is kept as `data/app_v1.db` and `data/chroma_v1` (572 chunks) for the labelled v1 numbers.
Of the 210, 67 belong to the Bộ Công an families (w-dvc: legal_text 38, form 6, guidance 13, change_notice 10; all 18 procedures linked) and 143 to
hộ tịch (w-moj): legal_text 105 (99 original-version articles of Luật 60/2014, NĐ 123/2015 and TT 04/2020, plus 6 articles of TT 08/2025/TT-BTP),
form 21 (the 20 tờ khai of TT 04/2024 Phụ lục 5, plus the NĐ 301/2026 liên thông tờ khai), change_notice 11, guidance 5 and fee_resolution 1;
all 39 hộ tịch procedures are linked. Together with the 94 procedure source records, that is 304 documents.

## 6. Depth plan (Round 4)

**What.** Add at least 100 new documents, for at least 150 in total (target 150–200), without adding any procedure (`docs/05_log/ROUND-4-DATA.md`).
Every new document is text, official, and linked to at least one of the 57 existing procedures.

| Kind | What it is | Where from |
|---|---|---|
| `legal_text` | only the cited articles (*điều/khoản*) of the laws, decrees and circulars in a procedure's legal basis | vanban.chinhphu.vn, datafiles.chinhphu.vn, moj.gov.vn/vbpq, bocongan.gov.vn |
| `form` | the declaration form (*tờ khai*) and how to fill it, as text | circular appendices (TT 04/2020/TT-BTP, TT 66/2023/TT-BCA …), ministry portals |
| `fee_resolution` | the provincial council resolution that sets a fee | HĐND Đắk Lắk and one or two more provinces |
| `guidance` | official how-to and Q&A pages (*hướng dẫn, hỏi đáp*) | provincial portals, bocongan.gov.vn, moj.gov.vn |
| `change_notice` | an official notice that something changed, with the effective date | baochinhphu.vn, chinhphu.vn, ministry news |

**Why.** Depth answers the questions a single procedure page cannot: "which article says this?", "what does the form ask?", "how much in my province?",
"did this change?". It also gives the grader a document count that matches the brief.

**How.** Each document is stored as `data/processed_docs/<kind>/<doc_id>.json` with `doc_id`, `kind`, `title`, `url`, `retrieved_at`, `sha256`,
`procedure_ids`, `sections` (each a heading and text), plus optional `issuer`, `effective_date`, `jurisdiction`, `link_method`, `notes`. Collection is split
by family: w-dvc the Bộ Công an families (căn cước, cư trú), w-moj hộ tịch. w-tools owns the schema, cleaning script, loader and index, all on copies;
the switch to corpus v2 happens only on the lead's word, then baseline and guardrailed are re-run (corpus v1 numbers stay, labelled).
Legal articles are evidence for narrative claims only; a number (fee, time limit) is still answered from the database row.

## 7. Limits

- **Not the suggested portal.** Content comes from the ministries and one province, not from `dichvucong.gov.vn`, for the reasons in §3.
- **Portals lag the law.** The BCA pages do not cite the 2026 decrees and circulars; 12 of 37 MOJ pages still list "thị trấn" (towns, abolished in 2025) as the receiving level, and 2 name the abolished district office. Records keep
  the source wording and flag it (`data/README.md` §3).
- **Scanned decisions are out.** The newest Bộ Công an decisions (5230, 5860/QĐ-BCA-C06) are scans; under the no-OCR rule their content is missing.
- **One province.** Only Đắk Lắk is modelled, and its fee rows mostly say "theo HĐND tỉnh" (set by the provincial council) without an amount.
- **Coming change.** Luật Hộ tịch 03/2026/QH16 takes effect on 01/03/2027 and will make the hộ tịch part stale.
- **Small by design.** 57 procedures in 3 fields; questions outside them are refused as out of scope or not in the corpus.
- **Amended laws are held in their original wording.** Luật Căn cước 2023 and Luật Cư trú 2020 were amended by Luật 118/2025/QH15 (in force
  01/07/2026); NĐ 70/2024 and NĐ 154/2024 by NĐ 58/2026; TT 17/2024 by TT 53/2025 and TT 118/2026. The amending texts were not available as text, so
  those records carry `original_version: true` and `amended_by`, and their chunks are marked "[Văn bản gốc – đã sửa đổi]".

### Skipped during Round-4 collection (Bộ Công an families), one line per reason
- **Scanned PDF, no text layer (no OCR):** TT 53/2025/TT-BCA, TT 73/2024/TT-BTC (căn cước fee), Luật 118/2025/QH15, and the signed PDFs of
  Luật Cư trú, NĐ 70/2024, NĐ 154/2024 on datafiles.chinhphu.vn (for these three the Công báo .doc was used instead).
- **Repealed text:** TT 55/2021, TT 56/2021, TT 66/2023/TT-BCA and their forms CT01/CT03/CT07 — repealed from 01/07/2026 by TT 116/2026/TT-BCA
  Điều 27, which is used instead; the 2020 form files (.doc) linked from the BCA portal pages — superseded.
- **Text loaded by a robots-disallowed script:** vbpl.vn (national legal database) detail pages fetch their text from `/api/`, which robots.txt forbids.
- **Mostly images or link lists:** xaydungchinhsach "nộp hồ sơ trực tuyến … cho người từ đủ 14 tuổi" (steps are screenshots).
- **Cites a repealed law:** BCA portal "Câu hỏi thường gặp" (answers under Luật Căn cước công dân 2014).
- **Duplicates the procedure page and cites repealed forms:** BCA portal "Phiếu hướng dẫn thực hiện thủ tục" pages.
- **Personal data:** in one BCA Q&A answer, the part about the asker's own ID numbers was left out; the general rule was kept.

### Skipped during Round-4 collection (hộ tịch family, w-moj), one line per reason
- **Dead official links:** the old moj.gov.vn `/vbpq/…/Attachments/` files (Luật 60/2014 .doc), vbpl.vn `/TW/Lists/vbpq/Attachments/` and `/FileData/` (NQ 24/2024 Đắk Lắk, TT 04/2020 gốc), thads.moj.gov.vn VBHN 123+104, the moj.gov.vn TCBC T6/2025 .docx and the pbgdpl.moj.gov.vn "Tờ gấp 03" all returned 404; vbpl.vn now redirects every page to `/`.
- **Host unreachable from this machine (timeouts or DNS):** vbpl.moj.gov.vn, phapdien.moj.gov.vn, qtht.moj.gov.vn, stp.travinh, yenthe and lucnam (Bắc Giang: TT 04/2024 PDF), camtrung.camxuyen (Hà Tĩnh: CV 481/BTP), phuongmyngai (Đồng Tháp), phuoclong (Bình Phước: fee decision).
- **Truncated download:** stp.angiang.gov.vn "1926 Nội dung 02 nhóm TTHC liên thông" .docx (incomplete zip, could not be opened).
- **Full text not reachable, summary used instead:** NQ 24/2024/NQ-HĐND Đắk Lắk is represented only by the Sở Tư pháp press release (gives Điều 19 "Lệ phí hộ tịch" and the effective date, no amounts). NQ 09/2025/NQ-HĐND (lệ phí 0 đồng online) was not found on any official host.
- **Duplicate:** the hatinh.gov.vn reprint of the Báo Chính phủ article on NĐ 120/2025 and the same article on xaydungchinhsach were skipped; the hcc.nghean.gov.vn copy is the longer one and is kept.
- **Draft, not law:** two xaydungchinhsach articles on the draft Luật Hộ tịch (sửa đổi) were skipped; the two articles on the adopted law are kept, dated 01/03/2027.
- **Client-side search, not usable:** the search pages of congbao.chinhphu.vn and vanban.chinhphu.vn render results in JavaScript. **Method that works:** the agency listing `congbao.chinhphu.vn/van-ban-dang-cong-bao/<agency>-cNN/trang-N.htm` → the document page → the attached `.doc` on g7.cdnchinhphu.vn; on xaydungchinhsach, the tag pages `/<tag>.html` (ho-tich, dang-ky-khai-sinh, dang-ky-ket-hon).
- **Fetched but not built (cutoff):** the NĐ 301/2026/NĐ-CP text PDF (datafiles.chinhphu.vn; it has a text layer) is in `data/raw/moj/docs/`. Its effect is covered by two change_notices and one form.
- **Original wording only:** Luật 60/2014, NĐ 123/2015 and TT 04/2020 come from one official .doc (media.lamdong.gov.vn) as originally issued; `original_version: true` and `amended_by` are set on each article.
