"""Baseline = the professor's skeleton, kept as close to the text as runnable (guidance.md A5, A6, Đề tài 5).

Every change from the guidance text is marked `# ADAPT:` with the reason. Behaviours that the
guardrailed graph fixes (architecture.md §4.1) are deliberately kept:
- `decide_next` sends to `generate` when `iteration >= MAX_ITER` (forced generation on exhaustion);
- `web_search -> generate` and `query_db -> generate` with no reflection;
- one `supported` flag for the whole draft (`self_critique`); static `gate` refusal text;
- retrieval over the whole corpus by the raw query (no procedure resolution).

Wiring of the Đề tài 5 nodes (the guidance does not draw it): `self_critique` replaces `grade_or_critique`
(as Phần A says), `gate` sits between `generate` and `finalize`. With `config={"gate": False}` the gate is
removed and the graph is exactly A6 with `self_critique` as the grader.
"""
from __future__ import annotations

import json
import re

from langgraph.graph import END, StateGraph

from src.self_rag import message_text
from src.state import AgentState

MAX_ITER = 2

# Đề tài 5 (4) prompt, verbatim
REFLECT = ('Cho NGỮ CẢNH và TRẢ LỜI nháp, trả JSON '
           '{{"relevant":bool,"supported":"fully|partial|no"}}. '
           'NGỮ CẢNH:{ctx}\nTRẢ LỜI:{ans}')

# ADAPT: route_question is a TODO in A5; minimal keyword router so the `data` branch (DB tool) is reachable.
DATA_WORDS = re.compile(r"lệ phí|\bphí\b|hồ sơ|giấy tờ|cơ quan|nộp ở đâu|bao lâu|thời gian", re.I)


def _ctx(items: list[dict]) -> str:
    return "\n\n".join(d["text"] for d in items)


def make_nodes(llm, retriever, db, web):
    def route_question(state):
        # TODO(theo đề tài) in A5 — ADAPT: keyword router
        return {"route": "data" if DATA_WORDS.search(state["query"]) else "knowledge", "iteration": 0}

    def retrieve_docs(state):
        # ADAPT: our retriever returns Evidence; whole-corpus retrieval by the raw query, as in A4/A5.
        # ADAPT: A6 never increments `iteration`, so the rewrite loop would run to the recursion limit;
        #        count a re-entry here (the skeleton has no rewrite node).
        it = state.get("iteration", 0) + (1 if "documents" in state else 0)
        docs = retriever.retrieve(state["query"], k=5)
        return {"documents": [{"text": d["text"], "meta": {k: d.get(k) for k in ("evidence_id", "procedure_id", "section", "source_url")}}
                              for d in docs], "iteration": it}

    def run_db_query(state):
        # A5: sql = state.get("route_sql", "SELECT 1")  # TODO: text-to-sql
        # ADAPT: free text-to-SQL is out of scope (PLAN §4); templated lookup of the best title match instead.
        hits = db.search_titles(state["query"])
        rows = []
        if hits:
            pid = (hits[0].get("structured") or {}).get("id") or hits[0].get("procedure_id")
            for fn in (db.get_procedure, db.get_required_documents, db.get_fees, db.get_agency):
                rows += fn(pid)
        return {"db_results": [{"text": r["text"], "meta": {"evidence_id": r["evidence_id"]}} for r in rows]}

    def run_web_search(state):
        hits = web(state["query"]) if web else []
        return {"web_results": [{"text": h["text"], "meta": {"url": h.get("source_url")}} for h in hits]}

    def self_critique(state):  # Đề tài 5 (1), verbatim except ADAPT lines
        ctx = '\n'.join(d['text'] for d in state.get('documents', []))
        draft = message_text(llm.invoke(f'Trả lời ngắn từ ngữ cảnh:\n{ctx}\nHỏi: ' + state['query']))  # ADAPT: strip <think>
        r = llm.invoke(REFLECT.format(ctx=ctx[:2000], ans=draft))
        try:
            flags = json.loads(message_text(r))  # ADAPT: strip <think>
        except Exception:
            flags = {'relevant': False, 'supported': 'no'}
        ok = flags.get('relevant') and flags.get('supported') == 'fully'
        return {'generation': draft if ok else None,
                'grades': {'verdict': 'enough' if ok else 'refuse', 'flags': flags}}

    def generate_answer(state):
        # ADAPT: A5 builds context from `documents` only, so the query_db/web_search -> generate paths would
        #        answer with an empty context; include db_results and web_results.
        ctx = _ctx(state.get("documents", []) + state.get("db_results", []) + state.get("web_results", []))
        msg = f"Ngữ cảnh:\n{ctx}\n\nCâu hỏi: {state['query']}\nTrả lời có trích nguồn:"
        return {"generation": message_text(llm.invoke(msg))}

    def gate(state):  # Đề tài 5 (1)
        if (state.get('grades') or {}).get('verdict') == 'refuse':  # ADAPT: .get — db path has no grades
            return {'generation': 'Chưa đủ căn cứ trong kho thủ tục. '
                    'Vui lòng liên hệ cơ quan tiếp nhận để được hướng dẫn.'}
        return {}

    def finalize_answer(state):
        # ADAPT: `outcome` written so eval can compare with the guardrailed variant.
        refused = (state.get("generation") or "").startswith("Chưa đủ căn cứ trong kho thủ tục")
        return {"generation": state["generation"], "outcome": "refuse" if refused else "answer"}

    return {"router": route_question, "retrieve": retrieve_docs, "query_db": run_db_query,
            "web_search": run_web_search, "grade": self_critique, "generate": generate_answer,
            "gate": gate, "finalize": finalize_answer}


def pick_branch(state):
    return state["route"]  # 'knowledge' | 'data'


def decide_next(state):  # A6, verbatim
    v = state["grades"]["verdict"]
    if v == "enough":
        return "generate"
    if state.get("iteration", 0) >= MAX_ITER:
        return "generate"
    return "web" if v == "insufficient" else "rewrite"


def build_graph(llm, retriever, db, web=None, callbacks=None, *, config=None, **_ignored):
    """Compiled baseline app; same signature as `src.graph.build_graph` (extra keyword args ignored)."""
    use_gate = (config or {}).get("gate", True)
    nodes = make_nodes(llm, retriever, db, web)
    g = StateGraph(AgentState)
    for name, fn in nodes.items():
        if name == "gate" and not use_gate:
            continue
        g.add_node(name, fn)
    g.set_entry_point("router")
    g.add_conditional_edges("router", pick_branch, {"knowledge": "retrieve", "data": "query_db"})
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", decide_next, {"generate": "generate", "web": "web_search", "rewrite": "retrieve"})
    g.add_edge("web_search", "generate")
    g.add_edge("query_db", "generate")
    if use_gate:
        g.add_edge("generate", "gate")
        g.add_edge("gate", "finalize")
    else:
        g.add_edge("generate", "finalize")
    g.add_edge("finalize", END)
    app = g.compile()
    if callbacks:
        app = app.with_config({"callbacks": callbacks})
    return app
