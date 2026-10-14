import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from src import db  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


@pytest.fixture
def built(tmp_path):
    out = tmp_path / "app.db"
    rep = db.build(out, [FIX / "moj", FIX / "dvc"], prefer="moj")
    con = sqlite3.connect(out)
    yield con, rep, out
    con.close()


def q(con, sql, *a):
    return con.execute(sql, a).fetchall()


def test_schema_sql_matches_design_doc():
    assert db.SCHEMA_SQL.strip() == db.doc_schema_sql().strip()


def test_row_counts(built):
    con, rep, _ = built
    assert rep.loaded == {"sources": 3, "procedures": 2, "required_documents": 4, "fees": 2, "agencies": 1,
                          "procedures_fts": 2, "documents": 0, "document_sections": 0, "document_procedures": 0}
    assert not rep.skipped


def test_precedence_moj_wins(built):
    con, _, _ = built
    assert q(con, "SELECT source_id, agency_summary FROM procedures WHERE id='KS-01'") == [
        ("moj-0001/QD-BTP#KS-01", "UBND cấp xã nơi cư trú của cha hoặc mẹ (toàn quốc)")]
    assert q(con, "SELECT COUNT(*) FROM required_documents WHERE procedure_id='KS-01'") == [(2,)]
    assert {r[0] for r in q(con, "SELECT source_id FROM fees WHERE procedure_id='KS-01'")} == {"moj-0001/QD-BTP#KS-01"}
    # the losing source still has a provenance row
    assert q(con, "SELECT url FROM sources WHERE source_id='dvc#KS-01'") == [
        ("https://dichvucong.gov.vn/fixture-1.004873",)]


def test_prefer_dvc_flips_precedence(tmp_path):
    out = tmp_path / "app.db"
    db.build(out, [FIX / "moj", FIX / "dvc"], prefer="dvc")
    con = sqlite3.connect(out)
    assert q(con, "SELECT source_id, fee_summary FROM procedures WHERE id='KS-01'") == [("dvc#KS-01", "50.000 đồng")]
    con.close()


def test_summaries(built):
    con, _, _ = built
    assert q(con, "SELECT fee_summary FROM procedures WHERE id='KS-01'") == [
        ("miễn lệ phí — đăng ký đúng hạn (toàn quốc); theo HĐND tỉnh — đăng ký quá hạn (theo tỉnh)",)]
    # unknown fee/agency stays NULL, never an invented "miễn"
    assert q(con, "SELECT fee_summary, agency_summary, variant_of FROM procedures WHERE id='KS-02'") == [
        (None, None, "KS-01")]
    assert q(con, "SELECT position, mandatory, quantity, quantity_text FROM required_documents"
                  " WHERE procedure_id='KS-01' ORDER BY position") == [
        (1, 1, 1, None), (2, 1, None, "01 bản chính hoặc 01 bản sao")]


def test_new_procedure_columns(built):
    con, _, _ = built
    ch, lb, cond = q(con, "SELECT channels, legal_basis, conditions FROM procedures WHERE id='KS-01'")[0]
    assert json.loads(ch) == ["trực tiếp", "trực tuyến toàn trình"]
    assert json.loads(lb) == ["Luật Hộ tịch 2014"] and cond is None


def test_sources_kind_and_locator(built):
    con, _, _ = built
    assert dict(q(con, "SELECT source_id, kind FROM sources")) == {
        "moj-0001/QD-BTP#KS-01": "moj_decision", "dvc#KS-01": "national_db_page",
        "dvc-hanoi#KS-02": "provincial_portal_page"}
    assert q(con, "SELECT locator FROM sources WHERE kind='moj_decision'") == [("Mục I.1, tr. 3",)]
    assert db.source_kind("bca-15/QD-BCA#1.001", {"bca-15": "other"}) == "other"
    assert db.source_kind("xyz#1") == "other"


def test_fts_title_search(built):
    con, _, _ = built
    rows = q(con, "SELECT p.id FROM procedures_fts f JOIN procedures p ON p.rowid = f.rowid"
                  " WHERE procedures_fts MATCH ? ORDER BY bm25(procedures_fts)", "\"nước ngoài\"")
    assert rows == [("KS-02",)]
    assert len(q(con, "SELECT rowid FROM procedures_fts WHERE procedures_fts MATCH 'khai AND sinh'")) == 2


def test_conflicts_reported(built):
    _, rep, _ = built
    text = "\n".join(rep.conflicts)
    assert "KS-01" in text and "receiving_agency" in text and "fees" in text
    assert "required_documents (count)" in text
    assert "KS-02" not in text


def test_idempotent_rebuild(built, tmp_path):
    _, rep1, out = built
    rep2 = db.build(out, [FIX / "moj", FIX / "dvc"], prefer="moj")
    assert rep1.loaded == rep2.loaded


