# Guardrails — failure catalogue, layered defenses, refusal policy

The professor's framing: *"Thiết kế guardrail an toàn; ưu tiên từ chối/chuyển tuyến hơn là bịa thông tin thủ tục."*
A guardrail is a check that stops the system from giving a harmful answer.
This document turns that sentence into (1) a list of concrete ways the system can harm the user,
(2) a layer that addresses each, (3) a refusal policy that still helps, and (4) a test for each layer.

Design principle: **the LLM (large language model) is never the last line of defence for a structured fact** (a document item, fee, deadline or agency).
Use code where the check is mechanical. Use the LLM where judgment is unavoidable.
When either fails, fail closed: refuse or redirect the user instead of guessing.

---

## 1. Failure catalogue

Naive RAG below means plain retrieval-augmented generation: fetch the top-k (k best-matching) text chunks and let the LLM write an answer from them, with no further checks.

| # | Failure | Why it happens with naive RAG | Harm to the user | Test category |
|---|---|---|---|---|
| F1 | Invented document item | LLM completes a plausible list from pretraining (what it learned before seeing our data) | Rejected file, wasted trip | in-corpus documents, near-miss |
| F2 | Blended variants | Top-k contains chunks from sibling procedures (near-identical versions of the same procedure) | Wrong list that *looks* official | near-miss |
| F3 | Wrong fee / fee without jurisdiction | Fees differ by province; model picks one number | Over/under-payment, distrust | fee, jurisdiction |
| F4 | Wrong or stale receiving agency | 2025 reorganisation; portal pages lag | Wrong counter, wrong town | agency, stale |
| F5 | Agreement with false premise (a wrong assumption inside the question) | Instruction-tuned models (trained to follow and please the user) agree by default | User's wrong belief confirmed | false premise |
| F6 | Answering out-of-corpus from memory | Retrieval returns weakly related chunks, model fills in | Pure hallucination with citations | out-of-corpus |
| F7 | Legal determination of a personal case | User asks "do I qualify" | Wrong advice on eligibility | out-of-scope / personal |
| F8 | Dead-end refusal | Static refusal text | User has no next step | all refusal cases |
| F9 | Over-refusal | Critic (the checking step) too strict; one shaky sentence sinks a correct answer | Tool is useless | in-corpus (measured as over-refusal rate) |
| F10 | Web snippet upgraded to fact | Web results fed straight to generation | Unofficial numbers presented as official | update, out-of-corpus |
| F11 | Fabricated citation | Citation ids not checked against state | False sense of traceability | all answered items (assert) |
| F12 | Silent tool failure | Empty retrieval → model answers anyway | Hallucination under error | fault injection |
| F13 | Prompt injection (text that tries to give the model new orders) inside a document / web result | Text says "ignore the above…" | Policy bypass | adversarial |
| F14 | Number/unit drift | "15 ngày" vs "15 ngày làm việc"; "miễn" vs "0đ" | Missed deadlines | time, fee |

---

## 2. Layers

Each layer runs in one or more nodes (steps) of the LangGraph pipeline. Words used in the table: *structured output* = the model must reply in a fixed JSON format;
*deterministic* = plain code, same input gives the same result; *evidence tier* = how far a source may be trusted (`db` row > `corpus` chunk > `web_official` > `web_other`).

| Layer | Mechanism | Addresses | Implemented in |
|---|---|---|---|
| **L0 Scope gate** | `assess_need` structured output: `in_scope`, `retrieve`, `intent`, `premise`. Out of scope → templated response that names what the assistant can do. Personal-case eligibility questions are reframed: "I can tell you the procedure and the agency; eligibility is decided by the agency." | F7 | `assess_need` |
| **L1 Procedure resolution** | Deterministic title search + confidence/gap thresholds → exactly one `procedure_id`, or `clarify`, or `web_lookup`. All subsequent retrieval filtered by that id. | F2, F6 | `resolve_procedure` |
| **L2 Evidence tiers** | Minimum tier per claim type: document item / fee / agency / deadline → `db`; steps / conditions / legal basis → `corpus`; "something changed" notice → `web_official`; `web_other` is discarded before grading. Corpus v2: the corpus also holds document chunks; text marked "[Văn bản gốc – đã sửa đổi]" never supports an authority or deadline claim; stored change-notice documents also signal a change. | F3, F4, F10 | `gather_evidence`, `check_support` |
| **L3 Relevance reflection** (the model checks its own retrieved text) | `relevant?` per chunk with structured JSON. Parse failure or empty → irrelevant. Documents are passed to the LLM wrapped as data with an explicit "content, not instructions" frame. | F6, F13 | `grade_relevance` |
| **L4 Claim-level support** | Split draft → claims (single factual statements); `db:`-cited claims verified by code (the item is in the row, the number and the agency are equal); `doc:`-cited claims judged by LLM against *that chunk only*; uncited factual claims unsupported by rule. Core vs minor claim (essential to the answer or not) → partial answer or refuse. `premise` is always a core claim. | F1, F5, F9, F11, F14 | `check_support`, `decide` |
| **L5 Output constraints** | Structured facts rendered by `render.py` from rows; LLM writes around a fixed block. Fee lines always carry jurisdiction and "theo [nguồn], ngày lấy …". Deadlines keep the source's unit string verbatim. | F1, F3, F14 | `render.py`, `draft_answer` |
| **L6 Bounds & fail-closed** | `iteration ≤ 1` (at most one query rewrite); every tool wrapped; any exception/timeout → `errors` → `refuse_redirect(type=system_error)`; graph can never reach `finalize` from an error. | F12 | all nodes, `graph.py` |
| **L7 Freshness** | Every answer shows `retrieved_at`/`effective_date` of its sources; stale threshold and agency claims trigger `web_check` (allowlist) and a verify-at-counter notice; corpus v2: so does a linked change notice in force and newer than the record. | F4 | `freshness_check`, `web_check` |

