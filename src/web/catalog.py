"""Procedure catalogue for the web UI's "Thủ tục" tab (docs/03_design/web-ui.md §5).

Read-only, fixed SQL over data/app.db through the read-only connection of src/tools/db.py (R4: no model call, no
model-written SQL). Two shapes, so the page never shows more than was asked for:
- `procedure_list()`: one compact row per procedure (code, title, field, agency, official source links, status, newest
  change notice) — no section texts;
- `procedure_detail(code)`: the values of one procedure (documents, fees, deadline, place of submission, legal basis),
  each with the URL of the record it came from, plus the linked depth documents. None for an unknown code.
"""
from __future__ import annotations

import json

from src.tools.db import _rows

DEPTH_KIND_ORDER = ("legal_text", "change_notice", "guidance", "form", "fee_resolution")

# every source a procedure's rows cite (the record itself, its documents, fees and agencies)
_PROC_SOURCES = """
SELECT DISTINCT x.pid AS procedure_id, s.source_id, s.kind, s.url, s.title, s.retrieved_at, s.effective_date
  FROM (SELECT id AS pid, source_id FROM procedures
        UNION SELECT procedure_id, source_id FROM required_documents
        UNION SELECT procedure_id, source_id FROM fees
        UNION SELECT procedure_id, source_id FROM agencies) x
  JOIN sources s ON s.source_id = x.source_id
 {where}
 ORDER BY x.pid, s.kind DESC, s.source_id"""


def family_labels(rows: list[dict]) -> dict[str, str | None]:
    """{procedure code: family label} from the resolver's family-noun table (src/families.py, data/family_nouns.json) —
    the same derivation head_noun_guard uses, not a second rule. A title's family is the group of its first family noun
    (family_group unions nouns that share a root, e.g. "giám hộ" / "chấm dứt"); the label is that group's main noun as written
    in its root's title ("Khai sinh", "Thay đổi, cải chính"). None when the title names no family."""
    import re
    import unicodedata

    from src.families import _fold, family_group, load_family_nouns, nouns_in
    nouns = load_family_nouns()
    titles = {r["code"]: r["title"] for r in rows}

    def accented(noun: str, title: str) -> str:
        """The noun as spelled in `title`, plus a trailing list of one-word items ("nhận cha" → "nhận cha, mẹ, con");
        display only, the grouping uses the noun."""
        t = unicodedata.normalize("NFC", title)
        words = list(re.finditer(r"\w+", t))
        for w1, w2 in zip(words, words[1:]):
            if f"{_fold(w1.group())} {_fold(w2.group())}" == noun:
                tail = re.match(r"((?:,\s*\w+)+)(?=$|\s+có\b)", t[w2.end():])
                return (t[w1.start():w2.end()] + (tail.group(1) if tail else "")).lower()
        return noun

    labels: dict[frozenset, str] = {}
    out: dict[str, str | None] = {}
    for code, title in titles.items():
        hits = nouns_in(title, nouns)
        if not hits:
            out[code] = None
            continue
        group = frozenset(family_group(hits[0][1], nouns))
        if group not in labels:
            roots = {r for n in group for r in nouns.get(n, ())}
            root_title = next((titles[r] for r in sorted(roots) if r in titles), title)
            pos = {n: i for i, n in nouns_in(root_title, {n: () for n in group})}
            ranked = sorted(group, key=lambda n: (-len(nouns.get(n, ())), pos.get(n, 99), n))
            top = [ranked[0]] + ([ranked[1]] if len(ranked) > 1 and len(nouns.get(ranked[1], ())) == len(nouns.get(ranked[0], ())) else [])
            label = ", ".join(accented(n, root_title) for n in top)
            labels[group] = label[:1].upper() + label[1:]
        out[code] = labels[group]
    return out


def _status() -> dict[str, dict]:
    from src.nodes import load_procedure_status
    return load_procedure_status()


def _sources_by_procedure(code: str | None = None) -> dict[str, list[dict]]:
    sql = _PROC_SOURCES.format(where="WHERE x.pid = ?" if code else "")
    out: dict[str, list[dict]] = {}
    for r in _rows(sql, (code,) if code else ()):
        out.setdefault(r["procedure_id"], []).append(
            {"kind": r["kind"], "url": r["url"], "title": r["title"], "retrieved_at": r["retrieved_at"],
             "effective_date": r["effective_date"]})
    return out


def _notice_dates(today: str) -> dict[str, dict]:
    """Per procedure: the newest change notice already in force (effective_date ≤ today) and the next one not yet in
    force. Dates only; whether a notice is printed in an answer is decided by the graph (src/nodes.py:notice_applies)."""
    try:
        rows = _rows("""SELECT dp.procedure_id,
                               MAX(CASE WHEN d.effective_date <= ? THEN d.effective_date END) AS in_force,
                               MIN(CASE WHEN d.effective_date > ? THEN d.effective_date END) AS upcoming
                          FROM documents d JOIN document_procedures dp ON dp.doc_id = d.id
                         WHERE d.kind = 'change_notice' GROUP BY dp.procedure_id""", (today, today))
    except Exception:  # noqa: BLE001 — corpus-v1 database: no documents table
        return {}
    return {r["procedure_id"]: {"in_force": r["in_force"], "upcoming": r["upcoming"]} for r in rows}


