"""R6: the stack needs no cloud key and every model object points at the local Ollama server."""
import sys
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class _S(BaseModel):
    x: bool


def test_no_cloud_keys_needed(monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    from src import llm as L
    L.get_llm.cache_clear(); L.get_judge.cache_clear(); L.get_embeddings.cache_clear()
    objs = [L.get_llm(), L.get_judge(), L.get_embeddings()]
    s = L.get_structured_llm(_S)
    objs.append((s.first if hasattr(s, "first") else s.bound.first).bound)
    for o in objs:
        assert urlparse(o.base_url).hostname in LOCAL_HOSTS, o


def test_no_cloud_sdk_imported_by_src():
    bad = ("openai", "anthropic", "langchain_openai", "langchain_anthropic", "google.generativeai")
    for p in (ROOT / "src").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        for b in bad:
            assert f"import {b}" not in text and f"from {b}" not in text, f"{p} imports {b}"
