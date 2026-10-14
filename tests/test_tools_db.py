"""src.tools.db against a fixture DB built by src.db.build from tests/fixtures/ (moj > dvc > daklak)."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import db as loader  # noqa: E402
from src.tools import db  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
EVIDENCE_KEYS = {"evidence_id", "tier", "procedure_id", "section", "text", "structured", "source_url",
                 "retrieved_at", "effective_date"}


@pytest.fixture(scope="module")
def fixture_db(tmp_path_factory):
    out = tmp_path_factory.mktemp("db") / "app.db"
    loader.build(out, [FIX / "moj", FIX / "dvc", FIX / "daklak"], prefer=["moj", "dvc", "daklak"])
    mp = pytest.MonkeyPatch()
    mp.setenv("APP_DB", str(out))
    yield out
    mp.undo()


def _check(evs):
    for e in evs:
        assert set(e) == EVIDENCE_KEYS and e["tier"] == "db" and e["evidence_id"].startswith("db:") and e["text"]


def test_search_titles_ranks_and_groups(fixture_db):
    evs = db.search_titles("đăng ký khai sinh")
    _check(evs)
    ids = [e["procedure_id"] for e in evs]
    assert ids[0] == "KS-01" and set(ids) == {"KS-01", "KS-02"}  # shorter exact title ranks first
    assert all(e["structured"]["variant_group"] == "KS-01" for e in evs)
    assert evs[0]["structured"]["score"] >= evs[1]["structured"]["score"]
    assert db.search_titles("yếu tố nước ngoài")[0]["procedure_id"] == "KS-02"


def test_search_titles_no_injection(fixture_db):
    assert db.search_titles("") == []
    for q in ('"; DROP TABLE procedures; --', "khai NEAR( sinh", "title:*", "x' OR 1=1"):
        db.search_titles(q)  # must not raise
    assert db.search_titles("khai sinh")  # table still there


def test_get_procedure(fixture_db):
    evs = db.get_procedure("KS-01")
    _check(evs)
    by_id = {e["evidence_id"]: e for e in evs}
    assert "db:procedures:KS-01:summary" in by_id
    pt = by_id["db:procedures:KS-01:processing_time"]
    assert pt["section"] == "processing_time" and "ngay trong ngày làm việc" in pt["text"]  # unit kept verbatim
    ch = by_id["db:procedures:KS-01:channels"]
    assert ch["structured"]["channels"] == ["trực tiếp", "trực tuyến toàn trình"]  # JSON decoded
    assert pt["source_url"] == "https://moj.gov.vn/fixture-qd" and pt["retrieved_at"] == "2026-10-10"
    assert pt["effective_date"] == "2025-07-01"
    assert "db:procedures:KS-01:conditions" not in by_id  # empty columns are skipped
    assert db.get_procedure("NOPE") == []


def test_get_required_documents(fixture_db):
    evs = db.get_required_documents("KS-01")
    _check(evs)
    assert [e["evidence_id"] for e in evs] == ["db:required_documents:KS-01:1", "db:required_documents:KS-01:2"]
    assert evs[1]["structured"]["item"] == "Giấy chứng sinh"
    assert "01 bản chính hoặc 01 bản sao" in evs[1]["text"] and "bắt buộc" in evs[1]["text"]
    assert db.get_required_documents("NOPE") == []


def test_get_fees_and_jurisdiction(fixture_db):
    evs = db.get_fees("KS-01")
    _check(evs)
    assert [e["structured"]["value"] for e in evs] == ["miễn lệ phí", "theo HĐND tỉnh", "8.000 đồng"]
    assert evs[2]["source_url"] == "https://daklak.gov.vn/fixture-qd-33"  # provenance per row
    dl = db.get_fees("KS-01", jurisdiction="đắk lắk")
    assert [e["evidence_id"] for e in dl] == ["db:fees:KS-01:1", "db:fees:KS-01:2", "db:fees:KS-01:3"]
    hn = db.get_fees("KS-01", jurisdiction="Hà Nội")
    assert [e["evidence_id"] for e in hn] == ["db:fees:KS-01:1", "db:fees:KS-01:2"]  # ids stable under filter
    assert "phạm vi: toàn quốc" in hn[0]["text"]


def test_get_agency(fixture_db):
    evs = db.get_agency("KS-01")
    _check(evs)
    assert evs[0]["evidence_id"] == "db:agencies:KS-01:1" and evs[0]["section"] == "agency"
    assert evs[0]["structured"]["name"] == "UBND cấp xã nơi cư trú của cha hoặc mẹ"
    assert evs[0]["effective_date"] == "2025-07-01"
    assert db.get_agency("KS-02") == []


def test_get_source(fixture_db):
    [e] = db.get_source("daklak-33/QD-UBND#KS-01")
    _check([e])
    assert e["evidence_id"] == "db:sources:KS-01:daklak-33/QD-UBND" and e["procedure_id"] == "KS-01"
    assert e["source_url"] == "https://daklak.gov.vn/fixture-qd-33" and "Phụ lục, mục 1" in e["text"]
    assert db.get_source("nope#X") == []


def test_read_only(fixture_db):
    with pytest.raises(sqlite3.OperationalError):
        with db._connect() as con:
            con.execute("DELETE FROM procedures")


def test_missing_db_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DB", str(tmp_path / "missing.db"))
    with pytest.raises(FileNotFoundError):
        db.get_procedure("KS-01")


def test_processing_time_cites_fallback_source(tmp_path, monkeypatch):
    # real case 1.003583: moj says only "5"; the loader takes "05 ngày làm việc." from the Đắk Lắk annex
    for d, sid, pt, url in (("moj", "moj-portal#1.003583", "5", "https://moj.gov.vn/x"),
                            ("daklak", "daklak-33/QD-UBND#1.003583", "05 ngày làm việc.", "https://daklak.gov.vn/qd33")):
        (tmp_path / d).mkdir()
        r = json.loads((FIX / "moj" / "KS-01.json").read_text(encoding="utf-8"))
        r.update(procedure_id="1.003583", processing_time=pt)
        r["source"].update(source_id=sid, url=url)
        (tmp_path / d / "1.003583.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    loader.build(tmp_path / "x.db", [tmp_path / "moj", tmp_path / "daklak"], prefer=["moj", "daklak"])
    monkeypatch.setenv("APP_DB", str(tmp_path / "x.db"))
    by_id = {e["evidence_id"]: e for e in db.get_procedure("1.003583")}
    pt = by_id["db:procedures:1.003583:processing_time"]
    assert "05 ngày làm việc." in pt["text"] and pt["source_url"] == "https://daklak.gov.vn/qd33"
    assert by_id["db:procedures:1.003583:summary"]["source_url"] == "https://moj.gov.vn/x"


def test_get_change_notices(tmp_path, monkeypatch):
    out = tmp_path / "cn.db"
    loader.build(out, [FIX / "moj", FIX / "dvc", FIX / "daklak"], prefer=["moj", "dvc", "daklak"])
    con = sqlite3.connect(out)
    for i, (kind, eff) in enumerate((("change_notice", "2025-07-01"), ("change_notice", "2026-01-01"),
                                     ("change_notice", None), ("legal_text", "2026-02-01"))):
        con.execute("INSERT INTO documents (id, kind, title, effective_date, url, retrieved_at, sha256) VALUES (?,?,?,?,?,?,?)",
                    (f"d{i}", kind, f"T{i}", eff, f"https://x.gov.vn/{i}", "2026-10-10", "0"))
        con.execute("INSERT INTO document_procedures VALUES (?, 'KS-01')", (f"d{i}",))
    con.commit(); con.close()
    monkeypatch.setenv("APP_DB", str(out))
    rows = db.get_change_notices("KS-01")
    assert [r["doc_id"] for r in rows] == ["d1", "d0", "d2"]           # newest first, NULL last, legal_text excluded
    assert set(rows[0]) == {"doc_id", "title", "effective_date", "url"} and rows[0]["url"] == "https://x.gov.vn/1"
    assert db.get_change_notices("NOPE") == []


def test_get_change_notices_corpus_v1_db(tmp_path, monkeypatch):
    out = tmp_path / "v1.db"
    con = sqlite3.connect(out)
    con.execute("CREATE TABLE procedures (id TEXT)"); con.commit(); con.close()
    monkeypatch.setenv("APP_DB", str(out))
    assert db.get_change_notices("KS-01") == []
