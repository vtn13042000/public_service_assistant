"""Round-4 depth documents for the Bộ Công an families — guidance and change_notice kinds from official web pages
(w-dvc, BRIEF-8 Part 3).

Usage: uv run python scripts/build_bca_depth_web.py
Reads raw HTML already fetched by scripts/fetch_depth_cached.py (data/raw/dvc/depth/index.jsonl); never fetches.
Keeps only the article body (navigation, "đọc nhiều" boxes, footers dropped); splits into sections at in-body headings
(h2/h3/h4 or a paragraph that is entirely bold); Vietnamese text verbatim. Writes data/processed_docs/<kind>/<doc_id>.json.
"""
import json, re, sys
from pathlib import Path

from bs4 import BeautifulSoup

INDEX = Path("data/raw/dvc/depth/index.jsonl")
ROOT = Path("data/processed_docs")
RETRIEVED = "2026-10-10"

CAP = ["1.001247", "2.000200", "1.012549", "1.014062"]
DOI = ["1.000889", "2.001195"]
LAI = ["1.000757", "2.001194"]
CC = CAP + DOI + LAI
TT_, XOA_TT, TAM, GH, XOA_TAM, TACH = "1.004222", "1.003197", "1.004194", "1.002755", "1.010028", "1.010038"
VANG, KB, XN = "1.003677", "1.010040", "1.010041"
CT = [TT_, XOA_TT, TAM, GH, XOA_TAM, VANG, TACH, KB, XN]
BCA = "Bộ Công an (bocongan.gov.vn)"
BCP = "Báo Điện tử Chính phủ (baochinhphu.vn)"

