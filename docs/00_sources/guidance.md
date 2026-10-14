# HƯỚNG DẪN THỰC HIỆN PROJECT MÔN AGENT

**BẢN CHI TIẾT — code skeleton · schema DB · test-set · prompt mẫu (8 đề tài)**

Bản này bổ sung chiều sâu kỹ thuật cho khung đã duyệt: Phần A cung cấp bộ mã nguồn khung chung chạy được (mọi nhóm kế thừa); Phần B, mỗi đề tài có node đặc thù (code), schema database, test-set mẫu và prompt cho kỹ thuật RAG nâng cao. Lộ trình 4 tuần và rubric giữ như bản khung.

Phiên bản thư viện tham chiếu: `langgraph`, `langchain-ollama`, `langchain-chroma`, `rank-bm25`, `sentence-transformers`, `ragas`, `langfuse`. Model qua Ollama: LLM `qwen2.5:7b`, embedding `bge-m3`.

## PHẦN A — BỘ KHUNG MÃ NGUỒN CHUNG

Cấu trúc theo file. Đây là skeleton chạy được: dựng được graph, gọi được 3 tool; phần logic miền để trống bằng TODO cho từng đề tài.

### A1. `state.py` — định nghĩa State

```python
from typing import TypedDict

class AgentState(TypedDict, total=False):
    query: str                 # câu hỏi gốc
    sub_queries: list[str]     # decompose / fusion (nếu có)
    documents: list[dict]      # ngữ cảnh truy hồi (vector/graph)
    db_results: list[dict]     # kết quả truy vấn database
    web_results: list[dict]    # kết quả web search
    grades: dict               # điểm relevance / supported
    route: str                 # quyết định định tuyến
    iteration: int             # đếm vòng lặp (chặn loop)
    generation: str            # câu trả lời
```

### A2. `llm.py` — model qua Ollama (nội bộ)

```python
from langchain_ollama import ChatOllama, OllamaEmbeddings

llm = ChatOllama(model="qwen2.5:7b", temperature=0)
embeddings = OllamaEmbeddings(model="bge-m3")

# Yêu cầu: đã chạy `ollama pull qwen2.5:7b` và `ollama pull bge-m3`
```

### A3. `ingest.py` — nạp corpus vào vector store

```python
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from llm import embeddings

def build_index(docs: list[dict], persist="./chroma"):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=700, chunk_overlap=100)
    chunks, metas = [], []
    for d in docs:                       # d = {'text':..., 'meta':{}}
        for ch in splitter.split_text(d['text']):
            chunks.append(ch); metas.append(d.get('meta', {}))
    return Chroma.from_texts(chunks, embeddings,
        metadatas=metas, persist_directory=persist,
        collection_name="corpus")
```

### A4. `tools.py` — 3 công cụ

```python
import sqlite3
from langchain_chroma import Chroma
from langchain_community.tools import DuckDuckGoSearchResults
from llm import embeddings

# 1) RAG retriever
vs = Chroma(collection_name="corpus", embedding_function=embeddings,
            persist_directory="./chroma")
retriever = vs.as_retriever(search_kwargs={"k": 5})

# 2) Database (mở read-only cho an toàn Text-to-SQL)
def run_sql(sql: str, db="app.db") -> list[dict]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(sql).fetchall()
    con.close()
    return [dict(r) for r in rows]

# 3) Web search
web_search = DuckDuckGoSearchResults(output_format="list")
```

### A5. `nodes.py` — các node dùng chung

```python
from llm import llm
from tools import retriever, run_sql, web_search

def route_question(state):
    # TODO(theo đề tài): phân nhánh knowledge/data/độ-phức-tạp
    return {"route": "knowledge", "iteration": 0}

def retrieve_docs(state):
    docs = retriever.invoke(state["query"])
    return {"documents": [
        {"text": d.page_content, "meta": d.metadata} for d in docs]}

def run_db_query(state):
    sql = state.get("route_sql", "SELECT 1")     # TODO: text-to-sql
    return {"db_results": run_sql(sql)}

def run_web_search(state):
    return {"web_results": web_search.invoke(state["query"])}

def grade_or_critique(state):
    # <== ĐIỂM CẮM RAG NÂNG CAO (thay theo từng đề tài, xem Phần B)
    return {"grades": {"verdict": "enough"}}

def generate_answer(state):
    ctx = "\n\n".join(d["text"] for d in state.get("documents", []))
    msg = f"Ngữ cảnh:\n{ctx}\n\nCâu hỏi: {state['query']}\nTrả lời có trích nguồn:"
    return {"generation": llm.invoke(msg).content}

def finalize_answer(state):
    return {"generation": state["generation"]}
```

### A6. `graph.py` — lắp graph + conditional routing

