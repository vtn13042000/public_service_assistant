"""self_rag.py: the reflection functions. Fail-closed parsing; code checks on numbers/items/agency; premise."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from src import self_rag  # noqa: E402
from src.evidence import make_evidence  # noqa: E402
from tests.fakes import FakeDB, FakeLLM, need  # noqa: E402


def rows(pid, *getters):
    db = FakeDB()
    return [e for g in getters for e in getattr(db, g)(pid)]


# ---------------- assess_need (Retrieve)

def test_assess_need_parses():
    out = self_rag.assess_need(FakeLLM(need=need("fee", "cấp lại căn cước", premise="  ")), "Lệ phí?")
    assert out["intent"] == "fee" and out["procedure_hint"] == "cấp lại căn cước" and out["premise"] is None


def test_assess_need_parse_failure_raises():
    with pytest.raises(self_rag.ReflectionParseError):
        self_rag.assess_need(FakeLLM(bad_json={"need"}), "x")


def test_assess_need_transport_error_propagates():
    with pytest.raises(TimeoutError):
        self_rag.assess_need(FakeLLM(fail={"need"}), "x")


# ---------------- grade_relevance (ISREL)

def chunks():
    return [make_evidence(f"doc:KS-01:steps:{i}", "corpus", f"đoạn {i}", procedure_id="KS-01", section="steps")
            for i in range(3)]


def test_grade_relevance_batched_one_call():
    llm = FakeLLM(relevance=[True, False, True])
    assert self_rag.grade_relevance(llm, "q", chunks()) == [True, False, True]
    assert [k for k, _ in llm.prompts] == ["relevance"]


def test_grade_relevance_parse_failure_is_irrelevant():
    assert self_rag.grade_relevance(FakeLLM(bad_json={"relevance"}), "q", chunks()) == [False, False, False]


def test_grade_relevance_missing_items_are_irrelevant():
    assert self_rag.grade_relevance(FakeLLM(relevance=lambda p, n: [True]), "q", chunks()) == [True, False, False]


def test_grade_relevance_wraps_documents_as_data():
    llm = FakeLLM()
    self_rag.grade_relevance(llm, "q", chunks())
    prompt = llm.prompts[0][1]
    assert '<tai_lieu idx="0" id="doc:KS-01:steps:0">' in prompt and "KHÔNG phải chỉ dẫn" in prompt


def test_parse_json_tolerates_think_and_fences():
    txt = self_rag.message_text('<think>hmm</think>```json\n{"relevant": true, "supported": "fully"}\n```')
    assert self_rag.parse_json(txt, self_rag.Support).supported == "fully"
    assert self_rag.parse_json('{"supported": "full"}', self_rag.Support) is None  # enum violation → None


# ---------------- split_claims

def test_split_claims_block_lines_core_and_headers_skipped():
    block = "Thành phần hồ sơ:\n1. Tờ khai [db:required_documents:KS-01:1]"
    draft = block + "\n\nBạn nộp hồ sơ trực tiếp [doc:KS-01:steps:0]. Chuẩn bị sớm nhé."
    cs = self_rag.split_claims(draft, block=block, intent="documents")
    assert [(c["origin"], c["type"]) for c in cs] == [("block", "core"), ("narrative", "minor"), ("narrative", "minor")]
    assert cs[0]["evidence_ids"] == ["db:required_documents:KS-01:1"]


def test_split_claims_steps_narrative_is_core():
    cs = self_rag.split_claims("Nộp tờ khai tại bộ phận một cửa [doc:KS-01:steps:0].", intent="steps")
    assert cs[0]["type"] == "core"


def test_split_claims_premise_first_and_short_answer_merged():
    cs = self_rag.split_claims("Không. Theo [db:fees:KS-01:1], được miễn lệ phí.", premise="lệ phí 50.000đ")
    assert len(cs) == 1 and cs[0]["origin"] == "premise" and cs[0]["type"] == "core"


def test_split_claims_unaddressed_premise_is_core_unsupported():
    cs = self_rag.split_claims("", premise="lệ phí 50.000đ")
    assert cs[0]["type"] == "core" and cs[0]["verdict"] == "unsupported"


def test_cited_ids_multi():
    assert self_rag.cited_ids("x [db:fees:A:1; doc:A:fees:0] y [db:fees:A:1]") == ["db:fees:A:1", "doc:A:fees:0"]


# ---------------- check_support (ISSUP, hybrid)

def verdict(text, evidence, llm=None, **kw):
    c = self_rag.split_claims(text, block=text if kw.pop("block", False) else "", **kw)
    return self_rag.check_support(llm or FakeLLM(support="no"), c, evidence, premise=kw.get("premise"))


def test_db_item_verified_by_code_without_llm():
    evs = rows("KS-01", "get_required_documents")
    llm = FakeLLM(support="no")
    out = verdict("1. Tờ khai đăng ký khai sinh theo mẫu — 01 bản [db:required_documents:KS-01:1]", evs, llm, block=True)
    assert out[0]["verdict"] == "supported" and llm.prompts == []


def test_db_invented_item_unsupported():
    out = verdict("3. Sổ hộ khẩu [db:required_documents:KS-01:1]", rows("KS-01", "get_required_documents"), block=True)
    assert out[0]["verdict"] == "unsupported" and "document item" in out[0]["reason"]


def test_db_wrong_number_unsupported():
    out = verdict("- 50.000 đồng [db:fees:CCCD-02:1]", rows("CCCD-02", "get_fees"), block=True)
    assert out[0]["verdict"] == "unsupported" and "numbers" in out[0]["reason"]


def test_db_number_formats_normalised():
    assert self_rag.numbers("70.000 đồng, 01 bản") == {"70000", "1"}


def test_db_agency_must_match():
    evs = rows("KS-01", "get_agency")
    assert verdict("- UBND cấp huyện [db:agencies:KS-01:1]", evs, block=True)[0]["verdict"] == "unsupported"
    ok = verdict("- UBND cấp xã nơi cư trú của cha hoặc mẹ [db:agencies:KS-01:1]", evs, block=True)
    assert ok[0]["verdict"] == "supported"


def test_processing_time_verbatim_unit():
    evs = rows("KS-02", "get_procedure")
    bad = verdict("Thời gian giải quyết: 03 ngày [db:procedures:KS-02:1]", evs, block=True)
    assert bad[0]["verdict"] == "unsupported"


def test_uncited_claim_unsupported_by_rule():
    out = verdict("Lệ phí là 50.000 đồng.", [], FakeLLM(support="fully"), intent="fee")
    assert out[0]["verdict"] == "unsupported" and out[0]["reason"] == "no citation"


def test_fabricated_citation_unsupported():
    out = verdict("Miễn lệ phí [db:fees:KS-01:9].", rows("KS-01", "get_fees"), FakeLLM(support="fully"))
    assert out[0]["verdict"] == "unsupported" and "not in evidence" in out[0]["reason"]


def test_doc_claim_judged_by_llm_against_cited_chunk_only():
    evs = [make_evidence("doc:KS-01:steps:0", "corpus", "Nộp tờ khai tại bộ phận một cửa.", procedure_id="KS-01", section="steps"),
           make_evidence("doc:KS-01:steps:1", "corpus", "ĐOẠN KHÔNG ĐƯỢC TRÍCH", procedure_id="KS-01", section="steps")]
    llm = FakeLLM(support="fully")
    out = verdict("Nộp tờ khai tại bộ phận một cửa [doc:KS-01:steps:0].", evs, llm)
    assert out[0]["verdict"] == "supported"
    assert "ĐOẠN KHÔNG ĐƯỢC TRÍCH" not in llm.prompts[0][1]


@pytest.mark.parametrize("judge,expected", [("partial", "partial"), ("no", "unsupported")])
def test_doc_claim_partial_and_no(judge, expected):
    evs = [make_evidence("doc:KS-01:steps:0", "corpus", "Nộp tờ khai.", procedure_id="KS-01", section="steps")]
    assert verdict("Nộp tờ khai [doc:KS-01:steps:0].", evs, FakeLLM(support=judge))[0]["verdict"] == expected


def test_doc_judge_parse_failure_unsupported():
    evs = [make_evidence("doc:KS-01:steps:0", "corpus", "Nộp tờ khai.", procedure_id="KS-01", section="steps")]
    assert verdict("Nộp tờ khai [doc:KS-01:steps:0].", evs, FakeLLM(bad_json={"support"}))[0]["verdict"] == "unsupported"


def test_fee_claim_citing_corpus_chunk_fails_tier():
    evs = [make_evidence("doc:KS-01:fees:0", "corpus", "Lệ phí: miễn lệ phí.", procedure_id="KS-01", section="fees")]
    out = verdict("Được miễn lệ phí [doc:KS-01:fees:0].", evs, FakeLLM(support="fully"))
    assert out[0]["verdict"] == "unsupported" and "L2" in out[0]["reason"]


def test_doc_claim_number_not_in_chunk_unsupported_before_llm():
    evs = [make_evidence("doc:KS-01:steps:0", "corpus", "Nộp tờ khai.", procedure_id="KS-01", section="steps")]
    llm = FakeLLM(support="fully")
    assert verdict("Nộp 2 tờ khai [doc:KS-01:steps:0].", evs, llm)[0]["verdict"] == "unsupported"
    assert llm.prompts == []


# ---------------- premise (F5)

FEE = "lệ phí đăng ký khai sinh là 50.000đ"


def test_false_premise_agreed_is_unsupported():
    out = verdict("Đúng, theo [db:fees:KS-01:1] được miễn lệ phí.", rows("KS-01", "get_fees"), premise=FEE)
    assert out[0]["verdict"] == "unsupported" and "does not say so" in out[0]["reason"]


def test_false_premise_contradicted_with_citation_supported():
    out = verdict("Không. Theo [db:fees:KS-01:1], đăng ký đúng hạn được miễn lệ phí.", rows("KS-01", "get_fees"), premise=FEE)
    assert out[0]["verdict"] == "supported"


def test_true_premise_denied_is_unsupported():
    out = verdict("Không, theo [db:fees:CCCD-02:1] lệ phí là 70.000 đồng.", rows("CCCD-02", "get_fees"),
                  premise="lệ phí cấp lại căn cước là 70.000đ")
    assert out[0]["verdict"] == "unsupported"


def test_premise_without_numbers_goes_to_llm():
    llm = FakeLLM(support="no")
    out = verdict("Đúng, nộp tại UBND cấp xã nơi cư trú của cha hoặc mẹ [db:agencies:KS-01:1].",
                  rows("KS-01", "get_agency"), llm, premise="nộp ở UBND xã")
    assert out[0]["verdict"] == "unsupported" and llm.prompts[0][0] == "support"


def test_support_summary():
    s = self_rag.support_summary
    assert s([{"type": "core", "verdict": "supported"}]) == "all_supported"
    assert s([{"type": "core", "verdict": "supported"}, {"type": "minor", "verdict": "partial"}]) == "minor_unsupported"
    assert s([{"type": "core", "verdict": "unsupported"}]) == "core_unsupported"


# ---------------- regression: correct paraphrases pruned in a saved trace (RUBRIC-REVIEW R5 Q2)

def _fee_row(i, value, cond, juris="toàn quốc", pid="1.000656"):
    from src.evidence import db_id
    return make_evidence(db_id("fees", pid, i), "db", f"Lệ phí: {value}", procedure_id=pid, section="fees",
                         structured={"value": value, "condition": cond, "jurisdiction": juris})


def test_regression_hdnd_paraphrase_supported():
    row = _fee_row(1, "theo HĐND tỉnh", "Mức lệ phí cụ thể do Hội đồng nhân dân tỉnh, thành phố trực thuộc Trung ương quyết định")
    ok, why = self_rag.check_db_claim("Lệ phí đăng ký khai tử do HĐND tỉnh quyết định [db:fees:1.000656:1].", [row])
    assert ok, why


def test_regression_tt281_paraphrase_supported():
    row = _fee_row(3, "theo Thông tư số 281/2016/TT-BTC", "Phí cấp bản sao Giấy khai sinh (nếu có yêu cầu)")
    ok, why = self_rag.check_db_claim("Phí cấp bản sao thực hiện theo TT 281/2016 [db:fees:1.000656:3].", [row])
    assert ok, why


def test_phrase_in_stays_strict_for_items_and_agencies():
    assert self_rag.phrase_in("Tờ khai đăng ký khai sinh theo mẫu", "Tờ khai đăng ký khai sinh theo mẫu — 01 bản")
    assert not self_rag.phrase_in("Tờ khai đăng ký khai sinh theo mẫu", "Tờ khai đăng ký kết hôn theo mẫu")
    assert not self_rag.phrase_in("UBND cấp xã", "Ủy ban nhân dân cấp huyện")
    assert self_rag.phrase_in("UBND cấp xã", "Ủy ban nhân dân cấp xã")
    assert not self_rag.phrase_in("theo Thông tư số 281/2016/TT-BTC", "theo Thông tư 999/2016", fee=True)


# ---------------- ROUND-2 item 2: the draft prompt carries no citation id the model could copy

def test_draft_prompt_has_no_example_citation_id():
    """qwen3.5 copied the v1 example `[db:fees:KS-01:1]` into 4 frozen-set answers (L4 blocked them → over-refusal)."""
    from src.self_rag import _CITE, load_prompt
    v2 = load_prompt("draft_answer").template
    assert _CITE.findall(v2) == [] and "KS-01" not in v2
    assert _CITE.findall(load_prompt("draft_answer_v1").template)  # v1 kept verbatim for reproducing the first draft


def test_draft_prompt_version_selected_by_config():
    from src.nodes import Deps
    from tests.fakes import FakeDB, FakeLLM, FakeRAG
    assert Deps(llm=FakeLLM(), rag=FakeRAG(), db=FakeDB()).draft_prompt == "draft_answer"
    assert Deps(llm=FakeLLM(), rag=FakeRAG(), db=FakeDB(), config={"draft_prompt": "v1"}).draft_prompt == "draft_answer_v1"


# ---------------- ROUND-2 item 8: tolerant citation parsing (format only; ids must still exist in state)

from src.self_rag import cited_ids, normalize_citations, split_claims  # noqa: E402

KNOWN = {"doc:P1:steps:0", "doc:P1:steps:1", "db:fees:P1:1"}


def test_tolerant_spacing_and_case_variants():
    assert normalize_citations("Câu một [ DOC : P1:steps:0 ].", KNOWN) == "Câu một [doc:P1:steps:0]."
    assert normalize_citations("Câu [db:FEES:p1:1].", KNOWN) == "Câu [db:fees:P1:1]."  # re-cased only to a known id
    assert cited_ids(normalize_citations("Sai [db:fees:P1:1, DB:fees:P1:1; doc : P1:steps:0].", KNOWN)) == [
        "db:fees:P1:1", "doc:P1:steps:0"]


def test_tolerant_citation_after_full_stop_moves_back():
    out = normalize_citations("Câu một. [doc:P1:steps:0] Câu hai. [doc:P1:steps:1] Câu ba.", KNOWN)
    assert out == "Câu một [doc:P1:steps:0]. Câu hai [doc:P1:steps:1]. Câu ba."
    lead = "[doc:P1:steps:0] Câu một. [doc:P1:steps:1] Câu hai."  # consistent leading style: left alone
    assert normalize_citations(lead, KNOWN) == lead


def test_tolerant_strips_example_id_only_when_not_in_state():
    assert normalize_citations("Đúng [db:fees:KS-01:1].", KNOWN) == "Đúng."
    assert normalize_citations("Đúng [db:fees:KS-01:1].", KNOWN | {"db:fees:KS-01:1"}) == "Đúng [db:fees:KS-01:1]."
    claims = split_claims(normalize_citations("Đúng [db:fees:KS-01:1].", KNOWN))
    assert claims[0]["evidence_ids"] == []  # → judged as an uncited claim


def test_tolerant_keeps_fabricated_and_malformed_ids_so_they_still_fail():
    assert cited_ids(normalize_citations("Câu [doc:P9:x:0].", KNOWN)) == ["doc:P9:x:0"]
    out = verdict(normalize_citations("Miễn lệ phí [ db : fees:KS-01:9 ].", set()), rows("KS-01", "get_fees"),
                  FakeLLM(support="fully"))
    assert out[0]["verdict"] == "unsupported" and "not in evidence" in out[0]["reason"]
    assert normalize_citations("Câu [doc:2.000806", KNOWN) == "Câu [doc:2.000806"  # truncated: not repaired


# ---------------- ROUND-4 guard: authority / deadline facts come from db rows, never from amended legal text

LEGAL = ("[Văn bản gốc – đã sửa đổi] Luật Hộ tịch 2014, Điều 7: Ủy ban nhân dân cấp huyện đăng ký khai sinh có yếu tố "
         "nước ngoài; thời hạn giải quyết 15 ngày.")


def _guard_evidence(steps="Người yêu cầu nộp hồ sơ tại Ủy ban nhân dân cấp xã."):
    return [make_evidence("doc:KS-01:legal_basis:0", "corpus", LEGAL, procedure_id="KS-01", section="legal_basis"),
            make_evidence("doc:KS-01:steps:0", "corpus", steps, procedure_id="KS-01", section="steps"),
            make_evidence("db:agencies:KS-01:1", "db", "Cơ quan thực hiện: Ủy ban nhân dân cấp xã", procedure_id="KS-01",
                          section="agency", structured={"name": "Ủy ban nhân dân cấp xã"}),
            make_evidence("db:procedures:KS-01:processing_time", "db", "Thời hạn giải quyết: 05 ngày làm việc",
                          procedure_id="KS-01", section="summary")]


def test_amended_legal_text_never_supports_an_authority_or_deadline():
    llm = FakeLLM(support="fully")  # the judge would accept it; the code rule decides first
    for claim in ("Nộp hồ sơ tại UBND cấp huyện [doc:KS-01:legal_basis:0].",
                  "Cơ quan giải quyết là Ủy ban nhân dân cấp xã [doc:KS-01:legal_basis:0].",
                  "Thời hạn giải quyết là 15 ngày [doc:KS-01:legal_basis:0]."):
        out = verdict(claim, _guard_evidence(), llm)
        assert out[0]["verdict"] == "unsupported", claim
    assert not llm.prompts


def test_amended_legal_text_still_supports_a_plain_legal_basis_claim():
    out = verdict("Thủ tục này căn cứ Luật Hộ tịch 2014 [doc:KS-01:legal_basis:0].", _guard_evidence(), FakeLLM(support="fully"))
    assert out[0]["verdict"] == "supported"


def test_authority_level_in_a_corpus_claim_must_match_the_db_agency_row():
    old = _guard_evidence(steps="Người yêu cầu nộp hồ sơ tại Ủy ban nhân dân cấp huyện.")
    out = verdict("Nộp hồ sơ tại UBND cấp huyện [doc:KS-01:steps:0].", old, FakeLLM(support="fully"))
    assert out[0]["verdict"] == "unsupported" and "huyen" in out[0]["reason"]
    out = verdict("Nộp hồ sơ tại UBND cấp xã [doc:KS-01:steps:0].", _guard_evidence(), FakeLLM(support="fully"))
    assert out[0]["verdict"] == "supported"
    no_agency = [e for e in _guard_evidence() if e["section"] != "agency"]
    out = verdict("Nộp hồ sơ tại UBND cấp xã [doc:KS-01:steps:0].", no_agency, FakeLLM(support="fully"))
    assert out[0]["verdict"] == "unsupported"


def test_deadline_in_a_corpus_claim_must_match_the_db_processing_time():
    evs = _guard_evidence(steps="Hồ sơ được giải quyết trong 05 ngày làm việc.")
    assert verdict("Hồ sơ được giải quyết trong 05 ngày làm việc [doc:KS-01:steps:0].", evs,
                   FakeLLM(support="fully"))[0]["verdict"] == "supported"
    evs = _guard_evidence(steps="Hồ sơ được giải quyết trong 15 ngày.")
    assert verdict("Hồ sơ được giải quyết trong 15 ngày [doc:KS-01:steps:0].", evs,
                   FakeLLM(support="fully"))[0]["verdict"] == "unsupported"


def test_administrative_levels():
    from src.self_rag import levels
    assert levels("UBND thị xã Sơn Tây") == {"huyen"}
    assert levels("Ủy ban nhân dân cấp xã, phường") == {"xa"}
    assert levels("Phòng Tư pháp") == {"huyen"}
    assert levels("bộ phận một cửa") == set()
    assert levels("cán bộ tư pháp - hộ tịch xử lý") == set()  # an official, not the ministry


def test_db_cite_next_to_an_old_legal_chunk_cannot_carry_a_wrong_level():
    out = verdict("Nộp tại Ủy ban nhân dân cấp xã hoặc UBND cấp huyện [db:agencies:KS-01:1][doc:KS-01:legal_basis:0].",
                  _guard_evidence(), FakeLLM(support="fully"))
    assert out[0]["verdict"] == "unsupported" and "huyen" in out[0]["reason"]
    out = verdict("Cơ quan thực hiện: Ủy ban nhân dân cấp xã [db:agencies:KS-01:1].", _guard_evidence())
    assert out[0]["verdict"] == "supported"


def test_a_denied_level_is_not_a_claimed_level():
    evs = _guard_evidence()
    for claim in ("Không, cơ quan tiếp nhận là UBND cấp xã chứ không phải Sở Tư pháp [doc:KS-01:steps:0].",
                  "Không phải UBND cấp huyện mà là UBND cấp xã tiếp nhận hồ sơ [doc:KS-01:steps:0]."):
        assert verdict(claim, evs, FakeLLM(support="fully"))[0]["verdict"] == "supported", claim


def test_amended_mark_matches_the_ingest_prefix():
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "src" / "ingest.py").read_text(encoding="utf-8")
    assert re.search(r'ORIGINAL_MARK = "(.*?)"', src).group(1).strip() == self_rag.AMENDED_MARK


# ---------------- Round-4 item (d): wrong tier prefix (QC re-audit probe 4)

PROBE4_IDS = ["db:procedures:1.001193:legal_basis", "db:agencies:1.001193:1", "db:fees:1.001193:1",
              "doc:1.001193:legal_basis:4e2497d4-0", "doc:1.001193:legal_basis:48470054-0"]
PROBE4 = ("Căn cứ pháp lý cho thủ tục này là Luật Hộ tịch số 60/2014/QH13 tại Điều 14 và Điều 16 "
          "[db:legal_basis:4e2497d4-0][db:legal_basis:48470054-0].")


def test_tier_repair_off_keeps_the_wrong_prefix():
    assert "db:legal_basis:4e2497d4-0" in cited_ids(normalize_citations(PROBE4, PROBE4_IDS))


def test_tier_repair_maps_the_probe_citations_to_the_gathered_chunks():
    repairs = []
    out = normalize_citations(PROBE4, PROBE4_IDS, repair=True, repairs=repairs)
    assert cited_ids(out) == ["doc:1.001193:legal_basis:4e2497d4-0", "doc:1.001193:legal_basis:48470054-0"]
    assert repairs == [("db:legal_basis:4e2497d4-0", "doc:1.001193:legal_basis:4e2497d4-0"),
                       ("db:legal_basis:48470054-0", "doc:1.001193:legal_basis:48470054-0")]


def test_tier_repair_never_guesses():
    from src.self_rag import repair_tier
    known = {"doc:A:steps:0", "doc:B:steps:0", "db:fees:A:1"}
    assert repair_tier("db:steps:0", known) is None          # two chunks end with steps:0 → ambiguous
    assert repair_tier("db:0", known) is None                # one segment is too little to identify anything
    assert repair_tier("doc:fees:X:1", known) is None        # nothing ends with fees:X:1
    assert repair_tier("db:fees:KS-01:1", {"db:fees:KS-01:1x"}) is None
    assert repair_tier("doc:fees:A:1", known) == "db:fees:A:1"  # a db row cited as doc: the db code check then applies


def test_repaired_doc_chunk_cannot_carry_a_db_only_claim():
    from src.evidence import make_evidence
    evs = [make_evidence("doc:KS-01:fees:x-0", "corpus", "Lệ phí 50.000 đồng.", procedure_id="KS-01", section="fees")]
    text = normalize_citations("Lệ phí là 50.000 đồng [db:fees:x-0].", [e["evidence_id"] for e in evs], repair=True)
    assert cited_ids(text) == ["doc:KS-01:fees:x-0"]
    out = verdict(text, evs, FakeLLM(support="fully"))
    assert out[0]["verdict"] == "unsupported" and "L2" in out[0]["reason"]  # a fee needs a db row