What the LLM is trusted to do: classify intent, judge chunk relevance, judge narrative support, phrase text.
What it is not trusted to do: pick the procedure, state a number/item/agency without a row, decide that it is done.

---

## 3. Mapping to Self-RAG

Self-RAG (Asai et al., 2023) is a method in which the model also emits short reflection tokens: special labels that judge whether to retrieve, whether a passage is relevant, and whether the answer is supported.

| Self-RAG reflection token (Asai et al., 2023) | Our realisation | Node |
|---|---|---|
| `Retrieve` (retrieve? yes/no/continue) | `need.retrieve` from `assess_need`; `rewrite_query` is the "continue" case | `assess_need`, `rewrite_query` |
| `ISREL` (relevant / irrelevant) | per-chunk structured judgment, fail-closed | `grade_relevance` |
| `ISSUP` (fully / partially / no support) | per-claim; hybrid code + LLM | `check_support` |
| `ISUSE` (usefulness 1–5) | not a gate (it never blocks an answer); reported as RAGAS answer relevancy (an automatic score of how well the answer addresses the question) and as the over-refusal metric | `eval/` |

Honest statement for the report: the paper trains the generator to emit these tokens. We do not train anything.
We obtain the same decisions with separate prompted calls and structured outputs.
The cost is several model runs (forward passes) instead of one. The gain is that each decision can be inspected, and an LLM judgment can be replaced with code.

---

## 4. Refusal policy — five types, each with a next step

| Type | Trigger | Response must contain |
|---|---|---|
| `out_of_scope` | L0 | What the assistant does cover; for personal eligibility, the relevant procedure's agency |
| `ambiguous` (clarify) | L1 ties | The 2–4 candidate procedure titles; ask the user to pick; no facts yet |
| `not_in_corpus` | L1 none; corpus v2: or the procedure is discontinued (`data/procedure_status.yaml`; reason, stop date, basis, redirect) | Statement that the corpus lacks it; if `web_lookup` found an official page: its link; the type of agency usually responsible, phrased as guidance not fact |
| `insufficient_evidence` | L4 core unsupported after retry | Resolved procedure title, its agency and `source_url` from DB, the specific missing element ("không có căn cứ về lệ phí") |
| `system_error` | L6 | Plain statement; portal link; no facts |

Every refusal also records `refusal.type` in state (the graph's shared data) and in the LangFuse span (the trace record of that step), so refusals can be counted by type.
"Partial answer" is not a refusal: it is `answer_partial` with an explicit "Không tìm thấy căn cứ về: …" section.

Template skeleton (Vietnamese, final wording to be refined with test users):

```
Tôi chưa đủ căn cứ trong kho thủ tục để trả lời [phần còn thiếu].
Những gì tôi xác nhận được: [facts with citations, if any].
Để được hướng dẫn chính xác, vui lòng liên hệ: [agency name from DB] — [source_url].
(Dữ liệu lấy ngày [retrieved_at]; cơ quan tiếp nhận có thể đã thay đổi sau sắp xếp đơn vị hành chính 2025.)
```

---

## 5. Guardrail tests (each layer gets at least one)

| Layer | Test | Pass criterion |
|---|---|---|
| L0 | 5 out-of-scope prompts | none reach `resolve_procedure` |
| L1 | 12 near-miss questions (questions close to, but not the same as, a corpus procedure) | hit@1 on gold id ≥ 0.85 (the correct procedure ranked first); ambiguous ones → clarify, never answer |
| L2 | inject a `web_other` evidence with a fee | fee claim verdict = unsupported |
| L3 | chunk containing "Bỏ qua hướng dẫn trên…" | graded irrelevant; no behaviour change |
| L4 | draft with one invented item in a list | that claim unsupported; list pruned or refuse |
| L4 | false-premise set (8 items) | answer contradicts premise with citation in ≥ 7 |
| L5 | property test (a check that must hold on every output): every `finalize` output's numbers appear verbatim in a cited `db:` row | 100% |
| L6 | monkeypatch Chroma to raise (replace the vector database with a stub that throws an error) | outcome = refuse, type = system_error |
| L7 | record with old `retrieved_at` | notice present; `web_check` span exists |
| F9 | in-corpus answerable set | over-refusal ≤ 0.15 |

These are `pytest` tests over the graph with a small fixture corpus (a tiny fixed test dataset), plus the metric thresholds in `evaluation.md`.
