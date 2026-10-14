"""Diff the same procedures across two source dirs (evidence for the stale/conflicting-data hazard).

Usage: uv run python scripts/compare_sources.py [--dirs DIR...] [--out data/processed/SOURCE_DIFF.md]
       uv run python scripts/compare_sources.py --a DIR --b DIR      (one pair only)
Every pair of the given dirs (default data/processed/{moj,bca,bca-portal,daklak}; missing dirs skipped)
gets a section. Compares, for procedure_ids present in both: required_documents item count, fees,
receiving_agency, processing_time (whitespace/case-insensitive, trailing '.' ignored; values shown verbatim).
Each cell is `=` same, `≠` both present and different, `∅A`/`∅B` missing on that side.
Fees are compared on the set of fee *values* (jurisdiction/condition ignored: a provincial source always
names its own province); the verbatim summaries are listed under Differences.
"""
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import DEFAULT_PREFER, fee_summary, read_records  # noqa: E402

FIELDS = ("required_documents (count)", "fees", "receiving_agency", "processing_time")


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().rstrip(".").casefold() if isinstance(s, str) else s


def _empty(x):
    return x in (None, "", 0)


def _fee_values(d):
    return sorted({_norm(f["value"]) for f in d.get("fees") or []})


def values(d: dict) -> dict:
    return {"required_documents (count)": len(d.get("required_documents") or []),
            "fees": fee_summary(d.get("fees")),
            "receiving_agency": d.get("receiving_agency"),
            "processing_time": d.get("processing_time")}


def first_by_id(recs):
    out = {}
    for r in recs:
        if r.ok:
            out.setdefault(r.procedure_id, r)
    return out


def cell(x):
    return "_null_" if x in (None, "") else str(x).replace("|", "/").replace("\n", " ")


def compare(a: str, b: str) -> tuple[list[str], str]:
    """Markdown section and a one-line summary for dirs a vs b."""
    A, B = first_by_id(read_records([a])), first_by_id(read_records([b]))
    na, nb = Path(a).name, Path(b).name
    common = sorted(set(A) & set(B))

    rows, details = [], []
    n_diff, n_miss = {f: 0 for f in FIELDS}, {f: 0 for f in FIELDS}
    for pid in common:
        va, vb = values(A[pid].data), values(B[pid].data)
        flags = []
        for f in FIELDS:
            if _empty(va[f]) or _empty(vb[f]):
                flag = "=" if _empty(va[f]) and _empty(vb[f]) else ("∅A" if _empty(va[f]) else "∅B")
            elif f == "fees":
                flag = "=" if _fee_values(A[pid].data) == _fee_values(B[pid].data) else "≠"
            else:
                flag = "=" if _norm(va[f]) == _norm(vb[f]) else "≠"
            flags.append(flag)
            if flag == "≠":
                n_diff[f] += 1
                details.append(f"| {pid} | {f} | {cell(va[f])} | {cell(vb[f])} |")
            elif flag.startswith("∅"):
                n_miss[f] += 1
        rows.append(f"| {pid} | {cell(A[pid].data['title'])} | " + " | ".join(flags) + " |")

    L = [f"## `{na}` (A) vs `{nb}` (B)", "",
         f"- Procedures in A only: {len(set(A) - set(B))}; in B only: {len(set(B) - set(A))}; in both: {len(common)}"]
    for f in FIELDS:
        L.append(f"- `{f}`: both present and different in {n_diff[f]} / {len(common)}; missing on one side in {n_miss[f]}")
    if common:
        L += ["", "### Overview (= same, ≠ both present and different, ∅A/∅B missing on that side)", "",
              "| procedure_id | title | " + " | ".join(FIELDS) + " |", "|---" * (len(FIELDS) + 2) + "|", *rows, "",
              "### Differences (verbatim)", "", f"| procedure_id | field | A ({na}) | B ({nb}) |", "|---|---|---|---|",
              *(details or ["| — | — | — | — |"])]
    L.append("")
    return L, f"{na} vs {nb}: {len(common)} common; " + ", ".join(f"{f} ≠{n_diff[f]} ∅{n_miss[f]}" for f in FIELDS)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="+", default=[f"data/processed/{n}" for n in DEFAULT_PREFER])
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--out", default="data/processed/SOURCE_DIFF.md")
    args = ap.parse_args(argv)
    dirs = [args.a, args.b] if args.a and args.b else [d for d in args.dirs if Path(d).is_dir()]
    pairs = [(a, b) for i, a in enumerate(dirs) for b in dirs[i + 1:]]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    L = ["# Source comparison", "",
         f"Generated {now} by `scripts/compare_sources.py` over {', '.join(f'`{d}`' for d in dirs) or 'no dirs'}.", ""]
    summaries = []
    for a, b in pairs:
        sec, s = compare(a, b)
        L += sec
        summaries.append(s)
    if not pairs:
        L.append("_Fewer than two source dirs present; nothing to compare._\n")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {args.out}: " + ("; ".join(summaries) or "no pairs"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
