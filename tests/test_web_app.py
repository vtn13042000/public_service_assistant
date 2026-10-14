"""Web UI backend (src/web/app.py) on fakes: one test per outcome, the clarify follow-up, and the wiring."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.callbacks import BaseCallbackHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.presets import DEFAULT_PRESET, graph_config  # noqa: E402
from src.web import app as web  # noqa: E402
from tests.fakes import PROCEDURES, TODAY, FakeDB, FakeLLM, FakeRAG, FakeWeb, need  # noqa: E402

KN = "Đăng ký khai sinh trong nước lần đầu cần giấy tờ gì?"
# v3+ (base_title_preference) answers a bare "đăng ký khai sinh" for the base; a said qualifier keeps the tie
AMBIG = "Con tôi có mẹ là người nước ngoài, hồ sơ đăng ký khai sinh?"


def client(llm, db=None, rag=None, web_=None, tracer=None) -> TestClient:
    deps = {"llm": llm, "retriever": rag or FakeRAG(), "db": db or FakeDB(),
            "web": web_ if web_ is not None else FakeWeb(),
            "trace": lambda *a, **k: None, "graph_kw": {"today": TODAY}}
    return TestClient(web.create_app(deps, tracer=tracer, tracing=False))


def ask(c, query, **kw):
    r = c.post("/ask", json={"query": query, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_index_served():
    c = client(FakeLLM())
    r = c.get("/")
    assert r.status_code == 200 and "Trợ lý thủ tục hành chính" in r.text and 'id="variant"' in r.text


def test_answer():
    d = ask(client(FakeLLM(need=need("documents", "đăng ký khai sinh trong nước lần đầu"))), KN)
    assert d["outcome"] == "answer" and d["procedure_id"] == "KS-01"
    assert "Giấy chứng sinh" in d["generation"] and d["citations"]
    assert {"evidence_id", "source_url", "retrieved_at"} <= set(d["citations"][0])
    assert d["refusal"] is None and d["candidates"] == []
    assert d["variant"] == "guardrailed" and d["latency_s"] >= 0 and d["trace_id"] is None
    assert d["preset"] == DEFAULT_PRESET


def test_answer_partial_has_gap_section():
    procs = {k: dict(v) for k, v in PROCEDURES.items()}
    for pid in ("KS-01", "KS-02", "KS-03"):
        procs[pid]["fees"] = []
    d = ask(client(FakeLLM(need=need("fee", "đăng ký khai sinh")), db=FakeDB(procedures=procs)), "Lệ phí khai sinh?")
    assert d["outcome"] == "answer_partial" and "Không tìm thấy căn cứ về: lệ phí" in d["generation"]
    assert d["gaps"]


def test_clarify_lists_candidates():
    d = ask(client(FakeLLM(need=need("documents", "đăng ký khai sinh"))), AMBIG)
    assert d["outcome"] == "clarify" and d["refusal"]["type"] == "ambiguous"
    ids = [c["procedure_id"] for c in d["candidates"]]
    assert "KS-01" in ids and all(c["title"] for c in d["candidates"])


def test_clarify_follow_up_with_procedure_id():
    c = client(FakeLLM(need=need("documents", "đăng ký khai sinh")))
    first = ask(c, AMBIG)
    assert first["outcome"] == "clarify"
    pick = next(x for x in first["candidates"] if x["procedure_id"] == "KS-01")
    second = ask(c, AMBIG, procedure_id=pick["procedure_id"])
    assert second["outcome"] in ("answer", "answer_partial") and second["procedure_id"] == "KS-01"
    assert second["candidates"] == []


def test_refuse_not_in_corpus_has_redirect():
    d = ask(client(FakeLLM(need=need("general", "nhập quốc tịch"))), "Nhập tịch?")
    assert d["outcome"] == "refuse" and d["refusal"]["type"] == "not_in_corpus"
    assert d["refusal"]["portal_url"] == "https://dichvucong.gov.vn/p/nhap-quoc-tich"


def test_refuse_system_error():
    d = ask(client(FakeLLM(need=need("documents", "đăng ký khai sinh trong nước lần đầu")), rag=FakeRAG(fail=True)), KN)
    assert d["outcome"] == "refuse" and d["refusal"]["type"] == "system_error" and d["errors"]


def test_out_of_scope():
    d = ask(client(FakeLLM(need=need(in_scope=False))), "Xin chào")
    assert d["outcome"] == "out_of_scope" and d["generation"]


def test_locality_passed_to_state():
    d = ask(client(FakeLLM(need=need("fee", "cấp lại thẻ căn cước"))), "Lệ phí cấp lại căn cước?", locality="Hà Nội")
    assert d["outcome"] in ("answer", "answer_partial") and d["procedure_id"] == "CCCD-02"
    assert "70.000" in d["generation"]


def test_baseline_variant_runs():
    d = ask(client(FakeLLM(need=need("documents", "đăng ký khai sinh trong nước lần đầu"), narrative="Cần tờ khai.")),
            KN, variant="baseline")
    assert d["variant"] == "baseline" and d["preset"] == "baseline" and d["outcome"] in ("answer", "refuse")


def test_trace_id_and_model_calls(monkeypatch):
    class FakeHandler(BaseCallbackHandler):
        last_trace_id = "abc123"

    seen = []
    monkeypatch.setattr(web, "trace_url", lambda tid: f"http://127.0.0.1:3000/trace/{tid}")
    monkeypatch.setattr(web, "_flush", lambda: None)
    c = client(FakeLLM(need=need(in_scope=False)), tracer=lambda name, variant, preset: seen.append((variant, preset)) or FakeHandler())
    d = ask(c, "Xin chào")
    assert d["trace_id"] == "abc123" and d["trace_url"].endswith("/trace/abc123")
    assert isinstance(d["model_calls"], int) and seen == [("guardrailed", DEFAULT_PRESET)]


@pytest.mark.parametrize("body", [{"query": "  "}, {"query": "x", "variant": "nope"}])
def test_bad_requests_rejected(body):
    assert client(FakeLLM()).post("/ask", json=body).status_code == 422


def test_guardrailed_graph_runs_the_default_preset(monkeypatch):
    """build_apps passes the default preset's flags (src/presets.py) and the invoke input carries its name (recorded by assess_need)."""
    import src.graph
    got, spans = {}, []
    real = src.graph.build_graph

    def spy(*a, **k):
        got["config"] = k.get("config")
        return real(*a, **k)

    monkeypatch.setattr(src.graph, "build_graph", spy)
    deps = {"llm": FakeLLM(need=need(in_scope=False)), "retriever": FakeRAG(), "db": FakeDB(), "web": FakeWeb(),
            "trace": lambda name, **m: spans.append((name, m)), "graph_kw": {"today": TODAY}}
    c = TestClient(web.create_app(deps, tracing=False))
    assert got["config"] == graph_config(DEFAULT_PRESET)
    ask(c, "Xin chào")
    assert ("assess_need", DEFAULT_PRESET) in [(n, m.get("preset")) for n, m in spans]
    assert c.get("/presets").json() == {"guardrailed": DEFAULT_PRESET, "baseline": "baseline"}


