# Data provenance — AI5013 Project 5 corpus

State as of 2026-10-10. Every record traces to a raw file plus a URL. Raw files live in `data/raw/` (git-ignored); each raw directory has an `index.jsonl` with `url`, `fetched_at` (UTC), `status`, `sha256`.
Identifiers are English. Content is Vietnamese, verbatim (whitespace cleanup only).

## 1. Sources used

| # | Source | Kind | Provides | URL pattern | Retrieved | Records | How fetched | Etiquette |
|---|---|---|---|---|---|---|---|---|
| 1 | **moj.gov.vn** — Bộ Tư pháp portal, *Thủ tục hành chính* | ministry procedure pages (server-rendered HTML) | hộ tịch: trình tự, cách thức (thời hạn + lệ phí per channel), thành phần hồ sơ, đối tượng, kết quả, căn cứ pháp lý, điều kiện | `https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-<mã TTHC>.html` | 2026-10-10 | **37** → `processed/moj/` (`source_id = moj-portal#<mã>`) | `scripts/fetch_moj.py`, `moj_fetch_portal.py`; parsed by `parse_moj.py` | robots.txt checked (allows `/portal/`); ≥2.5 s/host; each URL fetched once |
| 2 | **1833/QĐ-BTP** (23/06/2025, effective 01/07/2025) — Bộ Tư pháp *Quyết định công bố TTHC hộ tịch*, Phần I (danh mục) | legal decision, text PDF (copy hosted by Hải Phòng) | **cơ quan thực hiện** after the 2-tier reform, for 39 mã. Used as `receiving_agency` in source 1 | `cdn.haiphong.gov.vn/gov-hpg/6855/tintuc/2025/11/1833638988795114181791.pdf` | 2026-10-10 | (feeds the 37 above) | same | same |
| 3 | **33/QĐ-UBND tỉnh Đắk Lắk** (effective 08/01/2026, căn cứ 3673/QĐ-BTP), Phụ lục | provincial decision, text PDF | per mã: thời hạn, cách thức, **phí/lệ phí as applied in Đắk Lắk**, căn cứ (incl. NQ HĐND tỉnh). No document lists | `vpubnd.daklak.gov.vn/CMS/Content/VanBan/2026/01-2026/Tinh/33_QD-UBND PL.pdf` | 2026-10-10 | **39** → `processed/daklak/` (`daklak-33/QD-UBND#<mã>`, fee jurisdiction "Đắk Lắk") | `fetch_moj.py`; `moj_parse_daklak.py` | same |
| 4 | **dichvucong.bocongan.gov.vn** — Bộ Công an DVC portal, *Bộ thủ tục* | ministry procedure pages (server-rendered HTML) | cư trú (9) + căn cước (9): trình tự, hồ sơ by case group, thời hạn, phí, căn cứ | `https://dichvucong.bocongan.gov.vn/bocongan/bothutuc/tthc?matt=<id>` (lists: `…/bothutuc?linh_vuc=<code>`) | 2026-10-10 | **18** → `processed/bca-portal/` (`bca-portal#<mã>`) | `scripts/crawl_bca_portal.py`, `parse_bca_portal.py` (w-dvc) | robots-compliant; 4 s delay; cap 20 pages; each fetched once |

Raw: `data/raw/moj/` (+ `portal/`), `data/raw/dvc/bca-portal/`. Worker logs: `docs/05_log/workers/w-moj/STATUS.md`, `docs/05_log/workers/w-dvc/STATUS.md`.
Hand verification: `data/processed/bca-portal/VERIFICATION.md` (3 records, 15/15 fields match). For w-moj, 2 records were checked field by field and 3 spot-checked (w-moj STATUS). The MOJ and Đắk Lắk thời hạn values agree for all 37 shared mã.

## 2. Sources tried and not usable

