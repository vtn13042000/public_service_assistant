"""LangFuse tracing (architecture.md §7): one trace per question, one span per node, decisions as span metadata.

Usage in the graph runner:

    cb = get_callback(trace_name="T-017", tags=["variant=guardrailed"], metadata={"test_id": "T-017"})
    graph.invoke(state, config={"callbacks": [cb]})
    flush()                      # before the process exits

Usage inside a node (LangGraph passes `config` to nodes that accept it):

    def assess_need(state, config):
        need = ...
        set_span_metadata(config, need=need)
        return {"need": need}

Reading traces back: LangFuse v4 runs in "events_only" mode, where the legacy /api/public/traces endpoints
return an error; use `fetch_observations(trace_id)` (GET /api/public/v2/observations).

Server: self-hosted (infra/langfuse). Keys and LANGFUSE_BASE_URL come from the repo-root .env, loaded here
if the variables are not already set. Tracing never breaks the app: helpers swallow and log their own errors.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
os.environ.setdefault("LANGFUSE_BASE_URL", os.environ.get("LANGFUSE_HOST", "http://127.0.0.1:3000"))

from langchain_core.callbacks import BaseCallbackManager  # noqa: E402
from langfuse import get_client  # noqa: E402
from langfuse.langchain import CallbackHandler  # noqa: E402

log = logging.getLogger(__name__)
_TRACE_META_MAX = 200  # LangFuse coerces trace-level metadata values to str, ≤200 chars


def _short(v: Any) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s[:_TRACE_META_MAX]


def _jsonable(v: Any) -> Any:
    return json.loads(json.dumps(v, ensure_ascii=False, default=str))


class TracedCallbackHandler(CallbackHandler):
    """LangFuse LangChain handler that stamps trace name, tags and trace metadata on the root run.

    The stock handler reads these only from the root run's config metadata (`langfuse_trace_name`,
    `langfuse_tags`); injecting them here means callers only pass `callbacks=[handler]`.
    """

    def __init__(self, trace_name: str, tags: list[str], metadata: dict | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.trace_name = trace_name
        self.trace_tags = list(tags)
        self.trace_metadata = {k: _short(v) for k, v in (metadata or {}).items()}

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, tags=None, metadata=None, **kw):
        if parent_run_id is None:
            metadata = {**self.trace_metadata, **(metadata or {}),
                        "langfuse_trace_name": self.trace_name, "langfuse_tags": self.trace_tags}
        return super().on_chain_start(serialized, inputs, run_id=run_id, parent_run_id=parent_run_id,
                                      tags=tags, metadata=metadata, **kw)


def get_callback(trace_name: str, tags: list[str], metadata: dict | None = None) -> TracedCallbackHandler:
    """A fresh handler for one question. Use one handler per trace; read `handler.last_trace_id` afterwards."""
    return TracedCallbackHandler(trace_name, tags, metadata)


def set_span_metadata(config: Any = None, **fields: Any) -> bool:
    """Record decision fields (need, candidates, verdicts, outcome, refusal_type, …) on the current node's span.

    With `config` (the RunnableConfig LangGraph passes to the node) the span is found through the handler's
    run map, which is exact even across threads. Without it, falls back to the current OTel span.
    Returns True if metadata was attached. Never raises.
    """
    payload = _jsonable(fields)
    try:
        cbm = (config or {}).get("callbacks") if isinstance(config, dict) else None
        if isinstance(cbm, BaseCallbackManager) and cbm.parent_run_id is not None:
            for h in cbm.handlers + cbm.inheritable_handlers:
                obs = getattr(h, "_runs", {}).get(cbm.parent_run_id) if isinstance(h, CallbackHandler) else None
                if obs is not None:
                    obs.update(metadata=payload)
                    return True
        get_client().update_current_span(metadata=payload)
        return True
    except Exception as e:  # noqa: BLE001 — tracing must never break a node
        log.warning("set_span_metadata failed: %s", e)
        return False


def flush() -> None:
    """Send buffered spans (call before exit / before reading a trace back)."""
    try:
        get_client().flush()
    except Exception as e:  # noqa: BLE001
        log.warning("langfuse flush failed: %s", e)


def fetch_observations(trace_id: str, *, wait: float = 90, min_count: int = 1,
                       until: Callable[[list[dict]], bool] | None = None) -> list[dict]:
    """All observations of one trace (with metadata, model and trace_context: traceName, tags), via the v2 API.

    Ingestion is asynchronous (SDK batch → web → queue → worker → ClickHouse), so this polls every 2 s until
    at least `min_count` observations are visible and `until(observations)` (if given) is true, or `wait`
    seconds pass; then it returns whatever is visible. Transient HTTP errors are retried within the wait.
    """
    base = os.environ["LANGFUSE_BASE_URL"].rstrip("/")
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    params = {"traceId": trace_id, "fields": "core,basic,metadata,io,model,usage,trace_context", "limit": 1000}
    deadline = time.time() + wait
    data: list[dict] = []
    while True:
        try:
            r = httpx.get(f"{base}/api/public/v2/observations", params=params, auth=auth, timeout=10)
            r.raise_for_status()
            data = r.json().get("data", [])
        except httpx.HTTPError as e:
            if time.time() >= deadline:
                raise
            log.info("fetch_observations retry: %s", e)
        if (len(data) >= min_count and (until is None or until(data))) or time.time() >= deadline:
            return data
        time.sleep(2)
