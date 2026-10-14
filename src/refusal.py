"""Refusal policy (guardrails.md §4): five types, each built from state only, each with a next step.

No LLM is involved: names, links and dates come from `db` evidence rows already in state, so a
refusal can never introduce a fact that the evidence does not hold.
"""
from __future__ import annotations

from src.families import family_group, head_noun, load_family_nouns, title_has
from src.render import rows_with, title_of

PORTAL_URL = "https://dichvucong.gov.vn"
COVERAGE = ("thành phần hồ sơ, lệ phí, cơ quan tiếp nhận, thời gian giải quyết và trình tự thực hiện "
            "của các thủ tục hành chính (chủ yếu hộ tịch, cư trú, căn cước)")
STALE_NOTE = "cơ quan tiếp nhận có thể đã thay đổi sau sắp xếp đơn vị hành chính 2025"


def _agency(evidence: list[dict]) -> tuple[str | None, str | None, str | None]:
    """(agency name, source_url, retrieved_at) from the first agencies row, else from any db row."""
    rows = rows_with(evidence, "name")
    any_db = [e for e in evidence if e["tier"] == "db"]
    src = rows[0] if rows else (any_db[0] if any_db else None)
    name = rows[0]["structured"]["name"] if rows else None
    return name, (src or {}).get("source_url"), ((src or {}).get("retrieved_at") or "")[:10] or None


def build_refusal(state: dict, rtype: str, missing: list[str] | None = None, note: str | None = None) -> tuple[str, dict]:
    """(user-facing text, refusal dict) for one of the five types."""
    evidence = state.get("evidence") or []
    need = state.get("need") or {}
    missing = missing or []
    agency, url, date = _agency(evidence)
    title = title_of(evidence)
    refusal = {"type": rtype, "agency": agency, "portal_url": url or PORTAL_URL, "missing": missing,
               "procedure_id": state.get("procedure_id"), "title": title}

    if rtype == "out_of_scope":
        lines = [f"Câu hỏi này nằm ngoài phạm vi của trợ lý. Tôi có thể hướng dẫn {COVERAGE}."]
        if need.get("procedure_hint"):
            lines.append("Việc bạn có đủ điều kiện trong trường hợp cụ thể hay không do cơ quan tiếp nhận hồ sơ quyết định; "
                         f"tôi có thể cho bạn biết hồ sơ và nơi nộp của thủ tục \"{need['procedure_hint']}\".")
        lines.append(f"Tra cứu thủ tục: {PORTAL_URL}")
    elif rtype == "ambiguous":
        cands = state.get("candidates") or []
        refusal["candidates"] = [c["title"] for c in cands]
        lines = ["Có nhiều thủ tục gần giống nhau. Bạn muốn hỏi thủ tục nào?"]
        lines += [f"({i}) {c['title']}" for i, c in enumerate(cands, 1)]
        lines.append("Vui lòng chọn một thủ tục (hoặc nêu rõ hơn trường hợp của bạn) để tôi trả lời chính xác.")
    elif rtype == "not_in_corpus" and state.get("discontinued"):  # ROUND-4: in the corpus, but no longer performed
        st = state["discontinued"]
        since = "/".join(reversed(str(st.get("since") or "").split("-"))) or "không rõ"
        refusal.update(reason="discontinued", since=st.get("since"), basis=st.get("basis"), notice_url=st.get("notice_url"))
        lines = [f"Thủ tục này đã dừng thực hiện từ {since} theo {st.get('basis') or 'văn bản mới'}."
                 + (f" ({title})" if title else "")]
        if st.get("redirect"):
            lines.append(st["redirect"])
        if st.get("notice_url"):
            lines.append(f"Nguồn: {st['notice_url']}")
        contact = agency or "cơ quan quản lý của thủ tục này"
        lines.append(f"Nếu cần thêm hướng dẫn, vui lòng liên hệ: {contact} hoặc tra cứu tại {PORTAL_URL}.")
    elif rtype == "not_in_corpus":
        lines = ["Kho thủ tục hiện không có thủ tục này, nên tôi không liệt kê hồ sơ hay lệ phí để tránh thông tin sai."]
        web = [w for w in (state.get("web_results") or []) if w.get("tier") == "web_official"]
        if web:
            lines.append(f"Trang chính thức có thể liên quan (chưa được kiểm chứng): {web[0].get('source_url')}")
            refusal["portal_url"] = web[0].get("source_url")
        lines.append("Gợi ý: thủ tục hành chính thường do UBND cấp xã, Sở hoặc Bộ quản lý lĩnh vực tiếp nhận; "
                     f"vui lòng tra cứu tại {PORTAL_URL} hoặc hỏi bộ phận một cửa nơi bạn cư trú.")
    elif rtype == "insufficient_evidence":
        # restate the user's question, never a draft claim (owner trace c26ce7e9); claims stay in the refusal dict for the trace
        q = " ".join((state.get("query") or "").split())
        q = q if len(q) <= 160 else q[:157].rstrip() + "…"
        lines = [f"Tôi chưa đủ căn cứ trong kho thủ tục để trả lời câu hỏi: «{q}»." if q
                 else "Tôi chưa đủ căn cứ trong kho thủ tục để trả lời câu hỏi này."]
        if missing:
            lines.append(f"Phần chưa có căn cứ: {', '.join(missing)}.")
        refusal["unsupported_claims"] = [c.get("text", "")[:160] for c in state.get("claims") or []
                                         if c.get("type") == "core" and c.get("verdict") != "supported" and c.get("origin") != "gap"]
        if title:
            nouns = load_family_nouns()
            head = head_noun(need.get("procedure_hint") or state.get("query") or "", nouns)
            if head and not title_has(title, family_group(head, nouns)):  # the user named another family
                lines.append(f"Thủ tục gần nhất tìm được: {title}.")
                lines.append("Nếu bạn hỏi về thủ tục khác, hãy nêu rõ tên thủ tục.")
            else:
                lines.append(f"Thủ tục đã xác định: {title}.")
        contact = agency or "cơ quan tiếp nhận hồ sơ của thủ tục này"
        lines.append(f"Để được hướng dẫn chính xác, vui lòng liên hệ: {contact} — {url or PORTAL_URL}.")
        if date:
            lines.append(f"(Dữ liệu lấy ngày {date}; {STALE_NOTE}.)")
    elif rtype == "system_error":
        lines = ["Hệ thống đang gặp sự cố khi tra cứu nên tôi không đưa ra thông tin thủ tục lúc này.",
                 f"Vui lòng thử lại sau hoặc tra cứu trực tiếp tại {PORTAL_URL}."]
        refusal["agency"] = None
    else:
        raise ValueError(f"unknown refusal type {rtype!r}")
    if note:
        refusal["note"] = note
    return "\n".join(lines), refusal
