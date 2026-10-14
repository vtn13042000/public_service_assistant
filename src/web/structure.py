"""Answer parts for the web card (docs/03_design/web-ui.md §4): the same final text, split so the page can show it summary-first.

Pure functions over the final graph state. Nothing here creates or rewrites text: every string returned is a line
or paragraph that already appears in `state["generation"]` (or the code-rendered block inside it), so the CLI, the
evaluation and the page all show the same words. Sources:
- sections: `state["block"]` (render.render_block: one section per property, one line per DB row, each with its [db:…] tag);
- narrative: `state["draft"]` minus the block (the model's sentences that survived check_support / prune_claims);
- gaps, notices, notes, sources: the paragraphs `finalize` appended to the draft, recognised by their fixed openings.
"""
from __future__ import annotations

import re

# fixed openings of the paragraphs src/nodes.py finalize appends after the draft
GAP_PREFIX = "Không tìm thấy căn cứ về:"
SOURCES_PREFIX = "Nguồn:\n"
NOTICE_PREFIXES = ("Lưu ý:", "và ")            # freshness / change notices, and "và N văn bản khác (xem nguồn)."
NOTE_PREFIXES = ("Thông tin trên", "Việc bạn có đủ điều kiện")  # sibling group / assumed variant / eligibility

SECTION_KINDS = (  # block heading → property
    ("Thành phần hồ sơ", "documents"),
    ("Lệ phí", "fees"),
    ("Cơ quan tiếp nhận", "agency"),
    ("Thời gian giải quyết", "time"),
)
_CITE = re.compile(r"\s*((?:\[[a-z_]+:[^\]]+\]\s*)+)$")
_ITEM = re.compile(r"^(?:\d+\.\s+|-\s+)")


def _split_cite(line: str) -> tuple[str, list[str]]:
    m = _CITE.search(line)
    if not m:
        return line.strip(), []
    return line[: m.start()].strip(), re.findall(r"\[([^\]]+)\]", m.group(1))


def _kind(heading: str) -> str:
    for prefix, kind in SECTION_KINDS:
        if heading.startswith(prefix):
            return kind
    return "other"


def block_sections(block: str) -> list[dict]:
    """The code-rendered block as [{kind, heading, items: [{text, cites}]}]; fee sub-groups stay separate sections."""
    sections: list[dict] = []
    cur: dict | None = None
    for raw in (block or "").splitlines():
        line = raw.strip()
        if not line:
            cur = None
            continue
        if cur is not None and _ITEM.match(line):
            text, cites = _split_cite(_ITEM.sub("", line, count=1))
            cur["items"].append({"text": text, "cites": cites})
            continue
        text, cites = _split_cite(line)
        if text.endswith(":") and not cites:            # a heading with a list below it
            cur = {"kind": _kind(text), "heading": text[:-1], "items": []}
            sections.append(cur)
        else:                                            # a one-line section, e.g. "Thời gian giải quyết: 05 ngày …"
            head, _, value = text.partition(": ")
            kind = _kind(head)
            sections.append({"kind": kind, "heading": head if kind != "other" else "",
                             "items": [{"text": value if kind != "other" else text, "cites": cites}]})
            cur = None
    return sections


def answer_parts(state: dict) -> dict | None:
    """Structured parts of an answer / answer_partial; None for the other outcomes (their text is short)."""
    if state.get("outcome") not in ("answer", "answer_partial"):
        return None
    block = state.get("block") or ""
    draft = state.get("draft") or ""
    narrative = draft.replace(block, "").strip() if block else draft.strip()
    gen = state.get("generation") or ""
    tail = gen[len(draft):] if draft and gen.startswith(draft) else gen
    gap_text, notices, notes = None, [], []
    for para in (p.strip() for p in tail.split("\n\n")):
        if not para or para.startswith(SOURCES_PREFIX):
            continue
        if para.startswith(GAP_PREFIX):
            gap_text = para
        elif para.startswith(NOTICE_PREFIXES):
            notices.append(para)
        elif para.startswith(NOTE_PREFIXES):
            notes.append(para)
    pid = state.get("procedure_id")
    title = next((c.get("title") for c in state.get("candidates") or [] if c.get("procedure_id") == pid), None)
    if not title:
        from src.render import title_of
        title = title_of(state.get("evidence") or [])
    need = state.get("need") or {}
    return {
        "procedure": {"id": pid, "title": title},
        "locality": state.get("locality") or need.get("locality"),
        "intent": need.get("intent"),
        "gap_text": gap_text,
        "gaps": [{"element": g.get("element"), "kind": g.get("kind"), "detail": g.get("detail")}
                 for g in state.get("gaps") or []],
        "sections": block_sections(block),
        "narrative": narrative,
        "notices": notices,
        "notes": notes,
    }
