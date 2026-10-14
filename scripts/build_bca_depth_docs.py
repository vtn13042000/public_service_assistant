"""Round-4 depth documents for the Bộ Công an families (căn cước, cư trú) — legal_text kind (w-dvc, BRIEF-8 Part 3).

Usage: uv run python scripts/build_bca_depth_docs.py
Reads raw files already fetched by scripts/fetch_depth_cached.py (data/raw/dvc/depth/index.jsonl); never fetches.
.doc files are converted to text with LibreOffice (headless) in a temp dir; text PDFs are read with pdfplumber.
Writes one JSON per cited article to data/processed_docs/legal_text/ (record shape: docs/05_log/ROUND-4-DATA.md,
schema data/schema/document_record.schema.json). Vietnamese text is kept verbatim (only line-end whitespace stripped);
cleaning/NFC is w-tools' step. sha256 = hash of the raw fetched file (provenance), shared by all articles of one file.
"""
import json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

import pdfplumber

INDEX = Path("data/raw/dvc/depth/index.jsonl")
OUT = Path("data/processed_docs/legal_text")
RETRIEVED = "2026-10-10"

CAP = ["1.001247", "2.000200", "1.012549", "1.014062"]          # cấp thẻ căn cước (≥14 TW/tỉnh, <14 tỉnh/xã)
DOI = ["1.000889", "2.001195"]                                   # cấp đổi
LAI = ["1.000757", "2.001194"]                                   # cấp lại
CC = CAP + DOI + LAI
TT_, XOA_TT, TAM, GH, XOA_TAM, VANG, TACH, KB, XN = (
    "1.004222", "1.003197", "1.004194", "1.002755", "1.010028", "1.003677", "1.010038", "1.010040", "1.010041")
CT = [TT_, XOA_TT, TAM, GH, XOA_TAM, VANG, TACH, KB, XN]

# key: (url substring, doc_id stem, title stem, issuer, effective_date, link_method, extra note)
TEXTS = {
    "luat26": ("datafiles.chinhphu.vn/cpp/files/vbpq/2024/01/luat26.pdf", "26-2023-QH15", "Luật Căn cước số 26/2023/QH15",
               "Quốc hội", "2024-07-01", "legal_basis", "Công báo text PDF from vanban.chinhphu.vn docid=209628. Original 2023 text; amended by Luật 118/2025/QH15 (in force 01/07/2026; scanned PDF, not merged)."),
    "nd70": ("70-2024-N%c4%90-CP.doc", "70-2024-ND-CP", "Nghị định 70/2024/NĐ-CP", "Chính phủ", "2024-07-01", "legal_basis",
             "Công báo .doc (congbao.chinhphu.vn/van-ban/nghi-dinh-so-70-2024-nd-cp-42136.htm). Amended by NĐ 58/2026/NĐ-CP (text not held): not merged."),
    "tt17": ("17-2024-TT-BCA.doc", "17-2024-TT-BCA", "Thông tư 17/2024/TT-BCA", "Bộ Công an", "2024-07-01", "legal_basis",
             "Công báo .doc (congbao.chinhphu.vn/van-ban/thong-tu-so-17-2024-tt-bca-42016/50405.htm). Amended by TT 53/2025/TT-BCA and TT 118/2026/TT-BCA (neither held as text): not merged."),
    "luat68": ("68-2020-QH14.doc", "68-2020-QH14", "Luật Cư trú số 68/2020/QH14", "Quốc hội", "2021-07-01", "legal_basis",
               "Công báo .doc (congbao.chinhphu.vn tai-ve-van-ban-so-68-2020-qh14). Original 2020 text; amended by Luật 118/2025/QH15 (in force 01/07/2026; its text is only a scanned PDF on datafiles.chinhphu.vn) and earlier consolidated as VBHN 01/VBHN-VPQH (2025, not held): amendments not merged."),
    "nd154": ("154-2024-N%c4%90-CP.doc", "154-2024-ND-CP", "Nghị định 154/2024/NĐ-CP", "Chính phủ", "2025-01-10", "manual",
              "Công báo .doc (congbao.chinhphu.vn/noi-dung-van-ban-so-154-2024-nd-cp-43275). Linked manually: it replaces NĐ 62/2021/NĐ-CP, which the BCA portal pages still cite in legal_basis. Amended by NĐ 58/2026/NĐ-CP (incl. Điều 7, 9, 10; text not held): not merged."),
    "tt116": ("116%2f2026%2fTT-BCA.docx", "116-2026-TT-BCA", "Thông tư 116/2026/TT-BCA", "Bộ Công an", "2026-07-01", "legal_basis",
              "Công báo .docx (congbao.chinhphu.vn/van-ban/thong-tu-so-116-2026-tt-bca-470078/67091.htm). Current detailed rules for Luật Cư trú as amended by Luật 118/2025/QH15; from 01/07/2026 it repeals TT 55/2021, 56/2021, 66/2023 (Điều 27). Linked via the legal_basis entry TT 55/2021, which it replaces."),
}

