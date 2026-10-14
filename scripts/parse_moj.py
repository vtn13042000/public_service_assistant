"""Parse MOJ portal TTHC detail pages (hộ tịch) into canonical records.

Inputs (all fetched by fetch_moj.py / moj_fetch_portal.py, logged in data/raw/moj/index.jsonl):
  - data/raw/moj/portal/<mã>.html                — moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-<mã>.html
  - data/raw/moj/1833-QD-BTP-183363898879.pdf     — 1833/QĐ-BTP Phần I (danh mục): cơ quan thực hiện per mã, after 2025-07-01
Output: data/processed/moj/<mã>.json  (data-model.md §1 + lead deltas: source.locator, quantity_text, parse_flags)

Usage: uv run python scripts/parse_moj.py [mã ...]   (default: every page in data/raw/moj/portal/)
"""
import json
import re
import sys
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "moj"
OUT = ROOT / "data" / "processed" / "moj"
DECISION_PDF = RAW / "1833-QD-BTP-183363898879.pdf"
DECISION_URL = "https://cdn.haiphong.gov.vn/gov-hpg/6855/tintuc/2025/11/1833638988795114181791.pdf"

# Sibling grouping for clarify prompts: base procedure of each family (by title, see STATUS "Decisions").
FAMILY_BASE = [
    ("khai sinh", "1.001193"),
    ("kết hôn", "1.000894"),
    ("khai tử", "1.000656"),
    ("nhận cha, mẹ, con", "1.001022"),
    ("chấm dứt giám hộ", "1.004845"),
    ("giám hộ", "1.004837"),
    ("thay đổi, cải chính", "1.004859"),
]
PORTAL_URL = "https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-{code}.html"
# Defects verified by hand against the raw page (kept verbatim; flagged so answers can hedge)
SOURCE_DEFECTS = {
    "1.001193": "source_text_garbled: step 1 and 2 on the MOJ page have words out of order ('…đăng ký khai tâm Phục vụ…', '…hoàn tất việc sinh tại Trung nộp hồ sơ')",
}
CSDL_AGENCY = "Cơ quan quản lý Cơ sở dữ liệu hộ tịch điện tử (Sở Tư pháp, UBND cấp xã)"


def clean(s: str) -> str:
    return re.sub(r"[ \t\u00a0\u200e]+", " ", s).strip()


def load_index() -> dict:
    out = {}
    for line in (RAW / "index.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["path"]] = r
    return out


def load_danh_muc() -> dict:
    """mã -> (locator, cơ quan) from 1833/QĐ-BTP Phần I."""
    text = "\n".join(p.extract_text() or "" for p in pdfplumber.open(DECISION_PDF).pages)
    part_b = text.find("B. Thủ tục hành chính tại cơ quan quản lý")
    out = {}
    for m in re.finditer(r"^(\d+)\. ([12]\.\d{6})", text, re.M):
        in_b = m.start() > part_b
        sec = "B" if in_b else "A"
        out[m.group(2)] = (f"1833/QĐ-BTP Phần I, mục {sec}.{m.group(1)}",
                           CSDL_AGENCY if in_b else "UBND cấp xã")
    return out


def section(soup, label):
    for td in soup.select("table.contentvbdh > tbody > tr > td.InterSemibold"):
        if td.get_text(strip=True) == label:
            return td.find_next_sibling("td")
    return None


def rows(cell):
    if cell is None:
        return []
    out = []
    for tr in cell.find_all("tr"):
        tds = tr.find_all("td")
        if tds:
            out.append([clean(td.get_text("\n", strip=True)) for td in tds])
    return out


def split_steps(text: str) -> list[str]:
    steps, cur = [], []
    for line in text.split("\n"):
        line = clean(line)
        if not line:
            continue
        if line.startswith("- ") and cur:
            steps.append(" ".join(cur))
            cur = []
        cur.append(line[2:] if line.startswith("- ") else line)
    if cur:
        steps.append(" ".join(cur))
    return steps


def to_int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def fee_sentences(text: str) -> list[str]:
    t = clean(text.replace("\n", " "))
    t = re.sub(r"^\d*\s*Đồng\s*(?:-\s*)?", "", t)  # portal amount-field residue, e.g. "8000 Đồng - ", "0 Đồng"
    t = re.sub(r"\.(?=[A-ZĐ])", ". ", t)
    t = re.sub(r"\s*Đồng$", "", t)
    t = t.strip()
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1].strip()
    out = []
    for bullet in re.split(r"(?:^|\s+)-\s+(?=[A-ZĐ])", t):
        out += re.split(r"(?<=[.;])\s+(?=[A-ZĐÂĂÊÔƠƯ])", bullet)
    return [p.strip().rstrip(";").strip() for p in out if p.strip()]


