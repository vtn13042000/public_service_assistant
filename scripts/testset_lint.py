"""Lint the labelled test set (evaluation.md §1).

Checks: JSONL well-formed; required keys; unique ids (across both files); category and outcome in the allowed sets;
refusal_type consistent with outcome; category counts vs targets (ready + TODO); every gold evidence id resolves
against the records in data/processed/** (read straight from JSON, no DB needed); gold procedure_id / candidates exist.

If gold.source is set (e.g. "moj", "daklak", "bca-portal"), ids resolve only against data/processed/<source>/.

Evidence id grammar (see data/testset/README.md):
  db:required_documents:<pid>:<i>   -> record.required_documents[i]
  db:fees:<pid>:<i>                 -> record.fees[i]
  db:agencies:<pid>:0               -> record.receiving_agency is non-null
  db:procedures:<pid>:0             -> the record exists (procedure-level fields: title, processing_time, source)
  doc:<pid>:<section>:<i>           -> section ∈ data-model.md §3; array sections index the record array,
                                       scalar sections (conditions, processing_time, agency, submission_method, summary) need i == 0 and a value

Usage: uv run python scripts/testset_lint.py [--no-targets] [files...]
       (default files: data/testset.jsonl data/testset_adversarial.jsonl;
        --no-targets skips the category-minimum check, e.g. for data/testset_heldout.jsonl)
Exit 1 on any error; warnings never fail.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = [ROOT / "data" / "testset.jsonl", ROOT / "data" / "testset_adversarial.jsonl"]

TARGETS = {  # evaluation.md §1 (minimums; adversarial lives in its own file)
    "in_corpus_structured": 14, "in_corpus_narrative": 6, "near_miss": 8, "false_premise": 6,
    "jurisdiction_fee": 4, "out_of_corpus": 8, "out_of_scope": 5, "stale_update": 4, "adversarial": 4,
}
OUTCOMES = {"answer", "answer_partial", "clarify", "refuse", "out_of_scope"}
REFUSAL_TYPES = {"out_of_scope", "ambiguous", "not_in_corpus", "insufficient_evidence", "system_error"}
STATUSES = {"ready", "TODO"}
ARRAY_SECTIONS = {"required_documents": "required_documents", "steps": "steps", "fees": "fees", "legal_basis": "legal_basis"}
SCALAR_SECTIONS = {"conditions": "conditions", "processing_time": "processing_time", "agency": "receiving_agency",
                   "submission_method": "channels", "summary": "title"}


def load_records() -> dict[str, list[dict]]:
    recs: dict[str, list[dict]] = defaultdict(list)
    for p in sorted((ROOT / "data" / "processed").rglob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(d, dict) and d.get("procedure_id"):
            d["_source_dir"] = p.relative_to(ROOT / "data" / "processed").parts[0]
            recs[d["procedure_id"]].append(d)
    return recs


def resolve(eid: str, recs: dict[str, list[dict]], source: str | None = None) -> str | None:
    """Return an error string, or None if the id resolves in a record with that procedure_id
    (restricted to data/processed/<source>/ when the item names gold.source)."""
    parts = eid.split(":")
    if parts[0] == "db" and len(parts) == 4:
        _, table, pid, i = parts
    elif parts[0] == "doc" and len(parts) == 4:
        _, pid, table, i = parts
    else:
        return f"malformed evidence id {eid!r}"
    if pid not in recs:
        return f"{eid}: no record with procedure_id {pid}"
    if not i.isdigit():
        return f"{eid}: index not an integer"
    i = int(i)
    cands = [r for r in recs[pid] if source is None or r["_source_dir"] == source]
    if not cands:
        return f"{eid}: no {pid} record under data/processed/{source}/"
    for r in cands:
        if parts[0] == "db":
            if table in ("required_documents", "fees"):
                if i < len(r.get(table) or []):
                    return None
            elif table == "agencies":
                if i == 0 and r.get("receiving_agency"):
                    return None
            elif table == "procedures":
                if i == 0:
                    return None
            else:
                return f"{eid}: unknown table {table!r}"
        else:
            if table in ARRAY_SECTIONS:
                if i < len(r.get(ARRAY_SECTIONS[table]) or []):
                    return None
            elif table in SCALAR_SECTIONS:
                if i == 0 and r.get(SCALAR_SECTIONS[table]):
                    return None
            else:
                return f"{eid}: unknown section {table!r}"
    return f"{eid}: index/field out of range in every {pid} record"


def main(argv: list[str]) -> int:
    check_targets = "--no-targets" not in argv
    files = [Path(a) for a in argv if a != "--no-targets"] or DEFAULT_FILES
    recs = load_records()
    errors: list[str] = []
    warnings: list[str] = []
    ids: Counter = Counter()
    cats: dict[str, Counter] = defaultdict(Counter)
    n_items = 0

    for path in files:
        if not path.exists():
            errors.append(f"{path}: missing")
            continue
        for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            where = f"{path.name}:{ln}"
            try:
                it = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{where}: invalid JSON ({e})")
                continue
            n_items += 1
            for k in ("id", "category", "question", "gold"):
                if k not in it:
                    errors.append(f"{where}: missing key {k!r}")
            if "gold" not in it:
                continue
            iid = it.get("id", where)
            ids[iid] += 1
            where = f"{path.name}:{iid}"
            cat, g, status = it.get("category"), it["gold"], it.get("status", "ready")
            if cat not in TARGETS:
                errors.append(f"{where}: unknown category {cat!r}")
            if status not in STATUSES:
                errors.append(f"{where}: unknown status {status!r}")
            cats[cat][status] += 1
            if not (it.get("question") or "").strip():
                errors.append(f"{where}: empty question")
            if g.get("outcome") not in OUTCOMES:
                errors.append(f"{where}: outcome {g.get('outcome')!r} not in {sorted(OUTCOMES)}")
            rt = g.get("refusal_type")
            if rt is not None and rt not in REFUSAL_TYPES:
                errors.append(f"{where}: refusal_type {rt!r} not in {sorted(REFUSAL_TYPES)}")
            if g.get("outcome") in ("refuse", "out_of_scope") and rt is None:
                errors.append(f"{where}: outcome {g['outcome']} needs a refusal_type")
            if g.get("outcome") in ("answer", "answer_partial") and rt is not None:
                errors.append(f"{where}: outcome {g['outcome']} must have refusal_type null")
            if status == "TODO":
                if g.get("evidence_ids"):
                    warnings.append(f"{where}: TODO item already has evidence_ids")
                continue
            # ready items: everything must resolve
            for pid in [g.get("procedure_id")] + list(g.get("candidates") or []) + list(it.get("accept_procedure_ids") or []):
                if pid and pid not in recs:
                    errors.append(f"{where}: procedure_id {pid} not found in data/processed/**")
            if g.get("outcome") in ("answer", "answer_partial"):
                if not g.get("procedure_id"):
                    errors.append(f"{where}: answer item without gold procedure_id")
                if not g.get("evidence_ids"):
                    errors.append(f"{where}: answer item without evidence_ids")
            if g.get("outcome") == "clarify" and len(g.get("candidates") or []) < 2:
                errors.append(f"{where}: clarify item needs ≥2 candidates")
            src = g.get("source")
            gp = g.get("procedure_id")
            if gp and gp in recs and src is None and len({r["_source_dir"] for r in recs[gp]}) > 1:
                warnings.append(f"{where}: {gp} exists in several sources "
                                f"({sorted({r['_source_dir'] for r in recs[gp]})}); set gold.source")
            for eid in g.get("evidence_ids") or []:
                err = resolve(eid, recs, src)
                if err:
                    errors.append(f"{where}: {err}")
                elif g.get("procedure_id") and eid.split(":")[2 if eid.startswith("db:") else 1] not in \
                        {g["procedure_id"], *(it.get("accept_procedure_ids") or []), *(g.get("candidates") or [])}:
                    warnings.append(f"{where}: evidence {eid} is for another procedure than the gold one")

    for iid, n in ids.items():
        if n > 1:
            errors.append(f"duplicate id {iid} ({n}x)")

    print(f"{'category':<22} {'target':>6} {'ready':>6} {'TODO':>5} {'total':>6}")
    for cat, tgt in TARGETS.items():
        c = cats.get(cat, Counter())
        tot = c["ready"] + c["TODO"]
        flag = "" if tot >= tgt or not check_targets else "  <- below target"
        if tot < tgt and check_targets:
            errors.append(f"category {cat}: {tot} < target {tgt}")
        print(f"{cat:<22} {tgt:>6} {c['ready']:>6} {c['TODO']:>5} {tot:>6}{flag}")
    ready = sum(c["ready"] for c in cats.values())
    todo = sum(c["TODO"] for c in cats.values())
    print(f"\n{n_items} items ({ready} ready, {todo} TODO) in {len(files)} file(s); records loaded for {len(recs)} procedure_ids")
    for w in warnings:
        print("warn:", w)
    for e in errors:
        print("ERROR:", e)
    print("PASS" if not errors else f"FAIL ({len(errors)} errors)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
