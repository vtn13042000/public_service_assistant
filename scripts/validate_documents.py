"""Validate non-procedure document records against data/schema/document_record.schema.json (ROUND-4-DATA.md).

Usage: uv run python scripts/validate_documents.py [data/processed_docs] [--sources DIR...] [-q]
Reads <root>/<kind>/*.json. Errors (exit 1): schema, kind != directory, bad dates, duplicate doc_id, a procedure_id
missing from the procedure records in --sources. Warnings never fail: NFC, HTML remnants, boilerplate lines,
legal_text segmentation, fee_resolution without jurisdiction, short sections, missing diacritics, near-empty text,
link_method missing / manual without notes, doc_id prefix vs kind, non-government host, duplicate text or (kind, title).
A raw-file sha256 shared by several documents is normal (articles cut from one law).
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import DEFAULT_PREFER  # noqa: E402
from src.documents import cross_check, procedure_ids_from, read_documents  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default="data/processed_docs")
    ap.add_argument("--sources", nargs="+", default=[f"data/processed/{n}" for n in DEFAULT_PREFER],
                    help="procedure record dirs, for the procedure_id link check")
    ap.add_argument("-q", "--quiet", action="store_true", help="only print files with errors/warnings")
    args = ap.parse_args(argv)
    if not Path(args.root).is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 2
    docs = read_documents(args.root)
    cross_check(docs, procedure_ids_from(args.sources))

    width = max([len(str(d.path)) for d in docs] + [4])
    print(f"{'file':<{width}}  status  message")
    print(f"{'-' * width}  ------  -------")
    for d in docs:
        status = "ERROR" if d.errors else ("warn" if d.warnings else "ok")
        msgs = d.errors + [f"(warn) {w}" for w in d.warnings]
        if args.quiet and status == "ok":
            continue
        print(f"{str(d.path):<{width}}  {status:<6}  {msgs[0] if msgs else ''}")
        for m in msgs[1:]:
            print(f"{'':<{width}}  {'':<6}  {m}")

    n_err = sum(1 for d in docs if d.errors)
    n_warn = sum(1 for d in docs if not d.errors and d.warnings)
    kinds = Counter(d.kind_dir for d in docs)
    print(f"\nSummary: {len(docs)} files, {len(docs) - n_err} valid, {n_err} with errors, {n_warn} valid-with-warnings")
    print("  by kind dir: " + (", ".join(f"{k or '(none)'}={v}" for k, v in sorted(kinds.items())) or "-"))
    for k, v in Counter(w.split(":")[0].split(" (")[0] for d in docs for w in d.warnings).most_common():
        print(f"  warn x{v}: {k}")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