XD = "Cổng Thông tin điện tử Chính phủ (xaydungchinhsach.chinhphu.vn)"
# (url substring, kind, doc_id, procedure_ids, issuer, note)
PAGES = [
    ("cap-cap-doi-cap-lai-the-can-cuoc-tai-cong-an-cap-xa-119260828113820605", "guidance", "guide:xdcs:can-cuoc-cong-an-cap-xa-2026", CC, XD,
     "how to apply for issue/change/re-issue at commune police (2026)"),
    ("cap-doi-the-can-cuoc-cho-cong-dan-do-thay-doi-dia-gioi-hanh-chinh-119251002164655756", "guidance", "guide:xdcs:cap-doi-can-cuoc-dia-gioi-2025", DOI, XD,
     "card change after administrative-boundary changes (2025)"),
    ("quy-dinh-moi-trinh-tu-thu-tuc-cap-doi-cap-lai-the-can-cuoc-119240627144340876", "guidance", "guide:xdcs:trinh-tu-cap-doi-cap-lai-2024", CC, XD,
     "procedure for issue/change/re-issue under the 2024 rules"),
    ("huong-dan-nop-ho-so-truc-tuyen-de-nghi-cap-the-can-cuoc-cho-nguoi-tu-du-14-tuoi-119240804092027743", "guidance", "guide:xdcs:nop-truc-tuyen-can-cuoc-14-tuoi",
     ["1.001247", "2.000200"], XD, "online application for a card, age 14 and over"),
    ("huong-dan-thu-tuc-dang-ky-tam-tru-119260414165903409", "guidance", "guide:xdcs:dang-ky-tam-tru-2026", [TAM, GH], XD,
     "temporary-residence registration (2026, per QĐ 1523/QĐ-BCA-C06)"),
    ("huong-dan-thu-tuc-dang-ky-thuong-tru-119260415170002055", "guidance", "guide:xdcs:dang-ky-thuong-tru-2026", [TT_], XD,
     "permanent-residence registration (2026)"),
    ("huong-dan-ho-so-thu-tuc-xoa-dang-ky-thuong-tru-tam-tru-119260224155351632", "guidance", "guide:xdcs:xoa-dang-ky-thuong-tru-tam-tru-2026", [XOA_TT, XOA_TAM], XD,
     "permanent/temporary deregistration (2026)"),
    ("chung-minh-cho-o-hop-phap-de-dang-ky-thuong-tru-tam-tru-tu-10-1-2025-119241203091035359", "guidance", "guide:xdcs:cho-o-hop-phap-2025", [TT_, TAM, GH], XD,
     "documents proving lawful accommodation from 10/1/2025 (NĐ 154/2024 Điều 5)"),
    ("chung-minh-quan-he-nhan-than-khi-dang-ky-thuong-tru-tu-10-1-2025-119241203095828263", "guidance", "guide:xdcs:quan-he-nhan-than-2025", [TT_, TACH], XD,
     "documents proving family relationship from 10/1/2025 (NĐ 154/2024 Điều 6)"),
    ("nghi-dinh-58-2026-nd-cp-quy-dinh-ve-cu-tru-can-cuoc-quan-ly-su-dung-con-dau-119260224140920945", "change_notice", "change:xdcs:nd-58-2026",
     [XOA_TT, XOA_TAM] + CC, XD, "NĐ 58/2026/NĐ-CP amends residence (incl. NĐ 154/2024 Điều 9–10) and căn cước rules"),
    ("bocongan/tintuc/chitiet?matin=421", "change_notice", "change:dvcbca:luat-can-cuoc-nd-58-2026", CC, "Bộ Công an (dichvucong.bocongan.gov.vn)",
     "new rules implementing Luật Căn cước (NĐ 58/2026/NĐ-CP)"),
    ("nguoi-dan-duoc-cap-doi-the-can-cuoc-mien-phi-khi-thay-doi-dia-gioi-hanh-chinh-tren-vneid-102250812175451353", "change_notice", "change:bcp:cap-doi-can-cuoc-mien-phi-vneid-2025",
     DOI, "Báo Điện tử Chính phủ (baochinhphu.vn)", "free card change on VNeID after administrative-boundary changes (2025)"),
    ("quy-dinh-dang-ky-tam-tru-119260720101630132", "guidance", "guide:xdcs:quy-dinh-dang-ky-tam-tru-2026-07", [TAM, GH], XD,
     "temporary registration under TT 116/2026"),
    ("mot-so-diem-moi-co-ban-cua-luat-cu-tru-sua-doi-va-thong-tu-116-2026", "change_notice", "change:xdcs:luat-cu-tru-sua-doi-tt-116-2026", CT, XD,
     "what changed in residence rules from 01/07/2026 (Luật 118/2025/QH15, TT 116/2026)"),
    ("luat-so-118-2025-qh15-sua-doi-bo-sung-mot-so-dieu-cua-10-luat", "change_notice", "change:xdcs:luat-118-2025", CT + CC, XD,
     "Luật 118/2025/QH15 amends 10 laws incl. Luật Cư trú and Luật Căn cước (in force 01/07/2026)"),
    ("bo-cong-an-huong-dan-thu-tuc-khai-bao-tam-vang-11924020116361488", "guidance", "guide:xdcs:khai-bao-tam-vang-2024", [VANG], XD,
     "how to declare temporary absence (2024)"),
    ("quy-dinh-moi-dang-ky-cu-tru-cho-nguoi-khong-co-noi-thuong-tru-noi-tam-tru-tu-10-1-2025", "guidance", "guide:xdcs:khai-bao-cu-tru-nguoi-chua-du-dieu-kien-2025", [KB], XD,
     "residence declaration for people without permanent/temporary residence (NĐ 154/2024 Điều 4)"),
    ("khong-du-dieu-kien-dang-ky-thuong-tru-dang-ky-tam-tru-co-duoc-cap-the-can-cuoc", "guidance", "guide:xdcs:chua-du-dieu-kien-cu-tru-cap-can-cuoc", [KB] + CAP, XD,
     "can people without registered residence get a card"),
    ("ba-truong-hop-chua-duoc-thay-doi-noi-cu-tru-102294636", "guidance", "guide:bcp:ba-truong-hop-chua-duoc-thay-doi-noi-cu-tru", [TT_, TAM], BCP,
     "cases where residence temporarily cannot be changed"),
    ("chi-tiet-cau-hoi/ba7639df-6e51-488a-963c-33741ba40d7f", "change_notice", "change:bca:dung-xac-nhan-cmnd-9-so-2026", ["2.001178"], BCA,
     "BCA answer: from 15/03/2026 confirmation of 9-digit CMND numbers is no longer issued (NĐ 58/2026 Điều 5 khoản 7 rewrites NĐ 70/2024 Điều 12)",
     "Trường hợp công dân có 02 số"),
    ("luat-can-cuoc-d1-t1419", "change_notice", "change:bca:nd-70-2024-tom-tat", CC + ["2.001178"], BCA,
     "summary of NĐ 70/2024 implementing Luật Căn cước (2024)"),
    ("luat-cu-tru-d1-t1590", "change_notice", "change:bca:nd-154-2024-tom-tat", CT, BCA, "summary of NĐ 154/2024 implementing Luật Cư trú (2024)"),
    ("quy-dinh-moi-ve-linh-vuc-cu-tru-gop-phan-nang-cao-chat-luong-phuc-vu-nhan-dan", "change_notice", "change:bca:quy-dinh-moi-cu-tru-2026", CT, BCA,
     "new residence rules (2026)"),
    ("bocongan/tintuc/chitiet?matin=261", "change_notice", "change:dvcbca:cong-bo-tthc-can-cuoc", CC + ["2.001178"], "Bộ Công an (dichvucong.bocongan.gov.vn)",
     "announcement of new/changed căn cước procedures"),
]

