"""src.llm settings (offline) + one live round trip per factory (skipped when Ollama is unreachable)."""
import sys
from pathlib import Path
from typing import Literal

import httpx
import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import llm as L  # noqa: E402


def _ollama_up() -> bool:
    try:
        return httpx.get(L.base_url() + "/api/version", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


live = pytest.mark.skipif(not _ollama_up(), reason="Ollama not reachable")


class Verdict(BaseModel):
    supported: Literal["fully", "partial", "no"]


def test_generator_settings():
    m = L.get_llm()
    assert (m.model, m.temperature, m.num_ctx, m.keep_alive, m.reasoning) == ("qwen3.5", 0, 16384, -1, False)
    assert m.base_url == "http://127.0.0.1:11434"


def test_judge_settings():
    m = L.get_judge()
    assert (m.model, m.temperature, m.num_ctx, m.keep_alive, m.reasoning) == ("qwen3.6", 0, 16384, -1, False)


def test_embeddings_settings():
    assert L.get_embeddings().model == "bge-m3"


def test_base_url_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9999")
    assert L._chat("qwen3.5").base_url == "http://127.0.0.1:9999"


def test_generator_model_from_env(monkeypatch):
    for k in ("APP_GENERATOR_MODEL", "APP_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    assert L.generator_model() == "qwen3.5"
    monkeypatch.setenv("APP_LLM_MODEL", "old-name")
    assert L.generator_model() == "old-name"
    monkeypatch.setenv("APP_GENERATOR_MODEL", "qwen3.6")
    assert L.generator_model() == "qwen3.6"
    r = L.get_structured_llm(Verdict)
    first = r.first if hasattr(r, "first") else r.bound.first
    assert first.bound.model == "qwen3.6"
    L.get_llm.cache_clear()
    try:
        assert L.get_llm().model == "qwen3.6"
    finally:
        L.get_llm.cache_clear()


def test_structured_binds_schema():
    r = L.get_structured_llm(Verdict)
    first = r.first if hasattr(r, "first") else r.bound.first
    assert first.kwargs["format"]["properties"]["supported"]["enum"] == ["fully", "partial", "no"]


@live
def test_live_no_think_tag():
    msg = L.get_llm().invoke("Trả lời một từ: thủ đô của Việt Nam?")
    assert msg.content.strip() and "<think>" not in msg.content
    assert msg.usage_metadata["output_tokens"] < 50  # thinking on spends hundreds of tokens


@live
def test_live_structured_enum_enforced():
    v = L.get_structured_llm(Verdict).invoke(
        'Đoạn văn: "Miễn lệ phí đăng ký khai sinh." Câu trả lời: "Miễn lệ phí." '
        'Câu trả lời có được hỗ trợ không? Trả JSON {"supported": ...}')
    assert v.supported in ("fully", "partial", "no")


@live
def test_live_embedding_dim():
    assert len(L.get_embeddings().embed_query("đăng ký khai sinh")) == 1024
