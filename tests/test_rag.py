"""RAG tool tests. Pure tests always run; index tests need local Ollama with bge-m3 (marker `ollama`)."""
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import ingest  # noqa: E402
from src.tools import rag  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
DIRS = [FIX / "moj", FIX / "dvc", FIX / "daklak", FIX / "bca-portal"]


def _ollama_up() -> bool:
    try:
        tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2).json()
        return any(m["name"].startswith("bge-m3") for m in tags.get("models", []))
    except Exception:
        return False


needs_ollama = [pytest.mark.ollama, pytest.mark.skipif(not _ollama_up(), reason="Ollama/bge-m3 not reachable")]


def test_rrf_order():
    fused = rag.rrf([["a", "b", "c"], ["c", "a", "d"]])
    assert [i for i, _ in fused] == ["a", "c", "b", "d"]
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)


def test_tokenize_adds_unaccented_forms():
    assert rag.tokenize("Đăng ký") == ["đăng", "dang", "ký", "ky"]


def test_expand_query_uses_synonyms_yaml():
    e = rag.expand_query("Lệ phí cấp lại CCCD là bao nhiêu?")
    assert e.startswith("Lệ phí cấp lại CCCD là bao nhiêu? ") and "căn cước" in e and "cấp lại" in e
    assert "thường trú" in rag.expand_query("xoa ho khau")   # matched without diacritics
    assert rag.expand_query("thủ tục gì đó") == "thủ tục gì đó"


def test_normalize_abbrev_uses_abbreviations_yaml():
    assert rag.normalize_abbrev("Đk tạm trú cho sv ko") == "đăng ký tạm trú cho sinh viên không"
    assert rag.normalize_abbrev("con 15t làm cccd") == "con 15 tuổi làm căn cước công dân"
    assert rag.normalize_abbrev("phí 10k, khai sinh") == "phí 10k, khai sinh"   # whole tokens only


def test_abbrev_flag_default_off_and_feeds_both_rankers(monkeypatch):
    assert rag.ABBREV_DEFAULT is False   # env RAG_ABBREV unset in tests
    seen = []
    monkeypatch.setattr(rag, "_state", lambda path=None: seen.append(1) or {"n": 0})
    calls = []
    monkeypatch.setattr(rag, "normalize_abbrev", lambda q: calls.append(q) or q)
    rag._ranked("đk khai sinh", None, None, 5)
    assert calls == []
    rag._ranked("đk khai sinh", None, None, 5, abbrev=True)
    assert calls == ["đk khai sinh"]


