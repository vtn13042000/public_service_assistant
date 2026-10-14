"""R5: a traced LangGraph run reaches the self-hosted LangFuse and can be read back through the public API."""
import os
import sys
import uuid
from pathlib import Path
from typing import TypedDict

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import tracing  # noqa: E402  (loads .env)

BASE = os.environ.get("LANGFUSE_BASE_URL", "http://127.0.0.1:3000")
AUTH = (os.environ.get("LANGFUSE_PUBLIC_KEY", ""), os.environ.get("LANGFUSE_SECRET_KEY", ""))


def _up() -> bool:
    try:
        return httpx.get(BASE + "/api/public/health", timeout=2).status_code == 200 and all(AUTH)
    except httpx.HTTPError:
        return False


# network: talks to the local LangFuse server (and Ollama for the LLM test); skipped when it is not running.
pytestmark = [pytest.mark.network,
              pytest.mark.skipif(not _up(), reason="LangFuse not reachable or keys missing (run infra/langfuse/up.sh)")]


def _complete(names: set[str], meta_key: str | None = None, meta_node: str | None = None):
    """Predicate for fetch_observations: all named spans visible (and one node's metadata key, if given)."""
    def ok(obs: list[dict]) -> bool:
        by = {o.get("name"): o for o in obs}
        if not names <= set(by):
            return False
        return meta_key is None or meta_key in ((by[meta_node].get("metadata") or {}))
    return ok


class S(TypedDict, total=False):
    query: str
    need: dict
    outcome: str


def _graph():
    from langgraph.graph import END, START, StateGraph

    def assess_need(state: S, config) -> S:
        need = {"retrieve": True, "intent": "fee", "procedure_hint": "khai sinh"}
        assert tracing.set_span_metadata(config, need=need)
        return {"need": need}

    def finalize(state: S, config) -> S:
        tracing.set_span_metadata(config, outcome="answer", refusal_type=None)
        return {"outcome": "answer"}

    g = StateGraph(S)
    g.add_node("assess_need", assess_need)
    g.add_node("finalize", finalize)
    g.add_edge(START, "assess_need")
    g.add_edge("assess_need", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


def test_trace_roundtrip():
    run = uuid.uuid4().hex[:8]
    name = f"pytest-tracing-{run}"
    tags = ["variant=test", f"run={run}"]
    cb = tracing.get_callback(name, tags, {"test_id": name, "variant": "test"})
    out = _graph().invoke({"query": "Lệ phí đăng ký khai sinh?"}, config={"callbacks": [cb]})
    assert out["outcome"] == "answer"
    tracing.flush()
    assert cb.last_trace_id

    obs = tracing.fetch_observations(cb.last_trace_id, min_count=3,  # root graph span + 2 nodes
                                     until=_complete({"assess_need", "finalize"}, "need", "assess_need"))
    assert obs, "trace not visible through /api/public/v2/observations"
    assert {o["traceName"] for o in obs} == {name}
    assert all(set(tags) <= set(o["tags"]) for o in obs)
    by_name = {o["name"]: o for o in obs}
    assert by_name["assess_need"]["metadata"]["variant"] == "test"  # trace metadata propagated to spans
    assert {"assess_need", "finalize"} <= set(by_name)
    assert by_name["assess_need"]["metadata"]["need"]["intent"] == "fee"
    assert by_name["finalize"]["metadata"]["outcome"] == "answer"


def test_set_span_metadata_never_raises():
    assert tracing.set_span_metadata(None, x=1) in (True, False)
    assert tracing.set_span_metadata({"callbacks": None}, x=object()) in (True, False)


def _ollama_up() -> bool:
    try:
        from src.llm import base_url
        return httpx.get(base_url() + "/api/version", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama not reachable")
def test_llm_calls_are_generations():
    from pydantic import BaseModel

    from src.llm import get_llm, get_structured_llm

    class V(BaseModel):
        relevant: bool

    run = uuid.uuid4().hex[:8]
    cb = tracing.get_callback(f"pytest-llm-{run}", ["variant=test"], {})
    from langchain_core.runnables import RunnableLambda
    chain = RunnableLambda(lambda q: q, name="root") | (lambda q: {
        "chat": get_llm().invoke(q).content,
        "structured": get_structured_llm(V).invoke(f'Câu hỏi "{q}" có liên quan tới khai sinh không? JSON {{"relevant": bool}}'),
    })
    chain.invoke("Lệ phí đăng ký khai sinh?", config={"callbacks": [cb]})
    tracing.flush()
    obs = tracing.fetch_observations(
        cb.last_trace_id, min_count=4,
        until=lambda o: sum(x["type"] == "GENERATION" and bool(x.get("model")) for x in o) >= 2)
    gens = [o for o in obs if o["type"] == "GENERATION"]
    assert len(gens) == 2, [(o["type"], o["name"]) for o in obs]
    assert all((o.get("model") or "").startswith("qwen3.5") for o in gens), [o.get("model") for o in gens]
