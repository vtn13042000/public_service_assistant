"""Each edge function of graph.py on fixture states (architecture.md §4)."""
import sys
from pathlib import Path

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import graph as G  # noqa: E402
from src.nodes import RESOLVE, choose  # noqa: E402

ERR = {"errors": ["x: boom"]}


@pytest.mark.parametrize("state,label", [
    ({"need": {"in_scope": True, "retrieve": True}}, "resolve_procedure"),
    ({"need": {"in_scope": False, "retrieve": True}}, "out_of_scope"),
    ({"need": {"in_scope": True, "retrieve": False}}, "out_of_scope"),
    ({}, "out_of_scope"),
    ({**ERR, "need": {"in_scope": True, "retrieve": True}}, "refuse_redirect"),
])
def test_after_assess(state, label):
    assert G.after_assess(state) == label


@pytest.mark.parametrize("state,label", [
    ({"route": "one", "procedure_id": "KS-01"}, "gather_evidence"),
    ({"route": "one", "procedure_id": None}, "web_lookup"),
    ({"route": "tie", "candidates": [{}, {}]}, "clarify"),
    ({"route": "none"}, "web_lookup"),
    ({**ERR, "route": "one", "procedure_id": "KS-01"}, "refuse_redirect"),
])
def test_after_resolve(state, label):
    assert G.after_resolve(state) == label


@pytest.mark.parametrize("state,label", [
    ({"grades": {"usable": True}, "iteration": 0}, "draft_answer"),
    ({"grades": {"usable": False}, "iteration": 0}, "rewrite_query"),
    ({"grades": {"usable": False}, "iteration": 1}, "refuse_redirect"),
    ({**ERR, "grades": {"usable": True}}, "refuse_redirect"),
])
def test_after_grade(state, label):
    assert G.after_grade(state) == label


@pytest.mark.parametrize("state,label", [
    ({"grades": {"support": "all_supported"}}, "freshness_check"),
    ({"grades": {"support": "minor_unsupported"}}, "prune_claims"),
    ({"grades": {"support": "core_unsupported"}, "iteration": 0}, "rewrite_query"),
    ({"grades": {"support": "core_unsupported"}, "iteration": 1}, "refuse_redirect"),
    ({"grades": {}, "iteration": 1}, "refuse_redirect"),           # missing verdict → fail closed
    ({**ERR, "grades": {"support": "all_supported"}}, "refuse_redirect"),
])
def test_after_decide(state, label):
    assert G.after_decide(state) == label


@pytest.mark.parametrize("state,label", [
    ({"freshness": {"notice": True}}, "web_check"),
    ({"freshness": {"notice": False}}, "finalize"),
    ({**ERR, "freshness": {"notice": False}}, "refuse_redirect"),
])
def test_after_freshness(state, label):
    assert G.after_freshness(state) == label


def test_no_edge_sends_errors_toward_generation():
    for fn, _targets in G.CONDITIONAL.values():
        assert fn({**ERR, "need": {"in_scope": True, "retrieve": True}, "route": "one", "procedure_id": "A",
                   "grades": {"usable": True, "support": "all_supported"}, "freshness": {"notice": False}}) == "refuse_redirect"


# ---------------- resolve decision (L1 thresholds)

def c(pid, score, lexical, family=None, field="Hộ tịch", core=None):
    return {"procedure_id": pid, "title": pid, "score": score, "lexical": lexical, "family": family or pid,
            "field": field, "core": lexical if core is None else core}


def test_choose_none_below_core_floor():
    assert choose([c("A", 0.5, 0.4)], RESOLVE)[0] == "none"
    assert choose([], RESOLVE)[0] == "none"


def test_choose_unrelated_pile_is_none_not_clarify():
    """w-eval T-003: unrelated candidates with fused scores 0.62/0.56 must not clarify."""
    cands = [c("2.002189", 0.64, 0.41, core=0.13), c("1.000893", 0.57, 0.30, core=0.1)]
    assert choose(cands, RESOLVE)[0] == "none"


def test_choose_one_clear_winner():
    assert choose([c("A", 0.9, 1.0), c("B", 0.5, 0.4)], RESOLVE) == ("one", [c("A", 0.9, 1.0)])


def test_choose_tie_on_close_same_field_neighbour():
    d, opts = choose([c("A", 0.9, 1.0), c("B", 0.85, 0.9)], RESOLVE)
    assert d == "tie" and [o["procedure_id"] for o in opts] == ["A", "B"]