```python
from langgraph.graph import StateGraph, END
from state import AgentState
from nodes import (route_question, retrieve_docs, run_db_query,
    run_web_search, grade_or_critique, generate_answer, finalize_answer)

MAX_ITER = 2

def pick_branch(state):
    return state["route"]                 # 'knowledge' | 'data'

def decide_next(state):
    v = state["grades"]["verdict"]
    if v == "enough": return "generate"
    if state.get("iteration", 0) >= MAX_ITER: return "generate"
    return "web" if v == "insufficient" else "rewrite"

g = StateGraph(AgentState)
for name, fn in [("router",route_question),("retrieve",retrieve_docs),
    ("query_db",run_db_query),("web_search",run_web_search),
    ("grade",grade_or_critique),("generate",generate_answer),
    ("finalize",finalize_answer)]:
    g.add_node(name, fn)

g.set_entry_point("router")
g.add_conditional_edges("router", pick_branch,
    {"knowledge":"retrieve", "data":"query_db"})
g.add_edge("retrieve", "grade")
g.add_conditional_edges("grade", decide_next,
    {"generate":"generate", "web":"web_search", "rewrite":"retrieve"})
g.add_edge("web_search", "generate")
g.add_edge("query_db", "generate")
g.add_edge("generate", "finalize")
g.add_edge("finalize", END)
app = g.compile()
```

Mỗi đề tài ở Phần B chỉ cần thay node `grade_or_critique` (và đôi khi thêm 1–2 node như `build_graph`, `decompose`, `hyde_draft`) rồi nối lại cạnh — phần còn lại giữ nguyên.

### A7. `eval.py` — RAGAS + LangFuse (khung)

```python
from ragas import evaluate
from ragas.metrics import (faithfulness, answer_relevancy,
    context_precision, context_recall)
from datasets import Dataset

def run_eval(samples):   # {question, answer, contexts, ground_truth}
    ds = Dataset.from_list(samples)
    return evaluate(ds, metrics=[faithfulness, answer_relevancy,
        context_precision, context_recall])

# LangFuse: bọc callback quanh app.invoke(...) để lấy trace mỗi node.
```

## Đề tài 5. Trợ lý dịch vụ công — Self-RAG

**Kỹ thuật:** Self-RAG — phản tỉnh `relevant?` / `supported?`, ưu tiên từ chối hơn bịa.

### (1) Node đặc thù

```python
import json
from llm import llm

REFLECT = ('Cho NGỮ CẢNH và TRẢ LỜI nháp, trả JSON '
  '{"relevant":bool,"supported":"fully|partial|no"}. '
  'NGỮ CẢNH:{ctx}\nTRẢ LỜI:{ans}')

def self_critique(state):
    ctx = '\n'.join(d['text'] for d in state.get('documents', []))
    draft = llm.invoke(f'Trả lời ngắn từ ngữ cảnh:\n{ctx}\nHỏi: '
        + state['query']).content
    r = llm.invoke(REFLECT.format(ctx=ctx[:2000], ans=draft))
    try: flags = json.loads(r.content)
    except Exception: flags = {'relevant': False, 'supported': 'no'}
    ok = flags.get('relevant') and flags.get('supported') == 'fully'
    return {'generation': draft if ok else None,
        'grades': {'verdict': 'enough' if ok else 'refuse'}}

def gate(state):
    if state['grades']['verdict'] == 'refuse':
        return {'generation': 'Chưa đủ căn cứ trong kho thủ tục. '
            'Vui lòng liên hệ cơ quan tiếp nhận để được hướng dẫn.'}
    return state
```

### (2) Schema database

```sql
CREATE TABLE thu_tuc (
  id TEXT PRIMARY KEY, ten TEXT, linh_vuc TEXT,
  le_phi TEXT, co_quan TEXT, thoi_gian_xu_ly TEXT);
CREATE TABLE ho_so (
  thu_tuc_id TEXT, thanh_phan TEXT, so_luong INTEGER, bat_buoc INTEGER);
CREATE INDEX idx_hoso_tt ON ho_so(thu_tuc_id);
```

### (3) Test-set mẫu

| Câu hỏi | Loại | Kỳ vọng |
| --- | --- | --- |
| Hồ sơ đăng ký khai sinh gồm những gì? | in-corpus | Liệt kê từ `ho_so`, có trích nguồn |
| Lệ phí cấp lại CCCD là bao nhiêu? | in-corpus | Trả `le_phi` đúng thủ tục |
| Thủ tục nhập tịch cho người nước ngoài? | out-corpus | Không bịa → từ chối + chỉ dẫn cơ quan |

### (4) Prompt mẫu

**Prompt phản tỉnh (ISREL + ISSUP)**

```text
Đánh giá cặp (ngữ cảnh, trả lời nháp). Trả JSON:
{"relevant": true/false,           # ngữ cảnh có liên quan?
 "supported": "fully|partial|no"} # trả lời được chống lưng?
NGỮ CẢNH: {ctx}\nTRẢ LỜI: {ans}
```

**Prompt từ chối có kiểm soát**

```text
Nếu không đủ căn cứ, KHÔNG suy đoán thành phần hồ sơ/lệ phí.
Trả lời rằng chưa đủ thông tin và hướng người dùng tới đúng
cơ quan tiếp nhận (từ trường co_quan nếu có).
```
