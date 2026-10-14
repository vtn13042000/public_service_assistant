"""render.py: structured facts rendered by code from db rows, each line cited (L5)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import render  # noqa: E402
from src.self_rag import check_db_claim, cited_ids  # noqa: E402
from tests.fakes import FakeDB  # noqa: E402


def ev(pid, *getters):
    db = FakeDB()
    out = []
    for g in getters:
        out += getattr(db, g)(pid)
    return out


def test_documents_numbered_and_cited():
    evs = ev("KS-01", "get_required_documents")
    lines = render.render_documents(evs)
    assert lines[0] == "Thành phần hồ sơ:"
    assert lines[1].startswith("1. Tờ khai đăng ký khai sinh theo mẫu — 01 bản — bắt buộc")
    assert lines[1].endswith("[db:required_documents:KS-01:1]")
    assert "ghi chú" in lines[2]


def test_fee_line_has_jurisdiction_and_date():
    lines, gaps = render.render_fees(ev("CCCD-02", "get_fees"), None)
    assert "70.000 đồng" in lines[1] and "phạm vi: toàn quốc" in lines[1] and "ngày lấy 2026-10-01" in lines[1]
    assert gaps == []


def test_fee_varies_without_locality_is_needs_input():
    lines, gaps = render.render_fees(ev("CT-09", "get_fees"), None)
    assert "theo HĐND tỉnh" in lines[1]
    assert gaps and gaps[0]["kind"] == "needs_input"


def test_fee_varies_with_unknown_province_is_missing():
    _, gaps = render.render_fees(ev("CT-09", "get_fees"), "Đắk Lắk")
    assert gaps[0]["kind"] == "missing"


def test_no_fee_rows_is_missing_not_free():
    lines, gaps = render.render_fees([], None)
    assert lines == [] and gaps[0]["kind"] == "missing"
    assert render.primary_missing("fee", gaps)


def test_agency_and_time_verbatim():
    evs = ev("KS-02", "get_agency", "get_procedure")
    a = render.render_agency(evs)
    assert "UBND cấp xã nơi cư trú của cha hoặc mẹ" in a[1] and "hiệu lực theo nguồn: 2025-07-01" in a[1]
    t = render.render_time(evs)
    assert t[0].startswith("Thời gian giải quyết: 03 ngày làm việc ")


def test_every_rendered_line_passes_code_check():
    evs = ev("KS-01", "get_procedure", "get_agency", "get_required_documents", "get_fees")
    by_id = {e["evidence_id"]: e for e in evs}
    block, gaps = render.render_block("general", evs)
    for line in block.splitlines():
        if not line.strip() or line.endswith(":"):
            continue
        ids = cited_ids(line)
        assert ids, line
        ok, why = check_db_claim(line, [by_id[i] for i in ids])
        assert ok, (line, why)


def test_intent_blocks():
    evs = ev("KS-02", "get_procedure", "get_agency", "get_required_documents")
    block, _ = render.render_block("agency", evs)
    assert "Cơ quan tiếp nhận:" in block and "Thành phần hồ sơ:" in block and "Lệ phí" not in block
    assert render.render_block("steps", evs) == ("", [])


def test_premise_rendered_by_code():
    evs = ev("KS-01", "get_fees")
    line = render.render_premise("lệ phí đăng ký khai sinh là 50.000đ", "fee", evs)
    assert line.startswith("Không đúng — theo dữ liệu thủ tục, lệ phí: miễn lệ phí (đăng ký đúng hạn)")
    assert "50.000" not in line and line.endswith("[db:fees:KS-01:1]")
    ok, _ = check_db_claim(line, evs)
    assert ok
    assert render.render_premise("lệ phí là 70.000 đồng", "fee", ev("CCCD-02", "get_fees")).startswith("Đúng —")
    assert render.render_premise("nộp ở UBND xã", "agency", evs) is None
    assert render.render_premise(None, "fee", evs) is None


def _fees(rows):
    from src.evidence import db_id, make_evidence
    return [make_evidence(db_id("fees", "P", i), "db", v, procedure_id="P", section="fees", source_url="u",
                          structured={"value": v, "condition": c, "jurisdiction": j}) for i, (v, c, j) in enumerate(rows, 1)]


KHAI_SINH_FEES = [("theo HĐND tỉnh", "không đúng hạn", "theo tỉnh"), ("miễn lệ phí", "đúng hạn", "toàn quốc"),
                  ("theo HĐND tỉnh", "Mức lệ phí theo quy định của HĐND tỉnh", "Đắk Lắk"),
                  ("miễn lệ phí", "đúng hạn", "Đắk Lắk")]


def test_fees_grouped_no_locality_shows_national_and_names_provinces():
    lines, gaps = render.render_fees(_fees(KHAI_SINH_FEES), None)
    assert lines[0].startswith("Lệ phí (áp dụng toàn quốc")
    assert len(lines) == 3 and not any("Đắk Lắk" in ln for ln in lines)
    assert gaps[0]["kind"] == "needs_input" and "Đắk Lắk" in gaps[0]["detail"]


def test_fees_with_locality_adds_province_group():
    lines, gaps = render.render_fees(_fees(KHAI_SINH_FEES), "Đắk Lắk")
    assert "Lệ phí tại Đắk Lắk:" in lines and sum("phạm vi: Đắk Lắk" in ln for ln in lines) == 2
    assert gaps == []


def test_fees_locality_without_row_is_missing():
    _, gaps = render.render_fees(_fees(KHAI_SINH_FEES), "Hà Nội")
    assert gaps[0]["kind"] == "missing" and "Hà Nội" in gaps[0]["element"]


def test_free_premise_without_numbers_rendered_by_code():
    rows = _fees([("20.000 đồng", "trực tiếp", "toàn quốc"), ("miễn lệ phí", "trực tuyến", "toàn quốc")])
    assert render.render_premise("đăng ký thường trú được miễn phí", "fee", rows).startswith("Tùy trường hợp —")
    assert render.render_premise("được miễn phí", "fee", rows[1:]).startswith("Đúng —")
    assert render.render_premise("được miễn phí", "fee", rows[:1]).startswith("Không đúng —")
