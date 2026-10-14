# Web UI — a simple local page in front of the graph (added 2026-10-10)

Code: `src/web/app.py` (backend), `src/web/static/index.html` (page), `tests/test_web_app.py` (tests).
Run: `uv run python -m src.web.app`, then open http://127.0.0.1:8000.

## 1. What is built

A small web server on your own machine (**localhost**: reachable only from this computer, address `127.0.0.1`) with three addresses:

| Address | What it does |
|---|---|
| `GET /` | Sends the one page: a question box, a province field, a mode selector (Trợ lý (có rào chắn) = guardrailed / Bản so sánh không rào chắn = baseline) and a submit button. Labels are in Vietnamese. |
| `POST /ask` | Takes one question as **JSON** (a plain-text data format) `{query, locality?, procedure_id?, variant?}`, runs the graph once and returns the answer as JSON. |
| `GET /presets` | Says which named preset each selector value runs (`{"guardrailed": "<default preset>", "baseline": "baseline"}`); for tooling only — the page shows no preset or version name. |
| `GET /procedures` | The "Thủ tục" tab's list: every procedure in the database, compact (see §5). |
| `GET /procedures/{code}` | One procedure's values with their sources, fetched only when its row is opened (see §5); 404 for an unknown code. |
| `GET /health` | Says whether Ollama (the local model server), LangFuse (the trace viewer), SearxNG (the local web search) and the SQLite database answer; the database block also counts `procedures`, `documents` and `document_sections` (the last two exist from corpus v2 on, null on a v1 database). Each check is a 2-second localhost call. |

The server uses **FastAPI** (a Python library that turns Python functions into web addresses) and **uvicorn** (the program that actually listens on port 8000).
The page is plain HTML with a little JavaScript; there is no front-end framework, no login and no database of its own.

What `/ask` returns, field by field:

| Field | Meaning | Taken from (graph state, `src/state.py`) |
|---|---|---|
| `preset` | the named flag set that answered (the default preset in `src/presets.py`, or `baseline`; see §2) | `src/presets.py` |
| `outcome` | one of `answer`, `answer_partial`, `clarify`, `refuse`, `out_of_scope` | `outcome` |
| `generation` | the final text shown to the user | `generation` |
| `citations` | list of `{evidence_id, source_url, retrieved_at}` | `citations` |
| `refusal` | `{type, portal_url, agency, missing}` or null | `refusal` |
| `candidates` | `{procedure_id, title}` list, filled only when `outcome = clarify` | `candidates` |
| `parts` | answer / answer_partial only: the same text split by part (procedure, locality, gap text, block sections by property, notices, notes, narrative) — see §4 | `src/web/structure.py` |
| `procedure_id`, `freshness`, `gaps`, `errors` | which procedure was answered, the freshness notice, the facts not found, any node error | same names |
| `latency_s` | wall-clock seconds for the whole graph run | measured in `app.py` |
| `model_calls` | how many times a model was called | a callback counter (same idea as `eval/run_variant.py`) |
| `trace_id`, `trace_url` | the LangFuse trace of this question and a link to it on `http://127.0.0.1:3000` | the per-request LangFuse handler's `last_trace_id` |

How the page shows each outcome: see §4 (outcome labels and the summary-first answer card, added 2026-10-10 evening).

Every card ends with the latency, the mode (trợ lý / bản so sánh), the number of model calls, the procedure id and the trace link.

## 2. Why it is built this way

- **The owner asked for "a simple webhost UI" and "just the simple backend".** So: one page, one question endpoint, nothing else. The command-line demo (`src/cli.py`) already shows the full behaviour; the page only makes it easier to show in a demo or a screenshot.
- **Single turn by design.** The graph answers one question from one state; it has no memory of earlier questions (see `docs/03_design/as-built-pipeline.md` §2). Sending a chat history would suggest a memory the system does not have. So the server stores nothing between requests.
- **The clarify click is the only follow-up.** When the question matches several close procedures, the graph stops at `clarify` instead of guessing. The user's choice is passed back as `procedure_id`, exactly like `--procedure` on the CLI; the graph then skips the procedure search and answers for that one procedure.
- **Both variants side by side.** The selector lets a viewer ask the same question to the guardrailed graph and to the professor's baseline, which is the comparison the evaluation measures.
- **Named presets, not code defaults.** A **preset** is a named set of graph flags kept in one table, `src/presets.py` (v1 … v5, baseline).
  The CLI, the evaluation and this server all read that table, so a demo answer and a reported number cannot come from different flags.
  "guardrailed" on the page runs the default preset in `src/presets.py` (DEFAULT_PRESET; v5 since 2026-10-10 19:29Z); the preset name is
  returned as `preset` (not shown on the page since 2026-10-10 evening: one current product, no version labels), put in the LangFuse tags and metadata, and passed into the graph state, where the `assess_need` span records it.
