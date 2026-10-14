import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import ingest  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
DIRS = [FIX / "moj", FIX / "dvc", FIX / "daklak", FIX / "bca-portal"]


def by_id(chunks):
    return {c.id: c for c in chunks}


def test_sections_and_ids():
    chunks = by_id(ingest.chunks_from_sources(DIRS))
    ks01 = {cid for cid in chunks if cid.startswith("doc:KS-01:")}
    assert ks01 == {f"doc:KS-01:{s}:0" for s in (
        "summary", "required_documents", "steps", "submission_method", "fees", "agency", "processing_time", "legal_basis")}
    # KS-02 has no fees and no agency: no chunk rather than an empty / invented one
    assert "doc:KS-02:fees:0" not in chunks and "doc:KS-02:agency:0" not in chunks
    assert len(chunks) == 30


def test_prefix_and_metadata():
    c = by_id(ingest.chunks_from_sources(DIRS))["doc:KS-01:required_documents:0"]
    assert c.text.startswith("[Thủ tục: Đăng ký khai sinh] [Mục: Thành phần hồ sơ] ")
    assert "01 bản chính hoặc 01 bản sao" in c.text and "bắt buộc" in c.text
    assert c.metadata == {"procedure_id": "KS-01", "section": "required_documents",
                          "source_id": "moj-0001/QD-BTP#KS-01", "retrieved_at": "2026-10-10", "tier": "corpus",
                          "title": "Đăng ký khai sinh", "source_url": "https://moj.gov.vn/fixture-qd",
                          "effective_date": "2025-07-01", "kind": "procedure_page"}
    assert all(v is not None for v in c.metadata.values())


def test_same_precedence_and_fee_rows_as_db():
    chunks = by_id(ingest.chunks_from_sources(DIRS))
    fees = chunks["doc:KS-01:fees:0"].text
    assert "miễn lệ phí — đăng ký đúng hạn (toàn quốc)" in fees      # moj wins
    assert "8.000 đồng — đăng ký quá hạn (Đắk Lắk)" in fees          # daklak extra row, as in the DB
    assert "50.000 đồng" not in fees                                  # dvc lost
    assert chunks["doc:KS-02:summary:0"].metadata["variant_of"] == "KS-01"


def test_sub_split_with_overlap(tmp_path):
    d = json.loads((FIX / "moj" / "KS-01.json").read_text(encoding="utf-8"))
    d["required_documents"] = [{"item": f"Giấy tờ số {i} " + "chứng minh " * 20, "quantity": 1} for i in range(80)]
    chunks = ingest.chunk_record(d, "moj-x#KS-01")
    rd = [c for c in chunks if c.metadata["section"] == "required_documents"]
    assert len(rd) > 1 and [c.id for c in rd] == [f"doc:KS-01:required_documents:{i}" for i in range(len(rd))]
    for c in rd:
        assert c.text.startswith("[Thủ tục: Đăng ký khai sinh] [Mục: Thành phần hồ sơ] ")
        assert len(c.text.split()) <= ingest.MAX_WORDS + 12
    # last line of piece i is repeated at the start of piece i+1
    assert rd[0].text.split("\n")[-1] == rd[1].text.split("] ", 2)[2].split("\n")[0]


def test_split_long_single_line():
    pieces = ingest.split_words(" ".join(f"w{i}" for i in range(1500)), max_words=600, overlap=60)
    assert len(pieces) == 3 and pieces[1].split()[0] == "w540"


def test_submission_method_text_included():
    d = json.loads((FIX / "moj" / "KS-01.json").read_text(encoding="utf-8"))
    d["submission_method_text"] = "Nộp hồ sơ trực tiếp tại Trung tâm Phục vụ hành chính công cấp xã."
    c = by_id(ingest.chunk_record(d, "moj-x#KS-01"))["doc:KS-01:submission_method:0"]
    assert c.text.endswith("trực tiếp, trực tuyến toàn trình\nNộp hồ sơ trực tiếp tại Trung tâm Phục vụ hành chính công cấp xã.")


def test_variants_in_chunk_metadata(tmp_path):
    vf = tmp_path / "variants.yaml"
    vf.write_text('groups:\n  - root: "CC-01"\n    label: x\n    members: ["CT-01"]\n', encoding="utf-8")
    chunks = by_id(ingest.chunks_from_sources(DIRS, variants=vf))
    assert chunks["doc:CT-01:summary:0"].metadata["variant_of"] == "CC-01"
    assert "variant_of" not in chunks["doc:CC-01:summary:0"].metadata
    assert chunks["doc:KS-02:summary:0"].metadata["variant_of"] == "KS-01"  # record value kept


def test_chroma_telemetry_disabled(tmp_path):
    import os
    client = ingest.chroma_client(tmp_path)
    assert client.get_settings().anonymized_telemetry is False
    store = ingest.open_store(tmp_path, embeddings=object())  # no embedding call happens on open
    assert store._client.get_settings().anonymized_telemetry is False
    assert os.environ["ANONYMIZED_TELEMETRY"] == "False"
