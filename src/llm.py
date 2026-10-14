"""Local model factories. Everything runs on the local Ollama server; no cloud API key is read or needed.

Settings follow docs/01_context/HARDWARE.md: temperature 0, explicit num_ctx (the Qwen default of 262K
context does not fit one GPU), keep_alive=-1 so graph nodes never wait for a reload.

Thinking: qwen3.5 / qwen3.6 think by default. `reasoning=False` (langchain-ollama >= 1.0) sends Ollama's
`think: false`, so the reply carries no `<think>` block and no reasoning tokens are spent.
scripts/verify_local.py checks this on the live server.

Structured output: on Ollama 0.30.8 the `format` (JSON schema) field is IGNORED by /api/chat for the
qwen35 family, so `ChatOllama.with_structured_output(...)` is NOT constrained there (the model may emit
"full" for an enum of fully|partial|no). /api/generate does enforce it. `get_structured_llm(Schema)`
therefore goes through OllamaLLM (/api/generate, chat template still applied by Ollama) with the schema
passed as `format`, then validates into the pydantic model. Use it for every reflection call.
"""
from __future__ import annotations

import os
from functools import lru_cache

from langchain_core.runnables import Runnable, RunnableLambda
from langchain_ollama import ChatOllama, OllamaEmbeddings, OllamaLLM
from pydantic import BaseModel

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
LLM_MODEL = "qwen3.5"
JUDGE_MODEL = "qwen3.6"
EMBED_MODEL = "bge-m3"
NUM_CTX = 16384


def base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL)


def generator_model() -> str:
    """Generator / classifier model: APP_GENERATOR_MODEL, else the older APP_LLM_MODEL, else qwen3.5.

    Read when a factory is first called (the factories are cached per process), so set it before the run starts.
    """
    return os.environ.get("APP_GENERATOR_MODEL") or os.environ.get("APP_LLM_MODEL") or LLM_MODEL


def judge_model() -> str:
    return os.environ.get("APP_JUDGE_MODEL") or JUDGE_MODEL


def _chat(model: str, **overrides) -> ChatOllama:
    kw = dict(
        model=model,
        base_url=base_url(),
        temperature=0,
        num_ctx=NUM_CTX,
        keep_alive=-1,
        reasoning=False,
    )
    kw.update(overrides)
    return ChatOllama(**kw)


@lru_cache(maxsize=None)
def get_llm(**overrides) -> ChatOllama:
    """Generator (`generator_model()`, default qwen3.5). Overrides, e.g. `seed=42`, are passed to ChatOllama."""
    return _chat(generator_model(), **overrides)


@lru_cache(maxsize=None)
def get_judge(**overrides) -> ChatOllama:
    """Judge (`judge_model()`, default qwen3.6), same settings as the generator."""
    return _chat(judge_model(), **overrides)


@lru_cache(maxsize=None)
def get_embeddings() -> OllamaEmbeddings:
    """bge-m3, 1024-dim."""
    return OllamaEmbeddings(model=os.environ.get("APP_EMBED_MODEL", EMBED_MODEL), base_url=base_url(), keep_alive=-1)


def _structured(model: str, schema: type[BaseModel], **overrides) -> Runnable:
    kw = dict(model=model, base_url=base_url(), temperature=0, num_ctx=NUM_CTX, keep_alive=-1, reasoning=False)
    kw.update(overrides)
    llm = OllamaLLM(**kw).bind(format=schema.model_json_schema())
    # model_validate_json raises pydantic.ValidationError on bad output; callers fail closed on any exception.
    parse = RunnableLambda(lambda text: schema.model_validate_json(text), name=f"parse_{schema.__name__}")
    return (llm | parse).with_config(run_name=f"structured_{schema.__name__}")


def get_structured_llm(schema: type[BaseModel], **overrides) -> Runnable:
    """Runnable: prompt string -> `schema` instance, decoding constrained by the JSON schema (`generator_model()`).

    Input is one prompt string (put instructions and data in it). Raises on invalid output.
    """
    return _structured(generator_model(), schema, **overrides)


def get_structured_judge(schema: type[BaseModel], **overrides) -> Runnable:
    """As `get_structured_llm`, on the judge model (`judge_model()`)."""
    return _structured(judge_model(), schema, **overrides)