# Pages without an article:published_time meta: date read from the page text (date line under the title / answer date).
PUB = {"change:bca:dung-xac-nhan-cmnd-9-so-2026": "2026-08-21", "change:bca:nd-70-2024-tom-tat": "2024-06-26",
       "change:bca:nd-154-2024-tom-tat": "2024-12-02", "change:dvcbca:cong-bo-tthc-can-cuoc": "2024-07-04",
       "change:dvcbca:luat-can-cuoc-nd-58-2026": "2026-05-12"}
# change_notice effective_date (lead's request, 2026-10-10): (ISO date, how it was found). Stated in the notice text where possible; otherwise taken
# from the official text it announces (held in data/raw/dvc/depth/), else the publication date.
EFFECTIVE = {
    "change:bca:dung-xac-nhan-cmnd-9-so-2026": ("2026-03-15", "stated in the notice text (\"kể từ ngày 15/03/2026\")"),
    "change:xdcs:nd-58-2026": ("2026-03-15", "stated in the notice text (\"Nghị định có hiệu lực từ ngày 15/3/2026\")"),
    "change:bca:nd-154-2024-tom-tat": ("2025-01-10", "stated in the notice text (\"có hiệu lực thi hành từ ngày 10/01/2025\")"),
    "change:dvcbca:luat-can-cuoc-nd-58-2026": ("2026-03-15", "not stated in this notice; NĐ 58/2026 takes effect 15/3/2026 as stated in change:xdcs:nd-58-2026"),
    "change:bca:nd-70-2024-tom-tat": ("2024-07-01", "not stated in this notice; NĐ 70/2024 effective date from the Công báo record (legal:70-2024-ND-CP)"),
    "change:xdcs:luat-118-2025": ("2026-07-01", "not stated in this notice; Luật 118/2025/QH15 \"Ngày có hiệu lực 01-07-2026\" on vanban.chinhphu.vn docid=216534"),
    "change:xdcs:luat-cu-tru-sua-doi-tt-116-2026": ("2026-07-01", "not stated in this notice; TT 116/2026/TT-BCA Điều 27 (in force 01/7/2026) and Luật 118/2025/QH15 (01/7/2026)"),
    "change:bca:quy-dinh-moi-cu-tru-2026": ("2026-07-01", "not stated in this notice (no publication date either); it presents TT 116/2026/TT-BCA, in force 01/7/2026 per its Điều 27"),
    "change:dvcbca:cong-bo-tthc-can-cuoc": ("2024-07-04", "notice gives only the date of Quyết định 4864/QĐ-BCA (04/7/2024) = publication date; used as is"),
    "change:bcp:cap-doi-can-cuoc-mien-phi-vneid-2025": ("2025-08-12", "notice gives no effective date; publication date used"),
}
# change_notice links narrowed (lead's request): keep a procedure only if the notice names it ("named": code or title in the text) or the notice
# replaces/amends an instrument that the procedure's legal_basis cites and the change reaches that procedure ("instrument_scope").
N, I = "named", "instrument_scope"
NOTICE_LINKS = {
    "change:bca:dung-xac-nhan-cmnd-9-so-2026": [("2.001178", N, "answer names 'xác nhận số chứng minh nhân dân 09 số' and says it stopped on 15/03/2026")],
    "change:bcp:cap-doi-can-cuoc-mien-phi-vneid-2025": [("1.000889", N, "names 'cấp đổi thẻ Căn cước' (central level)"),
                                                        ("2.001195", N, "names 'cấp đổi thẻ Căn cước' (provincial level)")],
    "change:dvcbca:cong-bo-tthc-can-cuoc": [
        ("1.012549", N, "listed by code 1.012549 (cấp thẻ căn cước cho người dưới 14 tuổi, cấp tỉnh)"),
        ("1.001247", N, "names 'Cấp thẻ căn cước cho người từ đủ 14 tuổi trở lên'"), ("2.000200", N, "names 'Cấp thẻ căn cước cho người từ đủ 14 tuổi trở lên'"),
        ("1.000889", N, "names 'Cấp đổi thẻ Căn cước'"), ("2.001195", N, "names 'Cấp đổi thẻ Căn cước'"),
        ("2.001178", N, "names 'Xác nhận số chứng minh nhân dân 09 số, số định danh cá nhân'")],
    "change:dvcbca:luat-can-cuoc-nd-58-2026": [("2.001178", I, "NĐ 58/2026 rewrites NĐ 70/2024 Điều 12 (cited in its legal_basis), which governs this procedure; the notice names no card procedure")],
    "change:xdcs:nd-58-2026": [("1.004222", N, "amended NĐ 154 Điều 7: minors' đăng ký thường trú"), ("1.004194", N, "amended NĐ 154 Điều 7: minors' đăng ký tạm trú"),
                               ("1.010028", N, "amended NĐ 154 Điều 10: hồ sơ, thủ tục xóa đăng ký tạm trú")],
    "change:xdcs:luat-118-2025": [
        ("1.004222", N, "Luật Cư trú Điều 20 amended: more cases of đăng ký thường trú"), ("1.003677", N, "Luật Cư trú Điều 31 amended: khai báo tạm vắng electronically"),
        ("1.003197", I, "amends Luật Cư trú (in legal_basis); 'cư trú' redefined at commune level"), ("1.004194", I, "amends Luật Cư trú (in legal_basis); 'cư trú' redefined at commune level"),
        ("1.002755", I, "amends Luật Cư trú (in legal_basis); 'cư trú' redefined at commune level"), ("1.010028", I, "amends Luật Cư trú (in legal_basis); 'cư trú' redefined at commune level"),
        ("1.010038", I, "amends Luật Cư trú (in legal_basis); 'cư trú' redefined at commune level"), ("1.010040", I, "amends Luật Cư trú (in legal_basis); 'cư trú' redefined at commune level"),
        ("1.010041", I, "amends Luật Cư trú (in legal_basis); 'cư trú' redefined at commune level")],
    "change:bca:nd-154-2024-tom-tat": [
        ("1.004222", N, "names đăng ký thường trú"), ("1.003197", N, "names 'Hồ sơ, thủ tục xóa đăng ký thường trú'"), ("1.004194", N, "names đăng ký tạm trú"),
        ("1.010028", N, "names 'Hồ sơ, thủ tục xóa đăng ký tạm trú'"), ("1.003677", N, "names khai báo tạm vắng"),
        ("1.010040", N, "names residence of 'người không có nơi thường trú, nơi tạm trú'"),
        ("1.010041", I, "NĐ 154/2024 replaces NĐ 62/2021, cited in its legal_basis")],
    "change:bca:nd-70-2024-tom-tat": [
        ("1.001247", N, "names 'trình tự, thủ tục cấp … thẻ căn cước'"), ("2.000200", N, "names 'trình tự, thủ tục cấp … thẻ căn cước'"),
        ("1.012549", N, "names cấp thẻ căn cước for người dưới 14 tuổi"), ("1.014062", N, "names cấp thẻ căn cước for người dưới 14 tuổi"),
        ("1.000889", N, "names cấp đổi thẻ căn cước"), ("2.001195", N, "names cấp đổi thẻ căn cước"),
        ("1.000757", N, "names cấp lại thẻ căn cước"), ("2.001194", N, "names cấp lại thẻ căn cước"),
        ("2.001178", N, "names 'xác nhận thông tin số chứng minh nhân dân 09 số'")],
}
_TT116 = [("1.004222", N, "names đăng ký thường trú"), ("1.003197", N, "names 'xóa đăng ký thường trú'"), ("1.004194", N, "names đăng ký tạm trú"),
          ("1.010028", N, "names 'xóa đăng ký … tạm trú'"), ("1.003677", N, "names khai báo tạm vắng"), ("1.010041", N, "names 'xác nhận thông tin về cư trú'"),
          ("1.002755", I, "TT 116/2026 replaces TT 55/2021, cited in its legal_basis"), ("1.010040", I, "TT 116/2026 replaces TT 55/2021, cited in its legal_basis"),
          ("1.010038", I, "Luật Cư trú (sửa đổi) covered by the notice; Luật 68/2020 is in its legal_basis (tách hộ = Điều 25)")]
