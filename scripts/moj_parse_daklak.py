"""Parse the Đắk Lắk provincial annex (33/QĐ-UBND, căn cứ 3673/QĐ-BTP) into canonical records.

Input:  data/raw/moj/daklak-33_QD-UBND_PL.pdf (+ daklak-33_QD-UBND.pdf for the decision text)
Output: data/processed/daklak/<mã>.json — fees[].jurisdiction = "Đắk Lắk" (lead rule, 2026-10-10)
The annex is a danh mục: tên, thời hạn, cách thức, phí/lệ phí, căn cứ. It has no thành phần hồ sơ,
so required_documents = [] (unknown here; see data/processed/moj/<mã>.json).

Usage: uv run python scripts/moj_parse_daklak.py [--dump]
"""
import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "moj"
OUT = ROOT / "data" / "processed" / "daklak"
PDF = RAW / "daklak-33_QD-UBND_PL.pdf"
JUR = "Đắk Lắk"


def _vocab():
    """Vietnamese syllables seen in the MOJ portal records (HTML text, so no PDF spacing artifacts)."""
    words = set()
    for f in (ROOT / "data" / "processed" / "moj").glob("*.json"):
        words |= set(re.findall(r"\w+", json.loads(f.read_text(encoding="utf-8"))["raw_text"].lower()))
    return words


VOCAB = _vocab()


def repair_spacing(s):
    """Join PDF-split syllables ('chín h' -> 'chính') when the joined token is a known syllable
    and one part is not. Whitespace-only change."""
    out = []
    for t in s.split(" "):
        if out:
            a = out[-1]
            wa, wb = re.sub(r"\W", "", a).lower(), re.sub(r"\W", "", t).lower()
            if (re.fullmatch(r"\w+", a) and wb and (wa + wb) in VOCAB
                    and (wa not in VOCAB or wb not in VOCAB)):
                out[-1] = a + t
                continue
        out.append(t)
    return " ".join(out)


def clean(s):
    return repair_spacing(re.sub(r"\s+", " ", (s or "").replace("\u00a0", " ")).strip())


def index_meta():
    for line in (RAW / "index.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["path"].endswith("daklak-33_QD-UBND_PL.pdf"):
            return r
    raise SystemExit("annex not in index.jsonl")


def extract_rows():
    """Merge rows split across pages: a row with empty TT continues the previous row."""
    rows, section = [], None
    pdf = pdfplumber.open(PDF)
    for pno, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ""
        for m in re.finditer(r"^(I{1,3}V?|IV|V)\. (THỦ TỤC HÀNH CHÍNH[^\n]*(?:\n[^\n]*\))?)", text, re.M):
            section = clean(m.group(2))
        for table in page.extract_tables():
            for r in table:
                r = [c or "" for c in r] + [""] * (6 - len(r))
                if r[0].strip() == "TT":
                    continue
                if r[0].strip() == "" and rows:
                    prev = rows[-1]
                    for i in range(1, 6):
                        if r[i].strip():
                            prev["cells"][i] += "\n" + r[i]
                    prev["pages"].add(pno)
                elif r[0].strip():
                    rows.append({"cells": r[:6], "section": section, "pages": {pno}})
    return rows


def fees_from(cell):
    text = clean(cell)
    parts = [p.strip(" .;") for p in re.split(r"(?:^|\s)-\s+(?=[A-ZĐ])", text) if p.strip(" .;")]
    out = []
    for p in parts:
        amt = re.search(r"\d{1,3}(?:\.\d{3})+\s*đồng", p)
        if re.match(r"(?i)miễn lệ phí|không thu|không", p):
            cond = re.sub(r"(?i)^miễn lệ phí\s*(đối với|cho)?\s*", "", p).strip() or None
            out.append({"value": "miễn lệ phí", "condition": cond, "jurisdiction": JUR})
        elif amt:
            out.append({"value": clean(amt.group(0)), "condition": p, "jurisdiction": JUR})
        elif "281/2016/TT-BTC" in p:
            out.append({"value": "theo Thông tư số 281/2016/TT-BTC", "condition": p, "jurisdiction": JUR})
        elif "HĐND" in p or "Hội đồng nhân dân" in p:
            out.append({"value": "theo HĐND tỉnh", "condition": p, "jurisdiction": JUR})
        else:
            out.append({"value": p, "condition": None, "jurisdiction": JUR})
    return out


def main(argv):
    meta = index_meta()
    rows = extract_rows()
    if "--dump" in argv:
        for r in rows:
            c = r["cells"]
            print(c[0], "|", clean(c[1])[:70], "|", clean(c[4])[:200], "|", r["section"][:60] if r["section"] else None)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for r in rows:
        c = r["cells"]
        name = clean(c[1])
        m = re.search(r"\((\d\.\d{6})\)\s*$", name)
        if not m:
            print("skip (no mã):", name[:80])
            continue
        code = m.group(1)
        title = clean(name[: m.start()])
        legal = [clean(x) for x in re.split(r"(?:^|\n)\s*-\s+", c[5]) if clean(x)]
        pages = sorted(r["pages"])
        rec = {
            "procedure_id": code,
            "title": title,
            "variant_of": None,
            "field": "Hộ tịch",
            "level": "cấp tỉnh / cấp xã" if "CƠ SỞ DỮ LIỆU" in (r["section"] or "") else ("cấp xã" if "CẤP XÃ" in (r["section"] or "") else None),
            "jurisdiction": JUR,
            "receiving_agency": "Cơ quan quản lý Cơ sở dữ liệu hộ tịch điện tử (Sở Tư pháp, UBND cấp xã)" if "CƠ SỞ DỮ LIỆU" in (r["section"] or "") else None,
            "channels": [],
            "required_documents": [],
            "steps": [],
            "fees": fees_from(c[4]),
            "processing_time": clean(c[2]) or None,
            "legal_basis": legal,
            "conditions": None,
            "raw_text": "\n".join([
                f"Mục: {r['section']}", f"Tên thủ tục hành chính: {name}", f"Thời hạn giải quyết: {clean(c[2])}",
                f"Cách thức thực hiện: {clean(c[3])}", f"Phí, lệ phí: {clean(c[4])}", "Căn cứ pháp lý:\n" + "\n".join(f"- {x}" for x in legal),
            ]),
            "submission_method_text": clean(c[3]),
            "source": {
                "source_id": f"daklak-33/QD-UBND#{code}",
                "url": meta["url"],
                "locator": f"Phụ lục, {r['section']}, TT {clean(c[0])}, tr. {pages[0]}" + (f"–{pages[-1]}" if len(pages) > 1 else ""),
                "title": "Quyết định 33/QĐ-UBND tỉnh Đắk Lắk — Danh mục TTHC được sửa đổi, bổ sung lĩnh vực hộ tịch (căn cứ 3673/QĐ-BTP)",
                "retrieved_at": meta["fetched_at"][:10],
                "effective_date": "2026-01-08",
                "content_hash": "sha256:" + meta["sha256"],
            },
        }
        (OUT / f"{code}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(code, title[:60], "| fees:", [(f["value"], (f["condition"] or "")[:40]) for f in rec["fees"]])


if __name__ == "__main__":
    main(sys.argv[1:])
