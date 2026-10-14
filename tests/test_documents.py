"""ROUND-4 non-procedure documents: schema/validation, cleaning, loader tables, chunks, run-lock on copies."""
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from src import db, ingest  # noqa: E402
from src.documents import clean_corpus, read_documents  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
RAW = FIX / "docs_raw"
DIRS = [FIX / "moj", FIX / "dvc", FIX / "daklak", FIX / "bca-portal"]
SRC = [str(d) for d in DIRS]


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    import clean_documents
    out = tmp_path_factory.mktemp("clean") / "clean_docs"
    before = {p: p.read_bytes() for p in RAW.rglob("*.json")}
    assert clean_documents.main(["--in", str(RAW), "--out", str(out), "--sources", *SRC]) == 0
    assert {p: p.read_bytes() for p in RAW.rglob("*.json")} == before   # inputs never modified
    return out


def load(out, kind, name):
    return json.loads((out / kind / f"{name}.json").read_text(encoding="utf-8"))


def test_schema_and_validator(capsys):
    import validate_documents
    docs = {d.path.name: d for d in read_documents(RAW)}
    assert "'sha256' is a required property" in docs["change-missing-sha.json"].errors[0]
    assert docs["guidance-in-form-dir.json"].errors == ["kind 'guidance' != directory 'form'"]
    assert docs["form-tt04-to-khai-khai-sinh.json"].ok and not docs["form-tt04-to-khai-khai-sinh.json"].warnings
    w = docs["legal-123-2015-dieu-16.json"].warnings
    assert any("NFC" in x for x in w) and any("HTML" in x for x in w) and any("segmentation" in x for x in w)
    assert validate_documents.main([str(RAW), "--sources", *SRC]) == 1
    out = capsys.readouterr().out
    assert "procedure_ids not in the procedure records: ZZ-99" in out and "duplicate text" in out


def test_clean_actions_and_skips(clean):
    legal = load(clean, "legal_text", "legal-123-2015-dieu-16")
    assert [s["heading"] for s in legal["sections"]] == ["Điều 16. Thủ tục đăng ký khai sinh",
                                                          "Điều 17. Thủ tục đăng ký khai sinh lưu động"]
    t = legal["sections"][0]["text"]
    assert t == unicodedata.normalize("NFC", t) and " " not in t and "&amp;" not in t and "giấy tờ & thấy" in t
    assert "\n\n\n" not in t and "  " not in t
    guide = load(clean, "guidance", "guide-thuong-tru-copy")
    assert guide["sections"][0]["text"] == ("Người thuê nhà được đăng ký thường trú tại chỗ ở hợp pháp do thuê nếu "
                                            "được chủ nhà đồng ý bằng văn bản.")
    assert any("tail cut" in a for a in guide["cleaning_actions"])
    kept = sorted(p.relative_to(clean).as_posix() for p in clean.rglob("*.json"))
    assert kept == ["form/form-tt04-to-khai-khai-sinh.json", "guidance/guide-thuong-tru-copy.json",
                    "legal_text/legal-123-2015-dieu-16.json"]
    rep = (clean / "CLEAN_REPORT.md").read_text(encoding="utf-8")
    for reason in ("'sha256' is a required property", "no existing procedure linked",
                   "kind 'guidance' != directory 'form'", "duplicate text (same cleaned sections) of"):
        assert reason in rep
    assert all(d.ok for d in read_documents(clean))   # output re-validates
    assert len(legal["text_sha256"]) == 64


def test_articles_of_one_file_are_not_duplicates(tmp_path):
    """Per-article documents share the raw file's sha256; only identical cleaned text is a duplicate."""
    src = json.loads((RAW / "legal_text" / "legal-123-2015-dieu-16.json").read_text(encoding="utf-8"))
    for n, text in ((17, "Nội dung điều 17 về khai sinh lưu động cho trẻ em sinh ra tại địa bàn."),
                    (18, "Nội dung điều 18 về đăng ký khai sinh cho trẻ bị bỏ rơi tại địa phương.")):
        p = tmp_path / "in" / "legal_text" / f"dieu-{n}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({**src, "doc_id": f"legal:123-2015-ND-CP:dieu-{n}", "title": f"Nghị định 123, Điều {n}",
                                 "sections": [{"heading": f"Điều {n}.", "text": text}]}, ensure_ascii=False), encoding="utf-8")
    kept, skipped = clean_corpus(read_documents(tmp_path / "in"), None)
    assert len(kept) == 2 and not skipped and kept[0][1]["sha256"] == kept[1][1]["sha256"]


def test_scanned_document_skipped():
    d = next(x for x in read_documents(RAW) if x.path.name == "legal-123-2015-dieu-16.json")
    d.data = {**d.data, "sections": [{"heading": "Trang 1", "text": "— 1 —"}]}
    kept, skipped = clean_corpus([d], None)
    assert not kept and "no OCR" in skipped[0].errors[-1]


