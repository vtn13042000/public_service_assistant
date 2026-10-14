"""The guardrailed graph (architecture.md §4): nodes, the five conditional edges, loop bound, compile.

No business logic here: edge functions read state and return a label. Every edge checks `errors`
first so any failure goes to `refuse_redirect` (L6), never to generation or `finalize`.
"""
from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, StateGraph

from src.nodes import MAX_REWRITES, Deps, make_nodes
from src.state import AgentState

TERMINALS = ("finalize", "clarify", "refuse_redirect", "out_of_scope")


# ---------------------------------------------------------------- the five conditional edges

def after_assess(state: dict) -> str:
    if state.get("errors"):
        return "refuse_redirect"
    need = state.get("need") or {}
    if not need.get("in_scope") or not need.get("retrieve"):
        return "out_of_scope"
    return "resolve_procedure"


def after_resolve(state: dict) -> str:
    if state.get("errors"):
        return "refuse_redirect"
    route = state.get("route")
    if route == "one" and state.get("procedure_id"):
        return "gather_evidence"
    if route == "tie":
        return "clarify"
    return "web_lookup"


def after_grade(state: dict) -> str:
    if state.get("errors") or state.get("discontinued"):  # ROUND-4: a stopped procedure is never drafted
        return "refuse_redirect"
    if (state.get("grades") or {}).get("usable"):
        return "draft_answer"
    return "rewrite_query" if state.get("iteration", 0) < MAX_REWRITES else "refuse_redirect"


def after_decide(state: dict) -> str:
    if state.get("errors"):
        return "refuse_redirect"
    s = (state.get("grades") or {}).get("support")
    if s == "all_supported":
        return "freshness_check"
    if s == "minor_unsupported":
        return "prune_claims"
    return "rewrite_query" if state.get("iteration", 0) < MAX_REWRITES else "refuse_redirect"


def after_freshness(state: dict) -> str:
    if state.get("errors"):
        return "refuse_redirect"
    return "web_check" if (state.get("freshness") or {}).get("notice") else "finalize"


# ---------------------------------------------------------------- build

EDGES = {  # unconditional edges
    "rewrite_query": "gather_evidence",
    "gather_evidence": "grade_relevance",
    "draft_answer": "check_support",
    "prune_claims": "freshness_check",
    "web_check": "finalize",
    "web_lookup": "refuse_redirect",
}
CONDITIONAL = {  # source -> (edge function, possible targets)
    "assess_need": (after_assess, ["resolve_procedure", "out_of_scope", "refuse_redirect"]),
    "resolve_procedure": (after_resolve, ["gather_evidence", "clarify", "web_lookup", "refuse_redirect"]),
    "grade_relevance": (after_grade, ["draft_answer", "rewrite_query", "refuse_redirect"]),
    "check_support": (after_decide, ["freshness_check", "prune_claims", "rewrite_query", "refuse_redirect"]),
    "freshness_check": (after_freshness, ["web_check", "finalize", "refuse_redirect"]),
}


def build_graph(llm, retriever, db, web=None, callbacks=None, *, judge=None, classifier=None, today=None, trace=None,
                config=None):
    """Compiled guardrailed app. Dependencies are injected so tests pass fakes.

    llm: chat model; retriever: object with `retrieve` and `resolve_candidates` (src.tools.rag);
    db: object with the src.tools.db functions; web: `web_search(query) -> list[Evidence]` or None;
    callbacks: LangChain callbacks (LangFuse handler) attached to every invocation; when given and `trace`
    is None, node decisions go to the LangFuse spans via `span_hook()`;
    judge / classifier: structured-output factories for reflection (src.llm.get_structured_judge /
    get_structured_llm); both default to `llm`.
    """
    if trace is None:
        trace = span_hook() if callbacks else (lambda *a, **k: None)
    deps = Deps(llm=llm, rag=retriever, db=db, web=web, judge=judge, classifier=classifier, today=today,
                trace=trace, config=config or {})
    nodes = make_nodes(deps)
    g = StateGraph(AgentState)
    for name, fn in nodes.items():
        g.add_node(name, fn)
    g.set_entry_point("assess_need")
    for src, (fn, targets) in CONDITIONAL.items():
        g.add_conditional_edges(src, fn, {t: t for t in targets})
    for src, dst in EDGES.items():
        g.add_edge(src, dst)
    for t in TERMINALS:
        g.add_edge(t, END)
    app = g.compile()
    if callbacks:
        app = app.with_config({"callbacks": callbacks})
    return app


def span_hook():
    """Trace hook writing each node's decision fields to its LangFuse span (src.tracing.set_span_metadata),
    found through the RunnableConfig of the running node. Never raises."""
    from src.nodes import CURRENT_CONFIG
    from src.tracing import set_span_metadata

    def trace(node: str, **meta) -> None:
        try:
            set_span_metadata(CURRENT_CONFIG.get(), node=node, **meta)
        except Exception:  # noqa: BLE001 — tracing must never break an answer
            pass
    return trace


def export_mermaid(app, path: str | Path = "docs/06_rubric/assets/graph.mmd") -> str:
    graph = app.get_graph() if hasattr(app, "get_graph") else app.bound.get_graph()
    text = graph.draw_mermaid()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return text