def test_invalid_record_skipped(tmp_path):
    rep = db.build(tmp_path / "x.db", [FIX / "invalid", FIX / "moj"], prefer="moj")
    assert len(rep.skipped) == 1 and rep.loaded["procedures"] == 1
    errs = " ".join(rep.skipped[0].errors)
    assert "quantity" in errs and "retrieved_at" in errs and "source_id" in errs


def test_validator_cli(capsys):
    import validate_records
    assert validate_records.main([str(FIX / "moj"), str(FIX / "dvc")]) == 0
    assert validate_records.main([str(FIX / "invalid")]) == 1
    out = capsys.readouterr().out
    assert "fees missing" in out  # KS-02 smell is a warning, not an error


def test_sheet_and_diff_scripts(tmp_path):
    import compare_sources
    import make_verification_sheet
    sheet, diff = tmp_path / "v.md", tmp_path / "d.md"
    srcs = [str(FIX / "moj"), str(FIX / "dvc")]
    assert make_verification_sheet.main(["--n", "10", "--seed", "42", "--sources", *srcs, "--out", str(sheet)]) == 0
    s = sheet.read_text(encoding="utf-8")
    assert s.count("☐") > 10 and "KS-01" in s and "KS-02" in s
    assert compare_sources.main(["--a", srcs[0], "--b", srcs[1], "--out", str(diff)]) == 0
    d = diff.read_text(encoding="utf-8")
    assert "in both: 1" in d and "UBND cấp huyện" in d


def test_kind_rules():
    k = db.source_kind
    assert k("moj-1234/QD-BTP#1.004873") == "moj_decision"
    assert k("bca-15/QD-BCA-C06#1.001") == "bca_decision"
    assert k("bca-portal#1.001") == "ministry_portal_page"
    assert k("daklak-33/QD-UBND#1.004873") == "provincial_decision"
    assert k("dvc#1") == k("dvc-national#1") == "national_db_page"
    assert k("dvc-hanoi#1") == "provincial_portal_page"
    assert k("foo#1") == "other"


