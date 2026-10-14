"""Code-rendered structured block (guardrails.md L5). No LLM.

Every structured fact the user sees (document item, fee, agency, processing time) is a line
built here from a `db` evidence row and ends with that row's `[db:…]` id. The LLM writes only the
narrative around this block and is told the block is fixed text.

Rows are recognised by their columns (data-model.md §2): `item` → required_documents,
`value` → fees, `name` → agencies, `processing_time` → procedures.
What cannot be rendered becomes a *gap*: `missing` (no row: unknown is not free) or
`needs_input` (fees vary by province and the locality is unknown).
"""
from __future__ import annotations

import re
import unicodedata

from src.evidence import Evidence

# which blocks each intent shows (architecture.md §5 gather_evidence; walkthrough 5: agency + documents)
INTENT_BLOCKS = {
    "documents": ("documents",),
    "fee": ("fees",),
    "agency": ("agency", "documents"),
    "time": ("time",),
    "steps": (),
    "general": ("documents", "fees", "agency", "time"),
    "update": ("agency", "fees"),
}
# the element of each block that the user asked for when it is the intent's primary block
ELEMENT = {"documents": "thành phần hồ sơ", "fees": "lệ phí", "agency": "cơ quan tiếp nhận", "time": "thời gian giải quyết",
           "steps": "trình tự thực hiện"}
PRIMARY = {"documents": "documents", "fee": "fees", "agency": "agency", "time": "time"}  # intents with a code-rendered block
# what the user asked, in plain words, per intent: an insufficient_evidence refusal always names it (refusal_type)
ASKED = {**{i: ELEMENT[k] for i, k in PRIMARY.items()}, "steps": ELEMENT["steps"],
         "general": "thông tin chung về thủ tục", "update": "thông tin cập nhật của thủ tục"}
VARIES = ("theo tỉnh", "theo hđnd", "hđnd tỉnh", "tùy tỉnh", "tuỳ tỉnh")
NATIONWIDE = ("toàn quốc", "cả nước")
_FREE = re.compile(r"miễn|miễn phí|không mất (tiền|phí)|không thu|free")


def _row(e: Evidence) -> dict:
    return e.get("structured") or {}


def rows_with(evidence: list[Evidence], key: str) -> list[Evidence]:
    return [e for e in evidence if e["tier"] == "db" and _row(e).get(key) not in (None, "")]


def _cite(e: Evidence) -> str:
    return f"[{e['evidence_id']}]"


def _date(e: Evidence) -> str:
    return (e.get("retrieved_at") or "không rõ")[:10]


def _low(s) -> str:
    return unicodedata.normalize("NFC", str(s or "")).lower()


def render_documents(evidence: list[Evidence]) -> list[str]:
    rows = sorted(rows_with(evidence, "item"), key=lambda e: (_row(e).get("position") or 0))
    if not rows:
        return []
    lines = ["Thành phần hồ sơ:"]
    for n, e in enumerate(rows, 1):
        r = _row(e)
        qty = r.get("quantity_text") or (f"{r['quantity']} bản" if r.get("quantity") is not None else None)
        parts = [r["item"]]
        if qty:
            parts.append(qty)
        if r.get("mandatory") is not None:
            parts.append("bắt buộc" if r["mandatory"] else "không bắt buộc")
        line = f"{n}. " + " — ".join(parts)
        if r.get("note"):
            line += f" (ghi chú: {r['note']})"
        lines.append(f"{line} {_cite(e)}")
    return lines


def _jurisdiction(r: dict) -> str:
    return r.get("jurisdiction") or "nguồn không ghi phạm vi áp dụng"


def _varies(r: dict) -> bool:
    text = _low(f"{r.get('value')} {r.get('jurisdiction')}")
    return any(v in text for v in VARIES)


def _is_national(r: dict) -> bool:
    j = _low(r.get("jurisdiction"))
    return not j or any(n in j for n in NATIONWIDE) or any(v in j for v in VARIES)


