"""Fakes for graph tests: a scripted LLM and an in-memory DB / RAG / web over a tiny fixture world.

The world: KS-01 Đăng ký khai sinh, KS-02 … có yếu tố nước ngoài (variant_of KS-01),
KS-03 Đăng ký lại khai sinh (variant_of KS-01), CCCD-02 Cấp lại thẻ Căn cước (fees vary: one
nationwide row) and CT-09 a procedure whose fee varies by province (no provincial row).
Rows follow data-model.md §2 columns; ids follow src.evidence id builders.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage  # noqa: E402

from src.evidence import db_id, doc_id, make_evidence, web_id  # noqa: E402
from src.nodes import lexical  # noqa: E402
from src.self_rag import Need, Relevance, StoryName, Support  # noqa: E402

RETRIEVED = "2026-10-01"
URL = "https://dichvucong.gov.vn/p/fixture-{pid}"

PROCEDURES = {
    "KS-01": {"title": "Đăng ký khai sinh", "variant_of": None, "processing_time": "ngay trong ngày làm việc",
              "agency": "UBND cấp xã nơi cư trú của cha hoặc mẹ",
              "docs": [("Tờ khai đăng ký khai sinh theo mẫu", 1, "01 bản", True, None),
                       ("Giấy chứng sinh", 1, None, True, "nếu không có: văn bản xác nhận của người làm chứng")],
              "fees": [("miễn lệ phí", "đăng ký đúng hạn", "toàn quốc")]},
    "KS-02": {"title": "Đăng ký khai sinh có yếu tố nước ngoài", "variant_of": "KS-01",
              "processing_time": "03 ngày làm việc", "agency": "UBND cấp xã nơi cư trú của cha hoặc mẹ",
              "docs": [("Tờ khai đăng ký khai sinh theo mẫu", 1, "01 bản", True, None),
                       ("Văn bản thỏa thuận lựa chọn quốc tịch cho con", 1, None, True, None)],
              "fees": [("theo HĐND tỉnh", None, "theo tỉnh")]},
    "KS-03": {"title": "Đăng ký lại khai sinh", "variant_of": "KS-01", "processing_time": "05 ngày làm việc",
              "agency": "UBND cấp xã nơi đã đăng ký khai sinh trước đây",
              "docs": [("Tờ khai đăng ký lại khai sinh", 1, None, True, None)],
              "fees": [("theo HĐND tỉnh", None, "theo tỉnh")]},
    "CCCD-02": {"title": "Cấp lại thẻ Căn cước", "variant_of": None, "processing_time": "07 ngày làm việc",
                "agency": "Công an cấp xã nơi cư trú",
                "docs": [("Tờ khai căn cước", 1, None, True, None)],
                "fees": [("70.000 đồng", None, "toàn quốc")]},
    "CT-09": {"title": "Xóa đăng ký thường trú", "variant_of": None, "processing_time": "05 ngày làm việc",
              "agency": "Công an cấp xã", "docs": [("Tờ khai thay đổi thông tin cư trú", 1, None, True, None)],
              "fees": [("theo HĐND tỉnh", None, "theo tỉnh")]},
}

CHUNKS = {  # (pid, section) -> texts
    ("KS-01", "summary"): ["Đăng ký khai sinh. Thủ tục hộ tịch cấp xã cho trẻ sinh ra trong nước."],
    ("KS-01", "steps"): ["Đăng ký khai sinh — Trình tự thực hiện: Người đi đăng ký nộp tờ khai và giấy chứng sinh; "
                         "công chức tư pháp - hộ tịch kiểm tra và ghi vào Sổ hộ tịch."],
    ("KS-01", "required_documents"): ["Đăng ký khai sinh — Thành phần hồ sơ: Tờ khai; Giấy chứng sinh."],
    ("KS-01", "fees"): ["Đăng ký khai sinh — Lệ phí: miễn lệ phí khi đăng ký đúng hạn."],
    ("KS-02", "summary"): ["Đăng ký khai sinh có yếu tố nước ngoài. Trẻ có cha hoặc mẹ là người nước ngoài."],
    ("KS-02", "steps"): ["Đăng ký khai sinh có yếu tố nước ngoài — Trình tự: nộp hồ sơ tại UBND cấp xã."],
    ("KS-03", "summary"): ["Đăng ký lại khai sinh. Khi sổ hộ tịch và bản chính giấy khai sinh đều bị mất."],
    ("CCCD-02", "summary"): ["Cấp lại thẻ Căn cước. Khi thẻ bị mất, hư hỏng."],
    ("CCCD-02", "fees"): ["Cấp lại thẻ Căn cước — Lệ phí: 70.000 đồng."],
    ("CT-09", "summary"): ["Xóa đăng ký thường trú."],
}


def _proc_ev(pid: str) -> dict:
    p = PROCEDURES[pid]
    row = {"id": pid, "title": p["title"], "field": "Hộ tịch", "processing_time": p["processing_time"],
           "variant_of": p["variant_of"], "agency_summary": p["agency"]}
    return make_evidence(db_id("procedures", pid, 1), "db", f"{p['title']}. Thời gian giải quyết: {p['processing_time']}",
                         procedure_id=pid, section="summary", structured=row, source_url=URL.format(pid=pid),
                         retrieved_at=RETRIEVED)


class FakeDB:
    """Mirrors the src.tools.db interface (each function returns list[Evidence], tier db)."""

    def __init__(self, procedures: dict | None = None, retrieved_at: str = RETRIEVED, fail: str | None = None):
        self.p = procedures or PROCEDURES
        self.retrieved_at = retrieved_at
        self.fail = fail
        self.calls: list[str] = []

    def _check(self, name):
        self.calls.append(name)
        if self.fail in (name, "*"):
            raise RuntimeError(f"db {name} failed (injected)")

    def _ev(self, *a, **k):
        k["retrieved_at"] = self.retrieved_at
        return make_evidence(*a, **k)

    def search_titles(self, query: str, k: int = 5):
        self._check("search_titles")
        scored = sorted(((lexical(query, p["title"]), pid) for pid, p in self.p.items()), reverse=True)
        return [self.get_procedure(pid)[0] for s, pid in scored[:k] if s > 0]

    def get_procedure(self, pid: str):
        self._check("get_procedure")
        if pid not in self.p:
            return []
        ev = _proc_ev(pid)
        ev["retrieved_at"] = self.retrieved_at
        return [ev]

    def get_required_documents(self, pid: str):
        self._check("get_required_documents")
        out = []
        for i, (item, q, qt, m, note) in enumerate(self.p.get(pid, {}).get("docs", []), 1):
            row = {"procedure_id": pid, "position": i, "item": item, "quantity": q, "quantity_text": qt,
                   "mandatory": int(m), "note": note, "source_id": f"fx#{pid}"}
            out.append(self._ev(db_id("required_documents", pid, i), "db", item, procedure_id=pid,
                                section="required_documents", structured=row, source_url=URL.format(pid=pid)))
        return out

    def get_fees(self, pid: str):
        self._check("get_fees")
        out = []
        for i, (value, cond, juris) in enumerate(self.p.get(pid, {}).get("fees", []), 1):
            row = {"procedure_id": pid, "value": value, "condition": cond, "jurisdiction": juris, "source_id": f"fx#{pid}"}
            out.append(self._ev(db_id("fees", pid, i), "db", f"Lệ phí: {value}", procedure_id=pid, section="fees",
                                structured=row, source_url=URL.format(pid=pid)))
        return out

    def get_agency(self, pid: str):
        self._check("get_agency")
        if pid not in self.p:
            return []
        row = {"procedure_id": pid, "name": self.p[pid]["agency"], "jurisdiction": "toàn quốc",
               "effective_date": "2025-07-01", "source_id": f"fx#{pid}"}
        return [self._ev(db_id("agencies", pid, 1), "db", f"Cơ quan tiếp nhận: {row['name']}", procedure_id=pid,
                         section="agency", structured=row, source_url=URL.format(pid=pid), effective_date="2025-07-01")]

    def get_source(self, source_id: str):
        return []


class FakeRAG:
    """Mirrors src.tools.rag: retrieve(query, procedure_id, section, k) and resolve_candidates(query, k)."""

    def __init__(self, chunks: dict | None = None, fail: bool = False, order: list[str] | None = None,
                 extra: list[dict] | None = None):
        self.chunks = chunks or CHUNKS
        self.fail = fail
        self.order = order          # forced resolve_candidates ranking (e.g. KS-02 above KS-01)
        self.extra = extra or []    # extra Evidence returned by retrieve (injection tests)
        self.queries: list[str] = []

    def retrieve(self, query, procedure_id=None, section=None, k=5):
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("chroma unavailable (injected)")
        secs = section if isinstance(section, list) else ([section] if section else None)
        out = []
        for (pid, sec), texts in self.chunks.items():
            if procedure_id and pid != procedure_id:
                continue
            if secs and sec not in secs:
                continue
            for i, t in enumerate(texts):
                out.append(make_evidence(doc_id(pid, sec, i), "corpus", t, procedure_id=pid, section=sec,
                                         source_url=URL.format(pid=pid), retrieved_at=RETRIEVED))
        return (out + [e for e in self.extra if not procedure_id or e["procedure_id"] == procedure_id])[:k]

    def resolve_candidates(self, query, k=5):
        if self.fail:
            raise RuntimeError("chroma unavailable (injected)")
        titles = {pid: PROCEDURES[pid]["title"] for pid, sec in self.chunks if sec == "summary" and pid in PROCEDURES}
        ranked = self.order or sorted(titles, key=lambda pid: -lexical(query, titles[pid]))
        return [{"procedure_id": pid, "title": titles[pid], "score": round(2 / (61 + r), 6)}
                for r, pid in enumerate(ranked[:k]) if pid in titles]


class FakeWeb:
    def __init__(self, hits: list[dict] | None = None, fail: bool = False):
        self.hits = hits if hits is not None else [
            {"url": "https://dichvucong.gov.vn/p/nhap-quoc-tich", "title": "Nhập quốc tịch Việt Nam", "tier": "web_official"},
            {"url": "https://thuvienphapluat.vn/x", "title": "Bài viết", "tier": "web_other"}]
        self.fail = fail
        self.queries: list[str] = []

    def __call__(self, query: str, **_):
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("web down (injected)")
        return [make_evidence(web_id(h["url"]), h["tier"], h["title"], source_url=h["url"], retrieved_at=RETRIEVED)
                for h in self.hits]


# ---------------------------------------------------------------- the scripted LLM

Script = Any  # a value, or a callable(prompt) -> value


class _Runnable:
    def __init__(self, fn):
        self.fn = fn

    def invoke(self, prompt, *a, **k):
        return self.fn(prompt)


class FakeLLM:
    """Scripted chat model + structured factory.

    need:      dict for Need, or callable(prompt) -> dict
    relevance: bool (all), list[bool], or callable(prompt, n_docs) -> list[bool]
    support:   "fully|partial|no" or callable(prompt) -> str
    narrative: str or callable(prompt) -> str        (draft_answer)
    rewrite:   str                                     (rewrite_query)
    story:     str                                     (story_rewrite, StoryName)
    bad_json:  set of schema names whose structured call returns unparseable output
    fail:      set of names ('need','relevance','support','narrative','rewrite') that raise (transport error)
    """

    def __init__(self, need: Script = None, relevance: Script = True, support: Script = "fully",
                 narrative: Script = "", rewrite: str = "truy vấn viết lại", bad_json=(), fail=(), story: str = ""):
        self.need, self.relevance, self.support = need, relevance, support
        self.narrative, self.rewrite, self.story = narrative, rewrite, story
        self.bad_json, self.fail = set(bad_json), set(fail)
        self.prompts: list[tuple[str, str]] = []

    @staticmethod
    def _v(script, *args):
        return script(*args) if callable(script) else script

    # chat path (draft_answer, rewrite_query)
    def invoke(self, prompt, *a, **k):
        prompt = prompt if isinstance(prompt, str) else str(prompt)
        kind = "rewrite" if prompt.startswith("Viết lại CÂU HỎI") else "narrative"
        self.prompts.append((kind, prompt))
        if kind in self.fail:
            raise TimeoutError(f"ollama timeout (injected: {kind})")
        return AIMessage(content=self.rewrite if kind == "rewrite" else self._v(self.narrative, prompt))

    def bind(self, **k):
        return self

    # structured path (reflection)
    def structured(self, schema):
        def run(prompt):
            name = {Need: "need", Relevance: "relevance", Support: "support", StoryName: "story"}[schema]
            self.prompts.append((name, prompt))
            if name in self.fail:
                raise TimeoutError(f"ollama timeout (injected: {name})")
            if name in self.bad_json:
                return schema.model_validate_json('{"oops": ')  # raises ValidationError like src.llm's parser
            if name == "story":
                return StoryName(procedure_name=self.story)
            if name == "need":
                d = {"in_scope": True, "retrieve": True, "intent": "general", "procedure_hint": "",
                     "locality": None, "premise": None}
                d.update(self._v(self.need, prompt) or {})
                return Need(**d)
            if name == "relevance":
                n = len(re.findall(r"<tai_lieu idx=", prompt))
                r = self.relevance(prompt, n) if callable(self.relevance) else self.relevance
                flags = r if isinstance(r, list) else [bool(r)] * n
                return Relevance(items=[{"idx": i, "relevant": f, "reason": "fake"} for i, f in enumerate(flags)])
            return Support(supported=self._v(self.support, prompt), reason="fake")
        return _Runnable(run)


def need(intent="general", hint="", premise=None, locality=None, in_scope=True, retrieve=True) -> dict:
    return {"intent": intent, "procedure_hint": hint, "premise": premise, "locality": locality,
            "in_scope": in_scope, "retrieve": retrieve}


TODAY = date(2026, 10, 10)


def make_app(llm=None, rag=None, db=None, web=None, **kw):
    """Guardrailed app on fakes; returns (app, deps-ish dict) so tests can inspect calls."""
    from src.graph import build_graph
    rag, db, web = rag or FakeRAG(), db or FakeDB(), web if web is not None else FakeWeb()
    trace: list[tuple[str, dict]] = []
    app = build_graph(llm or FakeLLM(), rag, db, web, today=kw.pop("today", TODAY),
                      trace=lambda name, **m: trace.append((name, m)), **kw)
    return app, {"rag": rag, "db": db, "web": web, "trace": trace}


def run(query, llm=None, init=None, **kw):
    app, parts = make_app(llm, **kw)
    state = app.invoke({"query": query, **(init or {})})
    return state, parts
