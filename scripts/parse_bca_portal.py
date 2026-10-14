"""Parse dichvucong.bocongan.gov.vn procedure pages into canonical records (data-model.md §1).

Input : data/raw/dvc/bca-portal/<matt>.html + index.jsonl (written by crawl_bca_portal.py)
Output: data/processed/bca-portal/<mã TTHC>.json, plus PARSE_REPORT.md listing per-record gaps.

Rules: Vietnamese content verbatim (whitespace cleanup only); unknown -> null / []; nothing guessed.
Usage : uv run python scripts/parse_bca_portal.py
"""

import hashlib
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dvc" / "bca-portal"
OUT = ROOT / "data" / "processed" / "bca-portal"
SOURCE_PREFIX = "bca-portal"

CHANNEL_RE = r"Trực tiếp|Trực tuyến(?: toàn trình| một phần)?|Dịch vụ bưu chính|Qua bưu chính"
MONEY_RE = re.compile(r"\d{1,3}(?:\.\d{3})+")


def clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip() or None


def sections(soup: BeautifulSoup) -> dict[str, Tag]:
    out = {}
    for it in soup.select(".tthc-list-item"):
        title = it.select_one(".item-title")
        body = it.select_one(".tthc-panel-collapse")
        if title and body:
            out[title.get_text(strip=True)] = body
    return out


def text_of(el: Tag | None, sep: str = "\n") -> str | None:
    return clean(el.get_text(sep)) if el is not None else None


def pieces(el: Tag | None) -> list[str]:
    return [p for p in (clean(s) for s in el.stripped_strings)] if el is not None else []


def page_title(soup: BeautifulSoup, fallback: str | None) -> str | None:
    crumb = soup.select_one("li.active")
    name = clean(crumb.get_text(" ")) if crumb else None
    if name:
        for h in soup.find_all("h4"):
            if clean(h.get_text(" ")) == name:
                return name
    return name or fallback


def parse_channels(el: Tag | None) -> list[str]:
    return [p for p in pieces(el) if p]


def parse_steps(el: Tag | None) -> list[str]:
    txt = text_of(el)
    if not txt:
        return []
    txt = re.sub(r"(?m)^-\s*\n\s*(?=Bước)", "- ", txt)  # "-" and "Bước N" are split across text nodes
    parts = re.split(r"(?m)(?=^-?\s*Bước\s*\d+\s*[:.])", txt)
    steps = [p for p in (clean(p) for p in parts) if p and p != "-"]
    if len(steps) <= 1:  # no "Bước N" markers: one step per line
        steps = [l for l in txt.split("\n") if l.strip()]
    return steps


def parse_processing_time(el: Tag | None) -> str | None:
    ps = pieces(el)
    out = []
    for i, p in enumerate(ps):
        if re.fullmatch(CHANNEL_RE, p) and i + 1 < len(ps) and re.search(r"\d+\s*(Ngày|ngày|Giờ|giờ|tháng)", ps[i + 1]):
            out.append(f"{p}: {ps[i + 1]}")
    if out:
        return "; ".join(out)
    return text_of(el, " ")


def parse_fee_section(el: Tag | None, kind: str, gaps: list[str]) -> list[dict]:
    """kind = 'Phí' or 'Lệ phí'. Returns explicit entries only for statements the page actually makes."""
    txt = clean(el.get_text(" ")) if el is not None else None
    if not txt:
        gaps.append(f"{kind}: section empty")
        return []
    if re.fullmatch(r"(?i)không\.?", txt):
        return [{"value": "miễn lệ phí" if kind == "Lệ phí" else "miễn phí",
                 "condition": f"{kind}: trang ghi \"{txt}\"", "jurisdiction": "toàn quốc"}]
    if "Chưa quy định" in txt and not MONEY_RE.search(txt):
        gaps.append(f"{kind}: page says \"Chưa quy định.\" (left as unknown)")
        return []
    if not MONEY_RE.search(txt):
        gaps.append(f"{kind}: unparseable/placeholder value {txt[:60]!r} (left as unknown)")
        return []
    entries = []
    # Split into per-channel segments: "<channel> [NN Ngày làm việc]<amount><description>"
    segs = re.split(rf"(?=(?:{CHANNEL_RE})\s)", txt)
    for seg in segs:
        seg = seg.strip()
        m = re.match(rf"({CHANNEL_RE})\s*(\d+\s*Ngày làm việc)?\s*(.*)$", seg, flags=re.S)
        channel, body = (m.group(1), m.group(3)) if m else (None, seg)
        money = MONEY_RE.search(body or "")
        if not money:
            continue
        desc = clean(body[money.end():]) or None
        unit = " đồng" if desc and "đồng" in desc else ""
        cond = "; ".join(x for x in [f"{kind}" + (f" – {channel}" if channel else ""), desc] if x)
        entries.append({"value": money.group(0) + unit, "condition": cond, "jurisdiction": "toàn quốc"})
    return entries


def parse_quantity(td_text: str | None) -> tuple[int | None, str | None]:
    if not td_text:
        return None, None
    qt = "; ".join(x for x in (clean(l) for l in td_text.split("\n")) if x) or None
    nums = re.findall(r"Bản (?:chính|sao):\s*(\d+)", qt or "")
    total = sum(int(n) for n in nums) if nums else None
    return (total or None), qt  # "Bản chính: 0; Bản sao: 0" gives no usable count -> null, wording kept


