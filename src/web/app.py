"""Local web UI: `uv run python -m src.web.app` → http://127.0.0.1:8000 (docs/03_design/web-ui.md).

One page (`GET /`), one question endpoint (`POST /ask`), one reachability check (`GET /health`).
Single turn by design: the server keeps no history. The only follow-up is the clarify click, which re-sends
the same question with `procedure_id` (the CLI's `--procedure`). Graphs are built once at startup with the
same dependency wiring as `src/cli.py`; LangFuse handlers are attached per request through the invoke config
(as `eval/run_variant.py` does), so each question gets its own trace id.
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable

# The web tool's fallback backends (duckduckgo, bing) call the internet directly; the UI stays on the
# localhost SearxNG unless the operator overrides APP_WEB_BACKEND explicitly.
os.environ.setdefault("APP_WEB_BACKEND", "searxng")

import httpx  # noqa: E402
from fastapi import BackgroundTasks, FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from langchain_core.callbacks import BaseCallbackHandler  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from src.presets import apply_env, graph_config, resolve_preset  # noqa: E402
from src.web.structure import answer_parts  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
VARIANTS = ("guardrailed", "baseline")
DEFAULT_VARIANT = "guardrailed"
RECURSION_LIMIT = 50  # same as eval/run_variant.py
HOST, PORT = "127.0.0.1", 8000
LANGFUSE_UI = "http://127.0.0.1:3000"


class AskRequest(BaseModel):
    query: str
    locality: str | None = None
    procedure_id: str | None = None
    variant: str = DEFAULT_VARIANT


class CallCounter(BaseCallbackHandler):
    """Counts model calls (chat and completion endpoints) for one question (same as eval's counter)."""

    def __init__(self) -> None:
        self.calls = 0

    def on_llm_start(self, *a: Any, **k: Any) -> None:
        self.calls += 1

    def on_chat_model_start(self, *a: Any, **k: Any) -> None:
        self.calls += 1


# ---------------------------------------------------------------- wiring

def real_deps(tracing: bool = True) -> dict:
    """Real dependencies, as in src/cli.py: local Ollama models, Chroma/BM25 retriever, SQLite DB, web tool.
    The guardrailed preset's environment is applied first: it is read when src.tools.rag is imported."""
    apply_env(resolve_preset("guardrailed"))
    from src import llm as L
    from src.graph import span_hook
    from src.tools import db, rag
    try:
        from src.tools.web import web_search
    except ImportError:  # web tool optional: web_lookup/web_check degrade to notices without links
        web_search = None
    return {"llm": L.get_llm(), "retriever": rag, "db": db, "web": web_search,
            "judge": L.get_structured_judge, "classifier": L.get_structured_llm,
            "trace": span_hook() if tracing else None}


def build_apps(deps: dict) -> dict:
    """One compiled graph per variant, built once and reused for every request.
    guardrailed runs the default preset's flags (src/presets.py DEFAULT_PRESET), the same table the CLI and eval use."""
    from src.baseline import build_graph as build_baseline
    from src.graph import build_graph
    return {
        "guardrailed": build_graph(deps["llm"], deps["retriever"], deps["db"], deps.get("web"),
                                   judge=deps.get("judge"), classifier=deps.get("classifier"),
                                   trace=deps.get("trace"), config=graph_config(resolve_preset("guardrailed")),
                                   **deps.get("graph_kw", {})),
        "baseline": build_baseline(deps["llm"], deps["retriever"], deps["db"], deps.get("web")),
    }


def make_tracer() -> Callable[[str, str], Any] | None:
    """Factory of per-request LangFuse handlers, or None when LangFuse is not configured."""
    try:
        from src.tracing import get_callback  # loads the repo-root .env
    except Exception:  # noqa: BLE001 — tracing is optional
        return None
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return None

    def tracer(name: str, variant: str, preset: str):
        try:
            return get_callback(name, tags=[f"variant={variant}", f"preset={preset}", "source=web"],
                                metadata={"variant": variant, "preset": preset, "source": "web"})
        except Exception:  # noqa: BLE001
            return None
    return tracer


def trace_url(trace_id: str | None) -> str | None:
    """LangFuse UI link for a trace; falls back to the local UI root + /trace/<id>."""
    if not trace_id:
        return None
    try:
        from langfuse import get_client
        return get_client().get_trace_url(trace_id=trace_id)
    except Exception:  # noqa: BLE001
        return f"{LANGFUSE_UI}/trace/{trace_id}"


def _flush() -> None:
    try:
        from src.tracing import flush
        flush()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- response shaping

def to_response(state: dict, variant: str, preset: str) -> dict:
    """The JSON the page renders, read from the final graph state only."""
    refusal = state.get("refusal")
    return {
        "variant": variant,
        "preset": preset,
        "outcome": state.get("outcome"),
        "generation": state.get("generation") or "",
        "citations": [{"evidence_id": c.get("evidence_id"), "source_url": c.get("source_url"),
                       "retrieved_at": c.get("retrieved_at")} for c in state.get("citations") or []],
        "refusal": ({k: refusal.get(k) for k in ("type", "reason", "portal_url", "agency", "missing", "title",
                                                  "procedure_id", "since", "basis")} if refusal else None),
        "candidates": [{"procedure_id": c.get("procedure_id"), "title": c.get("title")}
                       for c in state.get("candidates") or []] if state.get("outcome") == "clarify" else [],
        "procedure_id": state.get("procedure_id"),
        "freshness": state.get("freshness"),
        "gaps": state.get("gaps") or [],
        "errors": list(state.get("errors") or []),
        # answer / answer_partial only: the same text split by part for the summary-first card (src/web/structure.py)
        "parts": answer_parts(state),
    }


# ---------------------------------------------------------------- app

def create_app(deps: dict | None = None, tracer: Callable | None = None, tracing: bool = True) -> FastAPI:
    """Build the FastAPI app. Tests pass fake `deps` (see tests/fakes.py) and `tracing=False`."""
    tracer = tracer if tracer is not None else (make_tracer() if tracing else None)
    apps = build_apps(deps if deps is not None else real_deps(tracing=tracer is not None))
    api = FastAPI(title="Trợ lý thủ tục hành chính", docs_url=None, redoc_url=None)

    @api.get("/")
    def index():
        return FileResponse(STATIC / "index.html", media_type="text/html; charset=utf-8")

    @api.post("/ask")
    def ask(req: AskRequest, background: BackgroundTasks):
        query = req.query.strip()
        if not query:
            raise HTTPException(422, "query is empty")
        if req.variant not in VARIANTS:
            raise HTTPException(422, f"variant must be one of {VARIANTS}")
        preset = resolve_preset(req.variant)
        init: dict[str, Any] = {"query": query}
        if req.variant == "guardrailed":  # the baseline graph has no preset / locality / procedure inputs
            init["preset"] = preset
            if req.locality and req.locality.strip():
                init["locality"] = req.locality.strip()
            if req.procedure_id:
                init["procedure_id"] = req.procedure_id
        counter = CallCounter()
        handler = tracer(f"web-{uuid.uuid4().hex[:8]}", req.variant, preset) if tracer else None
        t0 = time.perf_counter()
        state = apps[req.variant].invoke(init, config={"callbacks": [h for h in (handler, counter) if h],
                                                       "recursion_limit": RECURSION_LIMIT})
        out = to_response(state, req.variant, preset)
        tid = getattr(handler, "last_trace_id", None) if handler else None
        out.update({"latency_s": round(time.perf_counter() - t0, 3), "model_calls": counter.calls,
                    "trace_id": tid, "trace_url": trace_url(tid)})
        if handler:
            background.add_task(_flush)
        return out

    @api.get("/health")
    def health():
        return check_health()

    @api.get("/procedures")
    def procedures():
        """The "Thủ tục" tab's list: every procedure in data/app.db, compact (src/web/catalog.py; fixed SQL, no model)."""
        from src.web.catalog import procedure_list
        rows = procedure_list()
        return {"count": len(rows), "procedures": rows}

    @api.get("/procedures/{code}")
    def procedure(code: str):
        """One procedure's values with their sources, fetched only when the user opens that row."""
        from src.web.catalog import procedure_detail
        d = procedure_detail(code)
        if d is None:
            raise HTTPException(404, f"unknown procedure code {code!r}")
        return d

    @api.get("/presets")
    def presets():
        """Which preset each selector value runs (the page labels its options from this)."""
        return {v: resolve_preset(v) for v in VARIANTS}

    return api


def check_health() -> dict:
    """Reachability of the local services (localhost only, 2 s timeouts)."""
    def get(url: str) -> dict:
        try:
            r = httpx.get(url, timeout=2)
            return {"ok": r.status_code < 400, "status": r.status_code}
        except httpx.HTTPError as e:
            return {"ok": False, "error": type(e).__name__}

    ollama = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    langfuse = os.environ.get("LANGFUSE_BASE_URL", LANGFUSE_UI).rstrip("/")
    searx = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080").rstrip("/")
    out = {"ollama": get(f"{ollama}/api/tags"), "langfuse": get(f"{langfuse}/api/public/health"),
           "searxng": get(f"{searx}/healthz")}
    try:
        from src.tools.db import db_path
        p = db_path()
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            out["db"] = {"ok": True, "procedures": con.execute("SELECT COUNT(*) FROM procedures").fetchone()[0]}
            for t in ("documents", "document_sections"):  # corpus v2 only; absent on a v1 database
                try:
                    out["db"][t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except sqlite3.OperationalError:
                    out["db"][t] = None
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        out["db"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out["ok"] = all(v["ok"] for k, v in out.items() if k in ("ollama", "db"))
    return out


def main() -> None:
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    uvicorn.run(create_app(), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