# ---------------------------------------------------------------- UI v2: structured parts and the five labels

def test_answer_parts_split_without_changing_text():
    """parts are lines of `generation`: block sections by property, narrative, notices; generation itself unchanged."""
    from src.web.structure import answer_parts
    d = ask(client(FakeLLM(need=need("general", "đăng ký khai sinh trong nước lần đầu"),
                           narrative="Người đi đăng ký nộp tờ khai [doc:KS-01:steps:0].")),
            "Thủ tục khai sinh trong nước lần đầu?", procedure_id="KS-01")
    p = d["parts"]
    assert d["outcome"] == "answer" and p["procedure"] == {"id": "KS-01", "title": "Đăng ký khai sinh"}
    kinds = [s["kind"] for s in p["sections"]]
    assert kinds[:1] == ["documents"] and {"agency", "time"} <= set(kinds)
    docs = p["sections"][0]
    assert [i["cites"] for i in docs["items"]] == [["db:required_documents:KS-01:1"], ["db:required_documents:KS-01:2"]]
    assert p["narrative"].startswith("Người đi đăng ký nộp tờ khai")
    for item in (i["text"] for s in p["sections"] for i in s["items"]):
        assert item in d["generation"]
    for para in p["notices"] + p["notes"] + [p["narrative"]]:
        assert para in d["generation"]
    assert answer_parts({"outcome": "refuse"}) is None


