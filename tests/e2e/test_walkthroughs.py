"""The six request walkthroughs of architecture.md §6 on the e2e fixture DB/index with the real local models.

Fixture corpus: tests/e2e/fixtures/moj/*.json (hand-written from the design walkthroughs; not official text).
Needs Ollama (qwen3.5, qwen3.6, bge-m3) → marker `ollama`; skipped when unreachable. Web is disabled
(web=None) so the run is offline and deterministic apart from the models.
Run: uv run pytest -q -m ollama tests/e2e
"""
import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).parent / "fixtures" / "moj"


def _ollama_up() -> bool:
    try:
        names = [m["name"] for m in httpx.get("http://127.0.0.1:11434/api/tags", timeout=2).json().get("models", [])]
        return all(any(n.startswith(m) for n in names) for m in ("qwen3.5", "qwen3.6", "bge-m3"))
    except Exception:
        return False


pytestmark = [pytest.mark.ollama, pytest.mark.skipif(not _ollama_up(), reason="Ollama models not reachable")]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tools_db = pytest.importorskip("src.tools.db")
    from src import db as loader, ingest
    from src.tools import rag
    tmp = tmp_path_factory.mktemp("e2e")
    mp = pytest.MonkeyPatch()
    mp.setenv("APP_DB", str(tmp / "app.db"))
    mp.setenv("CHROMA_DIR", str(tmp / "chroma"))
    loader.build(tmp / "app.db", [FIX])
    ingest.build_index(ingest.chunks_from_sources([FIX]), tmp / "chroma")
    rag.reset_cache()
    yield {"db": tools_db, "rag": rag}
    rag.reset_cache()
    mp.undo()


def ask(world, query, rag=None, **init):
    from src import llm as L
    from src.graph import build_graph
    app = build_graph(L.get_llm(), rag or world["rag"], world["db"], None,
                      judge=L.get_structured_judge, classifier=L.get_structured_llm)
    return app.invoke({"query": query, **init})


def body(s):
    return s["generation"].split("\n\nNguồn:")[0]


def test_w1_documents_clarify_then_answer(world):
    s = ask(world, "Hồ sơ đăng ký khai sinh gồm những gì?")
    assert s["outcome"] == "clarify", (s.get("need"), s.get("candidates"))
    assert "Đăng ký khai sinh" in s["refusal"]["candidates"]
    s = ask(world, "Hồ sơ đăng ký khai sinh gồm những gì?", procedure_id="KS-01")
    assert s["outcome"] in ("answer", "answer_partial"), s.get("claims")
    assert "Tờ khai đăng ký khai sinh theo mẫu" in s["generation"] and "[db:required_documents:" in s["generation"]
    assert all(c["verdict"] == "supported" for c in s["claims"])


def test_w2_fee_nationwide_and_varying(world):
    s = ask(world, "Lệ phí cấp lại thẻ căn cước là bao nhiêu?")
    assert s["outcome"] == "answer", (s.get("candidates"), s.get("claims"), s.get("refusal"))
    assert "70.000 đồng" in s["generation"] and "toàn quốc" in s["generation"]
    s = ask(world, "Lệ phí đăng ký thường trú là bao nhiêu?")
    assert s["outcome"] == "answer_partial" and "tỉnh/thành phố" in s["generation"]


def test_w3_out_of_corpus_redirects_without_facts(world):
    s = ask(world, "Thủ tục nhập tịch cho người nước ngoài?")
    assert s["outcome"] in ("refuse", "out_of_scope")
    if s["outcome"] == "refuse":
        assert s["refusal"]["type"] == "not_in_corpus"
    assert "Tờ khai" not in s["generation"] and "dichvucong.gov.vn" in s["generation"]


def test_w4_false_premise_contradicted(world):
    """Lead P1: khai sinh siblings share "miễn lệ phí (đúng hạn)" in the fixture → sibling-invariant → answer."""
    s = ask(world, "Lệ phí khai sinh là 50.000đ phải không?")
    assert s["need"]["premise"], s["need"]
    assert s["outcome"] == "answer", (s.get("route"), s.get("claims"), s.get("refusal"))
    assert "miễn lệ phí" in s["generation"]
    assert not body(s).lstrip().lower().startswith("đúng"), s["generation"]  # never confirms the premise


def test_w5_personal_case_agency(world):
    s = ask(world, "Con tôi sinh ở Hàn Quốc, mẹ Việt bố Hàn, đăng ký khai sinh ở đâu?")
    assert s["need"]["in_scope"], s["need"]
    assert s.get("procedure_id") == "KS-02", (s.get("candidates"), s.get("route"))
    assert s["outcome"] in ("answer", "answer_partial"), s.get("claims")
    assert "UBND cấp xã nơi cư trú của cha hoặc mẹ là công dân Việt Nam" in s["generation"]
    assert "xác nhận tại cơ quan tiếp nhận" in s["generation"]  # agency → freshness notice


def test_w6_tool_failure_system_error(world):
    class Broken:
        def retrieve(self, *a, **k):
            raise RuntimeError("chroma down")

        def resolve_candidates(self, *a, **k):
            raise RuntimeError("chroma down")
    s = ask(world, "Hồ sơ đăng ký khai sinh gồm những gì?", rag=Broken())
    assert s["outcome"] == "refuse" and s["refusal"]["type"] == "system_error"
    assert "Tờ khai" not in s["generation"]