@pytest.fixture(scope="module")
def index(tmp_path_factory, monkeypatch_module):
    path = tmp_path_factory.mktemp("chroma")
    monkeypatch_module.setenv("CHROMA_DIR", str(path))
    ingest.build_index(ingest.chunks_from_sources(DIRS), path)
    rag.reset_cache()
    yield path
    rag.reset_cache()


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.mark.parametrize("_", [None], ids=["index"])
@pytest.mark.usefixtures("index")
class TestIndex:
    pytestmark = needs_ollama

    def test_evidence_shape(self, _):
        ev = rag.retrieve("hồ sơ đăng ký khai sinh", k=3)
        assert len(ev) == 3
        for e in ev:
            assert e["tier"] == "corpus" and e["evidence_id"].startswith(f"doc:{e['procedure_id']}:{e['section']}:")
            assert e["source_url"] and e["retrieved_at"] and e["text"].startswith("[Thủ tục: ")
            assert e["structured"] is None

    def test_filters_applied_before_fusion(self, _):
        ev = rag.retrieve("lệ phí bao nhiêu", procedure_id="KS-01", section="fees", k=5)
        assert [e["evidence_id"] for e in ev] == ["doc:KS-01:fees:0"]
        ev = rag.retrieve("thẻ căn cước", procedure_id="KS-01", k=10)
        assert ev and {e["procedure_id"] for e in ev} == {"KS-01"}
        ev = rag.retrieve("giấy tờ", section=["required_documents", "fees"], k=10)
        assert {e["section"] for e in ev} <= {"required_documents", "fees"} and len(ev) == 7
        assert rag.retrieve("x", procedure_id="NOPE") == []

    def test_relevant_procedure_first(self, _):
        assert rag.retrieve("thủ tục cấp thẻ căn cước", k=1)[0]["procedure_id"] == "CC-01"
        assert rag.retrieve("phi dang ky thuong tru", section="fees", k=1)[0]["procedure_id"] == "CT-01"

    def test_resolve_candidates(self, _):
        c = rag.resolve_candidates("đăng ký khai sinh có yếu tố nước ngoài", k=3)
        assert c[0]["procedure_id"] == "KS-02" and c[0]["title"] == "Đăng ký khai sinh có yếu tố nước ngoài"
        assert len({x["procedure_id"] for x in c}) == 3 and c[0]["score"] >= c[1]["score"]

    def test_resolve_modes(self, _):
        q = "đăng ký khai sinh có yếu tố nước ngoài"
        for mode in ("fused", "summary"):
            c = rag.resolve_candidates(q, k=4, mode=mode)
            assert c[0]["procedure_id"] == "KS-02" and len({x["procedure_id"] for x in c}) == 4
        # fused can place a procedure found only through body text (CT-01 fee chunk mentions "trực tuyến")
        assert rag.resolve_candidates("nộp trực tuyến 10.000 đồng", k=1, mode="fused")[0]["procedure_id"] == "CT-01"
        with pytest.raises(ValueError):
            rag.resolve_candidates(q, mode="nope")

    def test_synonym_flag(self, _):
        # "CCCD" appears in no fixture text; only the expansion lets BM25 reach CC-01's "căn cước" chunks
        b_off, _d, _i = rag._ranked("CCCD", None, None, 30, expand=False)
        b_on, _d, _i = rag._ranked("CCCD", None, None, 30, expand=True)
        assert b_off == [] and b_on and b_on[0].startswith("doc:CC-01:")
        assert rag.retrieve("cấp CCCD", k=1, expand=True)[0]["procedure_id"] == "CC-01"

    def test_abbrev_reaches_dense_query(self, _, monkeypatch):
        got = []
        st = rag._state()
        orig = st["store"].similarity_search_with_score
        monkeypatch.setattr(st["store"], "similarity_search_with_score", lambda q, **kw: got.append(q) or orig(q, **kw))
        rag._ranked("đk khai sinh", None, None, 5, abbrev=True)
        assert got == ["đăng ký khai sinh"]

    def test_rebuild_is_idempotent(self, _):
        assert ingest.build_index(ingest.chunks_from_sources(DIRS)) == 30
        rag.reset_cache()
        assert len(rag.retrieve("căn cước", k=50)) == 30


