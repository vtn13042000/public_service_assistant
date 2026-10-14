"""Validate canonical procedure records against data/schema/procedure_record.schema.json.

Usage: uv run python scripts/validate_records.py data/processed/moj data/processed/dvc [-q]
Prints one row per file (ok / warn / ERROR) and a summary. Exit 1 on any schema error;
warnings (smells) never fail.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import read_records  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("-q", "--quiet", action="store_true", help="only print files with errors/warnings")
    args = ap.parse_args(argv)

    for d in args.dirs:
        if not Path(d).is_dir():
            print(f"not a directory: {d}", file=sys.stderr)
            return 2
    recs = read_records(args.dirs)
    ids = Counter((r.source_dir, r.procedure_id) for r in recs if r.ok)
    all_ids = {r.procedure_id for r in recs if r.ok}
    for r in recs:
        if r.ok and ids[(r.source_dir, r.procedure_id)] > 1:
            r.warnings.append(f"procedure_id {r.procedure_id} duplicated within {r.source_dir}")
        vo = (r.data or {}).get("variant_of") if isinstance(r.data, dict) else None
        if r.ok and vo and vo not in all_ids:
            r.warnings.append(f"variant_of {vo!r} not found in the given dirs")

    width = max([len(str(r.path)) for r in recs] + [4])
    print(f"{'file':<{width}}  status  message")
    print(f"{'-' * width}  ------  -------")
    for r in recs:
        status = "ERROR" if r.errors else ("warn" if r.warnings else "ok")
        msgs = r.errors + [f"(warn) {w}" for w in r.warnings]
        if args.quiet and status == "ok":
            continue
        print(f"{str(r.path):<{width}}  {status:<6}  {msgs[0] if msgs else ''}")
        for m in msgs[1:]:
            print(f"{'':<{width}}  {'':<6}  {m}")

    n_err = sum(1 for r in recs if r.errors)
    n_warn = sum(1 for r in recs if not r.errors and r.warnings)
    smell_counts = Counter(w.split(":")[0].split(" (")[0] for r in recs for w in r.warnings)
    print(f"\nSummary: {len(recs)} files, {len(recs) - n_err} valid, {n_err} with errors, {n_warn} valid-with-warnings")
    for k, v in smell_counts.most_common():
        print(f"  warn x{v}: {k}")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
