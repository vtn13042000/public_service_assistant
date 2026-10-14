"""Build the SQLite DB (data-model.md §2) from canonical records. Rebuilds from scratch each run.

Usage: uv run python scripts/build_db.py --out data/app.db \
           --sources data/processed/moj data/processed/bca data/processed/bca-portal data/processed/daklak \
           --prefer moj bca bca-portal daklak
When a procedure_id exists in several source dirs, the first --prefer dir populates
procedures/required_documents/fees/agencies; every record's source still gets a `sources` row.
Fee rows from provincial dirs (daklak → "Đắk Lắk") are always added as extra fee rows.
Missing source dirs are skipped with a note.
Conflicts go to stdout and to --conflicts (default data/processed/CONFLICTS.md).
sources.kind comes from the source_id prefix (src/db.py DEFAULT_KIND_MAP, extend with --kind-map).
Invalid records are skipped and listed; --strict makes that exit 1.
--docs DIR loads cleaned non-procedure documents (data/clean_docs, from scripts/clean_documents.py) into
documents / document_sections / document_procedures (ROUND-4); without it no documents are loaded.
Refuses (exit 3) while data/.RUNLOCK exists unless --force (PROTOCOL "Shared artifacts lock"); only the shared
data/app.db is guarded, so a copy (--out data/app_v2.db) may be built while a run holds the lock.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import DEFAULT_PREFER, SOURCE_KINDS, build, runlock_refusal  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/app.db")
    ap.add_argument("--sources", nargs="+", default=[f"data/processed/{n}" for n in DEFAULT_PREFER])
    ap.add_argument("--force", action="store_true", help="build even if data/.RUNLOCK exists (only on the lead's explicit go)")
    ap.add_argument("--variants", default=None, help="sibling groups (default data/variants.yaml if present)")
    ap.add_argument("--prefer", nargs="+", default=DEFAULT_PREFER,
                    help="source dir basenames, highest precedence first")
    ap.add_argument("--conflicts", default="data/processed/CONFLICTS.md")
    ap.add_argument("--docs", default=None, help="cleaned documents dir (e.g. data/clean_docs); default: none")
    ap.add_argument("--kind-map", nargs="*", default=[], metavar="PREFIX=KIND",
                    help="extra source_id prefix -> sources.kind rules (longest prefix wins), e.g. dvc-hn=provincial_portal_page")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    refusal = runlock_refusal(args.force, target=args.out)
    if refusal:
        print(refusal, file=sys.stderr)
        return 3

    kind_map = {}
    for kv in args.kind_map:
        k, _, v = kv.partition("=")
        if v not in SOURCE_KINDS:
            ap.error(f"--kind-map {kv!r}: kind must be one of {', '.join(SOURCE_KINDS)}")
        kind_map[k] = v
    rep = build(args.out, args.sources, args.prefer, kind_map, args.variants, docs=args.docs)
    for r in rep.skipped:
        print(f"SKIPPED (invalid) {r.path}: {'; '.join(r.errors)[:300]}")
    for n in rep.notes:
        print("NOTE " + n[2:])
    print(f"Conflicts: {len(rep.conflicts)}")
    for c in rep.conflicts:
        print("  " + c)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    Path(args.conflicts).parent.mkdir(parents=True, exist_ok=True)
    Path(args.conflicts).write_text(
        f"# Source conflicts\n\nGenerated {now} by `scripts/build_db.py` "
        f"(sources: {', '.join(args.sources)}; prefer: {' > '.join(args.prefer)}).\n\n"
        + ("\n".join(rep.conflicts) if rep.conflicts else "_No conflicts._") + "\n"
        + ("\n## Notes\n\n" + "\n".join(rep.notes) + "\n" if rep.notes else ""),
        encoding="utf-8")
    print(f"Built {args.out}: " + ", ".join(f"{t}={n}" for t, n in rep.loaded.items())
          + f"; skipped={len(rep.skipped)}")
    return 1 if (args.strict and rep.skipped) else 0


if __name__ == "__main__":
    sys.exit(main())