- **dichvucong.gov.vn** (national portal): pure client-side SPA. Its JS bundle sits under `/assets/`, which robots.txt disallows for non-Googlebot agents, and blind API calls are rejected by the NDC WAF. See `data/raw/dvc/EVIDENCE.md`.
- **csdl.dichvucong.gov.vn** (national TTHC database): 503 on robots.txt, `/` redirects to a login page. See EVIDENCE.md.
- **Provincial DVC portals** (HCM, Đà Nẵng: VNPT iGate; Hà Nội): the API needs an OAuth `client_credentials` token whose secret is extracted from the public JS. The lead rejected this as circumventing an access control. Hà Nội is an SPA with no API visible. See EVIDENCE.md.
- **thuvienphapluat.vn**: Cloudflare JS challenge, HTTP 403 (`data/raw/moj/tvpl-3673-QD-BTP.html`). Not bypassed.
- **luatvietnam.vn**: metadata only; full text and attachments need a login.
- **Bộ Công an decisions 5230/QĐ-BCA-C06 (căn cước, 18/08/2026) and 5860/QĐ-BCA-C06 (cư trú, 16/09/2026)**: **scanned PDFs with no text layer** (`data/raw/moj/5230-…pdf`, `5860-…pdf`). Not used, per the owner's rule (text sources only, no OCR).
- **Bộ Tư pháp decisions 1833 (Phần II), 3673/QĐ-BTP (25/12/2025), 163/QĐ-BTP (16/01/2026)**: no reachable copy containing the procedure content (Phần II). Only 1833 Phần I was found (used for agencies). hue.gov.vn renders attachments via JS. See w-moj STATUS.

## 3. Staleness facts (feed the freshness guardrail)

| Fact | Date | Citation / evidence |
|---|---|---|
| All target hộ tịch procedures are received by **UBND cấp xã** (xã, phường, đặc khu). Foreign-element cases moved from cấp huyện. Copy and confirmation procedures sit with the CSDL hộ tịch điện tử authority (Sở Tư pháp, UBND cấp xã). | since **01/07/2025** | 1833/QĐ-BTP Điều 2 + Phần I (text held); NĐ 120/2025/NĐ-CP Điều 4 (secondary). Details: `docs/05_log/workers/w-moj/REORG-2025.md` §1 |
| The MOJ portal's own *Cơ quan thực hiện* field is outdated: **12/37 pages say "xã, phường, thị trấn"** (thị trấn no longer exist); **1.001669 and 2.000513 say "Phòng Tư Pháp"** (district level abolished). | observed 2026-10-10 | `data/raw/moj/portal/<mã>.html`. Records use the 1833 value and keep the portal wording in `raw_text` with `parse_flags: stale_agency_wording_at_source` |
| The BCA portal's legal basis lags the law. Cư trú pages lack TT 116/2026/TT-BCA and Luật 118/2025/QH15. Căn cước pages lack NĐ 58/2026 and TT 117/118/120/2026. There is no Công an cấp xã variant of cấp/cấp đổi/cấp lại (≥14 tuổi), although 5230/QĐ-BCA-C06 lists one. | observed 2026-10-10 | w-dvc STATUS Finding 2; `data/raw/ocr/5230-QD-BCA-C06/page-005.txt` (partial OCR, evidence only) |
| **Luật Hộ tịch số 03/2026/QH16** replaces Luật Hộ tịch 2014. The whole hộ tịch corpus goes stale. | effective **01/03/2027** | secondary sources (REORG-2025.md §1.3) |
| Temporary fee cuts end: căn cước lệ phí at 50% (TT 64/2025/TT-BTC, unverified); cư trú lệ phí free via VNeID (TT 29/2026/TT-BTC). | end **31/12/2026** | REORG-2025.md §3.2 (secondary) |
| Hộ tịch fees: exempt by law (Luật Hộ tịch 2014 Điều 11 khoản 1: khai sinh/khai tử đúng hạn, kết hôn, giám hộ in-country; gia đình có công, hộ nghèo, người khuyết tật). Otherwise **set by HĐND tỉnh** (TT 85/2019/TT-BTC). The only national amount is 8.000 đồng for bản sao trích lục / xác nhận thông tin hộ tịch (TT 281/2016/TT-BTC). | — | MOJ pages; Đắk Lắk annex (names NQ 24/2024 and 09/2025/NQ-HĐND, no amounts) |

## 4. Canonical record, schema, tooling (pointers)