# Currency of each text (lead's request): (original_version, amended_by). Sources: TT 116/2026 trích yếu ("Luật Cư trú … được sửa đổi,
# bổ sung bởi Luật số 118/2025/QH15"); vanban.chinhphu.vn docid=216534 (Luật 118/2025/QH15 amends 10 security-order laws incl. Luật Căn cước);
# NĐ 58/2026 notices (BCA portal matin=421: NĐ 70/2024; xaydungchinhsach: NĐ 154/2024); vbpl.vn sitemap title of TT 118/2026/TT-BCA (amends TT 17/2024,
# already amended by TT 53/2025). Consolidated texts were not available as text.
AMENDED = {"luat26": ["Luật 118/2025/QH15"], "luat68": ["Luật 118/2025/QH15"], "nd70": ["NĐ 58/2026/NĐ-CP"], "nd154": ["NĐ 58/2026/NĐ-CP"],
           "tt17": ["TT 53/2025/TT-BCA", "TT 118/2026/TT-BCA"]}

# (text key, article number, procedure_ids, relevance note)
ARTICLES = [
    ("luat26", 19, CAP, "who is issued a card"), ("luat26", 20, CC, "legal value of the card"),
    ("luat26", 21, CAP + DOI, "ages at which the card must be changed"), ("luat26", 23, CAP, "procedure to issue a card"),
    ("luat26", 24, DOI + LAI, "cases for change and re-issue"), ("luat26", 25, DOI + LAI, "procedure to change / re-issue"),
    ("luat26", 26, CC, "time limit"), ("luat26", 27, CC, "where to apply"), ("luat26", 28, CC, "competent authority"),
    ("nd70", 12, ["2.001178"], "confirmation of 9-digit ID number / personal ID number"),
    ("nd70", 21, CC, "procedure to issue, change, re-issue the card"),
    ("tt17", 6, CC, "receiving applications for issue, change, re-issue"), ("tt17", 8, CC, "forms used (CC01 …)"),
    ("luat68", 19, [KB], "residence of people without permanent/temporary residence"),
    ("luat68", 20, [TT_], "conditions for permanent registration"), ("luat68", 21, [TT_], "dossier for permanent registration"),
    ("luat68", 22, [TT_], "procedure for permanent registration"), ("luat68", 23, [TT_], "places where new permanent registration is not allowed"),
    ("luat68", 24, [XOA_TT], "deregistration of permanent residence"), ("luat68", 25, [TACH], "splitting a household"),
    ("luat68", 27, [TAM, GH], "conditions for temporary registration"), ("luat68", 28, [TAM, GH], "dossier/procedure for temporary registration and extension"),
    ("luat68", 29, [XOA_TAM], "deregistration of temporary residence"), ("luat68", 31, [VANG], "declaring temporary absence"),
    ("nd154", 4, [KB], "residence of people without permanent/temporary residence"),
    ("nd154", 5, [TT_, TAM, GH], "documents proving lawful accommodation"),
    ("nd154", 6, [TT_, TACH], "documents proving family relationship"), ("nd154", 7, [TT_, TAM], "registration for minors"),
    ("nd154", 9, [XOA_TT], "dossier/procedure for permanent deregistration"), ("nd154", 10, [XOA_TAM], "dossier/procedure for temporary deregistration"),
    ("tt116", 3, CT, "receiving and deciding residence dossiers, notifying results"),
    ("tt116", 5, [TT_, TAM], "cases where residence temporarily cannot be changed"),
    ("tt116", 6, [TT_, TACH], "relationship with the head of household; special cases"),
    ("tt116", 12, [TAM, GH], "temporary registration"), ("tt116", 15, [VANG], "temporary absence declaration"),
    ("tt116", 16, [XN], "confirmation of residence information"), ("tt116", 19, [XOA_TT, XOA_TAM], "permanent / temporary deregistration"),
    ("tt116", 20, CT, "forms used in residence registration (CT01 used by all nine)"),
]