def classify_fee(sent: str) -> dict:
    s = sent.rstrip(".")
    if re.match(r"(?i)miễn lệ phí", s):
        cond = re.sub(r"(?i)^miễn lệ phí\s*(đối với|cho)?\s*", "", s).strip() or None
        return {"value": "miễn lệ phí", "condition": cond, "jurisdiction": "toàn quốc"}
    if "Hội đồng nhân dân" in s:
        m = re.match(r"(?i)đối với (?:trường hợp )?(.+?):", s)
        return {"value": "theo HĐND tỉnh", "condition": m.group(1) if m else s, "jurisdiction": "theo tỉnh"}
    amt = re.search(r"\d{1,3}(?:\.\d{3})+\s*đồng", s)
    if amt:
        return {"value": amt.group(0), "condition": s, "jurisdiction": "toàn quốc"}
    if "281/2016/TT-BTC" in s:
        return {"value": "theo Thông tư số 281/2016/TT-BTC", "condition": s, "jurisdiction": "toàn quốc"}
    return {"value": s, "condition": None, "jurisdiction": None}


def parse(code: str, idx: dict, danh_muc: dict) -> dict:
    url = PORTAL_URL.format(code=code)
    meta = next(r for r in idx.values() if r["url"] == url)
    path = ROOT / meta["path"]
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    flags = []

    title = clean(section(soup, "Tên thủ tục").get_text(" ", strip=True))
    field = clean(section(soup, "Lĩnh vực").get_text(" ", strip=True))
    portal_agency = clean(section(soup, "Cơ quan thực hiện").get_text(" ", strip=True))
    result = clean(section(soup, "Kết quả thực hiện").get_text(" ", strip=True))
    subjects = clean(section(soup, "Đối tượng thực hiện").get_text(" ", strip=True))
    cond_cell = section(soup, "Yêu cầu, điều kiện thực hiện")
    conditions = clean(cond_cell.get_text("\n", strip=True)) if cond_cell else None

    step_rows = rows(section(soup, "Trình tự thực hiện"))
    steps = [s for r in step_rows for s in split_steps(r[-1])]
    # a bare "[* Lưu ý:] * Lưu ý" line is a heading left by the portal's markup, not a step
    steps = [s for s in steps if not re.fullmatch(r"\[\*\s*Lưu ý:\]\s*\*\s*Lưu ý", s)]

    # Cách thực hiện: [hình thức, thời hạn, lệ phí, mô tả] per channel
    channel_rows = rows(section(soup, "Cách thực hiện"))
    channels, times, fee_texts, channel_desc, time_keys = [], {}, [], [], {}
    for r in channel_rows:
        r = r + [""] * (4 - len(r))
        ch, t, fee, desc = r[:4]
        if ch and ch not in channels:
            channels.append(ch)
        tkey = re.sub(r"\.(?=\S)", ". ", t).strip().rstrip(".")
        if tkey not in time_keys:
            time_keys[tkey] = t
        times.setdefault(time_keys[tkey], []).append(ch)
        if fee and fee not in fee_texts:
            fee_texts.append(fee)
        if desc and desc not in channel_desc:
            channel_desc.append(desc)
    if len(times) == 1:
        processing_time = next(iter(times)) or None
    else:
        processing_time = "; ".join(f"{', '.join(chs)}: {t}" for t, chs in times.items())
    if any(re.fullmatch(r"\d+", t.strip()) for t in times):
        flags.append("processing_time_bare_number_at_source")

    fees, seen = [], set()
    for ft in fee_texts:
        for sent in fee_sentences(ft):
            f = classify_fee(sent)
            key = (f["value"], re.sub(r"[\W_]+", "", (f["condition"] or "").lower()))
            if key not in seen:
                seen.add(key)
                fees.append(f)

    # Thành phần hồ sơ: [tên giấy tờ, số bản chính, số bản sao]; rows with 0/0 are guidance notes, not documents
    docs, doc_notes = [], []
    for r in rows(section(soup, "Thành phần hồ sơ")):
        r = r + [""] * (3 - len(r))
        item = re.sub(r"^[-+]\s*", "", clean(r[0].replace("\n", " ")))
        n_main, n_copy = to_int(r[1]), to_int(r[2])
        if not item:
            continue
        if (n_main or 0) + (n_copy or 0) > 0:
            docs.append({
                "item": item,
                "quantity": (n_main or 0) + (n_copy or 0),
                "quantity_text": f"Số bản chính: {r[1] or '?'}; Số bản sao: {r[2] or '?'}",
                "mandatory": None,
                "note": None,
            })
        else:
            doc_notes.append(clean(r[0].replace("\n", " ")))
    flags.append("required_documents_order_is_portal_order_not_decision_order")
    if code in SOURCE_DEFECTS:
        flags.append(SOURCE_DEFECTS[code])

    legal = []
    for r in rows(section(soup, "Căn cứ pháp lý")):
        so, trich = (r + ["", ""])[:2]
        so, trich = clean(so), clean(trich.replace("\n", " "))
        if not so:
            continue
        legal.append(so if (not trich or trich == so) else f"{so} – {trich}")

    # receiving agency: the legal decision (1833/QĐ-BTP Phần I) wins over the portal field
    locator, decision_agency = danh_muc.get(code, (None, None))
    receiving_agency = decision_agency or portal_agency
    if decision_agency is None:
        flags.append("not_in_1833_danh_muc")
    if re.search(r"thị trấn|Phòng Tư [Pp]háp|cấp huyện|UBND huyện", portal_agency):
        flags.append("stale_agency_wording_at_source")
    level = "cấp tỉnh / cấp xã" if decision_agency == CSDL_AGENCY else ("cấp xã" if decision_agency else None)

    variant_of = None
    low = title.lower()
    for key, base in FAMILY_BASE:
        if key in low:
            variant_of = None if base == code else base
            break

    raw_parts = [
        f"Tên thủ tục: {title}", f"Mã thủ tục: {code}", f"Lĩnh vực: {field}",
        "Trình tự thực hiện:\n" + "\n".join(f"- {s}" for s in steps),
        "Cách thực hiện:\n" + "\n".join(" | ".join(r) for r in channel_rows),
        "Thành phần hồ sơ:\n" + "\n".join(f"- {d['item']} ({d['quantity_text']})" for d in docs),
        "Ghi chú về hồ sơ (các dòng 0 bản trên trang nguồn):\n" + "\n".join(f"- {n}" for n in doc_notes),
        f"Đối tượng thực hiện: {subjects}",
        f"Cơ quan thực hiện (theo trang Bộ Tư pháp): {portal_agency}",
        f"Cơ quan thực hiện (theo 1833/QĐ-BTP, Phần I): {decision_agency}",
        f"Kết quả thực hiện: {result}",
        "Căn cứ pháp lý:\n" + "\n".join(f"- {x}" for x in legal),
        f"Yêu cầu, điều kiện thực hiện: {conditions}",
    ]

    return {
        "procedure_id": code,
        "title": title,
        "variant_of": variant_of,
        "field": field,
        "level": level,
        "jurisdiction": "toàn quốc",
        "receiving_agency": receiving_agency,
        "channels": channels,
        "required_documents": docs,
        "steps": steps,
        "fees": fees,
        "processing_time": processing_time,
        "legal_basis": legal,
        "conditions": conditions,
        "raw_text": "\n\n".join(raw_parts),
        "parse_flags": flags,
        "source": {
            "source_id": f"moj-portal#{code}",
            "url": meta["url"],
            "locator": "; ".join(x for x in [f"moj.gov.vn TTHC chi tiết mã {code}", locator and f"cơ quan theo {locator} ({DECISION_URL})"] if x),
            "title": title,
            "retrieved_at": meta["fetched_at"][:10],
            "effective_date": None,
            "content_hash": "sha256:" + meta["sha256"],
        },
    }


def _portal_codes(idx: dict) -> list[str]:
    pat = re.compile(r"https://moj\.gov\.vn/portal/thu-tuc-hanh-chinh/chi-tiet-([12]\.\d{6})\.html")
    return sorted({m.group(1) for r in idx.values() if (m := pat.fullmatch(r["url"])) and r["status"] == 200})


def main(argv):
    idx = load_index()
    danh_muc = load_danh_muc()
    codes = argv or _portal_codes(idx)
    OUT.mkdir(parents=True, exist_ok=True)
    for code in codes:
        rec = parse(code, idx, danh_muc)
        (OUT / f"{code}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{code}  docs={len(rec['required_documents']):2d} steps={len(rec['steps']):2d} fees={len(rec['fees'])} "
              f"flags={','.join(f for f in rec['parse_flags'] if not f.startswith('required_documents_order'))}")


if __name__ == "__main__":
    main(sys.argv[1:])