- **Localhost only.** The server binds `127.0.0.1:8000`, so nobody else on the network can reach it. The web tool's internet fallbacks (direct DuckDuckGo/Bing calls) are switched off by default in this server (`APP_WEB_BACKEND=searxng` unless you set it yourself), so the only web search goes through the local SearxNG.
- **Graph semantics unchanged.** No file of the graph (`src/nodes.py`, `src/graph.py`, `src/self_rag.py`, `src/render.py`, `src/refusal.py`, `src/tools/`) was edited; the server only calls `build_graph` and reads the final state.

## 3. How a request travels

```
browser ──POST /ask {query, locality?, procedure_id?, variant}──▶ src/web/app.py: ask()
   1. checks: query not empty, variant ∈ {guardrailed, baseline}           (else HTTP 422)
   2. init state = {query}; for guardrailed also preset (DEFAULT_PRESET), locality, procedure_id   (baseline has none of these inputs)
   3. callbacks = [LangFuse handler for this request (if configured), CallCounter]
   4. state = apps[variant].invoke(init, config={callbacks, recursion_limit: 50})
            └─ the compiled graph built once at startup (build_apps):
               guardrailed: src.graph.build_graph(llm, rag, db, web_search, judge=…, classifier=…, trace=span_hook(),
                                                  config=graph_config(DEFAULT_PRESET))   (apply_env(DEFAULT_PRESET) runs before src.tools.rag is imported)
               baseline:    src.baseline.build_graph(llm, rag, db, web_search)
   5. to_response(state) + latency_s, model_calls, trace_id, trace_url
   6. after the reply is sent: flush the LangFuse buffer (background task)
browser ◀──JSON── renders the card for `outcome`
```

**Dependency wiring** is the same as `src/cli.py`: local Ollama models from `src/llm.py`, the Chroma/BM25 retriever `src/tools/rag.py`, the read-only SQLite tools `src/tools/db.py`, and `src/tools/web.web_search`.
The graphs are compiled once when the server starts and reused for every request. The LangFuse **handler** (the object that records one trace) is created per request and passed through the invoke config, so every question gets its own trace id, the same way `eval/run_variant.py` does it. `span_hook()` writes each node's decision fields onto that trace's spans.

**Tests.** `tests/test_web_app.py` builds the app with the fake model, database, retriever and web tool from `tests/fakes.py` (no live model needed) and calls it through FastAPI's `TestClient`: one test per outcome (answer, answer_partial, clarify, refuse not_in_corpus, refuse system_error, out_of_scope), the clarify follow-up with `procedure_id`, the default preset's flags and `preset` reaching the graph, locality, the baseline variant, the trace-id passthrough, and two bad requests.

## 4. Outcome labels and the summary-first answer card (added 2026-10-10)

### What

- **A fixed label at the top of every card**, the same five everywhere, each with a colour, a Vietnamese name, a one-line meaning that
  states how certain the result is, and a short "Vì sao tin được" (why it can be trusted) line:

  | Outcome | Label (colour) | Meaning shown | Why it can be trusted |
  |---|---|---|---|
  | answer | Trả lời có nguồn (green) | Danh sách giấy tờ, lệ phí, cơ quan, thời hạn được chương trình sao nguyên văn từ dữ liệu chính thức, kèm nguồn; lời giải thích của mô hình được kiểm từng câu với nguồn. | every line has a source tag; unsupported model sentences were dropped |
  | answer_partial | Trả lời một phần (amber) | Phần có căn cứ ở dưới; phần không tìm thấy căn cứ được nêu rõ, không suy đoán. | same, and the missing part is named instead of guessed |
  | clarify | Cần làm rõ (blue) | Câu hỏi khớp nhiều thủ tục, hãy chọn một. | no answer given yet |
  | refuse | Từ chối và chuyển tuyến — *reason* (red) | per reason (below); legend and fallback: Không trả lời; lý do và nơi cần đến ghi dưới đây. | no answer given; reason and where to ask |
  | out_of_scope | Ngoài phạm vi (grey) | Trợ lý chỉ trả lời về thủ tục hành chính. | no answer given |

  Why "Trả lời có nguồn" and not "đầy đủ" (QC AUDIT-LEAD2-1): an answer is not guaranteed complete (a compound question can lose
  its second half with no gap line, case X3) and its narrative is model-written and checked, not copied; the label promises only what
  RELEASE §3 promises. The refuse meaning is reason-specific (`REFUSE_MEANING` in index.html): not_in_corpus "Thủ tục này không có trong
  kho dữ liệu, nên không liệt kê hồ sơ hay lệ phí; nơi tra cứu chính thức ghi dưới đây."; insufficient_evidence "Không đủ căn cứ trong
  dữ liệu để trả lời chắc chắn; điều còn thiếu và nơi hỏi ghi dưới đây."; discontinued "Thủ tục này đã dừng thực
  hiện; văn bản, ngày dừng và nơi hỏi ghi dưới đây."; system_error "Có lỗi kỹ thuật nên không trả lời; vui lòng hỏi lại hoặc tra cứu ở
  nơi ghi dưới đây.".
  The refusal reason comes from `refusal.reason` / `refusal.type`: *không có trong kho* (not_in_corpus), *không đủ căn cứ*
  (insufficient_evidence), *đã dừng thực hiện* (discontinued), *lỗi hệ thống* (system_error). The red redirect box shows the
  reason, the procedure (if one was resolved), `refusal.missing` (the declared missing elements), the agency and the portal link.
  It never shows `refusal.unsupported_claims` (internal: the draft sentences that failed the check); the backend does not even send it.
