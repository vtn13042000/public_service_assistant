# ĐỀ XUẤT PROJECT MÔN AGENT

*Xây dựng AI Agent với LangGraph & Ollama nội bộ*

## Yêu cầu tối thiểu (bắt buộc cho mọi project)

- Tích hợp đủ các công cụ: tìm kiếm internet (web search), truy vấn database, RAG và một kỹ thuật RAG nâng cao.
- Orchestration bằng LangGraph (nodes / edges / state rõ ràng, có conditional routing).
- Sử dụng model Ollama nội bộ (chạy hoàn toàn on-premise, không gọi API LLM bên ngoài).

## Stack chung đề xuất

LangGraph (orchestration) · Ollama (LLM + embedding) · Chroma/Qdrant (vector store) · SQLite/PostgreSQL (DB quan hệ) · Tavily/DuckDuckGo hoặc SearxNG nội bộ (web search) · LangFuse (trace/eval).

Embedding tiếng Việt: `bge-m3` hoặc `nomic-embed-text`. LLM: `qwen2.5:7b/14b` (đa ngữ tốt) hoặc `gpt-oss:20b`.

## Project 5. Trợ lý dịch vụ công / thủ tục hành chính (Public Services Assistant)

**Kỹ thuật RAG nâng cao:** Self-RAG — token phản tỉnh (`retrieve?` / `relevant?` / `supported?`), tự đánh giá và trích nguồn; ưu tiên từ chối hơn là hướng dẫn sai.

### Tóm tắt

**Bài toán:** Trả lời về thủ tục hành chính (hồ sơ, quy trình, lệ phí, cơ quan tiếp nhận) với ràng buộc không được hướng dẫn sai giấy tờ.

**Bộ công cụ (tools):** RAG trên kho thủ tục, web search cho cập nhật mới, DB thủ tục/cơ quan.

**Luồng LangGraph:** `assess-need → retrieve → self-critique (supported?) → {đủ chứng cứ: answer + cite | không: từ chối + chỉ dẫn cơ quan}`.

**Thách thức chính:** Thiết kế guardrail an toàn; ưu tiên từ chối/chuyển tuyến hơn là bịa thông tin thủ tục.

### Nguồn dữ liệu gợi ý

| Loại dữ liệu | Nguồn gợi ý | Cách lấy / ghi chú |
| --- | --- | --- |
| **Corpus (RAG)** | Thủ tục từ Cổng Dịch vụ công Quốc gia (`dichvucong.gov.vn`) — quy trình, thành phần hồ sơ, lệ phí | Cào một nhóm thủ tục theo lĩnh vực (hộ tịch, đất đai, đăng ký kinh doanh...). |
| **DB quan hệ** | Bảng thủ tục / cơ quan / lĩnh vực / lệ phí | Trích cấu trúc từ chính trang thủ tục đã cào. |
| **Web search** | Cập nhật thay đổi thủ tục / văn bản mới | Fallback khi corpus không có hoặc lỗi thời. |

## Rubric chấm chung (áp dụng cho cả 8 project)

- Kiến trúc LangGraph: nodes/edges/state rõ ràng, có conditional routing.
- Triển khai đúng kỹ thuật RAG nâng cao được gán cho project.
- Chất lượng truy hồi: đo bằng RAGAS (faithfulness, context precision/recall).
- Tích hợp đủ 3 loại tool (web search + database + RAG).
- Trace được qua LangFuse.
- Vận hành hoàn toàn nội bộ với Ollama.
- Demo hoạt động + báo cáo kỹ thuật.

## Lưu ý về dữ liệu (khuyến nghị sư phạm)

Không để mỗi nhóm tự cào dữ liệu từ đầu — dễ tốn cả tuần chỉ để lấy data. Nên quy định "dataset tối thiểu" cho mỗi project (chỉ định đúng 1 nguồn chính như bảng trên), hoặc đóng gói sẵn corpus nhỏ (~50–200 tài liệu) + file SQLite mẫu phát kèm đề bài để chấm điểm công bằng trên cùng ground-truth.

Corpus tiếng Anh (arXiv, FEVER, Olist, WikiVoyage) sạch và nhiều; corpus tiếng Việt (luật, tin tức, dịch vụ công) sát thực tế hơn nhưng cần thêm bước làm sạch. Khuyến khích tiếng Việt ở các project mà nó thực sự tạo giá trị (dịch vụ công, luật, tin tức VN).
