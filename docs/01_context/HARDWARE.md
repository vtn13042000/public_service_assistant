# Hardware & Ollama Environment Spec

Measured on 2026-10-10 for the AI5013 agent project (Project 5 — Public Services Assistant, Self-RAG).

## Machine

| Component | Spec |
|---|---|
| OS | Ubuntu 22.04.5 LTS, kernel 5.15.0-194-generic, x86_64 |
| CPU | Intel Xeon W-3235 @ 3.30 GHz — 12 cores / 24 threads, AVX2, AVX-512 (F, VNNI), FMA, F16C |
| RAM | 62 GB total (≈59 GB available) + 37 GB swap |
| GPU 0 | NVIDIA RTX A5000, 24 GB VRAM, compute capability 8.6 |
| GPU 1 | NVIDIA RTX A5000, 24 GB VRAM, compute capability 8.6 |
| GPU total VRAM | 48 GB |
| NVIDIA driver | 575.57.08 (`nvcc` not installed; not needed for Ollama) |
| Disk `/` | 98 GB, 50 GB free |
| Disk `/home` | 1.4 TB, **61 GB free (96% used)** — Ollama models live here |
| Tooling | Docker, `uv` 0.11.26, miniconda/anaconda, Python 3.10.12 (system) |
| Network | Internet reachable (PyPI, dichvucong.gov.vn) |

## Ollama server

| Setting | Value |
|---|---|
| Version | 0.30.8 |
| Run as | systemd service `ollama`, user `ollama` |
| Endpoint | `http://0.0.0.0:11434` |
| Models dir | `/home/ollama/models` (`OLLAMA_MODELS`) |
| `OLLAMA_NUM_PARALLEL` | 6 |
| `OLLAMA_MAX_LOADED_MODELS` | 4 |

## Installed models

| Model | Params | Quant | Disk | Context (max) | Capabilities |
|---|---|---|---|---|---|
| `qwen3.5:latest` | 9.7B | Q4_K_M | 6.6 GB | 262,144 | completion, tools, thinking, vision |
| `gpt-oss:latest` | 20.9B | MXFP4 | 13 GB | 131,072 | completion, tools, thinking |
| `qwen3.6:latest` | 36B MoE | Q4_K_M | 23 GB | 262,144 | completion, tools, thinking, vision |
| `bge-m3:latest` | 567M | F16 | 1.2 GB | 8,192 | embedding (1024-dim) |

`qwen2.5:7b` (named in the course guidance) is **not** pulled; `qwen3.5` is used in its place.

## Benchmarks

Short Vietnamese prompt ("Hồ sơ đăng ký khai sinh..."), `temperature=0`, `num_predict=200`, thinking off, cold start. All models ran at **100% GPU** offload.

| Model | Cold load | Prompt eval | Generation |
|---|---|---|---|
| `qwen3.5` | 14.3 s | 296 tok/s | ~80 tok/s |
| `gpt-oss` | 21.4 s | 225 tok/s | ~109 tok/s |
| `qwen3.6` | 34.9 s | 143 tok/s | ~100 tok/s |
| `bge-m3` | — | 32 texts embedded in 3.2 s (incl. load) | — |

## Operational notes

- **VRAM vs. context:** Qwen models default to a 262K context. Loading `qwen3.6` with that default consumed ~37 GB across both GPUs for one request. Always set `num_ctx` explicitly (8192–16384 recommended) so a model fits on a single GPU and two models can stay resident together.
- **Cold load:** 15–35 s per model. Use `keep_alive=-1` during development to avoid reloads between graph nodes.
- **Disk:** `/home` is nearly full. Pull at most one or two additional models; free space in `/home/student02` (972 GB) if more is needed.
- **Python env:** the system Python has none of langgraph / chroma / ragas / langfuse and ships torch 1.13. Create a fresh `uv venv` for the project.

## Recommended model assignment for the project

| Role | Model | Settings |
|---|---|---|
| Generator + Self-RAG reflection (`relevant?` / `supported?`) | `qwen3.5` | `temperature=0`, `num_ctx=16384`, `keep_alive=-1` |
| RAGAS judge (evaluation) | `qwen3.6` | `temperature=0`, `num_ctx=16384`, second GPU |
| Embeddings (Chroma) | `bge-m3` | default |

```python
from langchain_ollama import ChatOllama, OllamaEmbeddings
llm   = ChatOllama(model="qwen3.5", temperature=0, num_ctx=16384, keep_alive=-1)
judge = ChatOllama(model="qwen3.6", temperature=0, num_ctx=16384, keep_alive=-1)
embeddings = OllamaEmbeddings(model="bge-m3")
```
