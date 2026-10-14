"""Shared code for loading canonical procedure records and building the SQLite DB.

Schema and field names follow docs/03_design/data-model.md §1 (record) and §2 (SQL).
Identifiers are English; content is kept verbatim (only whitespace is trimmed).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "data" / "schema" / "procedure_record.schema.json"
DATA_MODEL_PATH = ROOT / "docs" / "03_design" / "data-model.md"
VARIANTS_PATH = ROOT / "data" / "variants.yaml"
# PROTOCOL "Shared artifacts lock": runners create data/.RUNLOCK; builders refuse while it exists (env APP_RUNLOCK overrides the path).
RUNLOCK_PATH = Path(os.environ.get("APP_RUNLOCK", ROOT / "data" / ".RUNLOCK"))


def runlock_refusal(force: bool = False, path: str | Path | None = None, target: str | Path | None = None) -> str | None:
    """A refusal message if the run lock exists and `force` is not set, else None.

    `target`: what the caller is about to write. Only the shared artifacts next to the lock (`app.db`, `chroma/`)
    are guarded; a copy such as data/app_v2.db or data/chroma_v2 may be built while a run holds the lock.
    """
    path = Path(path or os.environ.get("APP_RUNLOCK") or RUNLOCK_PATH)
    if force or not path.exists():
        return None
    if target is not None and Path(target).resolve() not in {(path.parent / n).resolve() for n in ("app.db", "chroma")}:
        return None
    try:
        holder = path.read_text(encoding="utf-8").strip() or "(empty)"
    except OSError:
        holder = "(unreadable)"
    return (f"REFUSED: {path} exists ({holder}). A live run is using data/app.db and data/chroma/; "
            f"rebuilding now would invalidate it. Wait until the runner removes the lock, and only build with the "
            f"lead's go. Use --force only if the lead explicitly says so.")

# Verbatim copy of the ```sql block in data-model.md §2 (runs unchanged in SQLite 3.53, FTS5 built in).
# tests/test_build_db.py asserts this stays identical to the doc.
SCHEMA_SQL = """\
CREATE TABLE sources (                      -- provenance, one row per (document, procedure)
  source_id      TEXT PRIMARY KEY,          -- "<doc-id>#<procedure_id>"
  kind           TEXT,                      -- moj_decision | bca_decision | ministry_portal_page | provincial_decision
                                            -- | national_db_page | provincial_portal_page | other
  url            TEXT,                      -- URL of the document / page
  locator        TEXT,                      -- where in the document, e.g. "Mục I.3, tr. 12"
  title          TEXT,
  retrieved_at   TEXT,                      -- ISO date the content was fetched
  effective_date TEXT,                      -- ISO date the procedure version took effect, if stated
  content_hash   TEXT);

CREATE TABLE procedures (                   -- ≙ guidance.thu_tuc
  id              TEXT PRIMARY KEY,         -- "KS-01"
  title           TEXT,                     -- ≙ ten          (Vietnamese)
  field           TEXT,                     -- ≙ linh_vuc     ("Hộ tịch")
  fee_summary     TEXT,                     -- ≙ le_phi       (human-readable summary; see fees table)
  agency_summary  TEXT,                     -- ≙ co_quan      (human-readable summary; see agencies table)
  processing_time TEXT,                     -- ≙ thoi_gian_xu_ly (source wording kept verbatim)
  processing_time_source_id TEXT,           -- source the processing_time came from (see fallback rule below)
  level           TEXT,                     -- cấp xã / cấp tỉnh / trung ương
  variant_of      TEXT,                     -- sibling grouping for clarify prompts
  channels        TEXT,                     -- JSON array, e.g. ["trực tiếp", "trực tuyến toàn trình"]
  legal_basis     TEXT,                     -- JSON array of legal instruments
  conditions      TEXT,
  source_id       TEXT REFERENCES sources(source_id));

CREATE VIRTUAL TABLE procedures_fts USING fts5(  -- BM25 over title for search_titles
  title, content='procedures', content_rowid='rowid');

CREATE TABLE required_documents (           -- ≙ guidance.ho_so
  procedure_id TEXT REFERENCES procedures(id),
  position     INTEGER,                     -- order in the source list (loader assigns from array order, 1-based)
  item         TEXT,                        -- ≙ thanh_phan   (Vietnamese)
  quantity     INTEGER,                     -- ≙ so_luong
  quantity_text TEXT,                       -- source wording verbatim, e.g. "01 bản chính và 01 bản sao"
  mandatory    INTEGER,                     -- ≙ bat_buoc
  note         TEXT,
  source_id    TEXT);
