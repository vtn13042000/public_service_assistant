"""CLI demo: `uv run python -m src.cli "câu hỏi" [--variant guardrailed|baseline] [--preset v1|v2|v3|v4|v5] [--locality ...]
[--procedure ID]`. `--variant guardrailed` runs the v5 preset (DEFAULT_PRESET) unless `--preset` names another (src/presets.py).

Prints the answer, outcome, citations, refusal type and, when LangFuse is configured, the trace URL.
`--procedure` answers the clarify follow-up (the user picked one of the listed procedures).
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

from src.presets import DEFAULT_PRESET, GUARDRAILED_PRESETS, resolve_preset


def build_app(variant: str, callbacks=None, trace=None, preset: str | None = None):
    """Real dependencies: local Ollama models, Chroma/BM25 retriever, SQLite DB, allowlisted web.
    The graph flags come from the named preset (src/presets.py); its environment is applied before src.tools is imported."""
    from src.presets import apply_env, graph_config, resolve_preset
    name = resolve_preset(variant, preset)
    apply_env(name)
    from src import llm as L
    from src.tools import db, rag
    try:
        from src.tools.web import web_search
    except ImportError:  # web tool optional: web_lookup/web_check degrade to notices without links
        web_search = None
    if variant == "baseline":
        from src.baseline import build_graph
        return build_graph(L.get_llm(), rag, db, web_search, callbacks)
    from src.graph import build_graph
    return build_graph(L.get_llm(), rag, db, web_search, callbacks,
                       judge=L.get_structured_judge, classifier=L.get_structured_llm, trace=trace, config=graph_config(name))


def _tracing(name: str, variant: str, preset: str | None = None):
    """(callbacks, trace hook, handler) — all None when LangFuse is not configured."""
    try:
        from src.tracing import get_callback
        handler = get_callback(name, tags=[f"variant={variant}", f"preset={preset}"],
                               metadata={"variant": variant, "preset": preset})
    except Exception:  # noqa: BLE001 — tracing is optional for the CLI
        return None, None, None
    if handler is None:
        return None, None, None

    from src.graph import span_hook
    trace = span_hook()
    return [handler], trace, handler


def _trace_url(handler) -> str | None:
    """LangFuse URL of this run's trace (handler.last_trace_id), after flushing; None if unavailable."""
    try:
        from langfuse import get_client

        from src.tracing import flush
        flush()
        tid = getattr(handler, "last_trace_id", None)
        return get_client().get_trace_url(trace_id=tid) if tid else None
    except Exception:  # noqa: BLE001 — tracing is optional
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Trợ lý thủ tục hành chính (Self-RAG)")
    ap.add_argument("question")
    ap.add_argument("--variant", choices=["guardrailed", "baseline"], default="guardrailed")
    ap.add_argument("--preset", choices=list(GUARDRAILED_PRESETS),
                    help=f"guardrailed flag set (default {DEFAULT_PRESET}, the recommended configuration)")
    ap.add_argument("--locality", help="tỉnh/thành phố (lệ phí theo tỉnh)")
    ap.add_argument("--procedure", help="procedure_id chosen after a clarify prompt")
    ap.add_argument("--json", action="store_true", help="print the final state as JSON")
    a = ap.parse_args(argv)
    try:
        preset = resolve_preset(a.variant, a.preset)
    except ValueError as e:
        ap.error(str(e))

    name = f"cli-{uuid.uuid4().hex[:8]}"
    callbacks, trace, handler = _tracing(name, a.variant, preset)
    app = build_app(a.variant, callbacks, trace, preset=preset)
    init = {"query": a.question}
    if a.variant == "guardrailed":
        init["preset"] = preset
    if a.locality:
        init["locality"] = a.locality
    if a.procedure:
        init["procedure_id"] = a.procedure
    state = app.invoke(init)

    if a.json:
        print(json.dumps({**state, "preset": preset}, ensure_ascii=False, indent=2, default=str))
        return 0
    print(state.get("generation") or "")
    print("\n---")
    print(f"preset: {preset}")
    print(f"outcome: {state.get('outcome')}")
    if state.get("refusal"):
        print(f"refusal: {state['refusal'].get('type')}")
    if state.get("procedure_id"):
        print(f"procedure: {state['procedure_id']}")
    for c in state.get("citations") or []:
        print(f"cite: {c['evidence_id']}  {c.get('source_url') or ''}  ({(c.get('retrieved_at') or '')[:10]})")
    if state.get("errors"):
        print(f"errors: {state['errors']}")
    url = _trace_url(handler) if handler else None
    if url:
        print(f"trace: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
