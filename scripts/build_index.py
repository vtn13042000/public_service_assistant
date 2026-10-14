"""Build the Chroma `corpus` collection (section chunks, bge-m3) from canonical records. Drops and rebuilds.

Usage: uv run python scripts/build_index.py [--sources DIR...] [--prefer moj bca bca-portal daklak]
           [--chroma data/chroma] [--db data/app.db]
Reads records with the same precedence as scripts/build_db.py. With --db, checks that the index and the
DB cover the same procedure_ids (they must be rebuilt together, data-model.md §4).
--docs DIR also indexes cleaned non-procedure documents (data/clean_docs; ROUND-4), one chunk per document section
per linked procedure (src/ingest.py:chunk_document).
Refuses (exit 3) while data/.RUNLOCK exists unless --force (PROTOCOL "Shared artifacts lock"); only the shared
data/chroma is guarded, so a copy (--chroma data/chroma_v2) may be built while a run holds the lock.
"""
import argparse
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import DEFAULT_PREFER, runlock_refusal  # noqa: E402
from src.ingest import build_index, chroma_dir, chunks_from_sources  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", nargs="+", default=[f"data/processed/{n}" for n in DEFAULT_PREFER])
    ap.add_argument("--force", action="store_true", help="build even if data/.RUNLOCK exists (only on the lead's explicit go)")
    ap.add_argument("--variants", default=None, help="sibling groups (default data/variants.yaml if present)")
    ap.add_argument("--prefer", nargs="+", default=DEFAULT_PREFER)
    ap.add_argument("--chroma", default=None, help="Chroma dir (default env CHROMA_DIR or data/chroma)")
    ap.add_argument("--db", default=None, help="check procedure_id coverage against this DB")
    ap.add_argument("--docs", default=None, help="cleaned documents dir (e.g. data/clean_docs); default: none")
    args = ap.parse_args(argv)
    refusal = runlock_refusal(args.force, target=args.chroma or chroma_dir())
    if refusal:
        print(refusal, file=sys.stderr)
        return 3

    for d in args.sources:
        if not Path(d).is_dir():
            print(f"NOTE source dir `{d}` does not exist; skipped")
    chunks = chunks_from_sources(args.sources, args.prefer, args.variants, args.docs)
    if not chunks:
        print("no valid records; index not built", file=sys.stderr)
        return 1
    t0 = time.time()
    n = build_index(chunks, args.chroma)
    pids = {c.metadata["procedure_id"] for c in chunks}
    by_section = Counter(c.metadata["section"] for c in chunks)
    print(f"Built {args.chroma or chroma_dir()} collection `corpus`: {n} chunks, {len(pids)} procedures "
          f"in {time.time() - t0:.1f}s")
    print("  per section: " + ", ".join(f"{s}={c}" for s, c in sorted(by_section.items())))
    print("  per kind: " + ", ".join(f"{k}={c}" for k, c in sorted(Counter(c.metadata["kind"] for c in chunks).items())))
    if args.docs:
        print(f"  documents indexed: {len({c.metadata['doc_id'] for c in chunks if 'doc_id' in c.metadata})}")
    split = Counter((c.metadata["procedure_id"], c.metadata["section"]) for c in chunks if "doc_id" not in c.metadata)
    print(f"  sub-split sections (>1 chunk): {sum(1 for v in split.values() if v > 1)}")
    if args.db:
        con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        db_ids = {r[0] for r in con.execute("SELECT id FROM procedures")}
        con.close()
        if db_ids != pids:
            print(f"MISMATCH with {args.db}: only in DB {sorted(db_ids - pids)}; only in index {sorted(pids - db_ids)}")
            return 1
        print(f"  procedure_ids match {args.db} ({len(db_ids)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