@pytest.mark.parametrize("_", [None], ids=["docs-index"])
@pytest.mark.ollama
@pytest.mark.skipif(not _ollama_up(), reason="Ollama/bge-m3 not reachable")
def test_documents_retrievable_but_not_used_for_resolution(_, tmp_path, monkeypatch):
    """ROUND-4: document chunks come back from retrieve (filtered by procedure/section) as valid corpus evidence;
    resolve_candidates ranks over procedure_page chunks only."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import clean_documents
    clean = tmp_path / "clean_docs"
    assert clean_documents.main(["--in", str(FIX / "docs_raw"), "--out", str(clean), "--sources", *map(str, DIRS)]) == 0
    path = tmp_path / "chroma_v2"
    ingest.build_index(ingest.chunks_from_sources(DIRS, docs=clean), path)
    monkeypatch.setenv("CHROMA_DIR", str(path))
    rag.reset_cache()
    try:
        q = "công chức tư pháp ghi nội dung khai sinh vào Sổ hộ tịch"   # wording only in the legal article
        ev = rag.retrieve(q, procedure_id="KS-01", section="legal_basis", k=3)
        assert ev[0]["text"].startswith("[Thủ tục: Đăng ký khai sinh] [Văn bản: Nghị định 123/2015/NĐ-CP")
        assert ev[0]["evidence_id"].startswith("doc:KS-01:legal_basis:") and ev[0]["tier"] == "corpus"
        b, d, info = rag._ranked(q, None, None, 50, kind="procedure_page")
        assert info and all(m["kind"] == "procedure_page" for _t, m in info.values())
        assert not any("Văn bản:" in t for t, _m in info.values())
        assert rag.resolve_candidates("đăng ký khai sinh", k=1)[0]["procedure_id"] in {"KS-01", "KS-02"}
    finally:
        rag.reset_cache()


def test_kind_filter_ignored_on_v1_index(monkeypatch):
    """A corpus-v1 index has no `kind` metadata: the procedure_page filter must not empty it."""
    class Store:
        def similarity_search_with_score(self, q, k, filter=None):
            assert filter is None
            return []
    st = {"n": 1, "has_kind": False, "metas": [{"procedure_id": "A", "section": "summary"}], "ids": ["doc:A:summary:0"],
          "docs": ["đăng ký khai sinh"], "bm25": rag.BM25Okapi([rag.tokenize("đăng ký khai sinh")]), "store": Store()}
    monkeypatch.setattr(rag, "_state", lambda path=None: st)
    _b, _d, info = rag._ranked("khai sinh", None, None, 5, kind="procedure_page", expand=False)
    assert list(info) == ["doc:A:summary:0"]


@pytest.mark.ollama
@pytest.mark.skipif(not _ollama_up(), reason="Ollama/bge-m3 not reachable")
def test_sync_index_equals_full_rebuild(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import clean_documents
    clean = tmp_path / "clean_docs"
    assert clean_documents.main(["--in", str(FIX / "docs_raw"), "--out", str(clean), "--sources", *map(str, DIRS)]) == 0
    old = ingest.chunks_from_sources(DIRS, docs=clean)
    # start from a stale index: one chunk text changed, one metadata changed, one extra chunk, one missing
    stale = [ingest.Chunk(c.id, c.text + " (cũ)", c.metadata) if n == 0 else
             ingest.Chunk(c.id, c.text, {**c.metadata, "effective_date": "2000-01-01"}) if n == 1 else c
             for n, c in enumerate(old[:-1])]
    stale.append(ingest.Chunk("doc:KS-01:fees:deadbeef-0", "[Thủ tục: x] [Mục: Phí, lệ phí] y", {**old[0].metadata}))
    ingest.build_index(stale, tmp_path / "c")
    rep = ingest.sync_index(old, tmp_path / "c")
    assert rep == {"deleted": 1, "added": 1, "reembedded": 1, "metadata": 1, "unchanged": len(old) - 3}
    got = ingest.open_store(tmp_path / "c")._collection.get(include=["documents", "metadatas"])
    assert {i: (t, m) for i, t, m in zip(got["ids"], got["documents"], got["metadatas"])} == \
        {c.id: (c.text, c.metadata) for c in old}
    assert ingest.sync_index(old, tmp_path / "c", dry_run=True)["unchanged"] == len(old)
    # additions only (no re-embedded chunk in the batch): must not call delete with an empty list
    ingest.open_store(tmp_path / "c")._collection.delete(ids=[old[-1].id])
    assert ingest.sync_index(old, tmp_path / "c")["added"] == 1


def test_kind_scoped_bm25_ignores_other_kinds():
    """Resolution's BM25 statistics come from procedure_page chunks only: adding documents leaves its scores unchanged."""
    proc = ["đăng ký khai sinh cho trẻ em", "cấp thẻ căn cước", "đăng ký thường trú"]
    docs = ["khai sinh khai sinh khai sinh nghị định", "khai sinh thông tư"]
    metas = [{"kind": "procedure_page"}] * 3 + [{"kind": "legal_text"}] * 2
    st = {"n": 5, "metas": metas, "docs": proc + docs, "bm25": rag.BM25Okapi([rag.tokenize(d) for d in proc + docs])}
    q = rag.tokenize("khai sinh")
    scoped = list(rag._bm25_for(st, "procedure_page").get_scores(q))
    alone = list(rag.BM25Okapi([rag.tokenize(d) for d in proc]).get_scores(q))
    assert scoped[:3] == pytest.approx(alone) and scoped[3:] == [0.0, 0.0]
