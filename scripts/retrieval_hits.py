"""Procedure-level retrieval hit rate: hit@1 / hit@3 for a question JSONL.

Usage: uv run python scripts/retrieval_hits.py data/testset.jsonl [--chroma DIR] [--show] [--json OUT]
Accepts either {"question", "procedure_id"} lines or test-set items
({"id", "question", "gold": {"outcome", "procedure_id"}, "accept_procedure_ids"?}). Test-set items are scored only
when gold.outcome is answer/answer_partial and gold.procedure_id is set (out_of_scope, not_in_corpus refusals
and clarify items are skipped and counted). A hit is any id in accept_procedure_ids (default: [gold id]).

Views per question (the first three are the defence story: summary → fused → fused + synonyms):
  resolve:summary      = resolve_candidates(mode="summary", expand=False)  (pre-P18)
  resolve:fused        = resolve_candidates(mode="fused",   expand=False)  (P18)
  resolve:fused+syn    = resolve_candidates(mode="fused",   expand=True)   (P18 + P20 synonyms; the default)
  retrieve / retrieve+syn = retrieve(), unfiltered, distinct procedure_ids in rank order, without / with synonyms
family@1 counts rank 1 inside the gold procedure's sibling group (procedures.variant_of in --db, which the
loader fills from data/variants.yaml, P19): a family hit is one the graph's clarify step can still resolve.
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCORED_OUTCOMES = {"answer", "answer_partial"}


def load(path: str) -> tuple[list[dict], Counter]:
    items, skipped = [], Counter()
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        it = json.loads(line)
        if "gold" in it:
            g = it["gold"]
            if g.get("outcome") not in SCORED_OUTCOMES or not g.get("procedure_id"):
                skipped[g.get("refusal_type") or g.get("outcome") or "no gold"] += 1
                continue
            gold = g["procedure_id"]
        else:
            gold = it["procedure_id"]
        items.append({"id": it.get("id", f"L{n}"), "question": it["question"], "gold": gold,
                      "accept": it.get("accept_procedure_ids") or [gold]})
    return items, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl")
    ap.add_argument("--chroma", default=None)
    ap.add_argument("--show", action="store_true", help="print each question's top-3")
    ap.add_argument("--json", default=None, help="write per-item rankings and the summary here")
    ap.add_argument("--db", default="data/app.db", help="for variant_of families (family@1); skipped if missing")
    args = ap.parse_args(argv)
    if args.chroma:
        os.environ["CHROMA_DIR"] = args.chroma
    from src.tools.rag import reset_cache, resolve_candidates, retrieve
    reset_cache()

    items, skipped = load(args.jsonl)
    family = {}
    if Path(args.db).exists():
        con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        family = {i: v or i for i, v in con.execute("SELECT id, variant_of FROM procedures")}
        con.close()
    fam = lambda pid: family.get(pid, pid)  # noqa: E731

    def res(mode, expand):
        return lambda q: [c["procedure_id"] for c in resolve_candidates(q, k=3, mode=mode, expand=expand)]

    def ret(expand):
        return lambda q: list(dict.fromkeys(e["procedure_id"] for e in retrieve(q, k=15, expand=expand)))[:3]

    views = {"resolve:summary": res("summary", False), "resolve:fused": res("fused", False),
             "resolve:fused+syn": res("fused", True), "retrieve": ret(False), "retrieve+syn": ret(True)}
    hits = {v: [0, 0, 0] for v in views}
    rows = []
    for it in items:
        ranked = {v: f(it["question"]) for v, f in views.items()}
        row = {"id": it["id"], "gold": it["gold"], "question": it["question"], "ranked": ranked}
        for v, r in ranked.items():
            h1, h3 = bool(set(r[:1]) & set(it["accept"])), bool(set(r[:3]) & set(it["accept"]))
            hf = bool(r) and fam(r[0]) in {fam(a) for a in it["accept"]}
            hits[v][0] += h1
            hits[v][1] += h3
            hits[v][2] += hf
            row[v] = "hit@1" if h1 else ("hit@3" if h3 else "miss")
        rows.append(row)
        if args.show:
            flags = " ".join(f"{v}={row[v]:<5}" for v in views)
            print(f"{it['id']:<6} {it['gold']:<10} {flags} fused+syn={ranked['resolve:fused+syn']} | {it['question']}")

    n = len(items)
    print(f"\n{n} scored questions" + (f"; skipped: " + ", ".join(f"{k}={v}" for k, v in skipped.items()) if skipped else ""))
    print("| view | hit@1 | hit@3 | family@1 |\n|---|---|---|---|")
    for v, (h1, h3, hf) in hits.items():
        print(f"| {v} | {h1}/{n} = {h1 / n:.2f} | {h3}/{n} = {h3 / n:.2f} | {hf}/{n} = {hf / n:.2f} |")
    if args.json:
        Path(args.json).write_text(json.dumps({"n": n, "skipped": skipped, "hits": hits, "items": rows},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