NOTICE_LINKS["change:xdcs:luat-cu-tru-sua-doi-tt-116-2026"] = _TT116
NOTICE_LINKS["change:bca:quy-dinh-moi-cu-tru-2026"] = _TT116
BODY_CLASSES = ["detail-content", "gt-detail-content", "content-document", "tinymce-content"]
DROP = re.compile(r"^(-\s*)?(Xem thêm|Đọc nhiều|Tin liên quan|Tham khảo thêm|>>|Chia sẻ)", re.I)
MIN_CHARS = 600  # below this the page is mostly images or link lists: skipped and listed


def body_of(html: str):
    s = BeautifulSoup(html, "html.parser")
    gt = s.find(class_="gt-detail-title")  # BCA portal news: headline + trailing date
    if gt:
        title = re.sub(r"\s*\d{2}/\d{2}/\d{4}\s*$", "", gt.get_text(" ", strip=True))
    else:
        title = (s.find("h1").get_text(" ", strip=True) if s.find("h1") else s.title.get_text(strip=True)).strip()
    pub = s.find("meta", attrs={"property": "article:published_time"})
    body = None
    for c in BODY_CLASSES:
        body = s.find(class_=c)
        if body:
            break
    if body is None:
        return title, None, []
    for x in body(["script", "style"]):
        x.decompose()
    sections, head, buf = [], None, []

    def flush():
        txt = "\n".join(b for b in buf if b).strip()
        if txt:
            sections.append({"heading": head or title, "text": txt})

    for el in body.find_all(["h2", "h3", "h4", "p", "li", "td"], recursive=True):
        if el.find_parent(["li", "td"]) and el.name in ("p",):
            continue
        t = el.get_text(" ", strip=True)
        if not t or DROP.match(t) or "ĐỌC NGAY" in t.upper():
            continue
        bold = el.name == "p" and el.find(["strong", "b"]) and el.find(["strong", "b"]).get_text(" ", strip=True) == t and len(t) < 160
        if el.name in ("h2", "h3", "h4") or bold:
            flush(); head, buf = t, []
        else:
            buf.append(("- " if el.name == "li" else "") + t)
    flush()
    return title, (pub["content"][:10] if pub else None), sections


