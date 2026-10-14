"""Database tool: templated, read-only, parameterised lookups over the SQLite DB (data-model.md §2).

No free-form Text-to-SQL (DECISIONS.md D-003): every query below is fixed text with `?` parameters, and the
connection is opened `mode=ro`. Every function returns `list[Evidence]` with tier `db`; `structured` is the row
(JSON columns decoded) and `source_url` / `retrieved_at` / `effective_date` are joined from `sources`.
Not found → `[]`. A missing or unreadable DB raises (nodes turn that into `errors` → refuse_redirect, L6).

Evidence ids (src.evidence.db_id):
  procedures          db:procedures:<id>:<column>        one per filled column (summary, processing_time, …)
  required_documents  db:required_documents:<id>:<position>
  fees                db:fees:<id>:<n>                   n = 1-based order of the procedure's fee rows (stable, filter-independent)
  agencies            db:agencies:<id>:<n>
  sources             db:sources:<procedure_id>:<doc-id> (source_id "<doc-id>#<procedure_id>")
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from src.evidence import Evidence, db_id, make_evidence

ROOT = Path(__file__).resolve().parents[2]
NATIONWIDE = ("toàn quốc", "theo tỉnh")  # fee jurisdictions that apply whatever the user's province

_SRC_COLS = "s.url AS source_url, s.retrieved_at AS retrieved_at, s.effective_date AS source_effective_date"


def db_path() -> Path:
    p = Path(os.environ.get("APP_DB", "data/app.db"))
    return p if p.is_absolute() else ROOT / p


def _connect() -> sqlite3.Connection:
    p = db_path()
    if not p.is_file():
        raise FileNotFoundError(f"database not found: {p} (build it with scripts/build_db.py)")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _rows(sql: str, params: tuple) -> list[dict]:
    with closing(_connect()) as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def _decode(row: dict, *cols: str) -> dict:
    for c in cols:
        if isinstance(row.get(c), str):
            try:
                row[c] = json.loads(row[c])
            except json.JSONDecodeError:
                pass
    return row


def _split_source(row: dict) -> tuple[dict, dict]:
    src = {"source_url": row.pop("source_url", None), "retrieved_at": row.pop("retrieved_at", None),
           "effective_date": row.pop("source_effective_date", None)}
    return row, src


def _join(xs) -> str:
    return "; ".join(xs) if isinstance(xs, list) else str(xs)


# ---------------------------------------------------------------- search_titles

def _fts_query(q: str) -> str | None:
    """User text → FTS5 query: each word quoted (no operator injection), OR-ed so BM25 ranks partial matches."""
    words = re.findall(r"\w+", q.lower())
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words)) or None


def search_titles(q: str, k: int = 10) -> list[Evidence]:
    """BM25 title search over `procedures_fts`. Best first; `structured` = {procedure_id, title, score, variant_group, …}.

    `score` = -bm25 (higher is better; FTS5's default unicode61 tokenizer folds diacritics).
    `variant_group` = `variant_of` or the id itself, so callers can group siblings for a clarify prompt.
    """
    fq = _fts_query(q)
    if not fq:
        return []
    rows = _rows(
        f"""SELECT p.id, p.title, p.field, p.level, p.variant_of, -bm25(procedures_fts) AS score, {_SRC_COLS}
            FROM procedures_fts JOIN procedures p ON p.rowid = procedures_fts.rowid
            LEFT JOIN sources s ON s.source_id = p.source_id
            WHERE procedures_fts MATCH ? ORDER BY bm25(procedures_fts), p.id LIMIT ?""",
        (fq, int(k)),
    )
    out = []
    for r in rows:
        r, src = _split_source(r)
        r["procedure_id"] = r.pop("id")
        r["score"] = round(r["score"], 4)
        r["variant_group"] = r["variant_of"] or r["procedure_id"]
        out.append(make_evidence(db_id("procedures", r["procedure_id"], "title"), "db",
                                 f"{r['title']} (mã {r['procedure_id']})", procedure_id=r["procedure_id"],
                                 section="summary", structured=r, **src))
    return out


# ---------------------------------------------------------------- get_procedure

# column → (section, Vietnamese label)
_PROC_FIELDS = {
    "processing_time": ("processing_time", "Thời hạn giải quyết"),
    "channels": ("submission_method", "Cách thức thực hiện"),
    "conditions": ("conditions", "Điều kiện"),
    "legal_basis": ("legal_basis", "Căn cứ pháp lý"),
    "fee_summary": ("fees", "Lệ phí (tóm tắt)"),
    "agency_summary": ("agency", "Cơ quan thực hiện (tóm tắt)"),
}


def get_procedure(procedure_id: str) -> list[Evidence]:
    """The procedures row as one `summary` evidence plus one evidence per filled column (processing_time, channels, …).

    Splitting lets a claim cite exactly the column it uses, e.g. `db:procedures:1.000656:processing_time`.
    The processing_time evidence carries the provenance of `processing_time_source_id` (the loader's fallback source
    when the winning source had a bare number, data-model.md §2); every other evidence carries the row's `source_id`.
    """
    rows = _rows(f"SELECT p.*, {_SRC_COLS} FROM procedures p LEFT JOIN sources s ON s.source_id = p.source_id WHERE p.id = ?",
                 (procedure_id,))
    if not rows:
        return []
    row, src = _split_source(_decode(rows[0], "channels", "legal_basis"))
    pid = row["id"]
    head = f"Thủ tục: {row['title']} (mã {pid}). Lĩnh vực: {row['field'] or '—'}. Cấp thực hiện: {row['level'] or '—'}."
    out = [make_evidence(db_id("procedures", pid, "summary"), "db", head, procedure_id=pid, section="summary",
                         structured=row, **src)]
    pt_sid = row.get("processing_time_source_id")
    pt_src = _source_cols(pt_sid) if pt_sid and pt_sid != row.get("source_id") else src
    for col, (section, label) in _PROC_FIELDS.items():
        v = row.get(col)
        if v in (None, "", []):
            continue
        out.append(make_evidence(db_id("procedures", pid, col), "db", f"{label}: {_join(v)}", procedure_id=pid,
                                 section=section, structured=row, **(pt_src if col == "processing_time" else src)))
    return out


def _source_cols(source_id: str) -> dict:
    rows = _rows("SELECT url, retrieved_at, effective_date FROM sources WHERE source_id = ?", (source_id,))
    r = rows[0] if rows else {}
    return {"source_url": r.get("url"), "retrieved_at": r.get("retrieved_at"), "effective_date": r.get("effective_date")}


# ---------------------------------------------------------------- required_documents

def get_required_documents(procedure_id: str) -> list[Evidence]:
    """One evidence per document item, in source order (`position`)."""
    rows = _rows(
        f"""SELECT d.*, {_SRC_COLS} FROM required_documents d LEFT JOIN sources s ON s.source_id = d.source_id
            WHERE d.procedure_id = ? ORDER BY d.position""",
        (procedure_id,),
    )
    out = []
    for r in rows:
        r, src = _split_source(r)
        extra = [x for x in (r["quantity_text"], "bắt buộc" if r["mandatory"] == 1 else None, r["note"]) if x]
        text = f"{r['position']}. {r['item']}" + (f" ({'; '.join(extra)})" if extra else "")
        out.append(make_evidence(db_id("required_documents", procedure_id, r["position"]), "db", text,
                                 procedure_id=procedure_id, section="required_documents", structured=r, **src))
    return out


# ---------------------------------------------------------------- fees

def get_fees(procedure_id: str, jurisdiction: str | None = None) -> list[Evidence]:
    """Fee rows with condition and jurisdiction. With `jurisdiction` (a province), keeps that province's rows and
    the rows that apply everywhere (`toàn quốc`, `theo tỉnh`); matching is case-insensitive."""
    rows = _rows(
        f"""SELECT f.*, {_SRC_COLS} FROM fees f LEFT JOIN sources s ON s.source_id = f.source_id
            WHERE f.procedure_id = ? ORDER BY f.rowid""",
        (procedure_id,),
    )
    want = jurisdiction.strip().casefold() if jurisdiction else None
    out = []
    for n, r in enumerate(rows, 1):
        r, src = _split_source(r)
        j = (r["jurisdiction"] or "").strip().casefold()
        if want and j not in (want, *NATIONWIDE):
            continue
        text = f"Lệ phí: {r['value']}" + (f" — điều kiện: {r['condition']}" if r["condition"] else "") \
            + f" — phạm vi: {r['jurisdiction'] or 'không rõ'}"
        out.append(make_evidence(db_id("fees", procedure_id, n), "db", text, procedure_id=procedure_id,
                                 section="fees", structured=r, **src))
    return out


# ---------------------------------------------------------------- agencies

def get_agency(procedure_id: str) -> list[Evidence]:
    """Receiving agency rows. `effective_date` is the agency row's own date, else the source's."""
    rows = _rows(
        f"""SELECT a.*, {_SRC_COLS} FROM agencies a LEFT JOIN sources s ON s.source_id = a.source_id
            WHERE a.procedure_id = ? ORDER BY a.rowid""",
        (procedure_id,),
    )
    out = []
    for n, r in enumerate(rows, 1):
        r, src = _split_source(r)
        src["effective_date"] = r["effective_date"] or src["effective_date"]
        text = f"Cơ quan thực hiện: {r['name']}" + (f" — phạm vi: {r['jurisdiction']}" if r["jurisdiction"] else "")
        out.append(make_evidence(db_id("agencies", procedure_id, n), "db", text, procedure_id=procedure_id,
                                 section="agency", structured=r, **src))
    return out


# ---------------------------------------------------------------- sources

def get_source(source_id: str) -> list[Evidence]:
    """The provenance row for a source_id ("<doc-id>#<procedure_id>")."""
    rows = _rows("SELECT * FROM sources WHERE source_id = ?", (source_id,))
    if not rows:
        return []
    r = rows[0]
    doc, _, pid = source_id.partition("#")
    text = f"Nguồn: {r['title'] or doc}" + (f" — {r['url']}" if r["url"] else "") \
        + (f" ({r['locator']})" if r["locator"] else "") + (f"; lấy ngày {r['retrieved_at']}" if r["retrieved_at"] else "")
    return [make_evidence(db_id("sources", pid or doc, doc), "db", text, procedure_id=pid or None, structured=r,
                          source_url=r["url"], retrieved_at=r["retrieved_at"], effective_date=r["effective_date"])]


def get_change_notices(procedure_id: str) -> list[dict]:
    """change_notice documents linked to a procedure, newest first: [{doc_id, title, effective_date, url}].

    Plain dicts, not Evidence: used only for the freshness notice line (src/nodes.py:change_notices), which keeps rows with
    effective_date ≤ today. [] when the `documents` table does not exist (corpus-v1 DB). NULL effective_date sorts last.
    """
    try:
        return _rows(
            """SELECT d.id AS doc_id, d.title, d.effective_date, d.url
                 FROM documents d JOIN document_procedures dp ON dp.doc_id = d.id
                WHERE dp.procedure_id = ? AND d.kind = 'change_notice'
                ORDER BY d.effective_date IS NULL, d.effective_date DESC, d.id""",
            (procedure_id,))
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return []
        raise
