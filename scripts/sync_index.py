"""Bring an existing Chroma `corpus` collection in line with the current records + documents, embedding only what changed.

Usage: uv run python scripts/sync_index.py --chroma data/chroma_v2 --docs data/clean_docs [--db data/app_v2.db] [--dry-run]
Compares the chunks `build_index.py` would build (same sources, precedence, variants, documents) with the collection by id:
  removed ids            -> deleted
  new ids                -> embedded and added
  same id, text changed  -> re-embedded (upsert)
  same id and text, metadata changed -> metadata updated in place (no embedding)
The result has the same ids, texts and metadata as a full rebuild; a test checks that. Refuses (exit 3) on the shared
data/chroma while data/.RUNLOCK exists unless --force, like build_index.py.
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import DEFAULT_PREFER, runlock_refusal  # noqa: E402
from src.ingest import chroma_dir, chunks_from_sources, sync_index  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", nargs="+", default=[f"data/processed/{n}" for n in DEFAULT_PREFER])
    ap.add_argument("--prefer", nargs="+", default=DEFAULT_PREFER)
    ap.add_argument("--variants", default=None)
    ap.add_argument("--docs", default=None, help="cleaned documents dir (e.g. data/clean_docs)")
    ap.add_argument("--chroma", default=None, help="Chroma dir (default env CHROMA_DIR or data/chroma)")
    ap.add_argument("--db", default=None, help="check procedure_id coverage against this DB")
    ap.add_argument("--dry-run", action="store_true", help="report the differences only")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    path = Path(args.chroma or chroma_dir())
    refusal = runlock_refusal(args.force, target=path)
    if refusal:
        print(refusal, file=sys.stderr)
        return 3
    if not path.exists():
        print(f"{path} does not exist; use scripts/build_index.py", file=sys.stderr)
        return 2
    chunks = chunks_from_sources(args.sources, args.prefer, args.variants, args.docs)
    t0 = time.time()
    rep = sync_index(chunks, path, dry_run=args.dry_run)
    print(f"{'Dry run' if args.dry_run else 'Synced'} {path}: target {len(chunks)} chunks; "
          + ", ".join(f"{k}={v}" for k, v in rep.items()) + f" in {time.time() - t0:.1f}s")
    if args.db:
        con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        db_ids = {r[0] for r in con.execute("SELECT id FROM procedures")}
        con.close()
        pids = {c.metadata["procedure_id"] for c in chunks}
        if db_ids != pids:
            print(f"MISMATCH with {args.db}: only in DB {sorted(db_ids - pids)}; only in index {sorted(pids - db_ids)}")
            return 1
        print(f"  procedure_ids match {args.db} ({len(db_ids)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