CREATE INDEX idx_reqdoc_procedure ON required_documents(procedure_id);

CREATE TABLE fees (                         -- fees are multi-valued and jurisdiction-dependent
  procedure_id TEXT REFERENCES procedures(id),
  value        TEXT,                        -- "miễn lệ phí" | "theo HĐND tỉnh" | "50.000 đồng"
  condition    TEXT,                        -- "đăng ký đúng hạn"
  jurisdiction TEXT,                        -- "toàn quốc" | province name | "theo tỉnh"
  source_id    TEXT);

CREATE TABLE agencies (                     -- agency as a row so it can be cited, dated, and replaced
  procedure_id   TEXT REFERENCES procedures(id),
  name           TEXT,                      -- "UBND cấp xã nơi cư trú của cha hoặc mẹ"
  jurisdiction   TEXT,
  effective_date TEXT,                      -- proxy: the record's source.effective_date (no separate agency date)
  source_id      TEXT);

CREATE TABLE documents (                    -- non-procedure documents (ROUND-4): legal articles, forms, fee resolutions, …
  id             TEXT PRIMARY KEY,          -- doc_id, e.g. "legal:123-2015-ND-CP:dieu-16"
  kind           TEXT NOT NULL,             -- legal_text | form | fee_resolution | guidance | change_notice
  title          TEXT NOT NULL,
  issuer         TEXT,                      -- "Chính phủ", "HĐND tỉnh Đắk Lắk", …
  effective_date TEXT,
  jurisdiction   TEXT,                      -- province for fee_resolution / provincial guidance; NULL = national
  url            TEXT NOT NULL,
  retrieved_at   TEXT NOT NULL,
  sha256         TEXT NOT NULL,             -- of the fetched raw bytes
  link_method    TEXT,                      -- legal_basis | procedure_code | doc_links | manual | named | instrument_scope
  original_version INTEGER,                 -- legal_text: 1 = original wording of an article since amended
  amended_by     TEXT,                      -- JSON array of amending instruments
  notes          TEXT);

CREATE TABLE document_sections (            -- one row per điều / form part / heading, after cleaning
  doc_id   TEXT NOT NULL REFERENCES documents(id),
  position INTEGER NOT NULL,                -- 1-based order in the document
  heading  TEXT NOT NULL,
  text     TEXT NOT NULL,
  PRIMARY KEY (doc_id, position));

CREATE TABLE document_procedures (          -- which procedures a document is about
  doc_id       TEXT NOT NULL REFERENCES documents(id),
  procedure_id TEXT NOT NULL REFERENCES procedures(id),
  PRIMARY KEY (doc_id, procedure_id));