def _fee_line(e: Evidence) -> str:
    r = _row(e)
    cond = f" ({r['condition']})" if r.get("condition") else ""
    return (f"- {r['value']}{cond} — phạm vi: {_jurisdiction(r)} — theo nguồn {e.get('source_url') or 'không rõ'}, "
            f"ngày lấy {_date(e)} {_cite(e)}")


def render_fees(evidence: list[Evidence], locality: str | None) -> tuple[list[str], list[dict]]:
    """Fee lines grouped by jurisdiction, each line with its jurisdiction and source date.

    National rows ("toàn quốc", unspecified, or "theo tỉnh"/HĐND statements) are always shown. Provincial rows
    (a named province, e.g. Đắk Lắk) are shown only for the user's locality. Without a locality, the provinces
    that have their own rows are named in a `needs_input` gap; with a locality that has no row while the fee
    varies by province, a `missing` gap is returned. No rows at all → `missing` (unknown is not free)."""
    rows = rows_with(evidence, "value")
    if not rows:
        return [], [{"element": ELEMENT["fees"], "kind": "missing", "detail": "không có dữ liệu lệ phí cho thủ tục này"}]
    loc = _low(locality)
    national = [e for e in rows if _is_national(_row(e))]
    provincial = [e for e in rows if not _is_national(_row(e))]
    mine = [e for e in provincial if loc and loc in _low(_row(e).get("jurisdiction"))]
    provinces = sorted({_row(e)["jurisdiction"] for e in provincial})
    lines: list[str] = []
    if national:
        lines += ["Lệ phí (áp dụng toàn quốc / theo quy định chung):"] + [_fee_line(e) for e in national]
    if mine:
        lines += ([""] if lines else []) + [f"Lệ phí tại {_row(mine[0])['jurisdiction']}:"] + [_fee_line(e) for e in mine]
    gaps: list[dict] = []
    varies = any(_varies(_row(e)) for e in national)
    if not loc and (varies or provinces):
        detail = "lệ phí do HĐND tỉnh quy định" if varies else "một số tỉnh có mức riêng"
        if provinces:
            detail += f"; kho dữ liệu có mức riêng của: {', '.join(provinces)}"
        gaps.append({"element": "lệ phí tại tỉnh/thành của bạn", "kind": "needs_input",
                     "detail": detail + "; vui lòng cho biết tỉnh/thành phố"})
    elif loc and varies and not mine:
        gaps.append({"element": f"lệ phí tại {locality}", "kind": "missing",
                     "detail": f"kho dữ liệu chưa có mức lệ phí của {locality}"})
    if not lines:  # only provincial rows, none for this user
        gaps.append({"element": ELEMENT["fees"], "kind": "missing" if loc else "needs_input",
                     "detail": f"chỉ có mức lệ phí của: {', '.join(provinces)}"})
    return lines, gaps


def render_agency(evidence: list[Evidence]) -> list[str]:
    rows = rows_with(evidence, "name")
    if not rows:
        return []
    lines = ["Cơ quan tiếp nhận:"]
    for e in rows:
        r = _row(e)
        eff = r.get("effective_date") or e.get("effective_date")
        tail = f" — hiệu lực theo nguồn: {eff}" if eff else ""
        juris = f" — phạm vi: {r['jurisdiction']}" if r.get("jurisdiction") else ""
        lines.append(f"- {r['name']}{juris}{tail} — ngày lấy {_date(e)} {_cite(e)}")
    return lines


def render_time(evidence: list[Evidence]) -> list[str]:
    rows = rows_with(evidence, "processing_time")
    if not rows:
        return []
    e = next((r for r in rows if r.get("section") == "processing_time"), rows[0])
    return [f"Thời gian giải quyết: {_row(e)['processing_time']} {_cite(e)}"]  # source wording verbatim (F14)


