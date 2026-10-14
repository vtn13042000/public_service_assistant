"""Chunking ablation: section chunks (data/chroma, read-only) vs the skeleton's 700/100 character chunks.

Usage: uv run python scripts/chunk_ablation.py data/testset.jsonl [--abl data/processed/abl700/chroma] [--rebuild]
                                                [--chroma data/chroma] [--db data/app.db] [--show]
The 700-char index is built from the same merged records (same text as the section chunks, rendered as one plain
document per procedure with the Vietnamese section labels as headings, no `[Thủ tục: …]` prefix) and split with
RecursiveCharacterTextSplitter(700, 100), as in the course skeleton. It goes to its own directory (default
data/processed/abl700/chroma); data/chroma and data/app.db are only read. Built once; --rebuild rebuilds it.
Both indexes are queried with the same hybrid retriever (`src.tools.rag.retrieve`'s ranking, BM25 + bge-m3, RRF), unfiltered,
synonyms off, so only the chunking differs. Metrics over scored test-set items (as in scripts/retrieval_hits.py):
  proc hit@1 / hit@3  distinct procedure_ids of the top-15 chunks, in rank order
  top-5 purity        share of the top-5 chunks that belong to an accepted gold procedure
  sibling-in-top-5    share of questions whose top-5 holds a chunk of a gold *sibling* (same variant_of family,
                      different procedure): the raw material of variant blending (F2)
Refuses (exit 3) while data/.RUNLOCK exists unless --force (it embeds on the shared Ollama).
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.retrieval_hits import load  # noqa: E402
from src.db import DEFAULT_PREFER, runlock_refusal  # noqa: E402
from src.ingest import SECTION_LABELS, Chunk, build_index, chunks_from_sources  # noqa: E402

CHUNK_CHARS, OVERLAP_CHARS = 700, 100


def char_chunks(section_chunks: list[Chunk]) -> list[Chunk]:
    """One plain document per procedure (title, then `Label:` + body per section), split at 700/100 characters."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_CHARS, chunk_overlap=OVERLAP_CHARS)
    docs: dict[str, dict] = {}
    for c in section_chunks:
        m = c.metadata
        d = docs.setdefault(m["procedure_id"], {"meta": {k: v for k, v in m.items() if k != "section"}, "parts": []})
        body = c.text.split("] ", 2)[-1]  # drop the "[Thủ tục: …] [Mục: …] " prefix
        if m["section"] == "summary":
            d["parts"].insert(0, body)
        else:
            d["parts"].append(f"{SECTION_LABELS[m['section']]}:\n{body}")
    out = []
    for pid, d in sorted(docs.items()):
        for i, piece in enumerate(splitter.split_text("\n\n".join(d["parts"]))):
            out.append(Chunk(f"c700:{pid}:{i}", piece, {**d["meta"], "section": "c700"}))
    return out


def measure(items, family, chroma: str) -> dict:
    os.environ["CHROMA_DIR"] = chroma
    from src.tools.rag import _ranked, reset_cache, rrf
    reset_cache()
    fam = lambda p: family.get(p, p)  # noqa: E731
    h1 = h3 = sib = 0
    purity = 0.0
    rows = []
    for it in items:
        # retrieve(k=15) minus the Evidence wrapping (which rejects the ablation's section id)
        b, d, info = _ranked(it["question"], None, None, 60, expand=False)
        ev = [info[cid][1]["procedure_id"] for cid, _ in rrf([b, d])[:15]]
        procs = list(dict.fromkeys(ev))
        acc = set(it["accept"])
        top5 = ev[:5]
        h1 += bool(set(procs[:1]) & acc)
        h3 += bool(set(procs[:3]) & acc)
        purity += sum(p in acc for p in top5) / max(len(top5), 1)
        s = any(p not in acc and fam(p) in {fam(a) for a in acc} for p in top5)
        sib += s
        rows.append((it["id"], it["gold"], procs[:3], top5, s))
    n = len(items)
    return {"n": n, "h1": h1, "h3": h3, "purity": purity / n, "sib": sib, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl")
    ap.add_argument("--abl", default="data/processed/abl700/chroma")
    ap.add_argument("--chroma", default="data/chroma", help="the section index (read only)")
    ap.add_argument("--db", default="data/app.db", help="variant_of families (read only)")
    ap.add_argument("--sources", nargs="+", default=[f"data/processed/{n}" for n in DEFAULT_PREFER])
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args(argv)
    if Path(args.abl).resolve() == Path(args.chroma).resolve():
        print("--abl must not be the section index", file=sys.stderr)
        return 2
    refusal = runlock_refusal(args.force)
    if refusal:
        print(refusal, file=sys.stderr)
        return 3

    section = chunks_from_sources(args.sources, DEFAULT_PREFER)
    c700 = char_chunks(section)
    print(f"section chunks: {len(section)}; 700/100 char chunks: {len(c700)} "
          f"(mean {sum(len(c.text) for c in c700) / len(c700):.0f} chars)")
    if args.rebuild or not Path(args.abl).exists():
        print(f"built {build_index(c700, args.abl)} chunks into {args.abl}")

    items, skipped = load(args.jsonl)
    family = {}
    if Path(args.db).exists():
        con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        family = {i: v or i for i, v in con.execute("SELECT id, variant_of FROM procedures")}
        con.close()
    res = {"section chunks + prefix": measure(items, family, args.chroma),
           "700/100 char chunks": measure(items, family, args.abl)}
    n = len(items)
    print(f"\n{args.jsonl}: {n} scored questions; retrieve() unfiltered, synonyms off")
    print("| chunking | proc hit@1 | proc hit@3 | top-5 purity | sibling in top-5 |\n|---|---|---|---|---|")
    for name, r in res.items():
        print(f"| {name} | {r['h1']}/{n} = {r['h1'] / n:.2f} | {r['h3']}/{n} = {r['h3'] / n:.2f} | "
              f"{r['purity']:.2f} | {r['sib']}/{n} = {r['sib'] / n:.2f} |")
    if args.show:
        for name, r in res.items():
            print(f"\n## {name}")
            for row in r["rows"]:
                print(*row, sep="  ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