CREATE INDEX idx_docproc_procedure ON document_procedures(procedure_id);
"""

KNOWN_TOP_KEYS = {
    "procedure_id", "title", "variant_of", "field", "level", "jurisdiction", "receiving_agency",
    "channels", "required_documents", "steps", "fees", "processing_time", "legal_basis",
    "conditions", "raw_text", "source",
}


def doc_schema_sql(path: Path = DATA_MODEL_PATH) -> str:
    """The ```sql block from data-model.md, for drift checks."""
    m = re.search(r"```sql\n(.*?)```", path.read_text(encoding="utf-8"), re.S)
    return m.group(1) if m else ""


# ---------------------------------------------------------------- records

@dataclass
class Record:
    path: Path
    source_dir: str          # basename of the source dir, e.g. "moj"
    data: dict | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.data is not None

    @property
    def procedure_id(self) -> str | None:
        return (self.data or {}).get("procedure_id")


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def is_iso_date(s) -> bool:
    if not isinstance(s, str):
        return False
    try:
        if len(s) == 10:
            date.fromisoformat(s)
        else:
            datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def smells(data: dict, path: Path | None = None) -> list[str]:
    """Non-fatal warnings (BRIEF step 2 plus a few cheap extras)."""
    w = []
    if not data.get("required_documents"):
        w.append("required_documents is empty")
    if not data.get("fees"):
        w.append("fees missing/empty (fee_summary will be NULL, not 'miễn')")
    raw = data.get("raw_text") or ""
    if len(raw) < 200:
        w.append(f"raw_text short ({len(raw)} chars < 200)")
    src = data.get("source") or {}
    if "retrieved_at" in src and not is_iso_date(src["retrieved_at"]):
        w.append(f"source.retrieved_at not ISO: {src['retrieved_at']!r}")
    if src.get("effective_date") and not is_iso_date(src["effective_date"]):
        w.append(f"source.effective_date not ISO: {src['effective_date']!r}")
    sid, pid = src.get("source_id"), data.get("procedure_id")
    if isinstance(sid, str) and pid and not sid.endswith(f"#{pid}"):
        w.append(f"source.source_id {sid!r} not of the form '<doc-id>#{pid}'")
    if isinstance(sid, str) and source_kind(sid) == "other":
        w.append(f"source.source_id {sid!r}: unknown doc-id prefix (sources.kind = 'other')")
    ch = src.get("content_hash")
    if ch and not re.fullmatch(r"sha256:[0-9a-f]{64}", ch):
        w.append("source.content_hash not 'sha256:<64 hex>'")
    unknown = sorted(set(data) - KNOWN_TOP_KEYS)
    if unknown:
        w.append(f"unknown top-level keys (dropped by loader): {', '.join(unknown)}")
    if path is not None and data.get("procedure_id") and path.stem != data["procedure_id"]:
        w.append(f"file name {path.name} != procedure_id {data['procedure_id']}")
    return w


def read_records(dirs: list[str | Path], schema: dict | None = None) -> list[Record]:
    """Read and validate every *.json under each dir (recursive, sorted)."""
    schema = schema or load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    out = []
    for d in dirs:
        d = Path(d)
        for p in sorted(d.rglob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                out.append(Record(p, d.name, None, [f"unreadable JSON: {e}"]))
                continue
            errs = [
                f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
                for e in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))
            ]
            rec = Record(p, d.name, data, errs)
            if isinstance(data, dict):
                rec.warnings = smells(data, p)
            out.append(rec)
    return out


def source_id_of(data: dict) -> str:
    return data["source"]["source_id"]


SOURCE_KINDS = ("moj_decision", "bca_decision", "ministry_portal_page", "provincial_decision",
                "national_db_page", "provincial_portal_page", "other")
# Rules on the doc-id (the part of source_id before '#'); first match wins. --kind-map rules are checked first.
KIND_RULES = [
    (r"moj-portal", "ministry_portal_page"),   # "moj-portal#<mã>": moj.gov.vn procedure pages (w-moj)
    (r"moj-.+", "moj_decision"),               # "moj-<số hiệu>#<mã>": Bộ Tư pháp decisions (w-moj)
    (r"bca-portal", "ministry_portal_page"),   # "bca-portal#<mã>": dichvucong.bocongan.gov.vn (w-dvc)
    (r"bca-.+", "bca_decision"),               # "bca-<số hiệu>/QD-BCA-C06#<mã>": scanned BCA decisions (w-dvc)
    (r"daklak-.+", "provincial_decision"),     # "daklak-33/QD-UBND#<mã>": Đắk Lắk annex (w-moj)
    (r"dvc(-national)?", "national_db_page"),  # dichvucong.gov.vn (probably unused)
    (r"dvc-.+", "provincial_portal_page"),     # "dvc-<province>#…" (probably unused)
]
# Default source precedence: decisions over portals, national over provincial.
DEFAULT_PREFER = ["moj", "bca", "bca-portal", "daklak"]
# Source dirs whose fee rows are always loaded as extra rows for that province, even when another source
# wins the procedure row; their fee jurisdiction is set to the province.
PROVINCIAL_FEE_DIRS = {"daklak": "Đắk Lắk"}


def source_kind(source_id: str, kind_map: dict[str, str] | None = None) -> str:
    """sources.kind for a source_id; 'other' when no rule matches (callers warn)."""
    doc_id = source_id.split("#", 1)[0]
    for prefix, kind in (kind_map or {}).items():
        if doc_id.startswith(prefix):
            return kind
    for pattern, kind in KIND_RULES:
        if re.fullmatch(pattern, doc_id):
            return kind
    return "other"


def _clean(s):
    return s.strip() if isinstance(s, str) else s


def _json_list(x) -> str | None:
    return None if x is None else json.dumps([_clean(v) for v in x], ensure_ascii=False)


def fee_summary(fees: list[dict] | None) -> str | None:
    """Human-readable join of fee rows (≙ guidance le_phi). None when unknown — never 'free' by default."""
    if not fees:
        return None
    parts = []
    for f in fees:
        s = _clean(f["value"])
        if f.get("condition"):
            s += f" — {_clean(f['condition'])}"
        if f.get("jurisdiction"):
            s += f" ({_clean(f['jurisdiction'])})"
        parts.append(s)
    return "; ".join(parts)


def agency_rows(data: dict) -> list[dict]:
    name = _clean(data.get("receiving_agency"))
    if not name:
        return []
    return [{"name": name, "jurisdiction": _clean(data.get("jurisdiction")),
             "effective_date": (data.get("source") or {}).get("effective_date")}]


def agency_summary(rows: list[dict]) -> str | None:
    """Human-readable join of agency rows (≙ guidance co_quan)."""
    if not rows:
        return None
    return "; ".join(r["name"] + (f" ({r['jurisdiction']})" if r.get("jurisdiction") else "") for r in rows)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold() if isinstance(s, str) else repr(s)


def record_diff(a: dict, b: dict, fees: bool = True) -> list[tuple[str, str, str]]:
    """Field-level differences between two records of the same procedure: (field, a, b)."""
    diffs = []
    for k in ("title", "field", "level", "variant_of", "receiving_agency", "processing_time"):
        if _norm(a.get(k)) != _norm(b.get(k)):
            diffs.append((k, str(a.get(k)), str(b.get(k))))
    da, db_ = a.get("required_documents") or [], b.get("required_documents") or []
    if len(da) != len(db_):
        diffs.append(("required_documents (count)", str(len(da)), str(len(db_))))
    fa, fb = fee_summary(a.get("fees")), fee_summary(b.get("fees"))
    if fees and _norm(fa) != _norm(fb):
        diffs.append(("fees", str(fa), str(fb)))
    return diffs


# ---------------------------------------------------------------- build

@dataclass
class BuildReport:
    loaded: dict[str, int] = field(default_factory=dict)      # table -> rows
    skipped: list[Record] = field(default_factory=list)       # invalid records
    conflicts: list[str] = field(default_factory=list)        # markdown lines
    notes: list[str] = field(default_factory=list)            # markdown lines: warnings, extra fee rows


def select_records(records: list[Record], source_order: list[str]):
    """Group valid records by procedure_id; first in `source_order` wins.

    Returns ({procedure_id: [Record, ...] preferred-first}, conflict lines).
    """
    rank = {name: i for i, name in enumerate(source_order)}
    groups: dict[str, list[Record]] = {}
    for r in records:
        if r.ok:
            groups.setdefault(r.procedure_id, []).append(r)
    conflicts = []
    for pid, recs in groups.items():
        recs.sort(key=lambda r: (rank.get(r.source_dir, len(rank)), str(r.path)))
        seen_dirs = set()
        for r in recs:
            if r.source_dir in seen_dirs:
                conflicts.append(f"- **{pid}**: duplicate procedure_id within `{r.source_dir}`; "
                                 f"`{r.path}` ignored for procedure fields (source row still loaded)")
            seen_dirs.add(r.source_dir)
        win = recs[0]
        for other in recs[1:]:
            # provincial fee dirs add fee rows rather than conflict on fees
            for k, a, b in record_diff(win.data, other.data, fees=other.source_dir not in PROVINCIAL_FEE_DIRS):
                conflicts.append(f"- **{pid}** `{k}`: {win.source_dir}=`{a}` vs {other.source_dir}=`{b}` "
                                 f"→ kept {win.source_dir}")
    return groups, conflicts


def source_order(source_dirs: list[str | Path], prefer: str | list[str] | None = None) -> list[str]:
    """Dir basenames in precedence order: `prefer` (str or list) first, then the remaining dirs as given."""
    prefer = DEFAULT_PREFER if prefer is None else ([prefer] if isinstance(prefer, str) else list(prefer))
    names = [Path(d).name for d in source_dirs]
    head = [n for n in prefer if n in names]
    return head + [n for n in names if n not in head]


def fee_rows(recs: list[Record]) -> list[tuple[dict, str]]:
    """(fee, source_id) rows for a procedure: the winner's fees, plus the fees of the first record from each
    PROVINCIAL_FEE_DIRS dir that did not win. Fees from those dirs get the province as jurisdiction."""
    def rows(r):
        prov = PROVINCIAL_FEE_DIRS.get(r.source_dir)
        return [({**f, "jurisdiction": prov} if prov else f, source_id_of(r.data)) for f in r.data.get("fees") or []]
    out, seen = rows(recs[0]), {recs[0].source_dir}
    for r in recs[1:]:
        if r.source_dir in PROVINCIAL_FEE_DIRS and r.source_dir not in seen:
            out += rows(r)
        seen.add(r.source_dir)
    return out


def load_variants(path: str | Path | None = None) -> dict[str, str]:
    """{member procedure_id: root procedure_id} from data/variants.yaml (P19); {} if the file is missing."""
    import yaml
    path = Path(path or VARIANTS_PATH)
    if not path.exists():
        return {}
    out = {}
    for g in yaml.safe_load(path.read_text(encoding="utf-8")).get("groups") or []:
        for m in g.get("members") or []:
            out[str(m)] = str(g["root"])
    return out


def variant_of_for(d: dict, vmap: dict[str, str]) -> str | None:
    """The record's own variant_of wins; otherwise the variants.yaml root (None for roots and singletons)."""
    return d.get("variant_of") or vmap.get(d["procedure_id"])


def processing_time_choice(recs: list[Record]) -> tuple[str | None, str]:
    """(processing_time, source_id) for a procedure, `recs` preferred-first.

    The winner's value, unless it is empty or a bare number ("5"); then the first other source with a longer value.
    """
    win = recs[0].data
    value, sid = _clean(win.get("processing_time")), source_id_of(win)
    if not value or re.fullmatch(r"\s*\d+\s*", value):
        for r in recs[1:]:
            alt = _clean(r.data.get("processing_time"))
            if alt and len(alt) > len(value or ""):
                return alt, source_id_of(r.data)
    return value, sid


def build(out: str | Path, source_dirs: list[str | Path], prefer: str | list[str] | None = None,
          kind_map: dict[str, str] | None = None, variants: str | Path | None = None,
          docs: str | Path | None = None) -> BuildReport:
    """Rebuild the DB at `out` from scratch. Writes to a temp file, then atomically replaces.

    `variants`: sibling-group file (default data/variants.yaml if present) that fills missing variant_of.
    `docs`: cleaned non-procedure documents (`data/clean_docs`, from scripts/clean_documents.py) to load into
    documents / document_sections / document_procedures; None = none (the corpus-v1 DB).
    """
    out = Path(out)
    rep = BuildReport()
    vmap = load_variants(variants)
    present = [d for d in source_dirs if Path(d).is_dir()]
    rep.notes += [f"- source dir `{d}` does not exist; skipped" for d in source_dirs if d not in present]
    records = read_records(present)
    rep.skipped = [r for r in records if not r.ok]
    groups, rep.conflicts = select_records(records, source_order(present, prefer))

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(SCHEMA_SQL)
        # sources: every valid record contributes (one row per distinct source_id)
        src_seen: dict[str, tuple] = {}
        for recs in groups.values():
            for r in recs:
                sid, s = source_id_of(r.data), r.data["source"]
                row = (sid, source_kind(sid, kind_map), s["url"], s.get("locator"), s.get("title"),
                       s["retrieved_at"], s.get("effective_date"), s.get("content_hash"))
                if sid in src_seen:
                    if src_seen[sid] != row:
                        rep.conflicts.append(f"- source `{sid}` appears with different metadata "
                                             f"(`{r.path}`); first row kept")
                    continue
                src_seen[sid] = row
                if row[1] == "other":
                    rep.notes.append(f"- source `{sid}` (`{r.path}`): unknown doc-id prefix, kind='other'")
                con.execute("INSERT INTO sources (source_id, kind, url, locator, title, retrieved_at, effective_date,"
                            " content_hash) VALUES (?,?,?,?,?,?,?,?)", row)
        for pid in sorted(groups):
            d = groups[pid][0].data
            sid = source_id_of(d)
            agencies = agency_rows(d)
            fees = fee_rows(groups[pid])
            ptime, ptime_sid = processing_time_choice(groups[pid])
            vo = variant_of_for(d, vmap)
            if d.get("variant_of") and pid in vmap and vmap[pid] != d["variant_of"]:
                rep.notes.append(f"- **{pid}**: record variant_of {d['variant_of']} kept; variants.yaml says {vmap[pid]}")
            if ptime_sid != sid:
                rep.notes.append(f"- **{pid}**: processing_time {_clean(d.get('processing_time'))!r} → {ptime!r} from {ptime_sid}")
            n_extra = len(fees) - len(d.get("fees") or [])
            if n_extra:
                rep.notes.append(f"- **{pid}**: +{n_extra} provincial fee row(s) from "
                                 + ", ".join(sorted({s for _, s in fees} - {sid})))
            con.execute(
                "INSERT INTO procedures (id, title, field, fee_summary, agency_summary, processing_time,"
                " processing_time_source_id, level, variant_of, channels, legal_basis, conditions, source_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, _clean(d["title"]), _clean(d["field"]), fee_summary([f for f, _ in fees]),
                 agency_summary(agencies), ptime, ptime_sid, _clean(d.get("level")),
                 vo, _json_list(d.get("channels")), _json_list(d.get("legal_basis")),
                 _clean(d.get("conditions")), sid))
            for pos, doc in enumerate(d["required_documents"], 1):
                m = doc.get("mandatory")
                con.execute("INSERT INTO required_documents (procedure_id, position, item, quantity, quantity_text,"
                            " mandatory, note, source_id) VALUES (?,?,?,?,?,?,?,?)",
                            (pid, pos, _clean(doc["item"]), doc.get("quantity"), _clean(doc.get("quantity_text")),
                             None if m is None else int(m), _clean(doc.get("note")), sid))
            for f, fsid in fees:
                con.execute("INSERT INTO fees (procedure_id, value, condition, jurisdiction, source_id)"
                            " VALUES (?,?,?,?,?)",
                            (pid, _clean(f["value"]), _clean(f.get("condition")), _clean(f.get("jurisdiction")), fsid))
            for a in agencies:
                con.execute("INSERT INTO agencies (procedure_id, name, jurisdiction, effective_date, source_id)"
                            " VALUES (?,?,?,?,?)",
                            (pid, a["name"], a["jurisdiction"], a["effective_date"], sid))
        con.execute("INSERT INTO procedures_fts(procedures_fts) VALUES ('rebuild')")
        if docs is not None:
            _load_documents(con, docs, set(groups), rep)
        con.commit()
        for t in ("sources", "procedures", "required_documents", "fees", "agencies", "procedures_fts",
                  "documents", "document_sections", "document_procedures"):
            rep.loaded[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    finally:
        con.close()
    os.replace(tmp, out)
    return rep


def _load_documents(con, root: str | Path, procedure_ids: set[str], rep: BuildReport) -> None:
    """Insert cleaned documents. Invalid files and documents linked to no loaded procedure are skipped (noted)."""
    from src.documents import cross_check, read_documents
    if not Path(root).is_dir():
        rep.notes.append(f"- documents dir `{root}` does not exist; no documents loaded")
        return
    found = read_documents(root)
    cross_check(found, None)
    for d in found:
        if not d.ok:
            rep.notes.append(f"- document `{d.path}` skipped: {'; '.join(d.errors)}")
            continue
        x = d.data
        pids = [p for p in x["procedure_ids"] if p in procedure_ids]
        if len(pids) < len(x["procedure_ids"]):
            rep.notes.append(f"- document `{x['doc_id']}`: procedure(s) not in this DB dropped: "
                             + ", ".join(p for p in x["procedure_ids"] if p not in procedure_ids))
        if not pids:
            continue
        con.execute("INSERT INTO documents (id, kind, title, issuer, effective_date, jurisdiction, url, retrieved_at,"
                    " sha256, link_method, original_version, amended_by, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (x["doc_id"], x["kind"], _clean(x["title"]), _clean(x.get("issuer")), x.get("effective_date"),
                     _clean(x.get("jurisdiction")), x["url"], x["retrieved_at"][:10], x["sha256"],
                     x.get("link_method"), None if x.get("original_version") is None else int(x["original_version"]), _json_list(x.get("amended_by")),
                     _clean(x.get("notes"))))
        for pos, sec in enumerate(x["sections"], 1):
            con.execute("INSERT INTO document_sections (doc_id, position, heading, text) VALUES (?,?,?,?)",
                        (x["doc_id"], pos, sec["heading"], sec["text"]))
        for pid in pids:
            con.execute("INSERT INTO document_procedures (doc_id, procedure_id) VALUES (?,?)", (x["doc_id"], pid))