def test_choose_close_other_field_is_not_a_tie():
    assert choose([c("A", 0.9, 1.0), c("B", 0.85, 0.9, field="Cư trú")], RESOLVE)[0] == "one"


def test_choose_sibling_within_wider_gap_is_tie():
    """w-tools: KS-01 is ranked under its sibling KS-02; siblings within sibling_gap must clarify."""
    cands = [c("KS-02", 0.9, 0.6, "KS-01", core=1.0), c("KS-01", 0.7, 1.0, "KS-01")]
    assert choose(cands, RESOLVE)[0] == "tie"
    cands = [c("A", 0.9, 1.0), c("B", 0.7, 0.9)]  # same gap, not siblings → one
    assert choose(cands, RESOLVE)[0] == "one"


def test_choose_sibling_resolved_when_hint_names_the_variant():
    cands = [{**c("KS-03", 1.0, 1.0, "KS-01"), "title": "Đăng ký lại khai sinh"},
             {**c("KS-01", 0.93, 0.89, "KS-01"), "title": "Đăng ký khai sinh"}]
    assert choose(cands, RESOLVE, "đăng ký lại khai sinh")[0] == "one"
    assert choose(cands, RESOLVE, "đăng ký khai sinh")[0] == "tie"


def test_choose_plain_marker_picks_family_root():
    cands = [c("KS-02", 0.9, 0.6, "KS-01"), c("KS-01", 0.8, 0.8, "KS-01")]
    d, opts = choose(cands, RESOLVE, "đăng ký khai sinh trong nước lần đầu")
    assert d == "one" and opts[0]["procedure_id"] == "KS-01"


def test_choose_lower_ranked_lexical_match_wins_over_unrelated_top():
    cands = [c("X", 0.80, 0.3, core=0.1, field="Cư trú"), c("A", 0.75, 1.0)]
    assert choose(cands, RESOLVE) == ("one", [cands[1]])


# ---------------- F2 candidate A (ROUND-2 item 1, flag f2_rule, default off)

F2 = {**RESOLVE, "f2_rule": "distinguishing_words"}


def _f2_cands():
    return [{**c("KS-02", 0.95, 1.0, "KS-01"), "title": "Đăng ký khai sinh có yếu tố nước ngoài"},
            {**c("KS-01", 0.90, 1.0, "KS-01"), "title": "Đăng ký khai sinh"}]


def test_f2_rule_default_off_one_distinguishing_word_resolves():
    assert RESOLVE["f2_rule"] is None
    assert choose(_f2_cands(), RESOLVE, "khai sinh cho con ở nước ngoài")[0] == "one"


def test_f2_rule_requires_all_distinguishing_words():
    assert choose(_f2_cands(), F2, "khai sinh cho con ở nước ngoài")[0] == "tie"
    assert choose(_f2_cands(), F2, "khai sinh", query="đăng ký khai sinh có yếu tố nước ngoài")[0] == "one"


def test_f2_rule_keeps_other_sibling_rules():
    root_top = list(reversed(_f2_cands()))  # top adds nothing over the sibling → nothing to require
    root_top[0]["score"], root_top[1]["score"] = 0.95, 0.90
    assert choose(root_top, F2, "đăng ký khai sinh", intent="fee")[0] == "one"  # qualifier-only sibling
    cands = [c("A", 0.9, 1.0), c("B", 0.7, 0.9)]  # not siblings → unaffected
    assert choose(cands, F2)[0] == "one"


def test_f2_rule_config_flag_and_validation():
    from src.nodes import Deps
    from tests.fakes import FakeDB, FakeLLM, FakeRAG
    assert Deps(llm=FakeLLM(), rag=FakeRAG(), db=FakeDB()).resolve["f2_rule"] is None
    deps = Deps(llm=FakeLLM(), rag=FakeRAG(), db=FakeDB(), config={"f2_rule": "distinguishing_words"})
    assert deps.resolve["f2_rule"] == "distinguishing_words"
    with pytest.raises(ValueError):
        Deps(llm=FakeLLM(), rag=FakeRAG(), db=FakeDB(), config={"f2_rule": "bogus"})


# ---------------- sibling-invariant shortcut (lead decision P1)

