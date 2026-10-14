"""Round 4 (docs/05_log/ROUND-4-DATA.md): build hộ tịch depth documents → data/processed_docs/<kind>/<doc_id>.json.

legal_text: articles (điều) of Luật Hộ tịch 60/2014/QH13, NĐ 123/2015/NĐ-CP and TT 04/2020/TT-BTP, cut from one official
file (Lâm Đồng provincial portal, a .doc holding the three texts as originally issued). Only articles that a procedure
relies on are emitted; ARTICLES maps each to procedure_ids with the reason.

Raw files come from data/raw/moj/index.jsonl (fetched by scripts/moj_docs_fetch.py). .doc/.docx are converted to text
with LibreOffice into data/raw/moj/docs/txt/ (derived, reproducible).

Usage: uv run python scripts/moj_docs_build.py
"""
import json
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "moj"
TXT = RAW / "docs" / "txt"
OUT = ROOT / "data" / "processed_docs"

# --- procedure families (mã TTHC, all present in data/processed/moj or /daklak) ---
KS = ["1.001193", "1.003583", "1.004772", "1.000689"]          # khai sinh trong nước (+ lưu động, đã có giấy tờ, kết hợp CMC)
KS_N = ["2.000528", "1.000893", "1.001695"]                      # khai sinh có yếu tố nước ngoài
KH = ["1.000894", "1.000593"]                                    # kết hôn (+ lưu động)
KH_N = ["2.000806"]
KT = ["1.000656", "1.000419"]                                    # khai tử (+ lưu động)
KT_N = ["1.001766"]
GH, CDGH, GH_N, CDGH_N = ["1.004837"], ["1.004845"], ["1.001669"], ["2.000756"]
CMC = ["1.001022", "1.000689"]
CMC_N = ["2.000779", "1.001695"]
TD, TD_N = ["1.004859"], ["2.000748"]
LAI = ["1.004884", "1.004746", "1.005461"]                       # đăng ký lại KS / KH / KT
LAI_N = ["2.000522", "2.000513", "2.000497"]
BG = {"ks": ["1.000110"], "kh": ["1.000094"], "cmc": ["1.000080"], "kt": ["1.004827"]}  # khu vực biên giới
XNHN = ["1.004873"]
GC_KH, GC_LH, GC_KHAC = ["2.002189"], ["2.000554"], ["2.000547"]
BANSAO = ["2.000635"]
CORE = ["1.001193", "1.000894", "1.000656"]
ALL39 = sorted(set(KS + KS_N + KH + KH_N + KT + KT_N + GH + CDGH + GH_N + CDGH_N + CMC + CMC_N + TD + TD_N + LAI + LAI_N
                   + sum(BG.values(), []) + XNHN + GC_KH + GC_LH + GC_KHAC + BANSAO + ["2.002516", "3.000322", "3.000323"]))

# instrument key -> metadata. 'start' = the "Số:" line marker that opens it inside the compendium file.
INSTR = {
    "60-2014-QH13": dict(name="Luật Hộ tịch số 60/2014/QH13", issuer="Quốc hội", effective="2016-01-01",
                         start="Luật số: 60/2014/QH13", amended_by=["120/2025/NĐ-CP"],
                         amended="Luật đã được sửa đổi, bổ sung; thẩm quyền của UBND cấp huyện trong Luật được phân định lại cho UBND cấp xã "
                                 "từ 01/07/2025 (Nghị định 120/2025/NĐ-CP, Điều 4). Luật Hộ tịch số 03/2026/QH16 thay thế Luật này từ 01/03/2027."),
    "123-2015-ND-CP": dict(name="Nghị định 123/2015/NĐ-CP", issuer="Chính phủ", effective="2016-01-01",
                           start="Số: 123/2015/NĐ-CP", amended_by=["87/2020/NĐ-CP", "104/2022/NĐ-CP", "07/2025/NĐ-CP", "120/2025/NĐ-CP"],
                           amended="Văn bản gốc; đã được sửa đổi, bổ sung bởi Nghị định 87/2020/NĐ-CP, 104/2022/NĐ-CP, 07/2025/NĐ-CP và "
                                   "thẩm quyền được phân định lại theo Nghị định 120/2025/NĐ-CP (từ 01/07/2025)."),
    "04-2020-TT-BTP": dict(name="Thông tư 04/2020/TT-BTP", issuer="Bộ Tư pháp", effective="2020-07-16",
                           start="Số: 04/2020/TT-BTP", amended_by=["09/2022/TT-BTP", "04/2024/TT-BTP", "08/2025/TT-BTP"],
                           amended="Văn bản gốc; đã được sửa đổi, bổ sung bởi Thông tư 09/2022/TT-BTP, 04/2024/TT-BTP và Thông tư 08/2025/TT-BTP."),
}

# (instrument, điều) -> (procedure_ids, reason)
A = {}
def art(instr, nums, pids, reason):
    for n in nums:
        A[(instr, n)] = (pids, reason)

L = "60-2014-QH13"
art(L, [7], KS_N + KH_N + KT_N + GH_N + CDGH_N + CMC_N + TD_N + GC_KH + GC_LH + GC_KHAC, "thẩm quyền đăng ký hộ tịch (cấp huyện cho việc có yếu tố nước ngoài, nay là cấp xã)")
art(L, [9], CORE, "phương thức yêu cầu và tiếp nhận yêu cầu đăng ký hộ tịch")
art(L, [11], ALL39, "lệ phí hộ tịch: các trường hợp miễn lệ phí")
art(L, [13, 14, 15, 16], KS, "đăng ký khai sinh tại UBND cấp xã")
art(L, [17, 18], KH, "đăng ký kết hôn tại UBND cấp xã")
art(L, [19], GH + CDGH, "thẩm quyền đăng ký giám hộ, chấm dứt giám hộ")
art(L, [20, 21, 23], GH, "đăng ký giám hộ")
art(L, [22], CDGH, "đăng ký chấm dứt giám hộ")
art(L, [24, 25], CMC, "đăng ký nhận cha, mẹ, con")
art(L, [26, 27, 28, 29], TD, "thay đổi, cải chính, bổ sung hộ tịch")
art(L, [32, 33, 34], KT, "đăng ký khai tử")
art(L, [35, 36], KS_N, "đăng ký khai sinh có yếu tố nước ngoài")
art(L, [37, 38], KH_N, "đăng ký kết hôn có yếu tố nước ngoài")
art(L, [39, 40, 41], GH_N, "đăng ký giám hộ có yếu tố nước ngoài")
art(L, [42], CDGH_N, "chấm dứt, thay đổi giám hộ có yếu tố nước ngoài")
art(L, [43, 44], CMC_N, "nhận cha, mẹ, con có yếu tố nước ngoài")
art(L, [45, 46, 47], TD_N, "thay đổi, cải chính, bổ sung hộ tịch, xác định lại dân tộc có yếu tố nước ngoài")
art(L, [48], GC_KH + GC_LH + GC_KHAC, "thẩm quyền ghi vào Sổ hộ tịch việc hộ tịch đã giải quyết ở nước ngoài")
art(L, [49], GC_KHAC, "ghi vào Sổ hộ tịch việc khai sinh, giám hộ, nhận cha mẹ con… giải quyết ở nước ngoài")
art(L, [50], GC_KH + GC_LH, "ghi vào Sổ hộ tịch việc kết hôn, ly hôn, hủy việc kết hôn giải quyết ở nước ngoài")
art(L, [51, 52], KT_N, "đăng ký khai tử có yếu tố nước ngoài")
art(L, [63, 64], BANSAO, "cấp bản sao trích lục hộ tịch")

