"""Sample N records and write a field-by-field human verification checklist (data-model.md §5).

Usage: uv run python scripts/make_verification_sheet.py --n 10 --seed 42 \
           [--sources DIR...] [--prefer moj bca bca-portal daklak] [--out data/verification.md]
Samples from the same merged set the DB uses (one record per procedure_id, preferred source first).
"""
import argparse
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import DEFAULT_PREFER, read_records, select_records, source_id_of, source_order  # noqa: E402

BOX = "☐"


def _v(x):
    return "_null_" if x in (None, "", []) else str(x).replace("\n", " ")


def record_block(i: int, rec) -> str:
    d, s = rec.data, rec.data["source"]
    L = [f"## {i}. {d['procedure_id']} — {d['title']}", "",
         f"- Source: [{_v(s.get('title') or s['url'])}]({s['url']}) · `{source_id_of(d)}` · "
         f"locator {_v(s.get('locator'))} · retrieved {s['retrieved_at']} · effective {_v(s.get('effective_date'))}",
         f"- Record file: `{rec.path}`", "",
         "| ✓ | Field | Value in record | Correction / note |", "|---|---|---|---|"]

    def row(name, val):
        L.append(f"| {BOX} | {name} | {_v(val).replace('|', '/')} | |")

    row("title", d["title"])
    row("variant_of", d.get("variant_of"))
    row("field", d["field"])
    row("level", d.get("level"))
    row("jurisdiction", d.get("jurisdiction"))
    row("receiving_agency", d.get("receiving_agency"))
    row("channels", "; ".join(d.get("channels") or []))
    for j, doc in enumerate(d["required_documents"], 1):
        extra = f" · SL {_v(doc.get('quantity'))} ({_v(doc.get('quantity_text'))}) · bắt buộc {_v(doc.get('mandatory'))}"
        if doc.get("note"):
            extra += f" · ghi chú: {doc['note']}"
        row(f"required_documents[{j}]", doc["item"] + extra)
    if not d["required_documents"]:
        row("required_documents", None)
    L.append(f"| {BOX} | required_documents — none missing vs source | {len(d['required_documents'])} items | |")
    for j, f in enumerate(d.get("fees") or [], 1):
        row(f"fees[{j}]", f"{f['value']} · {_v(f.get('condition'))} · {_v(f.get('jurisdiction'))}")
    if not d.get("fees"):
        row("fees", None)
    row("processing_time", d.get("processing_time"))
    row("steps (count)", len(d.get("steps") or []))
    row("legal_basis", "; ".join(d.get("legal_basis") or []))
    row("conditions", (d.get("conditions") or "")[:300] or None)
    L += ["", f"Verifier: ______  Date: ______  Result: {BOX} all correct  {BOX} corrected (see notes)", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sources", nargs="+", default=[f"data/processed/{n}" for n in DEFAULT_PREFER])
    ap.add_argument("--prefer", nargs="+", default=DEFAULT_PREFER)
    ap.add_argument("--out", default="data/verification.md")
    args = ap.parse_args(argv)

    dirs = [d for d in args.sources if Path(d).is_dir()]
    groups, _ = select_records(read_records(dirs), source_order(dirs, args.prefer))
    ids = sorted(groups)
    if not ids:
        print("no valid records found", file=sys.stderr)
        return 1
    sample = sorted(random.Random(args.seed).sample(ids, min(args.n, len(ids))))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    head = [f"# Data verification sheet", "",
            f"Generated {now} by `scripts/make_verification_sheet.py --n {args.n} --seed {args.seed}` "
            f"from {len(ids)} procedures ({', '.join(dirs)}; prefer {' > '.join(args.prefer)}).",
            "Open each source URL, compare field by field, tick ☐ → ☑ when the record matches the source verbatim,",
            "otherwise write the correct value in the last column.", "",
            "| # | procedure_id | title | source |", "|---|---|---|---|"]
    for i, pid in enumerate(sample, 1):
        r = groups[pid][0]
        head.append(f"| {i} | {pid} | {r.data['title']} | {r.source_dir} |")
    body = [record_block(i, groups[pid][0]) for i, pid in enumerate(sample, 1)]
    summary = ["## Summary", "", "| Records checked | Fields checked | Fields wrong | Records fully correct |",
               "|---|---|---|---|", "| | | | |", ""]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(head) + "\n\n" + "\n".join(body) + "\n" + "\n".join(summary), encoding="utf-8")
    print(f"Wrote {args.out}: {len(sample)} of {len(ids)} procedures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