def _db_with_same_fee(differ=None):
    from tests.fakes import PROCEDURES, FakeDB
    procs = {k: dict(v) for k, v in PROCEDURES.items()}
    for pid in ("KS-01", "KS-02", "KS-03"):
        procs[pid]["fees"] = [("miễn lệ phí", "đăng ký đúng hạn", "toàn quốc")]
    if differ:
        procs[differ]["fees"] = [("theo HĐND tỉnh", None, "theo tỉnh")]
    return FakeDB(procedures=procs)


def _chosen():
    from tests.fakes import PROCEDURES
    return [{"procedure_id": p, "title": PROCEDURES[p]["title"], "family": "KS-01"} for p in ("KS-01", "KS-02", "KS-03")]


def test_sibling_invariant_fee_identical_returns_group():
    from src.nodes import Deps, sibling_invariant
    from tests.fakes import FakeLLM, FakeRAG
    deps = Deps(llm=FakeLLM(), rag=FakeRAG(), db=_db_with_same_fee())
    assert sibling_invariant(deps, _chosen(), "fee") == [c["title"] for c in _chosen()]


def test_sibling_invariant_one_differing_sibling_is_none():
    from src.nodes import Deps, sibling_invariant
    from tests.fakes import FakeLLM, FakeRAG
    deps = Deps(llm=FakeLLM(), rag=FakeRAG(), db=_db_with_same_fee(differ="KS-03"))
    assert sibling_invariant(deps, _chosen(), "fee") is None
    assert sibling_invariant(Deps(llm=FakeLLM(), rag=FakeRAG(), db=_db_with_same_fee()), _chosen(), "documents") is None


def test_premise_on_plain_hint_answers_root_variant():
    from tests.fakes import FakeLLM, need, run
    s, _ = run("Lệ phí khai sinh là 50.000đ phải không?",
               FakeLLM(need=need("fee", "đăng ký khai sinh", premise="lệ phí đăng ký khai sinh là 50.000đ")))
    assert s["outcome"] == "answer" and s["procedure_id"] == "KS-01"
    assert s["generation"].startswith("Không đúng")


def test_documents_never_sibling_invariant():
    from tests.fakes import FakeLLM, need, run
    s, _ = run("Hồ sơ khai sinh?", FakeLLM(need=need("documents", "đăng ký khai sinh")), db=_db_with_same_fee())
    assert s["outcome"] == "clarify"


def test_choose_sibling_with_other_action_is_not_an_alternative():
    """Real DB: 'Xóa đăng ký thường trú' is variant_of 'Đăng ký thường trú'; the bare hint means the latter."""
    top = {**c("1.004222", 1.0, 1.0, "1.004222"), "title": "Đăng ký thường trú"}
    xoa = {**c("1.003197", 0.92, 0.8, "1.004222"), "title": "Xóa đăng ký thường trú"}
    assert choose([top, xoa], RESOLVE, "đăng ký thường trú") == ("one", [top])
    assert choose([xoa, top], RESOLVE, "xóa đăng ký thường trú")[1][0]["procedure_id"] == "1.003197"


def test_contained_title_fallback():
    from src.nodes import contained_title
    cands = [{"procedure_id": "A", "title": "Đăng ký thường trú"}, {"procedure_id": "B", "title": "Tách hộ"}]
    assert contained_title(cands, "ở nhà thuê thì làm hộ khẩu thường trú cần hồ sơ gì")["procedure_id"] == "A"
    assert contained_title(cands, "nhập tịch") is None


def test_cjk_stripped_from_hint():
    from src import self_rag
    from tests.fakes import FakeLLM, need
    out = self_rag.assess_need(FakeLLM(need=need("documents", "đăng ký常住户口 thường trú")), "q")
    assert out["procedure_hint"] == "đăng ký thường trú"


def test_sibling_invariant_when_no_sibling_has_fee_rows():
    from tests.fakes import PROCEDURES, FakeDB, FakeLLM, need, run
    procs = {k: dict(v) for k, v in PROCEDURES.items()}
    for pid in ("KS-01", "KS-02", "KS-03"):
        procs[pid]["fees"] = []
    s, _ = run("Lệ phí khai sinh?", FakeLLM(need=need("fee", "đăng ký khai sinh")), db=FakeDB(procedures=procs))
    assert s["outcome"] == "answer_partial" and "Không tìm thấy căn cứ về: lệ phí" in s["generation"]