N = "123-2015-ND-CP"
art(N, [2, 3], CORE, "giấy tờ nộp, xuất trình và cách thức nộp hồ sơ đăng ký hộ tịch")
art(N, [4], KS + KT, "xác định nội dung đăng ký khai sinh, khai tử")
art(N, [7], TD + TD_N, "điều kiện thay đổi, cải chính hộ tịch")
art(N, [9], KS, "giấy tờ nộp và xuất trình khi đăng ký khai sinh")
art(N, [10], KH, "giấy tờ nộp và xuất trình khi đăng ký kết hôn")
art(N, [14, 15, 16], ["1.001193"], "đăng ký khai sinh trong trường hợp đặc biệt (trẻ bị bỏ rơi, chưa xác định cha mẹ, mang thai hộ)")
art(N, [17], BG["ks"], "đăng ký khai sinh tại khu vực biên giới")
art(N, [18], BG["kh"], "đăng ký kết hôn tại khu vực biên giới")
art(N, [19], BG["cmc"], "đăng ký nhận cha, mẹ, con tại khu vực biên giới")
art(N, [20], BG["kt"], "đăng ký khai tử tại khu vực biên giới")
art(N, [21, 22, 23], XNHN, "cấp Giấy xác nhận tình trạng hôn nhân")
art(N, [24, 25], LAI, "điều kiện, thẩm quyền đăng ký lại khai sinh, kết hôn, khai tử")
art(N, [26], ["1.004884"], "thủ tục đăng ký lại khai sinh")
art(N, [27], ["1.004746"], "thủ tục đăng ký lại kết hôn")
art(N, [28], ["1.005461"], "thủ tục đăng ký lại khai tử")
art(N, [29], ["1.001193"], "khai sinh cho trẻ em sinh ra ở nước ngoài về cư trú tại Việt Nam")
art(N, [30, 31, 32, 33], KH_N, "đăng ký kết hôn có yếu tố nước ngoài")
art(N, [34, 35, 36], GC_KH, "ghi vào Sổ hộ tịch việc kết hôn đã giải quyết ở nước ngoài")
art(N, [37, 38, 39], GC_LH, "ghi vào Sổ hộ tịch việc ly hôn, hủy việc kết hôn đã giải quyết ở nước ngoài")
art(N, [40, 41, 42], LAI_N, "đăng ký lại khai sinh, kết hôn, khai tử có yếu tố nước ngoài")

T = "04-2020-TT-BTP"
art(T, [2, 3], CORE, "ủy quyền; tiếp nhận hồ sơ và trả kết quả đăng ký hộ tịch")
art(T, [6], KS, "nội dung khai sinh")
art(T, [7], KS_N, "đăng ký khai sinh có yếu tố nước ngoài")
art(T, [8], ["1.004772", "1.000893"], "đăng ký khai sinh cho người đã có hồ sơ, giấy tờ cá nhân")
art(T, [9, 10], ["1.004884", "2.000522"], "đăng ký lại khai sinh: giấy tờ làm cơ sở, xác định nội dung")
art(T, [11], KH_N, "đăng ký kết hôn có yếu tố nước ngoài")
art(T, [12], XNHN, "cấp Giấy xác nhận tình trạng hôn nhân")
art(T, [13], KT + KT_N, "đăng ký khai tử")
art(T, [14, 16], CMC + CMC_N, "nhận cha, mẹ, con: chứng cứ, trường hợp đặc biệt")
art(T, [15], ["1.000689", "1.001695"], "kết hợp đăng ký khai sinh và nhận cha, mẹ, con")
art(T, [17, 18, 20], TD + TD_N, "cải chính, bổ sung, thay đổi thông tin hộ tịch")
art(T, [22], GC_KH + GC_LH + GC_KHAC, "ghi vào Sổ hộ tịch việc hộ tịch đã giải quyết ở nước ngoài")
art(T, [23], BANSAO, "cấp bản sao trích lục hộ tịch")
art(T, [24], ["1.003583", "1.000419", "1.000593"], "các trường hợp đăng ký lưu động")
art(T, [25], ["1.003583", "1.000419"], "thủ tục đăng ký khai sinh, khai tử lưu động")
art(T, [26], ["1.000593"], "thủ tục đăng ký kết hôn lưu động")

COMPENDIUM = "docs/luat-60-2014-QH13.lamdong"


def nfc(s):
    return unicodedata.normalize("NFC", s)


