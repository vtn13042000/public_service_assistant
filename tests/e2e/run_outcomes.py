"""Outcome-only run of data/testset.jsonl through a graph variant (no RAGAS judge).

uv run python tests/e2e/run_outcomes.py [--variant guardrailed|baseline] [--out PATH] [--ids T-001,T-002] [--web]
    [--testset PATH] [--config '{"f2_rule": "distinguishing_words"}']

Writes one JSON line per item (id, category, gold outcome/refusal/procedure, predicted outcome/refusal/procedure,
route, candidates[:3], seconds) and prints the gold × predicted outcome histogram plus procedure hit rate.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUTCOMES = ["answer", "answer_partial", "clarify", "refuse", "out_of_scope"]


def build(variant: str, web: bool, config: dict | None = None, trace=None):
    from src import llm as L
    from src.tools import db, rag
    web_fn = None
    if web:
        from src.tools.web import web_search as web_fn
    if variant == "baseline":
        from src.baseline import build_graph
        return build_graph(L.get_llm(), rag, db, web_fn)
    from src.graph import build_graph
    return build_graph(L.get_llm(), rag, db, web_fn, judge=L.get_structured_judge, classifier=L.get_structured_llm,
                       config=config or None, trace=trace)


def histogram(rows: list[dict]) -> str:
    m = collections.Counter((r["gold_outcome"], r["outcome"]) for r in rows)
    golds = [o for o in OUTCOMES if any(r["gold_outcome"] == o for r in rows)]
    preds = OUTCOMES + sorted({r["outcome"] for r in rows} - set(OUTCOMES))
    lines = ["| gold \\ predicted | " + " | ".join(preds) + " | n |", "|---" * (len(preds) + 2) + "|"]
    for g in golds:
        cells = [str(m[(g, p)] or "") for p in preds]
        lines.append(f"| {g} | " + " | ".join(cells) + f" | {sum(m[(g, p)] for p in preds)} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="guardrailed", choices=["guardrailed", "baseline"])
    ap.add_argument("--testset", default=str(ROOT / "data" / "testset.jsonl"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--web", action="store_true")
    ap.add_argument("--config", default=None, help="graph config as JSON (guardrailed only)")
    ap.add_argument("--trace-tag", default=None, help="trace each question to LangFuse with this tag (e.g. dev-w-graph)")
    a = ap.parse_args(argv)
    hook = None
    if a.trace_tag:
        from src.graph import span_hook
        from src.tracing import get_callback
        hook = span_hook()
    items = [json.loads(ln) for ln in open(a.testset, encoding="utf-8") if ln.strip()]
    if a.ids:
        keep = set(a.ids.split(","))
        items = [i for i in items if i["id"] in keep]
    app = build(a.variant, a.web, json.loads(a.config) if a.config else None, trace=hook)
    out = Path(a.out or ROOT / "docs/05_log/workers/w-graph" / f"outcomes_{a.variant}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with out.open("w", encoding="utf-8") as f:
        for it in items:
            init = {"query": it["question"]}
            if it.get("locality"):
                init["locality"] = it["locality"]
            t = time.time()
            cfg = {"callbacks": [get_callback(f"dev-{it['id']}", [a.trace_tag, "development"],
                                               {"item": it["id"], "graph_config": a.config})]} if a.trace_tag else None
            try:
                s = app.invoke(init, config=cfg)
                if any("does not exist" in e for e in s.get("errors") or []):  # index rebuilt under us: reopen, retry once
                    from src.tools import rag
                    rag.reset_cache()
                    s = app.invoke(init)
                    s.setdefault("errors", [])
                    s["retried_after_index_rebuild"] = True
            except Exception as exc:  # noqa: BLE001 — record and continue
                s = {"outcome": "crash", "errors": [repr(exc)]}
            g = it["gold"]
            accept = set(it.get("accept_procedure_ids") or []) | ({g.get("procedure_id")} - {None})
            row = {"id": it["id"], "category": it["category"], "question": it["question"],
                   "gold_outcome": g["outcome"], "gold_refusal": g.get("refusal_type"), "gold_procedure": g.get("procedure_id"),
                   "outcome": s.get("outcome"), "refusal": (s.get("refusal") or {}).get("type"),
                   "procedure_id": s.get("procedure_id"), "procedure_ok": (s.get("procedure_id") in accept) if accept else None,
                   "route": s.get("route"), "need": s.get("need"), "errors": s.get("errors"),
                   "retried": bool(s.get("retried_after_index_rebuild")),
                   "candidates": [{k: c.get(k) for k in ("procedure_id", "score", "core", "lexical")} for c in (s.get("candidates") or [])[:3]],
                   "claims": [(c.get("type"), c.get("verdict"), c.get("text", "")[:80]) for c in s.get("claims") or []
                              if c.get("verdict") != "supported"],
                   "generation": (s.get("generation") or "")[:600], "seconds": round(time.time() - t, 1)}
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{row['id']} {row['category']:<22} gold={row['gold_outcome']:<14} pred={row['outcome']:<14} "
                  f"pid={row['procedure_id']} ok={row['procedure_ok']} {row['seconds']}s", flush=True)
    print("\n" + histogram(rows))
    hits = [r["procedure_ok"] for r in rows if r["procedure_ok"] is not None and r["gold_outcome"] in ("answer", "answer_partial")]
    if hits:
        print(f"\nprocedure hit on gold answer/partial items: {sum(hits)}/{len(hits)}")
    print(f"exact outcome match: {sum(r['outcome'] == r['gold_outcome'] for r in rows)}/{len(rows)}")
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