def test_coverage_floor_with_synonyms():
    from src.nodes import coverage
    exp = "cấp lại cccd CCCD căn cước công dân thẻ căn cước căn cước làm lại cấp lại"
    assert coverage("cấp lại cccd", "Cấp lại thẻ căn cước (thực hiện tại cấp tỉnh)", exp) == 1.0
    assert coverage("làm căn cước lần đầu", "Cấp thẻ Căn cước cho người từ đủ 14 tuổi trở lên") == 1.0
    assert coverage("nhập tịch cho người nước ngoài",
                    "Thủ tục ghi vào Sổ hộ tịch việc kết hôn của công dân Việt Nam đã được giải quyết") < RESOLVE["core_floor"]


def test_choose_qualifier_sibling_resolves_except_for_documents():
    top = {**c("1.000656", 0.99, 1.0, "1.000656"), "title": "Thủ tục đăng ký khai tử"}
    luu = {**c("1.000419", 0.87, 1.0, "1.000656"), "title": "Thủ tục đăng ký khai tử lưu động"}
    assert choose([top, luu], RESOLVE, "đăng ký khai tử", intent="time")[0] == "one"
    assert choose([top, luu], RESOLVE, "đăng ký khai tử", intent="documents")[0] == "tie"


def test_choose_query_words_break_sibling_tie():
    tinh = {**c("2.001194", 0.68, 1.0, "2.000200", field="CC"), "title": "Cấp lại thẻ căn cước (thực hiện tại cấp tỉnh)"}
    tw = {**c("1.000757", 0.65, 1.0, "2.000200", field="CC"), "title": "Cấp lại thẻ căn cước (thực hiện tại cấp trung ương)"}
    assert choose([tinh, tw], RESOLVE, "làm lại căn cước", intent="steps")[0] == "tie"
    assert choose([tinh, tw], RESOLVE, "làm lại căn cước", query="Các bước làm lại căn cước ở công an tỉnh?",
                  intent="steps") == ("one", [tinh])


# ---------------- base_title_preference (audit finding 1; flag, default off)

BASE = {**RESOLVE, "base_title_preference": True}
T001 = "Hồ sơ đăng ký khai sinh gồm những gì?"


def _ks(pid, title, score):
    return {**c(pid, score, 1.0, "1.001193"), "title": title}


def test_base_title_preference_default_off_keeps_v1():
    assert RESOLVE["base_title_preference"] is False
    cands = [_ks("1.001193", "Thủ tục đăng ký khai sinh", 0.99), _ks("1.003583", "Thủ tục đăng ký khai sinh lưu động", 0.85)]
    assert choose(cands, RESOLVE, "đăng ký khai sinh", query=T001, intent="documents")[0] == "tie"


def test_base_title_preference_picks_base_for_every_intent_and_names_the_variant():
    base, luu = _ks("1.001193", "Thủ tục đăng ký khai sinh", 0.99), _ks("1.003583", "Thủ tục đăng ký khai sinh lưu động", 0.85)
    for intent in ("documents", "fee", "steps", "update"):
        d, chosen = choose([base, luu], BASE, "đăng ký khai sinh", query=T001, intent=intent)
        assert d == "one" and chosen[0]["procedure_id"] == "1.001193", intent
        assert chosen[0]["assumed_over"] == ["Thủ tục đăng ký khai sinh lưu động"]
    # the base ranked below its qualified sibling: still the base
    d, chosen = choose([{**luu, "score": 0.99}, {**base, "score": 0.9}], BASE, "đăng ký khai sinh", query=T001)
    assert d == "one" and chosen[0]["procedure_id"] == "1.001193"


def test_base_title_preference_generic_co_does_not_name_a_qualifier():
    """Probe 06: 'có' in the question is not the qualifier 'có yếu tố nước ngoài'."""
    tu = {**c("1.000656", 0.99, 1.0, "1.000656"), "title": "Thủ tục đăng ký khai tử"}
    nn = {**c("1.001766", 0.75, 1.0, "1.000656"), "title": "Thủ tục đăng ký khai tử có yếu tố nước ngoài"}
    q = "Thủ tục đăng ký khai tử có thay đổi gì mới không?"
    assert choose([tu, nn], RESOLVE, "đăng ký khai tử", query=q, intent="update")[0] == "tie"  # v1 defect
    assert choose([tu, nn], BASE, "đăng ký khai tử", query=q, intent="update")[1][0]["procedure_id"] == "1.000656"