def _status_row(code: str, status: dict[str, dict]) -> dict | None:
    st = status.get(code)
    return ({"status": "discontinued", "since": st.get("since"), "basis": st.get("basis"), "notice_url": st.get("notice_url")}
            if st else None)


def procedure_list(today: str | None = None) -> list[dict]:
    """All procedures, compact: [{code, title, field, level, agency, sources: [{kind, url}], provincial_only,
    status, change_notice: {in_force, upcoming}, family}] ordered by field then title."""
    from datetime import date
    sources = _sources_by_procedure()
    notices = _notice_dates(today or date.today().isoformat())
    status = _status()
    out = []
    for r in _rows("SELECT id, title, field, level, agency_summary FROM procedures ORDER BY field, title", ()):
        srcs = [{"kind": s["kind"], "url": s["url"]} for s in sources.get(r["id"], [])]  # titles only in the detail
        out.append({
            "code": r["id"], "title": r["title"], "field": r["field"], "level": r["level"], "agency": r["agency_summary"],
            "sources": srcs,
            "provincial_only": bool(srcs) and all(s["kind"] == "provincial_decision" for s in srcs),
            "status": _status_row(r["id"], status),
            "change_notice": notices.get(r["id"]) or {"in_force": None, "upcoming": None},
        })
    fams = family_labels(out)
    for row in out:
        row["family"] = fams.get(row["code"])  # None → the page's "Khác" sub-group
    return out


def procedure_detail(code: str) -> dict | None:
    """One procedure's values, each with its source URL; None if the code is unknown."""
    rows = _rows("""SELECT p.*, s.url AS source_url, ts.url AS time_url
                      FROM procedures p LEFT JOIN sources s ON s.source_id = p.source_id
                      LEFT JOIN sources ts ON ts.source_id = p.processing_time_source_id
                     WHERE p.id = ?""", (code,))
    if not rows:
        return None
    p = rows[0]
    docs = _rows("""SELECT d.position, d.item, d.quantity, d.quantity_text, d.mandatory, d.note, s.url AS source_url
                      FROM required_documents d LEFT JOIN sources s ON s.source_id = d.source_id
                     WHERE d.procedure_id = ? ORDER BY d.source_id, d.position""", (code,))
    fees = _rows("""SELECT f.value, f.condition, f.jurisdiction, s.url AS source_url
                      FROM fees f LEFT JOIN sources s ON s.source_id = f.source_id
                     WHERE f.procedure_id = ? ORDER BY f.jurisdiction, f.source_id""", (code,))
    agencies = _rows("""SELECT a.name, a.jurisdiction, a.effective_date, s.url AS source_url
                          FROM agencies a LEFT JOIN sources s ON s.source_id = a.source_id
                         WHERE a.procedure_id = ? ORDER BY a.jurisdiction""", (code,))
    try:
        depth = _rows("""SELECT d.id, d.kind, d.title, d.url, d.effective_date
                           FROM documents d JOIN document_procedures dp ON dp.doc_id = d.id
                          WHERE dp.procedure_id = ?
                          ORDER BY d.effective_date IS NULL, d.effective_date DESC, d.id""", (code,))
    except Exception:  # noqa: BLE001 — corpus-v1 database
        depth = []
    depth.sort(key=lambda d: DEPTH_KIND_ORDER.index(d["kind"]) if d["kind"] in DEPTH_KIND_ORDER else len(DEPTH_KIND_ORDER))
    try:
        legal = json.loads(p["legal_basis"]) if p["legal_basis"] else []
    except (TypeError, ValueError):
        legal = [p["legal_basis"]]
    status = _status()
    return {
        "code": p["id"], "title": p["title"], "field": p["field"], "level": p["level"],
        "status": _status_row(p["id"], status),
        "sources": [{"kind": s["kind"], "url": s["url"], "title": s["title"], "retrieved_at": s["retrieved_at"]}
                    for s in _sources_by_procedure(code).get(code, [])],
        "documents": [{"item": d["item"], "quantity": d["quantity_text"] or (f"{d['quantity']} bản" if d["quantity"] else None),
                       "mandatory": None if d["mandatory"] is None else bool(d["mandatory"]), "note": d["note"],
                       "source_url": d["source_url"]} for d in docs],
        "fees": [{"value": f["value"], "condition": f["condition"], "jurisdiction": f["jurisdiction"],
                  "source_url": f["source_url"]} for f in fees],
        "deadline": ({"text": p["processing_time"], "source_url": p["time_url"] or p["source_url"]}
                     if p["processing_time"] else None),
        "place": [{"name": a["name"], "jurisdiction": a["jurisdiction"], "effective_date": a["effective_date"],
                   "source_url": a["source_url"]} for a in agencies],
        "legal_basis": [{"text": t, "source_url": p["source_url"]} for t in legal if t],
        "depth_documents": [{"title": d["title"], "kind": d["kind"], "url": d["url"], "effective_date": d["effective_date"]}
                            for d in depth],
    }