# Forms printed in the circular appendices: (text key, form code, procedure_ids from the codes the BCA records name, title, note)
CT_FORM_USERS = [TT_, TAM, GH, XOA_TT, XOA_TAM, TACH, KB, XN]
FORMS = [
    ("tt116", "CT01", CT_FORM_USERS, "Tờ khai thay đổi thông tin cư trú", "Current version (TT 116/2026/TT-BCA, from 01/07/2026)."),
    ("tt116", "CT03", [VANG], "Phiếu khai báo tạm vắng", "Current version (TT 116/2026/TT-BCA, from 01/07/2026)."),
    ("tt116", "CT07", [XN], "Xác nhận thông tin về cư trú (result document)", "Current version (TT 116/2026/TT-BCA, from 01/07/2026)."),
    ("tt17", "CC01", [p for p in CC], "Phiếu thu nhận thông tin căn cước",
     "Version of TT 17/2024/TT-BCA; 2026 guidance cites CC01 per TT 118/2026/TT-BCA (text not held): fields may differ."),
    ("tt17", "DC01", ["1.012549", "1.014062", "2.000200"], "Phiếu thu thập thông tin dân cư", "Version of TT 17/2024/TT-BCA; may be superseded by TT 118/2026/TT-BCA (not held)."),
    ("tt17", "DC02", CC + ["2.001178"], "Phiếu đề nghị giải quyết thủ tục hành chính về căn cước", "Version of TT 17/2024/TT-BCA; may be superseded by TT 118/2026/TT-BCA (not held)."),
]
FORM_HEAD = re.compile(r"^\s*Mẫu\s+(C[CT]\d+a?|DC\d+)\s+ban hành")