def render_premise(premise: str | None, intent: str, evidence: list[Evidence]) -> str | None:
    """Code-rendered verdict on a user's numeric premise (F5), or None (no numbers / no rows → LLM addresses it).

    True iff every number in the premise appears in the rows of the asked kind (fees: `value`/`condition`;
    time: `processing_time`). A fee premise of "free" without numbers: Đúng if every fee row is free, Không đúng
    if none is, Tùy trường hợp if mixed. The line restates the record's values with their `[db:…]` ids; it never echoes
    the user's number."""
    from src.self_rag import numbers  # local import: self_rag imports nothing from render
    if not premise:
        return None
    if intent == "fee" and not numbers(premise) and _FREE.search(_low(premise)):
        rows = rows_with(evidence, "value")
        if not rows:
            return None
        free = [_FREE.search(_low(_row(e)["value"])) is not None for e in rows]
        verdict = "Đúng" if all(free) else ("Không đúng" if not any(free) else "Tùy trường hợp")
        vals = [f"{_row(e)['value']}" + (f" ({_row(e)['condition']})" if _row(e).get("condition") else "") for e in rows]
        return f"{verdict} — theo dữ liệu thủ tục, lệ phí: {'; '.join(vals)} {' '.join(_cite(e) for e in rows)}"
    if not numbers(premise):
        return None
    if intent == "fee":
        rows, what = rows_with(evidence, "value"), "lệ phí"
        vals = [f"{_row(e)['value']}" + (f" ({_row(e)['condition']})" if _row(e).get("condition") else "") for e in rows]
    elif intent == "time":
        rows = [e for e in rows_with(evidence, "processing_time") if e.get("section") == "processing_time"][:1] \
            or rows_with(evidence, "processing_time")[:1]
        what, vals = "thời gian giải quyết", [str(_row(e)["processing_time"]) for e in rows]
    else:
        return None
    if not rows:
        return None
    true = numbers(premise) <= numbers(" ".join(vals))
    verdict = "Đúng" if true else "Không đúng"
    cites = " ".join(_cite(e) for e in rows)
    return f"{verdict} — theo dữ liệu thủ tục, {what}: {'; '.join(vals)} {cites}"


def render_block(intent: str, evidence: list[Evidence], locality: str | None = None) -> tuple[str, list[dict]]:
    """(block text, gaps) for the intent. The block is empty for `steps` (narrative from corpus only)."""
    lines: list[str] = []
    gaps: list[dict] = []
    blocks = list(INTENT_BLOCKS.get(intent, INTENT_BLOCKS["general"]))
    prim = PRIMARY.get(intent)
    if prim and "agency" not in blocks:  # if the asked element is missing, the agency line is the next step
        blocks.append("agency_fallback")
    for b in blocks:
        if b == "agency_fallback":
            if any(g["kind"] == "missing" for g in gaps):
                part = render_agency(evidence)
                if part:
                    lines += part + [""]
            continue
        if b == "documents":
            part = render_documents(evidence)
        elif b == "fees":
            part, g = render_fees(evidence, locality)
            gaps += g
        elif b == "agency":
            part = render_agency(evidence)
        else:
            part = render_time(evidence)
        if not part and b != "fees":
            gaps.append({"element": ELEMENT[b], "kind": "missing", "detail": f"không có dữ liệu {ELEMENT[b]}"})
        if part:
            lines += part + [""]
    return "\n".join(lines).strip(), gaps


def primary_missing(intent: str, gaps: list[dict]) -> list[dict]:
    """Gaps of kind `missing` that concern what the user asked for (→ core unsupported)."""
    prim = PRIMARY.get(intent)
    if not prim:
        return []
    return [g for g in gaps if g["kind"] == "missing" and g["element"].startswith(ELEMENT[prim].split()[0])]


def title_of(evidence: list[Evidence]) -> str | None:
    for e in evidence:
        if e["tier"] == "db" and _row(e).get("title"):
            return _row(e)["title"]
    return None


def citation_list(evidence: list[Evidence], ids: list[str]) -> list[dict]:
    by_id = {e["evidence_id"]: e for e in evidence}
    return [{"evidence_id": i, "source_url": by_id[i].get("source_url"), "retrieved_at": by_id[i].get("retrieved_at"),
             "effective_date": by_id[i].get("effective_date")} for i in ids if i in by_id]