def test_partial_parts_put_the_gap_first():
    procs = {k: dict(v) for k, v in PROCEDURES.items()}
    for pid in ("KS-01", "KS-02", "KS-03"):
        procs[pid]["fees"] = []
    d = ask(client(FakeLLM(need=need("fee", "đăng ký khai sinh")), db=FakeDB(procedures=procs)), "Lệ phí khai sinh?")
    p = d["parts"]
    assert d["outcome"] == "answer_partial" and p["gap_text"].startswith("Không tìm thấy căn cứ về: lệ phí")
    assert p["gap_text"] in d["generation"] and p["gaps"][0]["kind"] == "missing"


def test_non_answers_have_no_parts_and_refusal_keeps_reason_fields():
    c = client(FakeLLM(need=need("general", "nhập quốc tịch")))
    d = ask(c, "Nhập tịch?")
    assert d["parts"] is None and d["refusal"]["type"] == "not_in_corpus"
    assert {"reason", "missing", "title", "procedure_id"} <= set(d["refusal"]) and "unsupported_claims" not in d["refusal"]


def test_page_has_the_five_labels_and_legend():
    html = client(FakeLLM()).get("/").text
    for key, name in (("answer", "Trả lời có nguồn"), ("answer_partial", "Trả lời một phần"), ("clarify", "Cần làm rõ"),
                      ("refuse", "Từ chối và chuyển tuyến"), ("out_of_scope", "Ngoài phạm vi")):
        assert f"{key}: {{ name: \"{name}\"" in html, key
    for reason in ("không có trong kho", "không đủ căn cứ", "đã dừng thực hiện", "lỗi hệ thống"):
        assert reason in html
    assert 'id="legend"' in html and "Vì sao tin được" in html
    assert "Trả lời đầy đủ" not in html and "như trả lời có nguồn" in html  # QC: no over-claim (AUDIT-LEAD2-1)
    for reason in ("not_in_corpus", "insufficient_evidence", "discontinued", "system_error"):
        assert f"  {reason}: \"" in html.split("const REFUSE_MEANING")[1].split("};")[0], reason
    assert "Không trả lời; lý do và nơi cần đến ghi dưới đây." in html


# ---------------------------------------------------------------- "Thủ tục" tab: /procedures and /procedures/{code}

def _real_db():
    from src.tools.db import db_path
    if not db_path().is_file():
        pytest.skip("data/app.db not built")


def test_procedure_list_is_complete_and_linked():
    _real_db()
    llm = FakeLLM()
    c = client(llm)
    d = c.get("/procedures").json()
    assert d["count"] == 57 == len(d["procedures"])
    assert all(p["sources"] and all(s["url"].startswith("http") for s in p["sources"]) for p in d["procedures"])
    stopped = {p["code"]: p["status"] for p in d["procedures"] if p["status"]}
    assert stopped["2.001178"]["status"] == "discontinued" and "58/2026" in stopped["2.001178"]["basis"]
    assert all("documents" not in p and "fees" not in p for p in d["procedures"])  # compact: no section texts
    assert all(set(p["change_notice"]) == {"in_force", "upcoming"} for p in d["procedures"])
    assert sum(p["provincial_only"] for p in d["procedures"]) == 2
    fam = {p["code"]: p["family"] for p in d["procedures"]}
    assert fam["1.001193"] == "Khai sinh" and fam["2.000635"] == "Khai sinh" and fam["1.004845"] == fam["1.004837"] == "Giám hộ"
    assert fam["2.002516"] is None  # no family noun in the title → the page's "Khác"
    assert llm.prompts == []  # no model call


def test_procedure_detail_has_a_source_for_every_value():
    _real_db()
    llm = FakeLLM()
    c = client(llm)
    d = c.get("/procedures/1.001193").json()
    assert d["code"] == "1.001193" and d["documents"] and d["fees"] and d["place"] and d["deadline"]
    for key in ("documents", "fees", "place", "legal_basis"):
        assert all(x["source_url"] and x["source_url"].startswith("http") for x in d[key]), key
    assert d["deadline"]["source_url"].startswith("http")
    assert all(x["url"] for x in d["depth_documents"]) and {x["kind"] for x in d["depth_documents"]} >= {"legal_text"}
    assert c.get("/procedures/9.999999").status_code == 404
    assert llm.prompts == []


def test_page_has_the_procedures_tab():
    html = client(FakeLLM()).get("/").text
    assert 'id="tab-procs"' in html and "/procedures/" in html
    assert "Đây là toàn bộ thủ tục trợ lý có thể trả lời; câu hỏi ngoài danh sách này sẽ được từ chối và chuyển hướng." in html