def forms(text: str) -> dict[str, str]:
    """{code: body} for each form appendix: from its 'Mẫu XX ban hành kèm theo' line to the next one (first occurrence)."""
    out, cur, buf = {}, None, []
    for l in text.splitlines():
        m = FORM_HEAD.match(l)
        if m:
            if cur and cur not in out:
                out[cur] = "\n".join(x.strip() for x in buf).strip()
            cur, buf = m.group(1), [l]
        elif cur:
            buf.append(l)
    if cur and cur not in out:
        out[cur] = "\n".join(x.strip() for x in buf).strip()
    return {k: re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", v)) for k, v in out.items()}


def index_by_sub() -> dict:
    recs = [json.loads(l) for l in INDEX.read_text(encoding="utf-8").splitlines() if l.strip()]
    recs = [r for r in recs if r.get("status") == 200]
    out = {}
    for k, (sub, *_rest) in TEXTS.items():
        hits = [r for r in recs if sub in r["url"]]
        if not hits:
            sys.exit(f"missing raw file for {k} ({sub}); fetch it first")
        out[k] = hits[-1]
    return out


def docx_text(p: Path) -> str:
    """Paragraph text from word/document.xml (some Công báo .docx files store zip names with backslashes, which docx libraries reject)."""
    import html, zipfile
    z = zipfile.ZipFile(p)
    name = next(n for n in z.namelist() if n.replace("\\", "/") == "word/document.xml")
    xml = z.read(name).decode("utf-8")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
    return "\n".join(html.unescape("".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", x))) for x in paras)


def text_of(rec: dict, tmp: Path) -> str:
    p = Path(rec["path"])
    if "wordprocessingml" in rec["content_type"]:
        return docx_text(p)
    if rec["content_type"].startswith("application/pdf"):
        with pdfplumber.open(p) as pdf:
            return "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    src = tmp / (rec["sha256"][:16] + ".doc")
    shutil.copy(p, src)
    subprocess.run(["soffice", "--headless", "--convert-to", "txt:Text (encoded):UTF8", "--outdir", str(tmp), str(src)],
                   check=True, capture_output=True, timeout=300)
    return (tmp / (src.stem + ".txt")).read_text(encoding="utf-8")


HEAD = re.compile(r"^\s*(Điều\s+(\d+)\s*\..*|Chương\s+[IVXLC]+.*|Mục\s+\d+.*)$")


def articles(text: str) -> dict[int, tuple[str, str]]:
    """First occurrence of each article in document order: {n: (heading, body)}. Stops at the next article or chapter."""
    lines = [l.rstrip() for l in text.splitlines()]
    out, cur, buf = {}, None, []

    def flush():
        if cur and cur[0] not in out:
            body = "\n".join(x.strip() for x in buf).strip()
            out[cur[0]] = (cur[1], re.sub(r"\n{3,}", "\n\n", body))

    for l in lines:
        m = HEAD.match(l)
        if m:
            flush()
            cur = (int(m.group(2)), m.group(1).strip()) if m.group(2) else None
            buf = []
        elif cur:
            buf.append(l)
    flush()
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    idx = index_by_sub()
    with tempfile.TemporaryDirectory() as td:
        raw = {k: text_of(r, Path(td)) for k, r in idx.items()}
    texts = {k: articles(t) for k, t in raw.items()}
    n = 0
    for key, num, pids, why in ARTICLES:
        _sub, stem, title, issuer, eff, link, note = TEXTS[key]
        if num not in texts[key]:
            print(f"SKIP {key} Điều {num}: not found in text"); continue
        head, body = texts[key][num]
        if len(body) < 40:
            print(f"SKIP {key} Điều {num}: body too short"); continue
        rec = idx[key]
        doc = {"doc_id": f"legal:{stem}:dieu-{num}", "kind": "legal_text", "title": f"{title}, Điều {num}", "issuer": issuer,
               "effective_date": eff, "url": rec["url"], "retrieved_at": RETRIEVED, "sha256": rec["sha256"],
               "procedure_ids": pids, "sections": [{"heading": head, "text": body}], "jurisdiction": None,
               "link_method": link, "notes": f"relevance: {why}. {note}"}
        if key in AMENDED:
            doc["original_version"], doc["amended_by"] = True, AMENDED[key]
        (OUT / f"legal_{stem}_dieu-{num}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    print(f"wrote {n} legal_text documents to {OUT}")
    fout = OUT.parent / "form"
    fout.mkdir(parents=True, exist_ok=True)
    m = 0
    for key, code, pids, ftitle, fnote in FORMS:
        _sub, stem, title, issuer, eff, _link, note = TEXTS[key]
        body = forms(raw[key]).get(code)
        if not body or len(body) < 200:
            print(f"SKIP form {code} in {key}: not found"); continue
        rec = idx[key]
        doc = {"doc_id": f"form:{stem}:{code}", "kind": "form", "title": f"Mẫu {code} – {ftitle} ({title})", "issuer": issuer,
               "effective_date": eff, "url": rec["url"], "retrieved_at": RETRIEVED, "sha256": rec["sha256"], "procedure_ids": pids,
               "sections": [{"heading": f"Mẫu {code} – {ftitle}", "text": body}], "jurisdiction": None, "link_method": "procedure_code",
               "notes": f"Linked through the form code {code} named in the procedures' document lists (BCA portal records). {fnote} Source: {note}"}
        if key in AMENDED:
            doc["original_version"], doc["amended_by"] = True, AMENDED[key]
        (fout / f"form_{stem}_{code}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        m += 1
    print(f"wrote {m} form documents to {fout}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