def test_unknown_prefix_is_other_with_note(tmp_path):
    src = tmp_path / "misc"
    src.mkdir()
    r = json.loads((FIX / "dvc" / "KS-02.json").read_text(encoding="utf-8"))
    r["source"]["source_id"] = "foo-1#KS-02"
    (src / "KS-02.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    rep = db.build(tmp_path / "x.db", [src, tmp_path / "missing"])
    con = sqlite3.connect(tmp_path / "x.db")
    assert q(con, "SELECT kind FROM sources") == [("other",)]
    con.close()
    notes = "\n".join(rep.notes)
    assert "foo-1#KS-02" in notes and "does not exist" in notes


def test_default_precedence_order():
    assert db.source_order(["d/daklak", "d/bca-portal", "d/x", "d/moj", "d/bca"]) == [
        "moj", "bca", "bca-portal", "daklak", "x"]


def test_daklak_fees_added_when_another_source_wins(tmp_path):
    out = tmp_path / "app.db"
    rep = db.build(out, [FIX / "daklak", FIX / "dvc", FIX / "moj"])  # default prefer: moj wins
    con = sqlite3.connect(out)
    assert q(con, "SELECT source_id FROM procedures WHERE id='KS-01'") == [("moj-0001/QD-BTP#KS-01",)]
    assert q(con, "SELECT value, jurisdiction, source_id FROM fees WHERE procedure_id='KS-01' ORDER BY rowid") == [
        ("miễn lệ phí", "toàn quốc", "moj-0001/QD-BTP#KS-01"),
        ("theo HĐND tỉnh", "theo tỉnh", "moj-0001/QD-BTP#KS-01"),
        ("8.000 đồng", "Đắk Lắk", "daklak-33/QD-UBND#KS-01")]
    assert q(con, "SELECT fee_summary FROM procedures WHERE id='KS-01'")[0][0].endswith(
        "; 8.000 đồng — đăng ký quá hạn (Đắk Lắk)")
    # moj's agency still wins; daklak's fees are additive, not a fee conflict
    assert q(con, "SELECT name FROM agencies WHERE procedure_id='KS-01'") == [("UBND cấp xã nơi cư trú của cha hoặc mẹ",)]
    con.close()
    conflicts = "\n".join(rep.conflicts)
    assert "daklak=`8.000" not in conflicts and "daklak=`UBND cấp xã`" in conflicts
    assert any("+1 provincial fee row" in n for n in rep.notes)


def test_daklak_winner_fees_not_duplicated(tmp_path):
    out = tmp_path / "app.db"
    db.build(out, [FIX / "daklak", FIX / "moj"], prefer=["daklak"])
    con = sqlite3.connect(out)
    assert q(con, "SELECT value, jurisdiction FROM fees WHERE procedure_id='KS-01'") == [("8.000 đồng", "Đắk Lắk")]
    con.close()


def test_bca_portal_is_not_bca_decision():
    # regression (w-dvc report): the old prefix map sent "bca-portal#…" to bca_decision
    assert db.source_kind("bca-portal#1.004222") == "ministry_portal_page"
    assert db.source_kind("bca-5230/QD-BCA-C06#1.004222") == "bca_decision"


def test_moj_portal_is_ministry_portal_page():
    assert db.source_kind("moj-portal#1.004873") == "ministry_portal_page"
    assert db.source_kind("moj-1872/QD-BTP#1.004873") == "moj_decision"


def test_bare_number_processing_time_falls_back(tmp_path):
    # real case 1.003583: moj page says only "5", the Đắk Lắk annex says "05 ngày làm việc."
    for d, sid, pt in (("moj", "moj-portal#1.003583", "5"), ("daklak", "daklak-33/QD-UBND#1.003583", "05 ngày làm việc.")):
        (tmp_path / d).mkdir()
        r = json.loads((FIX / "moj" / "KS-01.json").read_text(encoding="utf-8"))
        r.update(procedure_id="1.003583", processing_time=pt)
        r["source"]["source_id"] = sid
        (tmp_path / d / "1.003583.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    rep = db.build(tmp_path / "x.db", [tmp_path / "moj", tmp_path / "daklak"], prefer=["moj", "daklak"])
    con = sqlite3.connect(tmp_path / "x.db")
    assert q(con, "SELECT processing_time, processing_time_source_id, source_id FROM procedures") == [
        ("05 ngày làm việc.", "daklak-33/QD-UBND#1.003583", "moj-portal#1.003583")]
    con.close()
    assert any("processing_time '5'" in n for n in rep.notes)


def test_processing_time_source_is_winner_when_not_bare(built):
    con, _, _ = built
    assert q(con, "SELECT processing_time, processing_time_source_id FROM procedures WHERE id='KS-01'") == [
        ("ngay trong ngày làm việc", "moj-0001/QD-BTP#KS-01")]


def test_variants_yaml_fills_missing_variant_of(tmp_path):
    vf = tmp_path / "variants.yaml"
    vf.write_text('groups:\n  - root: "KS-01"\n    label: x\n    members: ["KS-02", "CC-01"]\n'
                  '  - root: "KS-09"\n    label: y\n    members: ["KS-01"]\n', encoding="utf-8")
    rep = db.build(tmp_path / "x.db", [FIX / "moj", FIX / "dvc", FIX / "bca-portal"], prefer="moj", variants=vf)
    con = sqlite3.connect(tmp_path / "x.db")
    got = dict(q(con, "SELECT id, variant_of FROM procedures"))
    con.close()
    assert got["CC-01"] == "KS-01"      # filled from the yaml
    assert got["KS-02"] == "KS-01"      # record value (same as yaml)
    assert got["KS-01"] == "KS-09"      # no record value -> yaml
    assert got["CT-01"] is None
    assert db.variant_of_for({"procedure_id": "KS-02", "variant_of": "X"}, {"KS-02": "KS-01"}) == "X"  # record wins
    assert db.load_variants(tmp_path / "missing.yaml") == {}
    assert not any("variants.yaml says" in n for n in rep.notes)


def test_builders_refuse_while_runlock_exists(tmp_path, monkeypatch, capsys):
    import build_db
    import build_index
    lock = tmp_path / ".RUNLOCK"
    lock.write_text("w-graph 2026-10-10T04:45:23Z outcome-pass", encoding="utf-8")
    monkeypatch.setenv("APP_RUNLOCK", str(lock))
    out, chroma = tmp_path / "app.db", tmp_path / "chroma"
    srcs = [str(FIX / "moj"), str(FIX / "dvc")]
    assert build_db.main(["--out", str(out), "--sources", *srcs, "--conflicts", str(tmp_path / "C.md")]) == 3
    assert build_index.main(["--sources", *srcs, "--chroma", str(chroma)]) == 3
    err = capsys.readouterr().err
    assert err.count("REFUSED") == 2 and "w-graph 2026-10-10T04:45:23Z outcome-pass" in err
    assert not out.exists() and not chroma.exists()
    # --force overrides (DB only; no embeddings needed)
    assert build_db.main(["--out", str(out), "--sources", *srcs, "--conflicts", str(tmp_path / "C.md"), "--force"]) == 0
    assert out.exists()
    # no lock -> no refusal
    lock.unlink()
    assert db.runlock_refusal() is None