- **A legend** of the five labels sits above the question box (a collapsible `<details>`, open by default; the browser remembers if the
  user closes it).
- **Answer cards are summary-first** (answer and answer_partial; every intent, and in particular `general`, which shows all four
  properties): label → "Thủ tục: *title* (*mã*)" and the province → for a partial answer, the highlighted "Không tìm thấy căn cứ" box
  **before any detail** → one summary line ("Hồ sơ: 8 giấy tờ · Lệ phí: 3 dòng · Cơ quan: UBND cấp xã · Thời hạn: …") → one section per
  property; a list with more than 3 items starts collapsed with its count ("Thành phần hồ sơ — 8 giấy tờ (bấm để xem)"); each item is one
  line with its citation tag, and items longer than 110 characters are cut with a "xem đầy đủ" button → notices (change notices,
  freshness, sibling/variant notes) → the model's explanation ("Giải thích (đã kiểm từng câu)") → sources, collapsed with their count.
  Clarify, refuse and out_of_scope keep their (short) text as before, under the label.
- **No version names on the page** (owner's decision, 2026-10-10 evening: one current product): the selector reads *Trợ lý (có rào
  chắn)* / *Bản so sánh không rào chắn* and the card footer *Chế độ: …*; the preset still travels in the `/ask` JSON, the LangFuse tags
  and `GET /presets`, for tooling and the trace.

### Why

A correct answer can still be unreadable: the trace 372f0f393f65e191da8ed88c9a993a23 (answer_partial on 1.000689, intent general,
locality An Giang) printed seven long verbatim document items, three fee lines, a long processing-time line, notices and a narrative as
one wall of text. The reader could not tell what kind of result it was, how sure it was, or what was missing. The label answers the
first two in one line, the gap box answers the third before anything else, and the summary line gives the shape of the answer before
its detail. Nothing about the answer changes: the page only reorders and folds the same text.

### How

- `src/web/structure.py` (pure functions, no model, no rewriting) builds `parts` from the final state:
  `block_sections(state["block"])` splits the code-rendered block (render.render_block) at its headings ("Thành phần hồ sơ:", "Lệ phí …:",
  "Cơ quan tiếp nhận:", "Thời gian giải quyết: …") into `{kind, heading, items: [{text, cites}]}`; the narrative is `state["draft"]` minus
  the block (what survived check_support and prune_claims); the gap text, notices and notes are the paragraphs `finalize` appended,
  recognised by their fixed openings ("Không tìm thấy căn cứ về:", "Lưu ý:", "và …", "Thông tin trên …", "Việc bạn có đủ điều kiện …");
  the title is the resolved candidate's title (else `render.title_of`). Every string in `parts` is a substring of `generation`
  (tested), and `generation` itself is unchanged, so the CLI and the evaluation are unaffected.
- `/ask` returns `parts` beside `generation` (null for clarify / refuse / out_of_scope) and a wider `refusal` (`type`, `reason`,
  `missing`, `title`, `procedure_id`, `since`, `basis`, `agency`, `portal_url`).
- `index.html` renders the label from a fixed table (`OUTCOMES`), the legend from the same table, and the answer card from `parts`.
- Tests (`tests/test_web_app.py`): parts are lines of the generation and cover documents / agency / time; the partial's gap text comes
  first; non-answers have no parts and the refusal carries the reason fields but not `unsupported_claims`; the page carries the five
  labels, the four refusal reasons and the legend.