def index():
    out = {}
    for line in (RAW / "index.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        out[r["path"].split("data/raw/moj/", 1)[-1]] = r
    return out


def to_text(rel):
    """LibreOffice .doc/.docx -> UTF-8 text, cached in data/raw/moj/docs/txt/."""
    TXT.mkdir(parents=True, exist_ok=True)
    out = TXT / (Path(rel).name + ".txt")
    if not out.exists():
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / ("in" + (Path(rel).suffix if Path(rel).suffix in (".doc", ".docx") else ".doc"))
            src.write_bytes((RAW / rel).read_bytes())
            subprocess.run(["soffice", "--headless", "--convert-to", "txt:Text", "--outdir", td, str(src)],
                           check=True, capture_output=True, timeout=180)
            out.write_text((Path(td) / "in.txt").read_text(encoding="utf-8-sig"), encoding="utf-8")
    return nfc(out.read_text(encoding="utf-8"))


def split_instruments(text):
    lines = text.splitlines()
    starts = sorted((next(i for i, l in enumerate(lines) if l.strip() == m["start"]), k) for k, m in INSTR.items())
    out = {}
    for j, (i, k) in enumerate(starts):
        end = starts[j + 1][0] if j + 1 < len(starts) else len(lines)
        out[k] = lines[i:end]
    return out


def articles(lines):
    """{điều number: (heading, body)}; a chapter/section heading line ends the previous article body."""
    arts, cur = {}, None
    for l in lines:
        s = l.strip()
        m = re.match(r"^Điều (\d+)\. ", s)
        if m:
            cur = int(m.group(1))
            arts[cur] = [s, []]
        elif cur is not None:
            if re.match(r"^(Chương|Mục) [IVX\d]+", s) or re.fullmatch(r"[A-ZĐÀ-Ỹ ,;]{12,}", s):
                continue
            if s:
                arts[cur][1].append(re.sub(r"\s+", " ", s))
    return {n: (h, "\n".join(b).strip()) for n, (h, b) in arts.items()}


def write(rec):
    d = OUT / rec["kind"]
    d.mkdir(parents=True, exist_ok=True)
    fname = re.sub(r"[^A-Za-z0-9._-]+", "_", rec["doc_id"]) + ".json"
    (d / fname).write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_legal(idx):
    meta = idx[COMPENDIUM]
    parts = split_instruments(to_text(COMPENDIUM))
    n = 0
    for (instr, num), (pids, reason) in sorted(A.items()):
        h, body = articles(parts[instr])[num]
        m = INSTR[instr]
        # trim a signature block that follows the last article of an instrument
        body = re.split(r"\n(?:CHỦ TỊCH QUỐC HỘI|TM\. CHÍNH PHỦ|BỘ TRƯỞNG)\n", body)[0].strip()
        write({
            "doc_id": f"legal:{instr}:dieu-{num}",
            "kind": "legal_text",
            "title": f"{m['name']}, Điều {num}",
            "issuer": m["issuer"],
            "effective_date": m["effective"],
            "jurisdiction": None,
            "url": meta["url"],
            "retrieved_at": meta["fetched_at"][:10],
            "sha256": meta["sha256"],
            "procedure_ids": sorted(set(pids)),
            "link_method": "legal_basis",
            "original_version": True,
            "amended_by": m["amended_by"],
            "sections": [{"heading": h, "text": body}],
            "notes": f"relevance: {reason}; {m['name']} is cited in legal_basis of these procedures (article chosen by topic). "
                     f"Source: văn bản gốc, bản Word do Cổng TTĐT tỉnh Lâm Đồng đăng tải. Hiệu lực/sửa đổi: {m['amended']}",
        })
        n += 1
    return n


if __name__ == "__main__":
    idx = index()
    print("legal_text:", build_legal(idx))


# ---------------------------------------------------------------- change_notice / guidance / fee_resolution (official pages)
def main_paras(path):
    """Paragraph texts of the page's main content block: the container whose <p>/<li>/<h*> text dominates its total text."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        t.decompose()
    nv = soup.select("div.hometext, div.bodytext")  # NukeViet portals (hcc.nghean.gov.vn): lead + body
    nv = nv or soup.select("h2.detail-sapo, div.detail-content")  # xaydungchinhsach.chinhphu.vn: sapo + body
    if nv:
        out = []
        for el in nv:
            blocks = el.find_all(["p", "li", "h2", "h3", "h4"]) or [el]
            out += [nfc(re.sub(r"\s+", " ", b.get_text(" ", strip=True))) for b in blocks if b.get_text(strip=True)]
        return out
    best, bs = None, 0
    for el in soup.find_all(["div", "article", "section", "td"]):
        n = sum(len(p.get_text(" ", strip=True)) for p in el.find_all(["p", "h2", "h3", "h4", "li"]))
        score = n - 0.3 * (len(el.get_text(" ", strip=True)) - n)
        if score > bs:
            best, bs = el, score
    return [nfc(re.sub(r"\s+", " ", p.get_text(" ", strip=True)))
            for p in best.find_all(["p", "h2", "h3", "h4", "li"]) if p.get_text(strip=True)]


def by_heading(paras, first_heading):
    """Short lines without final punctuation open a new section; everything else is body."""
    secs = [[first_heading, []]]
    for p in paras:
        if len(p) < 120 and not re.search(r"[.:;,)]$", p) and not re.match(r"^[-+a-zđ\d]+[).]\s", p) and secs[-1][1]:
            secs.append([p, []])
        else:
            secs[-1][1].append(p)
    return [{"heading": h, "text": "\n".join(b)} for h, b in secs if b]


# file, kind, doc_id, title, issuer, effective_date, slice of main_paras, procedure_ids, link_method, notes
PAGES = [
    ("docs/cn-nghean-nd120-trinh-tu.html", "change_notice", "change:nghean-hcc:nd120-2025-ho-tich",
     "Nghị định 120/2025/NĐ-CP: Trình tự, thủ tục đăng ký hộ tịch tại UBND cấp xã", "Trung tâm Phục vụ Hành chính công tỉnh Nghệ An",
     "2025-07-01", (0, 999), ALL39, "manual",
     "relevance: thông báo thay đổi thẩm quyền đăng ký hộ tịch sang UBND cấp xã từ 01/07/2025 (NĐ 120/2025/NĐ-CP Điều 4–5), áp dụng cho mọi thủ tục hộ tịch; "
     "thời hạn KH YTNN 05 ngày, nhận cha mẹ con 10 ngày, ghi chú kết hôn/ly hôn. Bài đăng 13/06/2025 trên cổng TTĐT tỉnh Nghệ An. "
     "Cùng nội dung bài Báo Chính phủ đăng lại trên hatinh.gov.vn (bỏ qua, trùng)."),
    ("docs/cn-cantho-thu-tuc-tu-0107.html", "change_notice", "change:cantho-pbgdpl:thu-tuc-ho-tich-tu-01-07-2025",
     "Thủ tục đăng ký hộ tịch từ ngày 01/7/2025", "Sở Tư pháp thành phố Cần Thơ (Phòng Nghiệp vụ 1)",
     "2025-07-01", (2, 11), ALL39, "manual",
     "relevance: tóm tắt NĐ 120/2025/NĐ-CP về trình tự, thời hạn đăng ký hộ tịch tại UBND cấp xã từ 01/07/2025; áp dụng cho mọi thủ tục hộ tịch. "
     "Bài đăng 13/06/2025 trên Trang PBGDPL thành phố Cần Thơ."),
    ("docs/cn-hatinh-linh-hoat-noi-dk.html", "change_notice", "change:hatinh:linh-hoat-noi-dang-ky-ho-tich",
     "Người dân được linh hoạt lựa chọn nơi đăng ký thủ tục hộ tịch từ ngày 1/7/2025", "Cổng thông tin điện tử tỉnh Hà Tĩnh",
     "2025-07-01", (1, 9), ALL39, "manual",
     "relevance: NĐ 120/2025/NĐ-CP khoản 1–2 Điều 5: quyền chọn nơi đăng ký hộ tịch (nơi thường trú/tạm trú) và hỗ trợ nộp trực tuyến khi nộp sai nơi; "
     "áp dụng cho mọi thủ tục hộ tịch. Bài đăng 29/01/2026."),
    ("docs/cn-nghean-2176-danh-muc-moi-bai-bo.html", "change_notice", "change:nghean-hcc:qd403-2025-tthc-ho-tich-moi-bai-bo",
     "Công bố Danh mục thủ tục hành chính mới ban hành, bị bãi bỏ trong lĩnh vực Hộ tịch, Quốc tịch, Chứng thực, Nuôi con nuôi (QĐ 403/QĐ-UBND ngày 25/02/2025, tỉnh Nghệ An)",
     "UBND tỉnh Nghệ An (tin: Trung tâm PVHCC tỉnh Nghệ An)", "2025-02-25", (0, 999), ["2.000635", "2.002516"], "manual",
     "relevance: công bố TTHC hộ tịch cấp tỉnh mới (Cấp bản sao trích lục hộ tịch; Xác nhận thông tin hộ tịch) theo NĐ 07/2025/NĐ-CP. "
     "Văn bản cấp tỉnh trước 01/07/2025; thẩm quyền sau đó theo 1833/QĐ-BTP (Cơ quan quản lý CSDL hộ tịch điện tử)."),
    ("docs/cn-nghean-2146-trien-khai-nd07.html", "change_notice", "change:nghean-hcc:cv935-2025-trien-khai-nd07",
     "Triển khai Nghị định sửa đổi, bổ sung một số điều của các Nghị định trong lĩnh vực hộ tịch, quốc tịch, chứng thực (CV 935/UBND-KSTT ngày 12/02/2025, tỉnh Nghệ An)",
     "UBND tỉnh Nghệ An (tin: Trung tâm PVHCC tỉnh Nghệ An)", "2025-01-09", (0, 999), KH + KH_N + KS + KT + XNHN, "manual",
     "relevance: thông báo việc triển khai NĐ 07/2025/NĐ-CP (hiệu lực từ ngày ký 09/01/2025) sửa đổi NĐ 123/2015, 87/2020 trong lĩnh vực hộ tịch: "
     "ảnh hưởng hồ sơ khai sinh, kết hôn, khai tử, xác nhận tình trạng hôn nhân."),
    ("docs/cn-nghean-1294-bai-bo-xac-nhan-tt-ho-tich.html", "change_notice", "change:nghean-hcc:qd1159-2024-bai-bo-xac-nhan-thong-tin-ho-tich-cap-xa",
     "Bãi bỏ thủ tục Xác nhận thông tin hộ tịch thuộc thẩm quyền giải quyết của UBND cấp xã (QĐ 1159/QĐ-UBND ngày 13/5/2024, tỉnh Nghệ An)",
     "UBND tỉnh Nghệ An (tin: Trung tâm PVHCC tỉnh Nghệ An)", "2024-05-13", (0, 10), ["2.002516"], "manual",
     "relevance: thủ tục Xác nhận thông tin hộ tịch không thuộc UBND cấp xã theo NĐ 87/2020/NĐ-CP Điều 8 (trích trong bài). "
     "Tin năm 2024: phần nói Phòng Tư pháp đã lỗi thời (cấp huyện bỏ từ 01/07/2025)."),
    ("docs/cn-nghean-1107-phan-cap-phong-tu-phap.html", "change_notice", "change:nghean-hcc:cv1929-2024-phan-cap-phong-tu-phap",
     "Phân cấp thẩm quyền giải quyết một số TTHC lĩnh vực Hộ tịch từ UBND cấp huyện về Phòng Tư pháp (CV 1929/UBND-KSTT ngày 13/3/2024, tỉnh Nghệ An)",
     "UBND tỉnh Nghệ An (tin: Trung tâm PVHCC tỉnh Nghệ An)", "2024-03-13", (0, 999),
     KS_N + KH_N + KT_N + GH_N + CDGH_N + CMC_N + TD_N + GC_KH + GC_LH + GC_KHAC + LAI_N, "manual",
     "relevance: lịch sử thẩm quyền các TTHC hộ tịch có yếu tố nước ngoài (cấp huyện → Phòng Tư pháp, theo QĐ 1015/QĐ-TTg và CV 987/BTP-HTQTCT). "
     "LỖI THỜI: từ 01/07/2025 không còn cấp huyện; các thủ tục này do UBND cấp xã thực hiện (NĐ 120/2025/NĐ-CP Điều 4). Dùng để giải thích thay đổi, không dùng làm thẩm quyền hiện hành."),
    ("docs/xdcs-luat-ht-sua-doi-khong-phu-thuoc-dia-gioi.htm", "change_notice", "change:xdcs:luat-ho-tich-2026-khong-phu-thuoc-dia-gioi", "LUẬT HỘ TỊCH (sửa đổi): Đăng ký khai sinh, kết hôn… không phụ thuộc địa giới hành chính", "Cổng TTĐT Chính phủ – Chính sách và cuộc sống (xaydungchinhsach.chinhphu.vn)", "2027-03-01", (0, 999), ALL39, "manual",
     "relevance: Luật Hộ tịch (sửa đổi) thông qua 23/4/2026, hiệu lực 01/3/2027 (trừ lộ trình riêng); thay đổi nguyên tắc nơi đăng ký cho mọi thủ tục hộ tịch. Thông tin về luật tương lai: chưa áp dụng trước 01/3/2027."),
    ("docs/xdcs-luat-ht-sua-doi-hieu-luc-2027.htm", "change_notice", "change:xdcs:luat-ho-tich-2026-hieu-luc-01-03-2027", "Luật Hộ tịch (sửa đổi) có hiệu lực thi hành từ 01/3/2027", "Cổng TTĐT Chính phủ – Chính sách và cuộc sống (xaydungchinhsach.chinhphu.vn)", "2027-03-01", (0, 999), ALL39, "manual",
     "relevance: Quốc hội thông qua Luật Hộ tịch (sửa đổi) 23/4/2026, hiệu lực 01/3/2027; toàn bộ thủ tục hộ tịch hiện hành sẽ thay đổi từ ngày đó. Chưa áp dụng trước 01/3/2027."),
    ("docs/xdcs-qd-moi-dkks-duoi-6-tuoi-2026.htm", "change_notice", "change:xdcs:nd301-2026-lien-thong-khai-sinh-duoi-6-tuoi", "QUY ĐỊNH MỚI về đăng ký khai sinh, thường trú, cấp thẻ bảo hiểm y tế cho trẻ em dưới 6 tuổi từ tháng 9/2026", "Cổng TTĐT Chính phủ – Chính sách và cuộc sống (xaydungchinhsach.chinhphu.vn)", "2026-09-01", (0, 999), ["1.001193"], "manual",
     "relevance: NĐ 301/2026/NĐ-CP (30/07/2026) sửa đổi NĐ 63/2024/NĐ-CP về liên thông đăng ký khai sinh – thường trú – BHYT cho trẻ dưới 6 tuổi (thời hạn không quá 3 ngày làm việc). effective_date 2026-09-01 theo NĐ 301/2026/NĐ-CP Điều 19 khoản 1 (văn bản gốc PDF datafiles.chinhphu.vn, data/raw/moj/docs/nd-301-2026.pdf)."),
    ("docs/xdcs-qd-moi-dkks-ho-tro-sinh-con.htm", "change_notice", "change:xdcs:nd301-2026-khai-sinh-ho-tro-sinh-con", "QUY ĐỊNH MỚI về đăng ký khai sinh; chi trả hỗ trợ tài chính cho phụ nữ sinh con", "Cổng TTĐT Chính phủ – Chính sách và cuộc sống (xaydungchinhsach.chinhphu.vn)", "2026-09-01", (0, 999), ["1.001193"], "manual",
     "relevance: NĐ 301/2026/NĐ-CP sửa Điều 8 NĐ 63/2024/NĐ-CP: giải quyết hồ sơ đăng ký khai sinh trong nhóm thủ tục liên thông. effective_date 2026-09-01 theo NĐ 301/2026/NĐ-CP Điều 19 khoản 1 (văn bản gốc PDF datafiles.chinhphu.vn)."),
    ("docs/xdcs-mau-to-khai-lien-thong-duoi-6-tuoi.htm", "form", "form:xdcs:nd301-2026-to-khai-lien-thong-khai-sinh-duoi-6-tuoi", "Mẫu Tờ khai điện tử liên thông đăng ký khai sinh, thường trú, cấp thẻ bảo hiểm y tế, căn cước công dân cho trẻ em dưới 6 tuổi (NĐ 301/2026/NĐ-CP)", "Cổng TTĐT Chính phủ – Chính sách và cuộc sống (xaydungchinhsach.chinhphu.vn)", None, (0, 999), ["1.001193"], "manual",
     "relevance: mẫu tờ khai điện tử liên thông dùng khi đăng ký khai sinh cho trẻ dưới 6 tuổi qua Cổng DVC (Mẫu số 01 thay thế theo NĐ 301/2026/NĐ-CP Điều 17). Nội dung lấy từ bài giới thiệu trên xaydungchinhsach.chinhphu.vn, không phải bản phụ lục gốc."),
    ("docs/xdcs-hd-dkks-dvcqg-2023.htm", "guidance", "guide:xdcs:lien-thong-khai-sinh-dvcqg-2023", "Hướng dẫn đăng ký khai sinh, thường trú, cấp thẻ BHYT cho trẻ em dưới 6 tuổi trên Cổng DVCQG", "Cổng TTĐT Chính phủ – Chính sách và cuộc sống (xaydungchinhsach.chinhphu.vn)", None, (0, 999), ["1.001193"], "manual",
     "relevance: hướng dẫn từng bước nộp hồ sơ liên thông khai sinh trên lienthong.dichvucong.gov.vn. Bài năm 2023: quy trình có thể đã thay đổi theo NĐ 63/2024 và NĐ 301/2026."),
    ("docs/xdcs-khong-yc-ban-sao-cccd-2023.htm", "guidance", "guide:xdcs:khong-yeu-cau-ban-sao-cccd-lien-thong-khai-sinh-2023", "Không yêu cầu người dân cung cấp bản sao Căn cước công dân khi làm thủ tục liên thông Đăng ký khai sinh", "Cổng TTĐT Chính phủ – Chính sách và cuộc sống (xaydungchinhsach.chinhphu.vn)", None, (0, 999), ["1.001193"], "manual",
     "relevance: chỉ đạo của Chính phủ (NQ 124/NQ-CP, 2023) không yêu cầu bản sao CCCD khi liên thông đăng ký khai sinh. Bài năm 2023."),
    ("docs/xdcs-hd-dang-ky-ket-hon-2022.htm", "guidance", "guide:xdcs:thu-tuc-dang-ky-ket-hon-2022", "HƯỚNG DẪN: Thủ tục đăng ký kết hôn", "Cổng TTĐT Chính phủ – Chính sách và cuộc sống (xaydungchinhsach.chinhphu.vn)", None, (0, 999), ["1.000894"], "manual",
     "relevance: hướng dẫn của Bộ Tư pháp về cách thức, thành phần hồ sơ, thời hạn đăng ký kết hôn trong nước. Bài năm 2022 (trước NĐ 07/2025 và cải cách 01/07/2025): hồ sơ, thẩm quyền cần đối chiếu bản ghi thủ tục hiện hành."),
    ("docs/xdcs-thi-diem-dkks-benh-vien.htm", "guidance", "guide:xdcs:hanoi-thi-diem-khai-sinh-tai-benh-vien-2026", "Thí điểm hỗ trợ ĐĂNG KÝ KHAI SINH tại bệnh viện", "Cổng TTĐT Chính phủ – Chính sách và cuộc sống (xaydungchinhsach.chinhphu.vn)", None, (0, 999), ["1.001193"], "manual",
     "relevance: Hà Nội (CV 4996/UBND-NC ngày 30/9/2026) thí điểm hỗ trợ đăng ký khai sinh tại Bệnh viện Phụ sản Hà Nội; chỉ áp dụng tại Hà Nội."),
]


def meta_of(idx, rel):
    m = idx[rel]
    return m["url"], m["fetched_at"][:10], m["sha256"]


def build_pages(idx):
    n = 0
    for rel, kind, doc_id, title, issuer, eff, (a, b), pids, how, notes in PAGES:
        paras = [p for p in main_paras(RAW / rel)[a:b] if p not in ("Ảnh minh họa",)]
        if "/xdcs-" in rel:  # cut the "Tham khảo thêm" related-article box and the link titles just before it
            k = next((i for i, p in enumerate(paras) if p.startswith("Tham khảo thêm")), len(paras))
            paras = paras[:k]
            while paras and len(paras[-1]) < 160 and not re.search(r"[.:;)]$", paras[-1]):
                paras.pop()
        url, ret, sha = meta_of(idx, rel)
        write({"doc_id": doc_id, "kind": kind, "title": title, "issuer": issuer, "effective_date": eff,
               "jurisdiction": "Hà Nội" if "hanoi" in doc_id else None,
               "url": url, "retrieved_at": ret, "sha256": sha, "procedure_ids": sorted(set(pids)), "link_method": how,
               "sections": by_heading(paras, title), "notes": notes})
        n += 1
    return n


def pdf_text(rel):
    return nfc(subprocess.run(["pdftotext", str(RAW / rel), "-"], capture_output=True, text=True, check=True).stdout)


def build_pdfs(idx):
    n = 0
    # guidance: Sở Tư pháp Kiên Giang (nay An Giang) CV 616/STP-HC&BTTP 06/03/2025, hướng dẫn NĐ 07/2025 theo CV 268/HTQTCT-HT của Cục HTQTCT
    rel = "docs/gd-angiang-trienkhai-nd07.pdf"
    t = pdf_text(rel)
    t = re.sub(r"\n\d\n", "\n", t)  # page numbers
    body = t[t.index("1. Tra cứu thông tin"): t.index("Nơi nhận:")]
    parts = re.split(r"\n(?=[1-5]\. )", "\n" + body)
    secs = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        lines = [re.sub(r"\s+", " ", x).strip() for x in p.split("\n")]
        text = re.sub(r"(?<![.:;])\n(?![-+(]|\d\. )", " ", "\n".join(x for x in lines if x))
        secs.append({"heading": text.split(" ", 1)[0] + " " + text[:90].split(" ", 1)[1].rsplit(" ", 1)[0] + " …", "text": text})
    url, ret, sha = meta_of(idx, rel)
    write({"doc_id": "guide:kiengiang-stp:cv616-2025-nd07", "kind": "guidance",
           "title": "Công văn 616/STP-HC&BTTP ngày 06/3/2025 của Sở Tư pháp Kiên Giang hướng dẫn triển khai Nghị định 07/2025/NĐ-CP (hộ tịch)",
           "issuer": "Sở Tư pháp tỉnh Kiên Giang", "effective_date": "2025-03-06", "jurisdiction": "Kiên Giang (nay thuộc An Giang)",
           "url": url, "retrieved_at": ret, "sha256": sha,
           "procedure_ids": sorted(set(KH + KH_N + KS + KT + XNHN)), "link_method": "manual", "sections": secs,
           "notes": "relevance: hướng dẫn tra cứu tình trạng hôn nhân khi đăng ký kết hôn/cấp GXNTTHN, tra cứu Giấy chứng nhận kết hôn của cha mẹ khi khai sinh, "
                    "Giấy chứng sinh/Giấy báo tử điện tử khi khai sinh/khai tử (NĐ 07/2025/NĐ-CP Điều 2; CV 268/HTQTCT-HT của Cục Hộ tịch, quốc tịch, chứng thực). "
                    "Văn bản cấp tỉnh trước 01/07/2025 (gửi Phòng Tư pháp cấp huyện); nội dung nghiệp vụ còn dùng được, thẩm quyền cấp huyện đã chuyển cho cấp xã."})
    n += 1
    # fee_resolution: NQ 24/2024/NQ-HĐND Đắk Lắk, as summarised in Sở Tư pháp Đắk Lắk Thông cáo báo chí 01/TCBC-STP (02/01/2025)
    rel = "docs/fee-daklak-tc-stp-02012025.pdf"
    t = pdf_text(rel)
    i = t.index("1.18. Nghị quyết số 24/2024/NQ-HĐND")
    j = t.index("1.19. Nghị quyết số 25/2024/NQ-HĐND")
    body = re.sub(r"\n\d{1,2}\n", "\n", t[i:j]).strip()
    body = re.sub(r"(?<![.:;])\n(?!Điều \d|[a-z]\) )", " ", body)
    nq24 = sorted(json.loads(f.read_text(encoding="utf-8"))["procedure_id"] for f in (ROOT / "data/processed/daklak").glob("*.json")
                  if "24/2024" in json.dumps(json.loads(f.read_text(encoding="utf-8"))["legal_basis"], ensure_ascii=False))
    url, ret, sha = meta_of(idx, rel)
    write({"doc_id": "fee:daklak:nq-24-2024-hdnd:tcbc-stp", "kind": "fee_resolution",
           "title": "Nghị quyết số 24/2024/NQ-HĐND ngày 06/12/2024 của HĐND tỉnh Đắk Lắk quy định thu phí, lệ phí thuộc thẩm quyền quyết định của HĐND tỉnh (tóm tắt trong Thông cáo báo chí 01/TCBC-STP)",
           "issuer": "HĐND tỉnh Đắk Lắk (tóm tắt: Sở Tư pháp Đắk Lắk)", "effective_date": "2024-12-16", "jurisdiction": "Đắk Lắk",
           "url": url, "retrieved_at": ret, "sha256": sha, "procedure_ids": nq24, "link_method": "legal_basis",
           "sections": [{"heading": "Nghị quyết số 24/2024/NQ-HĐND (mục 1.18 Thông cáo báo chí 01/TCBC-STP ngày 02/01/2025)", "text": body}],
           "notes": "relevance: căn cứ phí/lệ phí trong Phụ lục 33/QĐ-UBND Đắk Lắk cho các thủ tục này. Chỉ có tóm tắt: hiệu lực 16/12/2024, Điều 19 \"Lệ phí hộ tịch\", "
                    "thay thế NQ 08/2022 và 08/2023. KHÔNG có mức thu; toàn văn NQ chưa lấy được (link vbpl.vn cũ trả 404)."})
    n += 1
    return n


if __name__ == "__main__":
    idx = index()
    print("pages:", build_pages(idx), "pdfs:", build_pdfs(idx))


# ---------------------------------------------------------------- form: Phụ lục 5, Thông tư 04/2024/TT-BTP (Công báo 739–742/2024)
FORMS = [  # (danh mục no., procedure_ids)
    (1, KS + KS_N + BG["ks"]), (2, KH + KH_N + BG["kh"]), (3, KT + KT_N + BG["kt"]), (4, GH + GH_N), (5, CDGH + CDGH_N),
    (6, CMC + CMC_N + BG["cmc"]), (7, GC_KHAC), (8, GC_KH), (9, GC_LH), (10, GC_KHAC), (11, GC_KHAC), (12, GC_KHAC), (13, GC_KHAC),
    (14, ["1.004884", "2.000522"]), (15, ["1.004746", "2.000513"]), (16, ["1.005461", "2.000497"]), (17, TD + TD_N),
    (18, BANSAO), (19, XNHN), (20, KS + KH + XNHN + LAI),
]
FORM_FILES = ["docs/congbao-tt04-2024-1.doc", "docs/congbao-tt04-2024-3.doc"]


def clean_form_line(l):
    l = re.sub(r"\.{4,}|…{2,}", "…", l.replace("\t", " "))
    return re.sub(r"\s+", " ", l).strip()


def build_forms(idx):
    lines, origin = [], []
    for k, rel in enumerate(FORM_FILES):
        ls = to_text(rel).splitlines()
        if k == 0:
            ls = ls[next(i for i, l in enumerate(ls) if l.strip() == "Phụ lục 5"):]
        lines += ls
        origin += [rel] * len(ls)
    # danh mục names, in order
    i0 = next(i for i, l in enumerate(lines) if l.strip() == "Tên Tờ khai")
    names = []
    for l in lines[i0 + 1:]:
        s = l.strip()
        if s.startswith("Lưu ý"):
            break
        if s and not s.isdigit():
            names.append(s)
    assert len(names) == 20, names
    heads = [i for i, l in enumerate(lines) if i > i0 and (l.strip().startswith("TỜ KHAI") or l.strip() == "BẢN CAM ĐOAN")]
    assert len(heads) == 20, len(heads)
    n = 0
    for j, (no, pids) in enumerate(FORMS):
        a = heads[j]
        b = heads[j + 1] if j + 1 < len(heads) else len(lines)
        body = lines[a:b]
        # drop the next form's "CỘNG HÒA … / Độc lập …" header block at the end
        while body and (not body[-1].strip() or body[-1].strip().startswith(("CỘNG HÒA XÃ HỘI", "Độc lập - Tự do"))):
            body.pop()
        heading = clean_form_line(body[0])
        k = 1
        if heading in ("TỜ KHAI",):
            heading += " " + clean_form_line(body[1])
            k = 2
        txt = [clean_form_line(l) for l in body[k:]]
        txt = [t for t in txt if t]
        cut = next((i for i, t in enumerate(txt) if t.startswith("Chú thích")), len(txt))
        secs = [{"heading": heading, "text": "\n".join(txt[:cut])}]
        if cut < len(txt):
            secs.append({"heading": "Chú thích (hướng dẫn ghi Tờ khai)", "text": "\n".join(txt[cut + 1:]) or txt[cut]})
        rel = origin[a]
        m = idx[rel]
        slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFD", names[j].lower().replace("đ", "d")).encode("ascii", "ignore").decode()).strip("-")
        write({
            "doc_id": f"form:04-2024-TT-BTP:pl5-{no:02d}-{slug}",
            "kind": "form",
            "title": f"Mẫu {names[j]} (Phụ lục 5, Thông tư 04/2024/TT-BTP)",
            "issuer": "Bộ Tư pháp",
            "effective_date": "2024-06-06",
            "jurisdiction": None,
            "url": m["url"],
            "retrieved_at": m["fetched_at"][:10],
            "sha256": m["sha256"],
            "procedure_ids": sorted(set(pids)),
            "link_method": "manual",
            "sections": secs,
            "notes": f"relevance: tờ khai số {no} trong Danh mục Phụ lục 5 (Tờ khai đăng ký hộ tịch được đăng tải trên Cổng TTĐT Bộ Tư pháp, người dân tự in) "
                     f"dùng cho các thủ tục này. Nguồn: Công báo (congbao.chinhphu.vn), bản Word. Dấu chấm dẫn dòng được rút gọn thành \"…\". "
                     f"Thay thế Phụ lục Tờ khai của Thông tư 04/2020/TT-BTP từ 06/6/2024; chưa kiểm tra mẫu có bị thay đổi sau 01/07/2025 hay không.",
        })
        n += 1
    return n


if __name__ == "__main__":
    print("forms:", build_forms(index()))


# ---------------------------------------------------------------- legal_text: Thông tư 08/2025/TT-BTP (current, Công báo 835–836/2025)
TT08 = {2: (CORE, "nguyên tắc khai thác, sử dụng dữ liệu điện tử khi đăng ký hộ tịch"),
        3: (ALL39, "thẩm quyền, trình tự, thủ tục đăng ký hộ tịch của UBND cấp xã từ 01/07/2025"),
        4: (ALL39, "tiếp nhận hồ sơ và trả kết quả đăng ký hộ tịch (bản sao, bản chụp, VNeID; trả kết quả kết hôn)"),
        5: (GC_KH + GC_LH + GC_KHAC + CMC, "cách ghi Sổ, giấy tờ hộ tịch (ghi chú việc hộ tịch giải quyết ở nước ngoài)"),
        6: (CORE, "xóa dữ liệu hộ tịch điện tử"),
        23: (ALL39, "hiệu lực: từ 01/07/2025, hết hiệu lực từ 01/03/2027 (trừ trường hợp kéo dài)")}


def build_tt08(idx):
    rel = "docs/congbao-tt08-2025-1.doc"
    m = idx[rel]
    arts = articles(to_text(rel).splitlines())
    n = 0
    for num, (pids, reason) in TT08.items():
        h, body = arts[num]
        write({"doc_id": f"legal:08-2025-TT-BTP:dieu-{num}", "kind": "legal_text",
               "title": f"Thông tư 08/2025/TT-BTP, Điều {num}", "issuer": "Bộ Tư pháp", "effective_date": "2025-07-01", "jurisdiction": None,
               "url": m["url"], "retrieved_at": m["fetched_at"][:10], "sha256": m["sha256"],
               "procedure_ids": sorted(set(pids)), "link_method": "legal_basis", "original_version": False,
               "sections": [{"heading": h.strip(), "text": body}],
               "notes": f"relevance: {reason}; Thông tư 08/2025/TT-BTP is cited in legal_basis of these procedures. Nguồn: Công báo (congbao.chinhphu.vn), bản Word. "
                        "Văn bản đang có hiệu lực tại thời điểm thu thập; tự hết hiệu lực từ 01/03/2027 (Điều 23). Chưa kiểm tra văn bản sửa đổi sau ngày ban hành."})
        n += 1
    return n


if __name__ == "__main__":
    print("tt08:", build_tt08(index()))


# ---------------------------------------------------------------- change_notice link scoping (lead, round 4): keep a link only if the notice
# names the procedure ("named") or changes the instrument governing that procedure's family ("instrument_scope").
TITLES = {json.loads(f.read_text(encoding="utf-8"))["procedure_id"]: json.loads(f.read_text(encoding="utf-8"))["title"]
          for f in (ROOT / "data/processed/daklak").glob("*.json")}
MOVED = sorted(set(KS_N + KH_N + KT_N + GH_N + CDGH_N + CMC_N + TD_N + GC_KH + GC_LH + GC_KHAC + LAI_N))  # cấp huyện → cấp xã (NĐ 120/2025 Điều 4)
K2 = ["1.001193", "1.000656", "1.001022", "1.004837", "1.004845", "3.000323", "3.000322", "1.004859"]  # named in NĐ 120/2025 Điều 5 khoản 2
R_MOVED = "instrument_scope: thẩm quyền chuyển từ UBND cấp huyện sang UBND cấp xã theo NĐ 120/2025/NĐ-CP Điều 4 (khoản 2 Điều 7 Luật Hộ tịch; NĐ 123/2015 Điều 29–42)"
R_K2 = "named: thủ tục được nêu tên trong NĐ 120/2025/NĐ-CP Điều 5 khoản 2 (không phải có mặt để ký Sổ hộ tịch)"
SCOPE = {
    "change:nghean-hcc:nd120-2025-ho-tich":
        [(p, "instrument_scope", R_MOVED) for p in MOVED]
        + [(p, "instrument_scope", "instrument_scope: thẩm quyền khai thác CSDL hộ tịch điện tử, xác nhận thông tin hộ tịch theo NĐ 87/2020/NĐ-CP Điều 8, được NĐ 120/2025 Điều 4 phân định") for p in ["2.002516", "2.000635"]]
        + [(p, "named", R_K2) for p in K2],
    "change:cantho-pbgdpl:thu-tuc-ho-tich-tu-01-07-2025":
        [(p, "instrument_scope", R_MOVED) for p in MOVED]
        + [("1.001022", "named", "named: bài nêu thời hạn giải quyết thủ tục đăng ký nhận cha, mẹ, con (10 ngày làm việc)")],
    "change:hatinh:linh-hoat-noi-dang-ky-ho-tich":
        [(p, "named", "named: bài nêu tên thủ tục (đăng ký khai sinh, kết hôn, giám hộ, khai tử, cải chính hộ tịch) khi nói về quyền chọn nơi đăng ký, NĐ 120/2025 Điều 5 khoản 1")
         for p in ["1.001193", "1.000894", "1.004837", "1.000656", "1.004859"]]
        + [(p, "named", R_K2) for p in ["1.001022", "1.004845", "3.000323", "3.000322"]],
    "change:xdcs:luat-ho-tich-2026-hieu-luc-01-03-2027":
        [(p, "instrument_scope", "instrument_scope: Luật Hộ tịch (sửa đổi) 2026 thay thế Luật Hộ tịch 60/2014/QH13, văn bản gốc của thủ tục này") for p in ALL39],
    "change:xdcs:luat-ho-tich-2026-khong-phu-thuoc-dia-gioi":
        [(p, "instrument_scope", "instrument_scope: Luật Hộ tịch (sửa đổi) 2026 thay thế Luật Hộ tịch 60/2014/QH13, văn bản gốc của thủ tục này") for p in ALL39],
}


def scope_links():
    before = after = 0
    for doc_id, links in SCOPE.items():
        f = OUT / "change_notice" / (re.sub(r"[^A-Za-z0-9._-]+", "_", doc_id) + ".json")
        rec = json.loads(f.read_text(encoding="utf-8"))
        before += len(rec["procedure_ids"])
        seen = {}
        for p, how, why in links:
            seen.setdefault(p, (how, why))
        assert set(seen) <= set(TITLES), set(seen) - set(TITLES)
        rec["procedure_ids"] = sorted(seen)
        methods = {how for how, _ in seen.values()}
        rec["link_method"] = "instrument_scope" if "instrument_scope" in methods else "named"
        base = rec["notes"].split(" | links:")[0]
        rec["notes"] = base + " | links: " + "; ".join(f"{p} ({TITLES[p][:60]}): {seen[p][1]}" for p in sorted(seen))
        after += len(rec["procedure_ids"])
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return before, after


if __name__ == "__main__":
    print("change_notice links before/after (5 docs):", scope_links())