def test_procedure_groups_collapsed_and_filter_opens_only_matches():
    """Runs the page's pure groupState() (between the <group-state> markers in index.html) under node."""
    import json
    import re
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("node not installed")
    html = (Path(__file__).resolve().parents[1] / "src/web/static/index.html").read_text(encoding="utf-8")
    fn = re.search(r"// <group-state>.*?\n(.*?)// </group-state>", html, re.S).group(1)
    fold_src = re.search(r"const fold = (.*?);\n", html).group(1)
    procs = [{"code": "A", "title": "Đăng ký khai sinh", "field": "Hộ tịch", "provincial_only": False},
             {"code": "B", "title": "Đăng ký kết hôn", "field": "Hộ tịch", "provincial_only": False},
             {"code": "C", "title": "Cấp lại thẻ căn cước", "field": "Cấp, quản lý căn cước", "provincial_only": False},
             {"code": "D", "title": "Khai sinh lưu động", "field": "Hộ tịch", "provincial_only": True}]
    js = fn + f"""
const fold = {fold_src};
const P = {json.dumps(procs, ensure_ascii=False)};
const F = ["Hộ tịch", "Cấp, quản lý căn cước", "Đăng ký, quản lý cư trú"];
const out = {{}};
for (const q of ["", "khai sinh"]) out[q] = groupState(P, fold(q), fold, F, "Đắk Lắk").map((g) => [g.label, g.open, g.rows.length]);
console.log(JSON.stringify(out));"""
    res = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert res[""] == [["Hộ tịch (2)", False, 2], ["Cấp, quản lý căn cước (1)", False, 1], ["Đắk Lắk (1)", False, 1]]
    assert res["khai sinh"] == [["Hộ tịch (1 / 2)", True, 1], ["Cấp, quản lý căn cước (0 / 1)", False, 0], ["Đắk Lắk (1 / 1)", True, 1]]

    # second level: a group of more than 10 rows splits by `family` (size, then name; "Khác" last); filter opens only matches
    big = ([{"code": f"K{i}", "title": f"Đăng ký khai sinh {i}", "field": "Hộ tịch", "provincial_only": False, "family": "Khai sinh"}
            for i in range(6)]
           + [{"code": f"H{i}", "title": f"Đăng ký kết hôn {i}", "field": "Hộ tịch", "provincial_only": False, "family": "Kết hôn"}
              for i in range(4)]
           + [{"code": "X", "title": "Xác nhận thông tin hộ tịch", "field": "Hộ tịch", "provincial_only": False, "family": None},
              {"code": "C", "title": "Cấp lại thẻ căn cước", "field": "Cấp, quản lý căn cước", "provincial_only": False,
               "family": "Căn cước"}])
    js2 = fn + f"""
const fold = {fold_src};
const P = {json.dumps(big, ensure_ascii=False)};
const F = ["Hộ tịch", "Cấp, quản lý căn cước", "Đăng ký, quản lý cư trú"];
const out = {{}};
for (const q of ["", "ket hon"]) out[q] = groupState(P, fold(q), fold, F, "Đắk Lắk").map((g) =>
  [g.label, g.open, g.subgroups ? g.subgroups.map((s) => [s.label, s.open, s.rows.length]) : null]);
console.log(JSON.stringify(out));"""
    res2 = json.loads(subprocess.run(["node", "-e", js2], capture_output=True, text=True, check=True).stdout)
    assert res2[""] == [["Hộ tịch (11)", False, [["Khai sinh (6)", False, 6], ["Kết hôn (4)", False, 4], ["Khác (1)", False, 1]]],
                        ["Cấp, quản lý căn cước (1)", False, None]]
    assert res2["ket hon"] == [["Hộ tịch (4 / 11)", True, [["Khai sinh (0 / 6)", False, 0], ["Kết hôn (4 / 4)", True, 4],
                                                          ["Khác (0 / 1)", False, 0]]],
                               ["Cấp, quản lý căn cước (0 / 1)", False, None]]


def test_page_shows_no_version_or_preset_names():
    """Owner's decision: one current product; the page shows modes, not presets (the JSON and /presets keep them)."""
    import re
    html = client(FakeLLM()).get("/").text
    assert "Trợ lý (có rào chắn)" in html and "Bản so sánh không rào chắn" in html
    visible = re.sub(r"//[^\n]*", "", html)  # comments may name the endpoint
    assert not re.search(r"preset|guardrailed v\d|\bv[1-5]\b", visible.split("<script>")[0])
    assert '" · preset "' not in html and "p.guardrailed" not in html