def test_base_title_preference_a_said_qualifier_still_counts():
    base = _ks("1.001193", "Thủ tục đăng ký khai sinh", 0.95)
    nn = _ks("2.000528", "Thủ tục đăng ký khai sinh có yếu tố nước ngoài", 0.99)
    luu = _ks("1.003583", "Thủ tục đăng ký khai sinh lưu động", 0.85)
    q = "Con tôi có mẹ là người nước ngoài, hồ sơ đăng ký khai sinh?"
    assert choose([nn, base], BASE, "đăng ký khai sinh", query=q, intent="documents")[1][0]["procedure_id"] == "2.000528"
    q2 = "Đăng ký khai sinh lưu động cần giấy gì?"
    assert choose([{**luu, "score": 0.99}, base], BASE, "đăng ký khai sinh lưu động", query=q2) \
        == ("one", [{**luu, "score": 0.99}])
    # base on top, the user said "nước ngoài" → the foreign variant is a real alternative, lưu động is not
    d, chosen = choose([{**base, "score": 0.99}, {**nn, "score": 0.9}, luu], BASE, "đăng ký khai sinh", query=q)
    assert d == "tie" and [x["procedure_id"] for x in chosen] == ["1.001193", "2.000528"]


def test_qualifier_said_needs_the_qualifier_words_not_form_or_function_words():
    from src.nodes import _tokens, qualifier_said
    base = "Thủ tục đăng ký khai sinh"
    said = lambda q: [_tokens(q)]  # noqa: E731
    assert not qualifier_said(base, "Thủ tục đăng ký khai sinh cho người đã có hồ sơ, giấy tờ cá nhân", said(T001))
    assert qualifier_said(base, "Thủ tục đăng ký khai sinh cho người đã có hồ sơ, giấy tờ cá nhân",
                          said("người lớn đã có giấy tờ cá nhân đăng ký khai sinh"))
    assert not qualifier_said(base, "Thủ tục đăng ký khai sinh có yếu tố nước ngoài", said("tờ khai có mẫu không"))
    assert qualifier_said(base, "Thủ tục đăng ký khai sinh có yếu tố nước ngoài tại khu vực biên giới",
                          said("khai sinh ở biên giới"))


def test_base_title_preference_config_flag():
    from src.nodes import Deps
    from tests.fakes import FakeDB, FakeLLM, FakeRAG
    assert Deps(llm=FakeLLM(), rag=FakeRAG(), db=FakeDB()).resolve["base_title_preference"] is False
    deps = Deps(llm=FakeLLM(), rag=FakeRAG(), db=FakeDB(), config={"base_title_preference": True})
    assert deps.resolve["base_title_preference"] is True


def test_base_title_preference_graph_answers_base_with_variant_note():
    from tests.fakes import FakeLLM, need, run
    s, _ = run("Hồ sơ khai sinh?", FakeLLM(need=need("documents", "đăng ký khai sinh")), db=_db_with_same_fee(),
               config={"base_title_preference": True})
    assert s["outcome"] in ("answer", "answer_partial") and s["procedure_id"] == "KS-01"
    assert s["assumed_variants"] == ["Đăng ký khai sinh có yếu tố nước ngoài"]
    assert "Nếu trường hợp của bạn là «Đăng ký khai sinh có yếu tố nước ngoài»" in s["generation"]


def test_score_candidates_ignores_ids_without_a_procedure_row():
    """ROUND-4: a non-procedure chunk id (legal text, guidance page) can never become a resolve candidate."""
    from src.nodes import Deps, score_candidates
    from tests.fakes import FakeDB, FakeLLM, FakeRAG

    class RAG(FakeRAG):
        def resolve_candidates(self, query, k=5):
            return [{"procedure_id": "LAW-60-2014", "title": "Luật Hộ tịch 2014", "score": 0.0328},
                    {"procedure_id": "KS-01", "title": "Đăng ký khai sinh", "score": 0.0320}]
    cands = score_candidates(Deps(llm=FakeLLM(), rag=RAG(), db=FakeDB()), "đăng ký khai sinh")
    assert "LAW-60-2014" not in [c["procedure_id"] for c in cands] and cands[0]["procedure_id"] == "KS-01"


# ---------------- head_noun_guard (flag, default off; v5 candidate) — owner trace c26ce7e9

def _hn(pid, title, score, core, fam):
    return {"procedure_id": pid, "title": title, "score": score, "core": core, "lexical": core, "family": fam, "field": "Hộ tịch"}


X6_HINT = "đăng ký khai sinh điền tên cha cần giấy kết hôn để chứng minh quan hệ không"
X6_CANDS = [_hn("1.000689", "Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con", 0.663, 0.45, "1.001193"),
            _hn("1.000894", "Thủ tục đăng ký kết hôn", 0.619, 1.0, "1.000894"),
            _hn("1.001695", "Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con có yếu tố nước ngoài", 0.604, 0.45, "1.001193")]