def parse_documents(el: Tag | None, gaps: list[str]) -> list[dict]:
    """One entry per table row, in source order; the case heading (h4) above each table goes into note."""
    if el is None:
        return []
    docs = []
    group = None
    for node in el.descendants:
        if not isinstance(node, Tag):
            continue
        if node.name in ("h4", "h5", "p") and node.find_parent("table") is None and node.find_parent(["h4", "h5", "p"]) is None:
            g = clean(node.get_text(" "))
            if g:
                group = g
        elif node.name == "tr" and node.find_parent("thead") is None:
            tds = node.find_all("td", recursive=False)
            if not tds:
                continue
            item = clean(tds[0].get_text(" "))
            if not item:
                continue
            if group and re.match(r"\*?\s*Lưu ý", group):
                gaps.append(f"required_documents: row under '{group}' is guidance, not a document; kept in raw_text only")
                continue
            form = clean(tds[1].get_text(" ")) if len(tds) > 1 else None
            qty, qty_text = parse_quantity(tds[2].get_text("\n") if len(tds) > 2 else None)
            note_parts = []
            if group:
                note_parts.append(f"Nhóm hồ sơ: {group}")
            if form:
                note_parts.append(f"Mẫu: {form}")
            docs.append({"item": item, "quantity": qty, "quantity_text": qty_text,
                         "mandatory": None, "note": " | ".join(note_parts) or None})
    return docs


def parse_legal_basis(el: Tag | None) -> list[str]:
    if el is None:
        return []
    lis = el.find_all("li")
    if lis:
        return [t for t in (clean(li.get_text(" ")) for li in lis) if t]
    return [l for l in (text_of(el) or "").split("\n") if l]


def level_of(title: str, agency: str | None) -> str | None:
    t = f"{title} {agency or ''}".lower()
    if "cấp xã" in t or "công an xã" in t:
        return "cấp xã"
    if "cấp tỉnh" in t or "công an tỉnh" in t or agency and agency.lower().startswith("phòng"):
        return "cấp tỉnh"
    if "cấp trung ương" in t or agency and agency.lower().startswith("cục"):
        return "trung ương"
    return None


def parse_one(path: Path, meta: dict) -> tuple[dict, list[str]]:
    raw = path.read_bytes()
    soup = BeautifulSoup(raw.decode("utf-8"), "lxml")
    sec = sections(soup)
    gaps: list[str] = []

    code = text_of(sec.get("Mã thủ tục"), " ")
    title = page_title(soup, meta.get("title"))
    agency = text_of(sec.get("Cơ quan thực hiện"), " ")
    fees = parse_fee_section(sec.get("Phí"), "Phí", gaps) + parse_fee_section(sec.get("Lệ Phí"), "Lệ phí", gaps)
    docs = parse_documents(sec.get("Thành phần hồ sơ"), gaps)
    if not docs:
        gaps.append("required_documents: no table rows found")

    raw_text = "\n\n".join(f"{name}:\n{text_of(body)}" for name, body in sec.items() if text_of(body))
    rec = {
        "procedure_id": code,
        "title": title,
        "variant_of": None,
        "field": text_of(sec.get("Lĩnh vực"), " "),
        "level": level_of(title or "", agency),
        "jurisdiction": "toàn quốc",
        "receiving_agency": agency,
        "channels": parse_channels(sec.get("Cách thức thực hiện")),
        "required_documents": docs,
        "steps": parse_steps(sec.get("Trình tự thực hiện")),
        "fees": fees,
        "processing_time": parse_processing_time(sec.get("Thời hạn giải quyết")),
        "legal_basis": parse_legal_basis(sec.get("Căn cứ pháp lý")),
        "conditions": text_of(sec.get("Yêu cầu - điều kiện")),
        "raw_text": raw_text,
        "source": {
            "source_id": f"{SOURCE_PREFIX}#{code}",
            "url": meta["url"],
            "locator": None,
            "title": f"{title} — Cổng Dịch vụ công Bộ Công an",
            "retrieved_at": meta["fetched_at"][:10],
            "effective_date": None,
            "content_hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
        },
    }
    if meta.get("sha256") and meta["sha256"] != hashlib.sha256(raw).hexdigest():
        gaps.append("raw file sha256 differs from index.jsonl")
    for k in ("procedure_id", "title", "field", "receiving_agency", "processing_time"):
        if not rec[k]:
            gaps.append(f"{k}: missing")
    return rec, gaps


def main() -> int:
    index = [json.loads(l) for l in (RAW / "index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    details = {r["matt"]: r for r in index if r.get("kind") == "detail" and r.get("status") == 200}
    OUT.mkdir(parents=True, exist_ok=True)
    report = ["# PARSE_REPORT — bca-portal", "",
              "Generated by `scripts/parse_bca_portal.py`. One row per record; gaps = fields left unknown and why.", "",
              "| procedure_id | matt | title | docs | fees | gaps |", "|---|---|---|---|---|---|"]
    n = 0
    for matt, meta in sorted(details.items()):
        rec, gaps = parse_one(RAW / f"{matt}.html", meta)
        if not rec["procedure_id"]:
            print(f"{matt}: no mã thủ tục, skipped", file=sys.stderr)
            continue
        (OUT / f"{rec['procedure_id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fees = "; ".join(f["value"] for f in rec["fees"]) or "—"
        report.append(f"| {rec['procedure_id']} | {matt} | {rec['title']} | {len(rec['required_documents'])} | {fees} | {'; '.join(gaps) or '—'} |")
        n += 1
    (OUT / "PARSE_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"wrote {n} records to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