- Record definition: `docs/03_design/data-model.md` §1. DB schema: §2. Provenance rules: §4.
- JSON Schema: `data/schema/procedure_record.schema.json`. Validator: `uv run python scripts/validate_records.py <dirs>`.
- Loader / DB build: `src/db.py` (`read_records`, `source_kind`), `scripts/build_db.py` (source precedence `--prefer`, conflicts → `data/processed/CONFLICTS.md`).
- Source-id convention: `<source>#<mã TTHC>`. Prefixes used: `moj-portal`, `daklak-33/QD-UBND`, `bca-portal`.

## 5. Known limitations

- **Small corpus by design:** 37 hộ tịch (national) + 18 cư trú/căn cước + 39 Đắk Lắk fee/time rows. That is 55 national procedures.
- **No decision text for content:** procedure content comes from ministry portals, not from the legal *Quyết định công bố*. The portals lag those decisions (§3).
- **Fees:** nearly all hộ tịch fees are "theo HĐND tỉnh", and the only province modelled (Đắk Lắk) gives no amounts. On the BCA portal, real amounts appear only for thường trú. Six BCA records have `fees: []` (unknown), and placeholder junk ("1", "a") is not interpreted.
- **`mandatory` is always null:** neither portal states it. Conditional items are phrased "Trường hợp …".
- **Document order:** MOJ rows are in portal order, not decision order (flagged). BCA rows are grouped by case in `note`.
- **Source defects kept verbatim and flagged:** garbled word order in 1.001193 steps 1–2; bare-number thời hạn on 9 MOJ pages (unit "ngày làm việc" confirmed by Đắk Lắk); portal "Phí" vs "lệ phí" labelling on cư trú.
- **`effective_date` is mostly null:** the portals do not state it. Đắk Lắk = 2026-01-08. Answers should show `retrieved_at`.
- **BCA facts in REORG-2025.md §2–3 are secondary** (the decisions are scanned).

## Corpus v2 (switched in 2026-10-10T12:32Z by w-tools, lead's go)

v2 keeps the 57 procedures (procedure tables identical to v1) and adds 210 non-procedure documents (ROUND-4-DATA.md), cleaned by
`scripts/clean_documents.py` (`data/processed_docs` → `data/clean_docs`, report `data/clean_docs/CLEAN_REPORT.md`; 210 in, 210 kept, 0 skipped) and
validated by `scripts/validate_documents.py` against `data/schema/document_record.schema.json` (210 valid).

| kind | documents | sections |
|---|---|---|
| legal_text | 143 | 143 |
| form | 27 | 47 |
| change_notice | 21 | 56 |
| guidance | 18 | 85 |
| fee_resolution | 1 | 1 |
| **total** | **210** | **332** |

- `data/app.db` (= `data/app_v2.db`): sha256 `46c3f0d64e5da97c528ff234f84fdc2721d79130df6e97515e4b6dd824ffe941`;
  documents 210, document_sections 332, document_procedures 857 (document → procedure links); procedures 57, sources 94, required_documents 341, fees 218, agencies 55.
- `data/chroma` (= `data/chroma_v2`), collection `corpus`: **2429 chunks**. By kind: procedure_page 572, change_notice 822, legal_text 532, guidance 333, form 153, fee_resolution 17.
  A document chunk exists per document section per linked procedure, so its `procedure_id` filter works like a procedure chunk's.
- Built by a full embed (`build_index.py --docs`, 2673 chunks, 76 s). The narrowed change-notice links and dates were then applied with
  `scripts/sync_index.py`, which embeds only new or changed chunks (here 263 deleted, 183 metadata-only updates, 19 embedded, 2 s).
  A dry run against the full-rebuild target shows 0 differences.
- **BM25 per kind:** resolution ranks procedures over `procedure_page` chunks, with BM25 term statistics computed over those chunks only
  (`src/tools/rag.py:_bm25_for`). Without that, the documents alone lowered held-out resolution hit@1 from 0.82 to 0.59. With it, all resolution
  views are identical on v1 and v2 (tuned 0.81 / 0.96 / 0.98, held-out 0.82 / 0.82 / 1.00; `docs/05_log/workers/w-tools/evidence/round4/`).
- v1 is kept for the labelled corpus-v1 numbers: `data/app_v1.db` (sha256 `1d5931c79dd487055e01a12ab99a1e07ee48cbc970b2b976f0662322bd291a0b`), `data/chroma_v1` (572 chunks).

