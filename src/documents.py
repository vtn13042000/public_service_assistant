"""Non-procedure documents (ROUND-4-DATA.md): read, validate, clean ("làm sạch"), link to procedures.

A document is a legal article, form, fee resolution, guidance page or change notice, stored as
`data/processed_docs/<kind>/<file>.json` (collectors) and, after `scripts/clean_documents.py`, as
`data/clean_docs/<kind>/<file>.json` (what the loader and the indexer read). Shape:
`data/schema/document_record.schema.json`. Content stays Vietnamese verbatim apart from the cleaning
actions listed per document (Unicode NFC, whitespace, boilerplate lines, HTML remnants, legal re-segmentation).
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import jsonschema

from src.db import ROOT, is_iso_date

DOC_SCHEMA_PATH = ROOT / "data" / "schema" / "document_record.schema.json"
DOC_KINDS = ("legal_text", "form", "fee_resolution", "guidance", "change_notice")
VERSIONED_KINDS = ("legal_text", "form")   # versioned by the instrument that issues them (forms: by circular)
DOC_ID_PREFIX = {"legal_text": "legal", "form": "form", "fee_resolution": "fee", "guidance": "guide",
                 "change_notice": "change"}
LEGAL_HEADING = re.compile(r"^(Điều|Khoản|Điểm|Mục|Chương|Phụ lục|Mẫu)\b", re.I)
ARTICLE_LINE = re.compile(r"^Điều\s+\d+[a-zđ]?\s*[.:]", re.I)

# Whole-line navigation / boilerplate (matched case-insensitively after whitespace normalisation).
BOILERPLATE = [re.compile(p, re.I) for p in (
    r"(trang chủ|home)(\s*[>›»/|].*)?",
    r"(in|in trang|in bài|bản in|chia sẻ|share|gửi email|gửi bài|lưu|lưu bài|tải về|download|quay lại|trở về|"
    r"xem thêm|đầu trang|lên đầu trang|bình luận|góp ý|đăng nhập|menu)\s*:?",
    r"(facebook|zalo|twitter|youtube|email|e-mail)",
    r"(bản quyền|copyright|©).*",
    r"(lượt xem|số lượt truy cập|lượt truy cập)\s*:?\s*[\d.,]*",
    r".*(sử dụng cookie|chấp nhận cookie).*",
    r"(cỡ chữ|font size)\s*:?.*",
)]
# A line like this ends the useful text of a news/guidance page: it and everything after it are dropped.
RELATED_TAIL = re.compile(r"(tin liên quan|bài viết liên quan|các tin khác|tin khác|tin cùng chuyên mục|xem tiếp)\s*:?", re.I)
# Below this many letters a document is treated as scanned/empty (no OCR). A real one-sentence article has ~50.
MIN_LETTERS = 20
ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿­"), None)


@dataclass
class Doc:
    path: Path
    kind_dir: str                  # name of the directory the file sits in (must equal data["kind"])
    data: dict | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)   # cleaning actions applied

    @property
    def ok(self) -> bool:
        return not self.errors and self.data is not None

    @property
    def doc_id(self) -> str | None:
        return (self.data or {}).get("doc_id") if isinstance(self.data, dict) else None


def load_doc_schema() -> dict:
    return json.loads(DOC_SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_errors(data, validator) -> list[str]:
    errs = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))]
    if isinstance(data, dict):
        for k in ("retrieved_at", "effective_date"):
            if data.get(k) is not None and not is_iso_date(data[k]):
                errs.append(f"{k}: not an ISO date: {data[k]!r}")
    return errs


def _texts(data: dict):
    yield data.get("title") or ""
    for s in data.get("sections") or []:
        if isinstance(s, dict):
            yield s.get("heading") or ""
            yield s.get("text") or ""


def doc_smells(data: dict, path: Path | None = None) -> list[str]:
    """Non-fatal warnings for one document."""
    w = []
    kind = data.get("kind")
    texts = list(_texts(data))
    body = "\n".join(texts)
    if any(unicodedata.normalize("NFC", t) != t for t in texts):
        w.append("text not Unicode NFC (clean_documents.py normalises)")
    if re.search(r"<[a-zA-Z/][^>]*>|&(nbsp|amp|lt|gt|quot|#\d+);", body):
        w.append("HTML tags or entities in text")
    lines = [ln.strip() for t in texts[1:] for ln in t.split("\n") if ln.strip()]
    n_bp = sum(1 for ln in lines if is_boilerplate(ln) or RELATED_TAIL.fullmatch(ln))
    if n_bp:
        w.append(f"boilerplate lines: {n_bp}")
    if kind == "legal_text":
        bad = [s.get("heading", "") for s in data.get("sections") or [] if not LEGAL_HEADING.match(s.get("heading", ""))]
        if bad:
            w.append(f"legal_text heading not Điều/Khoản/…: {bad[0][:60]!r}" + (f" (+{len(bad) - 1})" if len(bad) > 1 else ""))
        multi = [s.get("heading", "") for s in data.get("sections") or []
                 if sum(bool(ARTICLE_LINE.match(ln.strip())) for ln in s.get("text", "").split("\n")) >= 1]
        if multi:
            w.append(f"legal_text section holds another 'Điều N.' line (segmentation): {multi[0][:60]!r}")
    if (data.get("original_version") is not None or data.get("amended_by")) and kind not in VERSIONED_KINDS:
        w.append("original_version / amended_by set on a document that is not legal_text or form")
    if data.get("original_version") is True and not data.get("amended_by"):
        w.append("original_version true without amended_by")
    if data.get("amended_by") and data.get("original_version") is not True:
        w.append("amended_by set but original_version is not true")
    if kind == "fee_resolution" and not data.get("jurisdiction"):
        w.append("fee_resolution without jurisdiction")
    short = [s.get("heading", "") for s in data.get("sections") or [] if len((s.get("text") or "").strip()) < 30]
    if short:
        w.append(f"section text < 30 chars: {short[0][:60]!r}" + (f" (+{len(short) - 1})" if len(short) > 1 else ""))
    letters = [c for c in body if c.isalpha()]
    if letters and not re.search(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", body.lower()):
        w.append("no Vietnamese diacritics (lost in extraction?)")
    if len(letters) < MIN_LETTERS:
        w.append(f"almost no text ({len(letters)} letters; scanned or empty?)")
    ra, ed = data.get("retrieved_at"), data.get("effective_date")
    if isinstance(ra, str) and len(ra) > 10:
        w.append("retrieved_at is a timestamp (date part used)")
    if is_iso_date(ra) and is_iso_date(ed) and ed[:10] > ra[:10]:
        w.append(f"effective_date {ed} after retrieved_at (not yet in force?)")
    if not data.get("link_method"):
        w.append("link_method missing (how were procedure_ids found?)")
    elif data["link_method"] == "manual" and not data.get("notes"):
        w.append("link_method manual without notes")
    did = data.get("doc_id") or ""
    if kind in DOC_ID_PREFIX and isinstance(did, str) and not did.startswith(DOC_ID_PREFIX[kind] + ":"):
        w.append(f"doc_id prefix is not '{DOC_ID_PREFIX[kind]}:' (kind {kind})")
    host = urlparse(data.get("url") or "").hostname or ""
    if host and not (host.endswith(".gov.vn") or host == "gov.vn" or host.endswith("chinhphu.vn")):
        w.append(f"url host {host} is not a government host")
    return w


def read_documents(root: str | Path, schema: dict | None = None) -> list[Doc]:
    """Read and validate every `<root>/<kind>/*.json` (sorted). Files outside a known kind dir are errors."""
    root = Path(root)
    validator = jsonschema.Draft202012Validator(schema or load_doc_schema())
    out = []
    for p in sorted(root.rglob("*.json")):
        kind_dir = p.relative_to(root).parts[0] if len(p.relative_to(root).parts) > 1 else ""
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            out.append(Doc(p, kind_dir, None, [f"unreadable JSON: {e}"]))
            continue
        d = Doc(p, kind_dir, data, _schema_errors(data, validator))
        if isinstance(data, dict):
            if kind_dir not in DOC_KINDS:
                d.errors.append(f"file is not under a kind directory ({', '.join(DOC_KINDS)})")
            elif data.get("kind") != kind_dir:
                d.errors.append(f"kind {data.get('kind')!r} != directory {kind_dir!r}")
            d.warnings = doc_smells(data, p)
        out.append(d)
    return out


def text_sha256(sections: list[dict]) -> str:
    """sha256 of the NFC, whitespace-collapsed headings and texts: the content identity used for de-duplication.
    (`sha256` is the raw fetched file; many per-article documents legitimately share it.)"""
    import hashlib
    joined = "\n".join(re.sub(r"\s+", " ", unicodedata.normalize("NFC", f"{s.get('heading', '')}\n{s.get('text', '')}")).strip()
                       for s in sections)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def cross_check(docs: list[Doc], procedure_ids: set[str] | None) -> None:
    """Cross-document checks, added to each Doc: duplicate doc_id (error), duplicate text / (kind, title) (warning),
    unknown procedure_ids (error when `procedure_ids` is given). A shared raw-file `sha256` is normal (articles of one law)."""
    ids = Counter(d.doc_id for d in docs if d.ok)
    first_text: dict[str, Path] = {}
    first_title: dict[tuple, Path] = {}
    for d in docs:
        if not d.ok:
            continue
        if ids[d.doc_id] > 1:
            d.errors.append(f"doc_id {d.doc_id} appears in {ids[d.doc_id]} files")
        th = text_sha256(d.data["sections"])
        if th in first_text:
            d.warnings.append(f"duplicate text: same sections as {first_text[th]}")
        else:
            first_text[th] = d.path
        key = (d.data["kind"], norm_title(d.data["title"]))
        if key in first_title:
            d.warnings.append(f"duplicate (kind, title): same as {first_title[key]}")
        else:
            first_title[key] = d.path
        if procedure_ids is not None:
            unknown = [p for p in d.data["procedure_ids"] if p not in procedure_ids]
            if unknown:
                d.errors.append(f"procedure_ids not in the procedure records: {', '.join(unknown)}")


# ---------------------------------------------------------------- cleaning

def norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip().rstrip(".").lower()


def is_boilerplate(line: str) -> bool:
    return any(p.fullmatch(line) for p in BOILERPLATE)


def normalise_text(s: str) -> tuple[str, list[str]]:
    """NFC, HTML remnants, zero-width/nbsp, whitespace per line, blank-line runs. Returns (text, actions)."""
    acts = []
    t = unicodedata.normalize("NFC", s)
    if t != s:
        acts.append("nfc")
    u = html.unescape(t)
    u2 = re.sub(r"<[^>]+>", " ", u)
    if u2 != t:
        acts.append("html")
    t = u2.translate(ZERO_WIDTH).replace(" ", " ").replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    lines = [re.sub(r" {2,}", " ", ln).strip() for ln in t.split("\n")]
    t2 = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if t2 != unicodedata.normalize("NFC", s).strip() and "html" not in acts:
        acts.append("whitespace")
    return t2, acts


def strip_boilerplate(text: str, repeated: set[str]) -> tuple[str, list[str]]:
    """Drop navigation/boilerplate lines, lines repeated across the same site (`repeated`), and the related-news tail."""
    acts, keep = [], []
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s and RELATED_TAIL.fullmatch(s):
            acts.append(f"tail cut at {s!r} ({len(lines) - i} lines)")
            break
        if s and is_boilerplate(s):
            acts.append(f"boilerplate {s[:40]!r}")
            continue
        if s and s in repeated:
            acts.append(f"repeated site line {s[:40]!r}")
            continue
        keep.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip(), acts


def resegment_legal(sections: list[dict]) -> tuple[list[dict], list[str]]:
    """Split legal_text sections that contain further 'Điều N.' lines, one section per article."""
    out, acts = [], []
    for s in sections:
        lines = s["text"].split("\n")
        cuts = [i for i, ln in enumerate(lines) if ARTICLE_LINE.match(ln.strip())]
        if not cuts:
            out.append(s)
            continue
        head = "\n".join(lines[:cuts[0]]).strip()
        if head:
            out.append({"heading": s["heading"], "text": head})
        for a, b in zip(cuts, cuts[1:] + [len(lines)]):
            body = "\n".join(lines[a + 1:b]).strip()
            out.append({"heading": lines[a].strip(), "text": body or lines[a].strip()})
        acts.append(f"resegmented {s['heading'][:40]!r} into {len(cuts) + bool(head)} article sections")
    return out, acts


def repeated_site_lines(docs: list[Doc], min_docs: int = 4, share: float = 0.5, max_len: int = 120) -> dict[str, set[str]]:
    """Per host: short lines that occur in at least `share` of that host's documents (and in >= `min_docs`):
    site headers/footers. Legal texts are excluded (their shared lines are content, e.g. 'Căn cứ …')."""
    by_host: dict[str, list[set[str]]] = defaultdict(list)
    for d in docs:
        if not d.ok or d.data["kind"] == "legal_text":
            continue
        host = urlparse(d.data["url"]).hostname or ""
        lines = {ln.strip() for s in d.data["sections"] for ln in s["text"].split("\n")
                 if ln.strip() and len(ln.strip()) <= max_len}
        by_host[host].append(lines)
    out = {}
    for host, sets in by_host.items():
        if len(sets) < min_docs:
            continue
        c = Counter(ln for st in sets for ln in st)
        out[host] = {ln for ln, n in c.items() if n >= max(min_docs, share * len(sets))}
    return out


def clean_document(d: Doc, repeated: set[str], procedure_ids: set[str] | None) -> dict | None:
    """Cleaned copy of `d.data` (actions in `d.actions`), or None with the reason in `d.errors`."""
    data = json.loads(json.dumps(d.data, ensure_ascii=False))
    for k in ("title", "issuer", "jurisdiction", "notes"):
        if isinstance(data.get(k), str):
            new, acts = normalise_text(data[k])
            new = re.sub(r"\s+", " ", new)
            if new != data[k]:
                d.actions.append(f"{k}: {'+'.join(acts) or 'whitespace'}")
            data[k] = new
    if isinstance(data.get("retrieved_at"), str) and len(data["retrieved_at"]) > 10:
        data["retrieved_at"] = data["retrieved_at"][:10]
        d.actions.append("retrieved_at: timestamp -> date")
    sections = []
    for s in data["sections"]:
        h, ha = normalise_text(s["heading"])
        h = re.sub(r"\s+", " ", h)
        t, ta = normalise_text(s["text"])
        t, ba = strip_boilerplate(t, repeated)
        if ha or ta:
            d.actions.append(f"section {h[:30]!r}: {'+'.join(dict.fromkeys(ha + ta))}")
        d.actions += [f"section {h[:30]!r}: {a}" for a in ba]
        if not t:
            d.actions.append(f"section {h[:30]!r} dropped (empty after cleaning)")
            continue
        sections.append({"heading": h, "text": t})
    if data["kind"] == "legal_text":
        sections, acts = resegment_legal(sections)
        d.actions += acts
    if not sections:
        d.errors.append("no text left after cleaning")
        return None
    if sum(c.isalpha() for s in sections for c in s["text"]) < MIN_LETTERS:
        d.errors.append(f"almost no text (< {MIN_LETTERS} letters): scanned or empty, skipped (no OCR)")
        return None
    data["sections"] = sections
    if procedure_ids is not None:
        unknown = [p for p in data["procedure_ids"] if p not in procedure_ids]
        if unknown:
            data["procedure_ids"] = [p for p in data["procedure_ids"] if p in procedure_ids]
            d.actions.append(f"unknown procedure_ids removed: {', '.join(unknown)}")
        if not data["procedure_ids"]:
            d.errors.append("no existing procedure linked")
            return None
    data["text_sha256"] = text_sha256(sections)
    data["cleaning_actions"] = d.actions
    return data


def clean_corpus(docs: list[Doc], procedure_ids: set[str] | None) -> tuple[list[tuple[Doc, dict]], list[Doc]]:
    """Clean all valid documents; de-duplicate by doc_id, cleaned text (`text_sha256`) and (kind, title), first file
    (sorted path) wins. The raw-file `sha256` is provenance only: articles cut from one law share it.
    Returns ([(doc, cleaned data)], [skipped docs with reasons in .errors])."""
    rep = repeated_site_lines(docs)
    kept, skipped = [], []
    seen_id: dict[str, Path] = {}
    seen_text: dict[str, Path] = {}
    seen_title: dict[tuple, Path] = {}
    for d in docs:
        if not d.ok:
            skipped.append(d)
            continue
        host = urlparse(d.data["url"]).hostname or ""
        data = clean_document(d, rep.get(host, set()), procedure_ids)
        if data is None:
            skipped.append(d)
            continue
        key = (data["kind"], norm_title(data["title"]))
        dup = (f"duplicate doc_id of {seen_id[data['doc_id']]}" if data["doc_id"] in seen_id else
               f"duplicate text (same cleaned sections) of {seen_text[data['text_sha256']]}" if data["text_sha256"] in seen_text else
               f"duplicate (kind, title) of {seen_title[key]}" if key in seen_title else None)
        if dup:
            d.errors.append(dup)
            skipped.append(d)
            continue
        seen_id[data["doc_id"]], seen_text[data["text_sha256"]], seen_title[key] = d.path, d.path, d.path
        kept.append((d, data))
    return kept, skipped


def procedure_ids_from(source_dirs: list[str | Path]) -> set[str]:
    from src.db import read_records
    return {r.procedure_id for r in read_records([p for p in source_dirs if Path(p).is_dir()]) if r.ok}