def test_loader_tables(clean, tmp_path):
    out = tmp_path / "app_v2.db"
    rep = db.build(out, DIRS, docs=clean)
    assert rep.loaded["documents"] == 3 and rep.loaded["document_sections"] == 5
    con = sqlite3.connect(out)
    assert sorted(con.execute("SELECT doc_id, procedure_id FROM document_procedures")) == [
        ("form:TT04-2020-TT-BTP:to-khai-khai-sinh", "KS-01"), ("form:TT04-2020-TT-BTP:to-khai-khai-sinh", "KS-02"),
        ("guide:daklak:hoi-dap-thuong-tru-2", "CT-01"), ("legal:123-2015-ND-CP:dieu-16", "KS-01")]
    assert con.execute("SELECT kind, jurisdiction, link_method FROM documents WHERE id LIKE 'guide:%'").fetchone() == (
        "guidance", "Đắk Lắk", "procedure_code")
    assert con.execute("SELECT position, heading FROM document_sections WHERE doc_id LIKE 'legal:%' ORDER BY position"
                       ).fetchall()[1] == (2, "Điều 17. Thủ tục đăng ký khai sinh lưu động")
    # without docs: the v1 DB, tables present and empty
    rep1 = db.build(tmp_path / "app.db", DIRS)
    assert rep1.loaded["documents"] == 0 and rep1.loaded["procedures"] == rep.loaded["procedures"]


def test_document_chunks(clean):
    v1 = ingest.chunks_from_sources(DIRS)
    v2 = ingest.chunks_from_sources(DIRS, docs=clean)
    assert [c.id for c in v2[:len(v1)]] == [c.id for c in v1]       # procedure chunks unchanged
    docs = [c for c in v2[len(v1):]]
    assert len(docs) == 2 * 2 + 1 + 2                                # form x2 procedures, guide, legal 2 articles
    assert len({c.id for c in v2}) == len(v2)
    legal = [c for c in docs if c.metadata["kind"] == "legal_text"]
    assert legal[1].text.startswith("[Thủ tục: Đăng ký khai sinh] [Văn bản: Nghị định 123/2015/NĐ-CP, Điều 16–17] "
                                    "[Mục: Điều 17. Thủ tục đăng ký khai sinh lưu động] ")
    m = legal[0].metadata
    assert m["section"] == "legal_basis" and m["doc_id"] == "legal:123-2015-ND-CP:dieu-16" and m["procedure_id"] == "KS-01"
    assert legal[0].id.startswith("doc:KS-01:legal_basis:") and legal[0].id.endswith("-0")
    form = [c for c in docs if c.metadata["kind"] == "form"]
    assert {c.metadata["procedure_id"] for c in form} == {"KS-01", "KS-02"} and form[0].metadata["section"] == "required_documents"
    assert all(v is not None for c in docs for v in c.metadata.values())


def test_runlock_guards_only_shared_artifacts(clean, tmp_path, monkeypatch):
    import build_db
    lock = tmp_path / ".RUNLOCK"
    lock.write_text("w-eval run", encoding="utf-8")
    monkeypatch.setenv("APP_RUNLOCK", str(lock))
    c = ["--conflicts", str(tmp_path / "C.md"), "--sources", *SRC]
    assert build_db.main(["--out", str(tmp_path / "app.db"), *c]) == 3
    assert build_db.main(["--out", str(tmp_path / "app_v2.db"), "--docs", str(clean), *c]) == 0
    assert db.runlock_refusal(target=tmp_path / "chroma") and db.runlock_refusal(target=tmp_path / "chroma_v2") is None


def test_original_version_marked_in_prefix_and_db(tmp_path):
    src = json.loads((RAW / "legal_text" / "legal-123-2015-dieu-16.json").read_text(encoding="utf-8"))
    x = {**src, "original_version": True, "amended_by": ["Nghị định 120/2025/NĐ-CP, Điều 4"],
         "sections": [{"heading": "Điều 16.", "text": "Nội dung gốc của điều 16 về thẩm quyền đăng ký khai sinh."}]}
    p = tmp_path / "docs" / "legal_text" / "d16.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
    d = read_documents(tmp_path / "docs")[0]
    assert d.ok and not any("original_version" in w for w in d.warnings)
    c = ingest.chunk_document(x, {"KS-01": "Đăng ký khai sinh"})[0]
    assert c.text.startswith("[Văn bản gốc – đã sửa đổi] [Thủ tục: Đăng ký khai sinh] [Văn bản: ")
    assert c.metadata["original_version"] is True and c.metadata["amended_by"] == "Nghị định 120/2025/NĐ-CP, Điều 4"
    db.build(tmp_path / "v2.db", DIRS, docs=tmp_path / "docs")
    con = sqlite3.connect(tmp_path / "v2.db")
    assert con.execute("SELECT original_version, amended_by FROM documents").fetchone() == (
        1, '["Nghị định 120/2025/NĐ-CP, Điều 4"]')
    assert "original_version true without amended_by" in __import__("src.documents", fromlist=["x"]).doc_smells(
        {**x, "amended_by": []})


def test_versioned_kinds():
    from src.documents import doc_smells
    form = json.loads((RAW / "form" / "form-tt04-to-khai-khai-sinh.json").read_text(encoding="utf-8"))
    v = {"original_version": True, "amended_by": ["Thông tư 17/2024/TT-BCA"]}
    assert not any("original_version" in w for w in doc_smells({**form, **v}))
    assert any("not legal_text or form" in w for w in doc_smells({**form, **v, "kind": "guidance"}))
