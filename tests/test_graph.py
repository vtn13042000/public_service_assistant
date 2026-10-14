"""Graph structure (node set, edge set) and reachability of every terminal on fakes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.graph import TERMINALS, export_mermaid  # noqa: E402
from tests.fakes import PROCEDURES, FakeDB, FakeLLM, FakeRAG, FakeWeb, make_app, need, run  # noqa: E402

NODES = {"assess_need", "resolve_procedure", "gather_evidence", "grade_relevance", "rewrite_query", "draft_answer",
         "check_support", "prune_claims", "freshness_check", "web_check", "web_lookup", "finalize", "clarify",
         "out_of_scope", "refuse_redirect"}
EDGES = {
    ("__start__", "assess_need"),
    ("assess_need", "resolve_procedure"), ("assess_need", "out_of_scope"), ("assess_need", "refuse_redirect"),
    ("resolve_procedure", "gather_evidence"), ("resolve_procedure", "clarify"), ("resolve_procedure", "web_lookup"),
    ("resolve_procedure", "refuse_redirect"),
    ("gather_evidence", "grade_relevance"),
    ("grade_relevance", "draft_answer"), ("grade_relevance", "rewrite_query"), ("grade_relevance", "refuse_redirect"),
    ("rewrite_query", "gather_evidence"),
    ("draft_answer", "check_support"),
    ("check_support", "freshness_check"), ("check_support", "prune_claims"), ("check_support", "rewrite_query"),
    ("check_support", "refuse_redirect"),
    ("prune_claims", "freshness_check"),
    ("freshness_check", "web_check"), ("freshness_check", "finalize"), ("freshness_check", "refuse_redirect"),
    ("web_check", "finalize"),
    ("web_lookup", "refuse_redirect"),
    ("finalize", "__end__"), ("clarify", "__end__"), ("refuse_redirect", "__end__"), ("out_of_scope", "__end__"),
}


def drawn():
    app, _ = make_app()
    return app.get_graph()


def test_node_set():
    assert set(drawn().nodes) - {"__start__", "__end__"} == NODES


def test_edge_set():
    assert {(e.source, e.target) for e in drawn().edges} == EDGES


def test_conditional_edges_marked():
    cond = {(e.source, e.target) for e in drawn().edges if e.conditional}
    assert {s for s, _ in cond} == {"assess_need", "resolve_procedure", "grade_relevance", "check_support", "freshness_check"}


def test_rewrite_is_the_only_loop_and_bounded():
    s, _ = run("Các bước khai sinh?", FakeLLM(need=need("steps", "đăng ký khai sinh trong nước"), relevance=False))
    assert s["iteration"] == 1 and s["outcome"] == "refuse"


def paths():
    """One scenario per terminal (and per refusal type)."""
    kn = "Đăng ký khai sinh trong nước lần đầu cần giấy tờ gì?"
    return {
        "finalize": run(kn, FakeLLM(need=need("documents", "đăng ký khai sinh trong nước lần đầu"))),
        "clarify": run("Hồ sơ đăng ký khai sinh?", FakeLLM(need=need("documents", "đăng ký khai sinh"))),
        "out_of_scope": run("Xin chào", FakeLLM(need=need(in_scope=False))),
        "not_in_corpus": run("Nhập tịch?", FakeLLM(need=need("general", "nhập quốc tịch"))),
        "insufficient": run("Các bước?", FakeLLM(need=need("steps", "đăng ký khai sinh trong nước lần đầu"), support="no",
                                                  narrative="Nộp tờ khai [doc:KS-01:steps:0].")),
        "partial_missing": run(kn, FakeLLM(need=need("documents", "đăng ký khai sinh trong nước lần đầu"), relevance=False),
                               db=FakeDB(procedures={"KS-01": {**PROCEDURES["KS-01"], "docs": []}}),
                               init={"procedure_id": "KS-01"}),
        "system_error": run(kn, FakeLLM(need=need("documents", "đăng ký khai sinh trong nước lần đầu")),
                            rag=FakeRAG(fail=True)),
    }


def test_every_terminal_reachable():
    p = paths()
    assert p["finalize"][0]["outcome"] == "answer"
    assert p["clarify"][0]["outcome"] == "clarify"
    assert p["out_of_scope"][0]["outcome"] == "out_of_scope"
    for k, rtype in (("not_in_corpus", "not_in_corpus"), ("insufficient", "insufficient_evidence"),
                     ("system_error", "system_error")):
        s = p[k][0]
        assert s["outcome"] == "refuse" and s["refusal"]["type"] == rtype, (k, s.get("refusal"), s.get("errors"))
    s = p["partial_missing"][0]  # asked-for element missing → declared gap + agency as next step
    assert s["outcome"] == "answer_partial" and "Không tìm thấy căn cứ về: thành phần hồ sơ" in s["generation"]
    assert "UBND cấp xã nơi cư trú của cha hoặc mẹ" in s["generation"]
    assert {"finalize", "clarify", "refuse_redirect", "out_of_scope"} == set(TERMINALS)


def test_every_outcome_has_generation_and_next_step():
    for name, (s, _) in paths().items():
        assert s["generation"].strip(), name
        if s["outcome"] != "answer":
            assert "dichvucong.gov.vn" in s["generation"] or "chọn" in s["generation"], name


def test_export_mermaid(tmp_path):
    app, _ = make_app()
    text = export_mermaid(app, tmp_path / "g.mmd")
    assert "assess_need" in text and "refuse_redirect" in text and (tmp_path / "g.mmd").exists()


def test_web_tool_called_only_on_lookup_and_check():
    s, parts = run("Nhập tịch?", FakeLLM(need=need("general", "nhập quốc tịch")), web=FakeWeb())
    assert len(parts["web"].queries) == 1


# ---------------- baseline (professor's skeleton) — same signature, skeleton behaviours kept

def _baseline_llm(supported: str):
    def reply(prompt):
        if prompt.startswith("Cho NGỮ CẢNH"):
            return '{"relevant": true, "supported": "%s"}' % supported
        return "Hồ sơ gồm tờ khai và sổ hộ khẩu."
    return FakeLLM(narrative=reply)


def test_baseline_same_signature_and_skeleton_nodes():
    from src.baseline import build_graph as bl
    app = bl(_baseline_llm("fully"), FakeRAG(), FakeDB(), FakeWeb(), None)
    assert set(app.get_graph().nodes) - {"__start__", "__end__"} == {
        "router", "retrieve", "query_db", "web_search", "grade", "generate", "gate", "finalize"}


def test_baseline_supported_answers_without_citation_checks():
    from src.baseline import build_graph as bl
    s = bl(_baseline_llm("fully"), FakeRAG(), FakeDB(), FakeWeb()).invoke({"query": "Các bước khai sinh?"})
    assert s["outcome"] == "answer" and "sổ hộ khẩu" in s["generation"]  # invented item passes (F1)


def test_baseline_exhaustion_forces_generate_then_static_gate():
    from src.baseline import build_graph as bl
    llm = _baseline_llm("partial")
    s = bl(llm, FakeRAG(), FakeDB(), FakeWeb()).invoke({"query": "Các bước khai sinh?"})
    assert s["iteration"] == 2 and s["outcome"] == "refuse"
    assert s["generation"].startswith("Chưa đủ căn cứ trong kho thủ tục")  # static, no agency (F8)
    s2 = bl(llm, FakeRAG(), FakeDB(), FakeWeb(), config={"gate": False}).invoke({"query": "Các bước khai sinh?"})
    assert s2["outcome"] == "answer"  # pure A6: forced generation reaches the user


def test_baseline_db_path_bypasses_reflection():
    from src.baseline import build_graph as bl
    llm = _baseline_llm("no")
    s = bl(llm, FakeRAG(), FakeDB(), FakeWeb()).invoke({"query": "Lệ phí cấp lại thẻ căn cước?"})
    assert s["route"] == "data" and s["outcome"] == "answer"
    assert not any(p.startswith("Cho NGỮ CẢNH") for _, p in llm.prompts)


# ---------------- eval ablations (config={"ablation": ...})

def test_ablations_compile_with_same_graph():
    for ab in ("no_resolve", "llm_support"):
        app, _ = make_app(config={"ablation": ab})
        assert set(app.get_graph().nodes) - {"__start__", "__end__"} == NODES


def test_unknown_ablation_rejected():
    import pytest
    with pytest.raises(ValueError):
        make_app(config={"ablation": "nope"})


def test_ablation_no_resolve_trusts_rank1_and_unfiltered_retrieval():
    llm = FakeLLM(need=need("documents", "đăng ký khai sinh"))
    s, _ = run("Hồ sơ đăng ký khai sinh?", llm, rag=FakeRAG(order=["KS-02", "KS-01", "KS-03"]),
               config={"ablation": "no_resolve"})
    assert s["procedure_id"] == "KS-02" and s["outcome"] != "clarify"   # sibling blending risk is now live
    s_full, _ = run("Hồ sơ đăng ký khai sinh?", llm, rag=FakeRAG(order=["KS-02", "KS-01", "KS-03"]))
    assert s_full["outcome"] == "clarify"
    s2, parts = run("Các bước?", FakeLLM(need=need("steps", "khai sinh có yếu tố nước ngoài")),
                    config={"ablation": "no_resolve"})
    assert len({e["procedure_id"] for e in s2["documents"]} | {"KS-02"}) > 1 or len(
        {e["procedure_id"] for e in s2["evidence"] if e["tier"] == "corpus"}) > 1


def test_ablation_llm_support_lets_wrong_db_claim_through_when_llm_agrees():
    narr = "Đúng, lệ phí là 50.000 đồng [db:fees:KS-01:1]."
    llm = FakeLLM(need=need("fee", "đăng ký khai sinh trong nước lần đầu", premise="lệ phí là 50.000đ"),
                  narrative=narr, support="fully")
    s_full, _ = run("q", llm)
    assert "50.000 đồng" not in s_full["generation"]
    s_ab, _ = run("q", llm, config={"ablation": "llm_support"})
    assert s_ab["outcome"] == "answer" and "50.000 đồng" in s_ab["generation"]
    assert all("LLM only" in c["reason"] for c in s_ab["claims"])


# ---------------- ROUND-2 item 5: story_rewrite (P22), default off

STORY = "Cháu mới chào đời tuần trước, giờ tôi cần làm giấy gì cho cháu?"


def test_story_rewrite_off_by_default_no_extra_call():
    llm = FakeLLM(need=need("documents", "giấy tờ cho cháu mới chào đời"), story="Đăng ký khai sinh")
    s, _ = run(STORY, llm)
    assert s["outcome"] == "refuse" and s["refusal"]["type"] == "not_in_corpus"
    assert not any(k == "story" for k, _ in llm.prompts)


def test_story_rewrite_names_procedure_then_same_floor_applies():
    llm = FakeLLM(need=need("fee", "giấy tờ cho cháu mới chào đời"), story="Đăng ký khai sinh")
    s, parts = run(STORY, llm, config={"story_rewrite": True})
    assert [k for k, _ in llm.prompts].count("story") == 1
    assert s["route"] == "one" and s["procedure_id"] == "KS-01"
    meta = next(m for n, m in parts["trace"] if n == "resolve_procedure")
    assert meta["story_rewrite"] == "Đăng ký khai sinh"


def test_story_rewrite_invented_or_empty_name_keeps_not_in_corpus():
    for name in ("Nhập quốc tịch Việt Nam", ""):
        llm = FakeLLM(need=need("general", "nhập quốc tịch"), story=name)
        s, _ = run("Tôi là người nước ngoài muốn thành công dân Việt Nam?", llm, config={"story_rewrite": True})
        assert s["refusal"]["type"] == "not_in_corpus", name


def test_story_rewrite_parse_failure_is_not_an_error():
    llm = FakeLLM(need=need("documents", "giấy tờ cho cháu mới chào đời"), bad_json={"story"})
    s, _ = run(STORY, llm, config={"story_rewrite": True})
    assert s["refusal"]["type"] == "not_in_corpus" and not s.get("errors")


# ---------------- ROUND-2 item 8: citation_parse

def test_citation_parse_strict_default_and_tolerant_rescues_spacing_variant():
    import pytest
    from src.nodes import CITATION_PARSE
    narr = "Người đi đăng ký nộp tờ khai và giấy chứng sinh [ DOC : KS-01:steps:0 ]."
    mk = lambda: FakeLLM(need=need("steps", "đăng ký khai sinh trong nước lần đầu"), narrative=narr, support="fully")
    s_default, _ = run("Các bước đăng ký khai sinh?", mk())
    s_strict, _ = run("Các bước đăng ký khai sinh?", mk(), config={"citation_parse": "strict"})
    s_tol, _ = run("Các bước đăng ký khai sinh?", mk(), config={"citation_parse": "tolerant"})
    assert s_strict["outcome"] == "refuse"  # the spaced id is not a citation → no supported step
    assert s_default["outcome"] == (s_tol if CITATION_PARSE == "tolerant" else s_strict)["outcome"]
    assert s_tol["outcome"] == "answer" and "[doc:KS-01:steps:0]" in s_tol["generation"]
    with pytest.raises(ValueError):
        run("q", FakeLLM(), config={"citation_parse": "loose"})


def test_citation_parse_tolerant_never_accepts_an_id_not_in_state():
    narr = "Người đi đăng ký nộp tờ khai [doc:KS-01:steps:7]."
    s, _ = run("Các bước đăng ký khai sinh?", FakeLLM(need=need("steps", "đăng ký khai sinh trong nước lần đầu"),
                                                     narrative=narr, support="fully"),
               config={"citation_parse": "tolerant"})
    assert s["outcome"] == "refuse" and "doc:KS-01:steps:7" not in (s.get("generation") or "")


# ---------------- ROUND-4: change-notice freshness and discontinued procedures (code rules, no flag)

class _NoticeDB(FakeDB):
    def get_change_notices(self, pid):
        if pid != "KS-01":
            return []
        return [{"doc_id": "change:test:old", "title": "Thông tư 99/2026/TT-BTP", "effective_date": "2026-07-01",
                 "url": "https://moj.gov.vn/tt-99-2026"},
                {"doc_id": "change:test:future", "title": "Nghị định 999/2030/NĐ-CP", "effective_date": "2030-01-01",
                 "url": "https://chinhphu.vn/nd-999-2030"}]


def test_change_notice_in_force_adds_a_notice_with_title_date_and_url():
    from datetime import date
    s, parts = run("Đăng ký khai sinh nộp ở đâu?", FakeLLM(need=need("agency", "đăng ký khai sinh")), db=_NoticeDB(),
                   today=date(2026, 10, 10))
    assert s["outcome"] in ("answer", "answer_partial")
    assert "change_notice" in s["freshness"]["reasons"]
    assert [n["doc_id"] for n in s["freshness"]["change_notices"]] == ["change:test:old"]  # the future one is not in force
    assert ("Lưu ý: thủ tục này có thay đổi theo «Thông tư 99/2026/TT-BTP», hiệu lực 01/07/2026; "
            "vui lòng kiểm tra lại trước khi nộp hồ sơ. Nguồn: https://moj.gov.vn/tt-99-2026") in s["generation"]
    assert "Nghị định 999/2030" not in s["generation"]
    assert any(n == "web_check" for n, _ in parts["trace"])  # the existing web path still runs


def test_no_change_notice_query_means_no_change_notice():
    from datetime import date
    s, _ = run("Đăng ký khai sinh nộp ở đâu?", FakeLLM(need=need("agency", "đăng ký khai sinh")), today=date(2026, 10, 10))
    assert s["freshness"]["change_notices"] == [] and "change_notice" not in s["freshness"]["reasons"]


STOPPED = {"KS-01": {"status": "discontinued", "since": "2026-03-15", "basis": "Nghị định 58/2026/NĐ-CP",
                     "notice_url": "https://bocongan.gov.vn/x", "redirect": "Dùng thẻ căn cước hoặc VNeID."}}


def test_discontinued_procedure_is_refused_with_the_stop_sentence_and_no_drafting():
    llm = FakeLLM(need=need("documents", "đăng ký khai sinh trong nước"))
    s, _ = run("Hồ sơ đăng ký khai sinh trong nước gồm những gì?", llm, config={"procedure_status": STOPPED})
    assert s["outcome"] == "refuse" and s["procedure_id"] == "KS-01"
    r = s["refusal"]
    assert r["type"] == "not_in_corpus" and r["reason"] == "discontinued" and r["since"] == "2026-03-15"
    assert "Thủ tục này đã dừng thực hiện từ 15/03/2026 theo Nghị định 58/2026/NĐ-CP." in s["generation"]
    assert "Dùng thẻ căn cước hoặc VNeID." in s["generation"] and r["agency"]
    assert [k for k, _ in llm.prompts] == ["need"]  # no relevance grading, no draft, no judge


def test_discontinued_procedure_refused_after_a_clarify_follow_up_too():
    s, _ = run("Hồ sơ?", FakeLLM(need=need("documents", "đăng ký khai sinh")), init={"procedure_id": "KS-01"},
               config={"procedure_status": STOPPED})
    assert s["outcome"] == "refuse" and s["refusal"]["reason"] == "discontinued"


def test_finalize_never_answers_a_discontinued_procedure():
    from src.nodes import final_safety_violations
    assert "discontinued procedure" in final_safety_violations({"discontinued": STOPPED["KS-01"]})


def test_procedure_status_file_lists_the_stopped_cmnd_confirmation():
    from src.nodes import load_procedure_status
    st = load_procedure_status()
    assert st["2.001178"]["since"] == "2026-03-15" and "58/2026" in st["2.001178"]["basis"]
    assert load_procedure_status("/nonexistent.yaml") == {}


def test_notice_applies_only_when_newer_than_the_record():
    from datetime import date
    from src.nodes import notice_applies
    today = date(2026, 10, 10)
    n = lambda d, t="Thông báo": {"title": t, "url": "u", "effective_date": d}  # noqa: E731
    assert notice_applies(n("2026-03-15"), today, None)                       # no source date: within 365 days
    assert not notice_applies(n("2025-07-01"), today, None)                   # older than the window
    assert not notice_applies(n("2027-03-01"), today, None)                   # not yet in force
    assert not notice_applies(n(None), today, None)                           # undated: cannot be placed
    assert notice_applies(n("2026-03-15"), today, date(2026, 1, 8))           # newer than the record's source date
    assert not notice_applies(n("2025-12-01"), today, date(2026, 1, 8))
    assert not notice_applies(n("2026-03-15", "Nghị định 58/2026/NĐ-CP"), today, None,
                              "Căn cứ pháp lý: Nghị định số 58/2026/NĐ-CP ngày 13/02/2026")  # record already cites it


class _ManyNoticeDB(FakeDB):
    def get_change_notices(self, pid):
        return [{"doc_id": f"change:{i}", "title": f"Văn bản {i}", "effective_date": f"2026-0{i}-01", "url": f"https://x/{i}"}
                for i in range(1, 5)]


def test_at_most_two_notices_are_printed_then_a_count():
    from datetime import date
    s, _ = run("Đăng ký khai sinh nộp ở đâu?", FakeLLM(need=need("agency", "đăng ký khai sinh")), db=_ManyNoticeDB(),
               today=date(2026, 10, 10))
    g = s["generation"]
    assert "«Văn bản 4», hiệu lực 01/04/2026" in g and "«Văn bản 3»" in g and "«Văn bản 2»" not in g
    assert "và 2 văn bản khác (xem nguồn)." in g


# ---------------- Round-4 item (c): scope_gate (flag, default off)

GATE = {"scope_gate": "in_scope"}


def test_scope_gate_off_keeps_v3_routing():
    s, _ = run("Hồ sơ đăng ký khai sinh?", FakeLLM(need=need("documents", "", retrieve=False)))
    assert s["outcome"] == "out_of_scope"


def test_scope_gate_opens_an_in_scope_question_with_retrieve_false():
    s, parts = run("Hồ sơ đăng ký khai sinh trong nước?", FakeLLM(need=need("documents", "", retrieve=False)), config=GATE)
    assert s["outcome"] != "out_of_scope" and s["procedure_id"] == "KS-01"  # empty hint → the question itself
    assert next(m for n, m in parts["trace"] if n == "assess_need")["scope_gate"] == "opened"


def test_scope_gate_floor_still_refuses_what_is_not_in_the_corpus():
    s, _ = run("Thủ tục nhập tịch cho người nước ngoài?", FakeLLM(need=need("general", "", retrieve=False)), config=GATE)
    assert s["outcome"] == "refuse" and s["refusal"]["type"] == "not_in_corpus"


def test_scope_gate_keeps_eligibility_questions_out_of_scope():
    for q in ("Tôi ở nhà bạn trai 2 năm rồi, tôi có đủ điều kiện đăng ký thường trú ở đó không?",
              "em có đk tạm trú được ko hay là bị từ chối"):
        s, parts = run(q, FakeLLM(need=need("general", "", retrieve=False)), config=GATE)
        assert s["outcome"] == "out_of_scope", q
        assert next(m for n, m in parts["trace"] if n == "assess_need")["scope_gate"] == "kept_eligibility"


def test_scope_gate_never_opens_an_out_of_scope_classification():
    s, _ = run("Thời tiết hôm nay thế nào?", FakeLLM(need=need("general", "", in_scope=False, retrieve=False)), config=GATE)
    assert s["outcome"] == "out_of_scope"


def test_scope_gate_validated():
    import pytest
    from src.nodes import Deps
    with pytest.raises(ValueError):
        Deps(llm=FakeLLM(), rag=FakeRAG(), db=FakeDB(), config={"scope_gate": "all"})


def test_coverage_folds_leading_zeros_only_when_asked():
    from src.nodes import coverage
    t = "Cấp xác nhận số chứng minh nhân dân 09 số"
    assert coverage("xác nhận số chứng minh 9 số", t) < coverage("xác nhận số chứng minh 9 số", t, zeros=True) == 1.0
    assert coverage("xác nhận 90", t, zeros=True) < 1.0  # "90" is not "09"


def test_citation_repair_flag_validated_and_recorded():
    import pytest
    from src.nodes import Deps
    with pytest.raises(ValueError):
        Deps(llm=FakeLLM(), rag=FakeRAG(), db=FakeDB(), config={"citation_repair": "any"})
    _, parts = run("Các bước đăng ký khai sinh?", FakeLLM(need=need("steps", "đăng ký khai sinh")),
                   config={"citation_parse": "tolerant", "citation_repair": "tier"})
    meta = next(m for n, m in parts["trace"] if n == "draft_answer")
    assert meta["citation_repair"] == "tier" and meta["repaired_citations"] == []


# ---------------- owner trace c26ce7e90e7c4f055b314ddcb23dc749: refusal wording (no flag)

X6_QUERY = "đăng ký khai sinh để điền tên cha có cần phải có giấy kết hôn để chứng minh quan hệ không"


def _x6_state():
    from src.evidence import make_evidence
    agency = make_evidence("db:agencies:1.000894:1", "db", "Cơ quan thực hiện: UBND cấp xã", procedure_id="1.000894",
                           section="agency", structured={"name": "UBND cấp xã"}, source_url="https://moj.gov.vn/x",
                           retrieved_at="2026-10-10")
    title = make_evidence("db:procedures:1.000894:summary", "db", "Thủ tục: Thủ tục đăng ký kết hôn (mã 1.000894).",
                          procedure_id="1.000894", section="summary", structured={"title": "Thủ tục đăng ký kết hôn"})
    claim = {"type": "core", "verdict": "unsupported", "origin": "draft", "evidence_ids": ["db:required_documents:1.000894:2"],
             "text": "Không. Tờ khai đăng ký kết hôn là thành phần duy nhất trong danh sách quy định để chứng minh quan hệ giữa hai bên."}
    return {"query": X6_QUERY, "procedure_id": "1.000894", "evidence": [title, agency], "claims": [claim], "gaps": [],
            "need": {"intent": "documents", "procedure_hint": "đăng ký khai sinh điền tên cha cần giấy kết hôn để chứng minh quan hệ không",
                     "premise": "lệ phí đăng ký khai sinh là 50.000đ"}}


def test_insufficient_evidence_restates_the_question_never_a_draft_claim():
    from src.nodes import refusal_type
    from src.refusal import build_refusal
    st = _x6_state()
    rtype, missing, note = refusal_type(st)
    text, ref = build_refusal(st, rtype, missing=missing, note=note)
    assert rtype == "insufficient_evidence" and missing == ["thành phần hồ sơ"]
    assert f"để trả lời câu hỏi: «{X6_QUERY}»" in text
    assert "Tờ khai đăng ký kết hôn là thành phần duy nhất" not in text and "Tờ khai" not in " ".join(ref["missing"])
    assert ref["unsupported_claims"] and ref["unsupported_claims"][0].startswith("Không. Tờ khai")
    # the chosen title lacks the family the user named first (khai sinh) → "gần nhất", plus the ask-again line
    assert "Thủ tục gần nhất tìm được: Thủ tục đăng ký kết hôn." in text and "Thủ tục đã xác định" not in text
    assert "Nếu bạn hỏi về thủ tục khác, hãy nêu rõ tên thủ tục." in text


def test_insufficient_evidence_keeps_da_xac_dinh_when_the_family_matches():
    from src.refusal import build_refusal
    st = {**_x6_state(), "need": {"intent": "documents", "procedure_hint": "đăng ký kết hôn"}, "query": "Đăng ký kết hôn cần gì?"}
    text, _ = build_refusal(st, "insufficient_evidence", missing=["thành phần hồ sơ"])
    assert "Thủ tục đã xác định: Thủ tục đăng ký kết hôn." in text and "gần nhất" not in text


def test_premise_post_check_drops_a_premise_with_a_number_the_question_lacks():
    from src.nodes import premise_invented
    assert premise_invented("lệ phí đăng ký khai sinh là 50.000đ", X6_QUERY)
    assert not premise_invented("lệ phí là 50.000đ", "Lệ phí khai sinh là 50.000 đồng phải không?")
    assert not premise_invented("Lệ phí đăng ký kết hôn ở xã là 100.000đ", "Lệ phí đăng ký kết hôn ở xã là 100.000đ phải không?")
    assert not premise_invented("nộp ở Phòng Tư pháp huyện", "Nộp ở Phòng Tư pháp huyện đúng không?")  # no number: kept
    llm = FakeLLM(need=need("documents", "đăng ký khai sinh", premise="lệ phí đăng ký khai sinh là 50.000đ"))
    s, parts = run(X6_QUERY, llm)
    assert s["need"]["premise"] is None
    assert next(m for n, m in parts["trace"] if n == "assess_need")["premise_dropped"] == "lệ phí đăng ký khai sinh là 50.000đ"
    q = "Lệ phí đăng ký khai sinh là 50.000đ phải không?"  # a premise the user did assert is kept
    s, _ = run(q, FakeLLM(need=need("fee", "đăng ký khai sinh", premise="lệ phí đăng ký khai sinh là 50.000đ")))
    assert s["need"]["premise"] == "lệ phí đăng ký khai sinh là 50.000đ"


def test_refusal_always_names_the_asked_part_for_every_intent():
    from src.nodes import refusal_type
    from src.refusal import build_refusal
    want = {"steps": "trình tự thực hiện", "general": "thông tin chung về thủ tục", "update": "thông tin cập nhật của thủ tục",
            "documents": "thành phần hồ sơ", "fee": "lệ phí", "agency": "cơ quan tiếp nhận", "time": "thời gian giải quyết"}
    for intent, element in want.items():
        st = {**_x6_state(), "need": {"intent": intent, "procedure_hint": "đăng ký kết hôn"}}
        rtype, missing, _ = refusal_type(st)
        text, _ = build_refusal(st, rtype, missing=missing)
        assert missing == [element] and f"Phần chưa có căn cứ: {element}." in text, intent