## 5. Procedures tab (added 2026-10-10)

### What

A second tab, **Thủ tục**, next to **Hỏi đáp** (the ask page, unchanged). Link straight to it with `http://127.0.0.1:8000/#thu-tuc`.

- One line at the top states the refusal policy: "Đây là toàn bộ thủ tục trợ lý có thể trả lời; câu hỏi ngoài danh sách này sẽ được từ
  chối và chuyển hướng."
- A text filter (matches title, code or agency; accents optional, so "khai tử" and "khai tu" both match) and a count "n / 57 thủ tục".
- The 57 procedures grouped by field (Hộ tịch 37 · Cấp, quản lý căn cước 9 · Đăng ký, quản lý cư trú 9) plus a group "Chỉ có trong quyết
  định của tỉnh Đắk Lắk" for the 2 procedures whose only source is the provincial decision. Each row: title, a red "đã dừng thực hiện"
  pill for a discontinued procedure (2.001178), code · agency, a quiet line with change-notice dates ("thay đổi gần nhất có hiệu lực …
  · sắp có hiệu lực …"), the "Nguồn chính thức" links (Bộ Tư pháp / Bộ Công an / QĐ UBND tỉnh Đắk Lắk), and a **Xem thêm** button.
- The groups are collapsible too: the tab opens with only the four group headers (name, count, chevron); a click opens a group's rows
  (built on first open, nothing fetched) and a second click closes it. While the filter has text, groups with matches open and show
  "matches / total" (e.g. "Hộ tịch (3 / 37)"), groups without a match close, and clearing the filter collapses all again (`groupState()`
  in index.html, tested under node).
- A group of more than 10 rows (today only Hộ tịch, 37) has a second collapsible level by procedure family, with the same
  behaviour (collapsed, "Khai sinh (12)", filter opens only matching sub-groups with "n / total"): `GET /procedures` returns each row's
  `family`, derived in `src/web/catalog.py:family_labels` from the resolver's own family-noun table (`src/families.py`,
  `data/family_nouns.json`, the head_noun_guard data), so the grouping is data, not a second rule; rows with no family noun go last
  under "Khác"; sub-groups are ordered by size, then name. If the API has no `family` (an older running server) the group stays flat.
- **Xem thêm** fetches that one procedure once and opens it under the row: thành phần hồ sơ, lệ phí, thời hạn giải quyết, nơi nộp / cơ
  quan tiếp nhận, căn cứ pháp lý, văn bản liên quan trong kho (title, kind, link, effective date). Every value has a "nguồn" link to the
  record it came from. Lists longer than 3 start collapsed with their count, as on the answer card. A second click closes the row.

### Why

The owner's rule after the answer-card lesson: **the page never shows more text than the person asked for**. The list is a map
(what exists, where its official page is), not a document; the values appear only for the row the person opens. The tab also makes the
refusal policy concrete: a question about a procedure that is not in this list will be refused and redirected (B4 in the runbook), and
the list shows what *would* be answered. Change-notice dates are shown as quiet text, not as badges, because 50 of the 57 procedures
have a notice in force and 39 are linked to the amended Luật Hộ tịch (in force 01/03/2027): a badge on every row would mean nothing.
Whether a notice is printed in an *answer* stays the graph's decision (`src/nodes.py:notice_applies`).

### How

- `src/web/catalog.py`: fixed SQL only, through the read-only connection of `src/tools/db.py` (`mode=ro`), no model call, no
  model-written SQL (R4). `procedure_list()` joins every source a procedure's rows cite (record, documents, fees, agencies), the
  discontinued table `data/procedure_status.yaml` (via `src/nodes.py:load_procedure_status`) and, per procedure, the newest change-notice
  date in force and the next upcoming one (no texts; about 27 KB for 57 rows). `procedure_detail(code)` returns documents, fees, deadline
  (`processing_time` with its own source), agencies, legal basis (the record's list, sourced to the record) and the linked depth
  documents, each value with its `source_url`.
- `src/web/app.py`: `GET /procedures` → `{count, procedures: [...]}`; `GET /procedures/{code}` → the detail, or 404.
- `index.html`: the list is fetched the first time the tab opens; each detail is fetched on the first "Xem thêm" and cached in the row.
- Tests (`tests/test_web_app.py`, real `data/app.db`, read-only): the list has 57 rows, each with at least one http source, compact (no
  section texts), the two notice dates, 2 Đắk Lắk-only rows, and 2.001178 flagged discontinued under NĐ 58/2026; the detail of 1.001193
  has a source for every value; an unknown code gives 404; the fake model records zero calls; the page carries the tab and the policy line.