def main() -> int:
    recs = [json.loads(l) for l in INDEX.read_text(encoding="utf-8").splitlines() if l.strip()]
    recs = [r for r in recs if r.get("status") == 200]
    n = 0
    for sub, kind, doc_id, pids, issuer, why, *cut in PAGES:
        hit = [r for r in recs if sub in r["url"]]
        if not hit:
            print(f"SKIP {doc_id}: not fetched"); continue
        r = hit[-1]
        title, pub, sections = body_of(Path(r["path"]).read_text(encoding="utf-8"))
        pub = pub or PUB.get(doc_id)
        if not sections:
            print(f"SKIP {doc_id}: no article body found"); continue
        if cut:  # drop the person-specific remainder of a Q&A answer (it names a citizen's ID number); the general rule is kept
            kept = []
            for x in sections:
                if cut[0] in x["text"]:
                    x = {"heading": x["heading"], "text": x["text"].split(cut[0])[0].strip()}
                    kept.append(x); break
                kept.append(x)
            sections = [x for x in kept if x["text"]]
            why += ". Excerpt: the answer's part about the asker's own ID numbers is left out (personal data)"
        if sum(len(x["text"]) for x in sections) < MIN_CHARS:
            print(f"SKIP {doc_id}: under {MIN_CHARS} chars of text (image steps / link lists)"); continue
        doc = {"doc_id": doc_id, "kind": kind, "title": title, "issuer": issuer, "effective_date": None, "url": r["url"],
               "retrieved_at": RETRIEVED, "sha256": r["sha256"], "procedure_ids": pids, "sections": sections, "jurisdiction": None,
               "link_method": "manual",
               "notes": f"relevance: {why}. Published {pub or 'date not stated'}. Linked manually from the page topic (the page gives no mã TTHC)."
                        + (" Published before Luật 118/2025/QH15 and TT 116/2026/TT-BCA took effect (01/07/2026): check against current rules." if pub and pub < "2026-07-01" else "")}
        if kind == "change_notice" and doc_id in NOTICE_LINKS:
            links = NOTICE_LINKS[doc_id]
            doc["procedure_ids"] = [pid for pid, _m, _w in links]
            doc["link_method"] = N if all(m == N for _p, m, _w in links) else I
            doc["notes"] = doc["notes"].replace(" Linked manually from the page topic (the page gives no mã TTHC).", "")
            doc["notes"] += " Links: " + "; ".join(f"{pid} ({m}): {w}" for pid, m, w in links) + "."
        if kind == "change_notice" and doc_id in EFFECTIVE:
            doc["effective_date"], how = EFFECTIVE[doc_id]
            doc["notes"] += f" effective_date: {how}."
        out = ROOT / kind
        out.mkdir(parents=True, exist_ok=True)
        (out / (re.sub(r"[^A-Za-z0-9._-]+", "_", doc_id) + ".json")).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
        print(f"{doc_id}: {len(sections)} sections, {sum(len(s['text']) for s in sections)} chars, pub {pub}")
    print(f"wrote {n} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
