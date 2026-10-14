"""Canonical records -> section chunks -> Chroma collection `corpus` (data-model.md §3).

Records are read with the same precedence as the DB (`src.db.read_records` + `select_records`), so the
index and `data/app.db` are two views of one record set. One chunk per non-empty section per procedure;
sections longer than ~900 tokens are sub-split with overlap. Chunk text starts with a Vietnamese prefix
`[Thủ tục: <title>] [Mục: <label>] `; the English section id lives in metadata only.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from src.db import (DEFAULT_PREFER, fee_rows, load_variants, processing_time_choice, read_records, select_records,
                    source_id_of, source_order, variant_of_for)
from src.evidence import doc_id
from src.llm import get_embeddings

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = "corpus"
# Fully local (R6): Chroma's anonymized telemetry off, via client Settings and, as a backstop, the env var.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

SECTION_LABELS = {  # English id -> Vietnamese label used in the chunk prefix
    "summary": "Tóm tắt",
    "required_documents": "Thành phần hồ sơ",
    "steps": "Trình tự thực hiện",
    "submission_method": "Cách thức thực hiện",
    "fees": "Phí, lệ phí",
    "agency": "Cơ quan thực hiện",
    "processing_time": "Thời hạn giải quyết",
    "conditions": "Yêu cầu, điều kiện",
    "legal_basis": "Căn cứ pháp lý",
}

# ROUND-4 documents: chunk `section` metadata reuses the procedure section ids (evidence contract, graph intent filters);
# the document kind is in `kind`. Procedure chunks have kind "procedure_page".
KIND_SECTION = {
    "legal_text": "legal_basis",
    "form": "required_documents",       # the tờ khai and its filling instructions belong with the dossier
    "fee_resolution": "fees",
    "guidance": "steps",
    "change_notice": "legal_basis",     # a change of the rules / version; also reached by unfiltered (general, update) retrieval
}
PROCEDURE_KIND = "procedure_page"
# An amended article's original wording is kept, but the generator and the judge must see that it is not current law.
ORIGINAL_MARK = "[Văn bản gốc – đã sửa đổi] "

# bge-m3 uses ~1.3–1.5 tokens per Vietnamese syllable; 600 words ≈ 900 tokens.
MAX_WORDS = 600
OVERLAP_WORDS = 60


def chroma_dir() -> Path:
    return Path(os.environ.get("CHROMA_DIR", ROOT / "data" / "chroma"))


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict


# ---------------------------------------------------------------- section text

def _join(lines) -> str:
    return "\n".join(s.strip() for s in lines if s and s.strip())


def section_texts(d: dict, fees: list[dict] | None = None) -> dict[str, str]:
    """Section id -> body text (Vietnamese, from the record verbatim). Empty sections are omitted.

    `fees` overrides `d["fees"]` (the build passes the same fee rows the DB gets, incl. provincial extras).
    Missing fees produce no `fees` chunk: unknown is not free.
    """
    fees = d.get("fees") if fees is None else fees
    s = {}
    head = [d["title"] + "."]
    meta = [f"Lĩnh vực: {d['field']}"]
    if d.get("level"):
        meta.append(f"cấp thực hiện: {d['level']}")
    if d.get("jurisdiction"):
        meta.append(f"phạm vi: {d['jurisdiction']}")
    head.append("; ".join(meta) + ".")
    if d.get("receiving_agency"):
        head.append(f"Cơ quan tiếp nhận: {d['receiving_agency']}.")
    s["summary"] = _join(head)

    docs = []
    for i, doc in enumerate(d.get("required_documents") or [], 1):
        parts = [doc["item"]]
        qty = doc.get("quantity_text") or (f"{doc['quantity']} bản" if doc.get("quantity") is not None else None)
        if qty:
            parts.append(f"số lượng: {qty}")
        if doc.get("mandatory") is True:
            parts.append("bắt buộc")
        elif doc.get("mandatory") is False:
            parts.append("không bắt buộc")
        if doc.get("note"):
            parts.append(f"ghi chú: {doc['note']}")
        docs.append(f"{i}. " + "; ".join(parts))
    s["required_documents"] = _join(docs)
    s["steps"] = _join(f"Bước {i}: {x}" for i, x in enumerate(d.get("steps") or [], 1))
    # `submission_method_text` is not in data-model.md §1 yet but both moj and daklak parsers emit it (verbatim source text)
    s["submission_method"] = _join([", ".join(d.get("channels") or []), d.get("submission_method_text") or ""])
    s["fees"] = _join(
        f["value"] + (f" — {f['condition']}" if f.get("condition") else "")
        + (f" ({f['jurisdiction']})" if f.get("jurisdiction") else "")
        for f in fees or [])
    agency = d.get("receiving_agency")
    s["agency"] = (agency + (f" ({d['jurisdiction']})" if d.get("jurisdiction") else "")) if agency else ""
    s["processing_time"] = d.get("processing_time") or ""
    s["conditions"] = d.get("conditions") or ""
    s["legal_basis"] = _join(d.get("legal_basis") or [])
    return {k: v.strip() for k, v in s.items() if v and v.strip()}


def split_words(body: str, max_words: int = MAX_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    """Split on line boundaries into pieces of <= max_words, repeating ~overlap words between pieces.
    A single line longer than max_words is split on words."""
    lines = []
    for line in body.split("\n"):
        w = line.split()
        while len(w) > max_words:
            lines.append(" ".join(w[:max_words]))
            w = w[max_words - overlap:]
        if w:
            lines.append(" ".join(w))
    if sum(len(x.split()) for x in lines) <= max_words:
        return ["\n".join(lines)]
    pieces, cur = [], []
    for line in lines:
        if cur and sum(len(x.split()) for x in cur) + len(line.split()) > max_words:
            pieces.append("\n".join(cur))
            tail, n = [], 0
            for prev in reversed(cur):  # carry trailing lines up to `overlap` words
                if n + len(prev.split()) > overlap:
                    break
                tail.insert(0, prev)
                n += len(prev.split())
            cur = tail
        cur.append(line)
    if cur:
        pieces.append("\n".join(cur))
    return pieces


def prefix(title: str, section: str) -> str:
    return f"[Thủ tục: {title}] [Mục: {SECTION_LABELS[section]}] "


def chunk_record(d: dict, source_id: str, fees: list[dict] | None = None) -> list[Chunk]:
    pid, src = d["procedure_id"], d["source"]
    base = {"procedure_id": pid, "source_id": source_id, "retrieved_at": src["retrieved_at"],
            "tier": "corpus", "title": d["title"], "source_url": src["url"], "kind": PROCEDURE_KIND}
    if src.get("effective_date"):
        base["effective_date"] = src["effective_date"]  # Chroma metadata may not hold None
    if d.get("variant_of"):
        base["variant_of"] = d["variant_of"]
    out = []
    for section, body in section_texts(d, fees).items():
        for i, piece in enumerate(split_words(body)):
            out.append(Chunk(doc_id(pid, section, i), prefix(d["title"], section) + piece,
                             {**base, "section": section}))
    return out


def document_chunk_id(pid: str, section: str, doc: str, i: int) -> str:
    """`doc:<procedure_id>:<section>:<8 hex of doc_id>-<i>`: the `doc:<pid>:<section>:` shape of procedure chunks
    (parsed by eval/run_variant.py, cited as [doc:…]) without clashing with their `<i>`."""
    return f"doc:{pid}:{section}:{hashlib.sha1(doc.encode('utf-8')).hexdigest()[:8]}-{i}"


def chunk_document(x: dict, titles: dict[str, str], variant_of: dict[str, str | None] | None = None) -> list[Chunk]:
    """Chunks of one cleaned document: one per section (sub-split like procedure sections) per linked procedure
    in `titles`. Text prefix `[Thủ tục: <procedure title>] [Văn bản: <document title>] [Mục: <heading>] `."""
    section = KIND_SECTION[x["kind"]]
    out = []
    for pid in x["procedure_ids"]:
        if pid not in titles:
            continue
        base = {"procedure_id": pid, "source_id": x["doc_id"], "doc_id": x["doc_id"], "kind": x["kind"],
                "retrieved_at": x["retrieved_at"][:10], "tier": "corpus", "title": titles[pid],
                "doc_title": x["title"], "source_url": x["url"], "section": section}
        for k in ("effective_date", "jurisdiction"):
            if x.get(k):
                base[k] = x[k]
        if x.get("original_version") is True:
            base["original_version"] = True
            base["amended_by"] = "; ".join(x.get("amended_by") or [])   # Chroma metadata holds no lists
        if (variant_of or {}).get(pid):
            base["variant_of"] = variant_of[pid]
        i = 0
        for sec in x["sections"]:
            head = (ORIGINAL_MARK if x.get("original_version") is True else "") + \
                f"[Thủ tục: {titles[pid]}] [Văn bản: {x['title']}] [Mục: {sec['heading']}] "
            for piece in split_words(sec["text"]):
                out.append(Chunk(document_chunk_id(pid, section, x["doc_id"], i), head + piece, dict(base)))
                i += 1
    return out


def chunks_from_documents(root: str | Path, titles: dict[str, str],
                          variant_of: dict[str, str | None] | None = None) -> list[Chunk]:
    """Chunks for every valid cleaned document under `root` (data/clean_docs), linked procedures restricted to `titles`."""
    from src.documents import read_documents
    out = []
    for d in read_documents(root):
        if d.ok:
            out += chunk_document(d.data, titles, variant_of)
    return out


def chunks_from_sources(source_dirs: list[str | Path], prefer: str | list[str] | None = None,
                        variants: str | Path | None = None, docs: str | Path | None = None) -> list[Chunk]:
    """All chunks for the merged record set (same precedence, fee rows, processing_time and variant_of as `src.db.build`).
    `docs`: also chunk the cleaned documents there (ROUND-4), as `src.db.build(docs=...)` loads them."""
    vmap = load_variants(variants)
    present = [d for d in source_dirs if Path(d).is_dir()]
    groups, _ = select_records(read_records(present), source_order(present, prefer))
    out = []
    for pid in sorted(groups):
        win = groups[pid][0].data
        ptime, _ = processing_time_choice(groups[pid])  # same fallback as the DB
        out += chunk_record({**win, "processing_time": ptime, "variant_of": variant_of_for(win, vmap)},
                            source_id_of(win), [f for f, _ in fee_rows(groups[pid])])
    if docs is not None and Path(docs).is_dir():
        titles = {pid: groups[pid][0].data["title"] for pid in groups}
        out += chunks_from_documents(docs, titles, {pid: variant_of_for(groups[pid][0].data, vmap) for pid in groups})
    return out


# ---------------------------------------------------------------- Chroma

def chroma_client(path: str | Path | None = None):
    """The one way this project opens Chroma: a local PersistentClient with anonymized telemetry disabled."""
    import chromadb
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=str(path or chroma_dir()), settings=Settings(anonymized_telemetry=False))


def open_store(path: str | Path | None = None, embeddings=None):
    from langchain_chroma import Chroma
    return Chroma(collection_name=COLLECTION, embedding_function=embeddings or get_embeddings(),
                  client=chroma_client(path), collection_metadata={"hnsw:space": "cosine"})


def build_index(chunks: list[Chunk], path: str | Path | None = None, embeddings=None) -> int:
    """Drop and rebuild the `corpus` collection from `chunks`. Returns the chunk count."""
    path = Path(path or chroma_dir())
    path.mkdir(parents=True, exist_ok=True)
    client = chroma_client(path)
    if COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    store = open_store(path, embeddings)
    for i in range(0, len(chunks), 64):
        batch = chunks[i:i + 64]
        store.add_texts([c.text for c in batch], metadatas=[c.metadata for c in batch], ids=[c.id for c in batch])
    return store._collection.count()


def sync_index(chunks: list[Chunk], path: str | Path | None = None, embeddings=None, dry_run: bool = False) -> dict:
    """Make the existing `corpus` collection at `path` equal to `chunks`, embedding only new or changed texts.
    Metadata-only changes are re-added with the stored embedding (delete + add; Chroma's upsert merges metadata, so a
    removed key such as a stale effective_date would survive).
    Returns counts {deleted, added, reembedded, metadata, unchanged}."""
    path = Path(path or chroma_dir())
    store = open_store(path, embeddings)
    coll = store._collection
    have = coll.get(include=["documents", "metadatas"])
    old = {i: (t, m) for i, t, m in zip(have["ids"], have["documents"], have["metadatas"])}
    want = {c.id: c for c in chunks}
    deleted = [i for i in old if i not in want]
    added = [c for i, c in want.items() if i not in old]
    retext = [c for i, c in want.items() if i in old and old[i][0] != c.text]
    remeta = [c for i, c in want.items() if i in old and old[i][0] == c.text and old[i][1] != c.metadata]
    rep = {"deleted": len(deleted), "added": len(added), "reembedded": len(retext), "metadata": len(remeta),
           "unchanged": len(want) - len(added) - len(retext) - len(remeta)}
    if dry_run:
        return rep
    for i in range(0, len(deleted), 256):
        coll.delete(ids=deleted[i:i + 256])
    for i in range(0, len(remeta), 256):
        batch = remeta[i:i + 256]
        got = coll.get(ids=[c.id for c in batch], include=["embeddings"])
        emb = dict(zip(got["ids"], got["embeddings"]))
        coll.delete(ids=[c.id for c in batch])   # upsert would merge metadata and keep removed keys
        coll.add(ids=[c.id for c in batch], embeddings=[emb[c.id] for c in batch],
                 metadatas=[c.metadata for c in batch], documents=[c.text for c in batch])
    todo = added + retext
    for i in range(0, len(todo), 64):
        batch = todo[i:i + 64]
        stale = [c.id for c in batch if c.id in old]
        if stale:   # Chroma rejects an empty id list
            coll.delete(ids=stale)
        store.add_texts([c.text for c in batch], metadatas=[c.metadata for c in batch], ids=[c.id for c in batch])
    return rep