def _hn_cfg():
    from src.families import load_family_nouns
    return {**RESOLVE, "head_noun_guard": True, "family_nouns": load_family_nouns()}


def test_head_noun_guard_off_keeps_v4():
    assert RESOLVE["head_noun_guard"] is False
    assert choose(X6_CANDS, RESOLVE, X6_HINT)[1][0]["procedure_id"] == "1.000894"


def test_head_noun_guard_a_fully_covered_other_family_cannot_win():
    d, chosen = choose(X6_CANDS, _hn_cfg(), X6_HINT)
    assert d == "none"  # only khai sinh candidates remain and none clears the floor (resolve_procedure then tries the rescue)
    with_base = X6_CANDS + [_hn("1.001193", "Thủ tục đăng ký khai sinh", 0.55, 1.0, "1.001193")]
    assert choose(with_base, _hn_cfg(), X6_HINT) == ("one", [with_base[-1]])


def test_head_noun_guard_two_families_not_at_the_start_clarify():
    with_base = X6_CANDS + [_hn("1.001193", "Thủ tục đăng ký khai sinh", 0.55, 1.0, "1.001193")]
    d, chosen = choose(with_base, _hn_cfg(), "muốn biết giấy tờ để đăng ký khai sinh và đăng ký kết hôn")
    assert d == "tie" and {c["procedure_id"] for c in chosen} == {"1.001193", "1.000894"}  # only floor-clearing candidates


def test_head_noun_guard_no_family_named_changes_nothing():
    cands = [_hn("1.010038", "Tách hộ", 1.0, 1.0, "1.010038")]
    assert choose(cands, _hn_cfg(), "tách hộ") == choose(cands, RESOLVE, "tách hộ")


def test_family_nouns_file_matches_the_titles():
    import json
    from pathlib import Path
    from src.families import FAMILY_NOUNS_PATH, derive_from_db
    db = Path(__file__).resolve().parents[1] / "data" / "app.db"
    if not db.exists():
        pytest.skip("no data/app.db")
    assert json.loads(FAMILY_NOUNS_PATH.read_text(encoding="utf-8")) == derive_from_db(db)
    assert {"khai sinh", "ket hon", "khai tu", "can cuoc", "tam tru", "thuong tru", "giam ho"} <= set(derive_from_db(db))


def test_head_noun_guard_off_path_is_unchanged_for_every_shape():
    """Flag off: choose() must not even look at family nouns (v4 byte-identical)."""
    from src.families import load_family_nouns
    off_with_nouns = {**RESOLVE, "family_nouns": load_family_nouns()}  # nouns present but flag off
    with_base = X6_CANDS + [_hn("1.001193", "Thủ tục đăng ký khai sinh", 0.55, 1.0, "1.001193")]
    for cands, hint in ((X6_CANDS, X6_HINT), (with_base, "muốn biết giấy tờ để đăng ký khai sinh và đăng ký kết hôn"),
                        (with_base, "đăng ký kết hôn")):
        assert choose(cands, off_with_nouns, hint) == choose(cands, RESOLVE, hint)


def test_head_noun_guard_two_families_below_the_floor_stay_none():
    """T-053 shape: a story_rewrite name listing two families, no candidate clearing the floor → none, never a clarify."""
    story = ("Xác nhận đăng ký khai sinh, xác nhận thay đổi hoặc bổ sung hồ sơ khai sinh cho trẻ em dưới 01 tuổi; "
             "Cấp hộ chiếu phổ thông lần đầu cho công dân")
    cands = [_hn("1.004772", "Thủ tục đăng ký khai sinh cho người đã có hồ sơ, giấy tờ cá nhân", 0.63, 0.1, "1.001193"),
             _hn("2.000547", "Thủ tục ghi vào Sổ hộ tịch việc hộ tịch khác (khai sinh; giám hộ; thay đổi hộ tịch)", 0.2, 0.25, "1.001193"),
             _hn("2.000748", "Thủ tục thay đổi, cải chính, bổ sung thông tin hộ tịch, xác định lại dân tộc có yếu tố nước ngoài", 0.18, 0.2,
                 "1.004859")]
    assert choose(cands, _hn_cfg(), story)[0] == "none"
    assert choose(cands, RESOLVE, story)[0] == "none"
