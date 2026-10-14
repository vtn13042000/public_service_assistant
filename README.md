# Public Service Assistant

A fully local assistant that answers questions about Vietnamese administrative procedures (required documents,
fees, receiving agency, processing time, steps) only from a checked corpus of official texts, with a citation for
every fact, and otherwise refuses with a redirect to the right office or official page.

AI5013 - AI Agents · Thao-Nguyen Vuong (2532013) · Professor Tien-Dung Cao

## What it is

- **Agent:** a LangGraph graph (15 nodes, 5 conditional edges) with Self-RAG-style checks: relevance grading before
  writing, per-claim support checking after writing, code rules for numbers, authorities, deadlines and change notices.
- **Tools, in trust tiers:** SQLite rows for exact facts, hybrid retrieval (bge-m3 vectors + BM25) over section chunks
  of 57 procedures and 304 official documents, and an allowlisted web search (self-hosted SearxNG) for links only.
- **Local models on Ollama:** qwen3.5 (classifier, writer), qwen3.6 (judge), bge-m3 (embeddings).
- **Tracing:** one LangFuse trace per question, one span per node with its decision.
- **Evaluation:** a safety matrix over the structured result and RAGAS with a local judge, against the first version.

## Repository layout

```
docs/00_sources/    the assignment: project description and guidance
docs/01_context/    hardware and environment
docs/02_plan/       the plan and the requirement-to-evidence traceability
docs/03_design/     product design: architecture, as-built pipeline, guardrails, data model, data collection,
                    data-to-RAG rationale, evaluation design, question sets, prompt index, web UI
docs/04_decisions/  decision log
docs/report/        technical report: design, guardrails, evaluation results
src/                graph, nodes, Self-RAG checks, tools, rendering, web app
scripts/            crawling, parsing, cleaning, validation, database and index builds, demo start/stop
data/               processed records, documents, synonyms, test sets (the database and index are built locally)
eval/               evaluation harness and results
tests/              unit and end-to-end tests
infra/              docker-compose files for LangFuse and SearxNG
```

## Running it

1. `uv sync`; Ollama with `qwen3.5`, `qwen3.6` and `bge-m3` pulled; copy `.env.example` to `.env` and fill it in.
2. Services: `bash infra/langfuse/up.sh` and `bash infra/searxng/up.sh`.
3. Build the database and the index from the processed records (see the usage notes at the top of each script):
   `uv run python scripts/build_db.py --out data/app.db …` and `uv run python scripts/build_index.py …`.
4. `bash scripts/demo_up.sh` checks everything, warms the models, starts the web app on http://127.0.0.1:8000 and
   prints sample questions; `bash scripts/demo_down.sh` stops it.
5. Tests: `uv run pytest`. Evaluation: `uv run python -m eval.run_variant --help`.
