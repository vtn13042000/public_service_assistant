"""RAGAS on a variant's result file with a local judge (evaluation.md §2.1).

    uv run python -m eval.ragas_run eval/results/guardrailed.json [--testset data/testset.jsonl] \
        [--out eval/results/ragas_guardrailed.json] [--relevancy 20] [--noise 15] [--limit N]

Scope: items whose gold outcome is answer/answer_partial **and** whose predicted outcome is answer/answer_partial.
RAGAS is undefined for a refusal (no claims to check); refusals are scored by eval/safety.py instead. The number of
items excluded for that reason is written to the output, so a variant cannot look better by refusing more.

Metrics (ragas legacy single-turn metrics, LLM = judge qwen3.6, embeddings = bge-m3, both via Ollama):
  faithfulness, context_precision (LLM, with reference), context_recall (LLM), answer_relevancy (optional), and
  and, computed here without an LLM, doc_id_precision / doc_id_recall: retrieved `doc:` chunk ids vs gold `doc:` ids
  (secondary; only items whose gold names chunks). `db:` ids are excluded on purpose: gold `db:` ids index the
  record arrays while the DB tool emits its own row ids (data/testset/README.md "Resolution rule").
Sample fields: user_input = question; response = answer without the "Nguồn:" paragraph; retrieved_contexts = the
evidence (faithfulness/relevancy: the evidence the answer cites; precision/recall: all evidence in graph order, see
context_sets); reference = gold answer note + gold items/value.

Local-only: OPENAI_API_KEY is removed from the environment and any OpenAI client construction raises, so ragas
cannot fall back to its OpenAI default. ragas analytics is disabled (RAGAS_DO_NOT_TRACK=true).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.safety import ANSWERED, body, load_testset  # noqa: E402

MAX_CONTEXT_CHARS = 1500    # per context
CONTEXT_BUDGET_CHARS = 12000  # per sample, all contexts together (num_ctx 16384; Vietnamese is token-heavy)
USED_CONTEXT_METRICS = ("faithfulness", "answer_relevancy")  # judged against the evidence the answer cites
LLM_METRICS = ("faithfulness", "context_precision", "context_recall")
ID_METRICS = ("doc_id_precision", "doc_id_recall")


# ---------------------------------------------------------------- local-only guards

class OpenAIFallbackError(RuntimeError):
    pass


def forbid_openai() -> None:
    """Remove OpenAI credentials and make any OpenAI client construction fail loudly."""
    for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
        os.environ.pop(k, None)
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    import openai

    def _refuse(self, *a, **k):
        raise OpenAIFallbackError("an OpenAI client was constructed during eval; ragas must use the local judge")
    for cls in (openai.OpenAI, openai.AsyncOpenAI):
        cls.__init__ = _refuse


def shim_ragas_imports() -> None:
    """ragas 0.4.3 imports `langchain_community.chat_models.vertexai.ChatVertexAI`, removed in langchain-community 0.4.
    It is only used in an isinstance check (n-completion support), so an empty stand-in class is enough."""
    name = "langchain_community.chat_models.vertexai"
    try:
        __import__(name)
    except ImportError:
        mod = types.ModuleType(name)
        mod.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules[name] = mod


def make_metrics(relevancy: bool = False) -> list:
    shim_ragas_imports()
    from ragas.metrics._context_precision import LLMContextPrecisionWithReference
    from ragas.metrics._context_recall import LLMContextRecall
    from ragas.metrics._faithfulness import Faithfulness
    ms = [Faithfulness(), LLMContextPrecisionWithReference(name="context_precision"), LLMContextRecall()]
    if relevancy:
        from ragas.metrics._answer_relevance import ResponseRelevancy
        ms.append(ResponseRelevancy(strictness=1))
    return ms


def judge_wrappers(llm=None, embeddings=None):
    shim_ragas_imports()
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    if llm is None or embeddings is None:
        from src.llm import get_embeddings, get_judge
        llm, embeddings = llm or get_judge(), embeddings or get_embeddings()
    return LangchainLLMWrapper(llm), LangchainEmbeddingsWrapper(embeddings)


# ---------------------------------------------------------------- samples

def reference(gold: dict) -> str:
    parts = [gold.get("answer") or ""]
    if gold.get("items"):
        parts.append("\n".join(f"- {x}" for x in gold["items"]))
    if gold.get("value"):
        parts.append(gold["value"])
    return "\n".join(p for p in parts if p)


def _budget(texts: list[str]) -> list[str]:
    out, total = [], 0
    for t in texts:
        t = t[:MAX_CONTEXT_CHARS]
        if out and total + len(t) > CONTEXT_BUDGET_CHARS:
            break
        out.append(t)
        total += len(t)
    return out


def context_sets(row: dict) -> tuple[list[str], list[str]]:
    """(retrieved, used).
    retrieved = all evidence in graph order (for context precision/recall).
    used = the evidence the answer cites, in citation order (for faithfulness/relevancy); if nothing is cited
    (the baseline), every retrieved context is what the answer was generated from.
    Both are cut to CONTEXT_BUDGET_CHARS. A fixed top-k is not used: the guardrailed graph puts 7 procedure-summary
    rows first, and a top-8 cut dropped the document rows the answer was built from (bug found 2026-10-10)."""
    pairs = [(i, c) for i, c in zip(row.get("context_ids") or [None] * len(row.get("contexts") or []),
                                     row.get("contexts") or []) if c]
    retrieved = _budget([c for _, c in pairs])
    by_id = {i: c for i, c in pairs if i}
    cited = [by_id[i] for i in row.get("cited_ids") or [] if i in by_id]
    return retrieved, _budget(cited) if cited else retrieved


def build_samples(result: dict, items: list[dict]) -> tuple[list[dict], dict]:
    """(samples, coverage). One sample per eligible item; coverage counts why others were excluded."""
    rows = result["items"]
    samples, cov = [], {"gold_answerable": 0, "run": 0, "declined": 0, "no_context": 0, "scored": 0}
    for it in items:
        if it["gold"]["outcome"] not in ANSWERED:
            continue
        cov["gold_answerable"] += 1
        r = rows.get(it["id"])
        if r is None:
            continue
        cov["run"] += 1
        if r.get("outcome") not in ANSWERED:
            cov["declined"] += 1
            continue
        retrieved, used = context_sets(r)
        if not retrieved:
            cov["no_context"] += 1
            continue
        samples.append({"id": it["id"], "user_input": it["question"], "response": body(r.get("answer")),
                        "retrieved_contexts": retrieved, "used_contexts": used, "reference": reference(it["gold"]),
                        "doc_ids": [i for i in (r.get("context_ids") or []) if i and i.startswith("doc:")],
                        "gold_doc_ids": [i for i in it["gold"].get("evidence_ids") or [] if i.startswith("doc:")]})
    cov["scored"] = len(samples)
    return samples, cov


# ---------------------------------------------------------------- scoring

def doc_id_scores(s: dict) -> dict:
    """Chunk-id precision/recall over all `doc:` ids the graph used (not truncated). None if gold names no chunk."""
    got, gold = set(s["doc_ids"]), set(s["gold_doc_ids"])
    if not gold:
        return {"doc_id_precision": None, "doc_id_recall": None}
    return {"doc_id_precision": round(len(got & gold) / len(got), 4) if got else 0.0,
            "doc_id_recall": round(len(got & gold) / len(gold), 4)}


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else round(x, 4)


def score(samples: list[dict], metrics: list, llm, embeddings, workers: int = 2, timeout: int = 900) -> dict[str, dict]:
    """{test_id: {metric: value|None}}. NaN (judge parse failure) becomes None and is counted, not averaged."""
    if not samples:
        return {}
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.run_config import RunConfig
    for m in metrics:  # set explicitly so nothing can lazily build a default (OpenAI) model
        if hasattr(m, "llm"):
            m.llm = llm
        if hasattr(m, "embeddings"):
            m.embeddings = embeddings
    out = {s["id"]: doc_id_scores(s) for s in samples}
    groups = [("used_contexts", [m for m in metrics if m.name in USED_CONTEXT_METRICS]),
              ("retrieved_contexts", [m for m in metrics if m.name not in USED_CONTEXT_METRICS])]
    for ctx_key, ms in groups:
        if not ms:
            continue
        ds = EvaluationDataset(samples=[SingleTurnSample(user_input=s["user_input"], response=s["response"],
                                                         retrieved_contexts=s.get(ctx_key) or s["retrieved_contexts"],
                                                         reference=s["reference"]) for s in samples])
        res = evaluate(ds, metrics=ms, llm=llm, embeddings=embeddings, raise_exceptions=False, show_progress=False,
                       run_config=RunConfig(timeout=timeout, max_retries=2, max_workers=workers, seed=42))
        df = res.to_pandas()
        for i, s in enumerate(samples):
            for m in ms:
                out[s["id"]][m.name] = _num(df.iloc[i][m.name]) if m.name in df.columns else None
    return out


def summarise(per_item: dict[str, dict]) -> dict:
    names = sorted({k for v in per_item.values() for k in v})
    out = {}
    for n in names:
        vals = [v[n] for v in per_item.values() if v.get(n) is not None]
        out[n] = {"mean": round(sum(vals) / len(vals), 4) if vals else None, "n": len(vals),
                  # None for a doc_id metric = gold names no chunk (not applicable), not a judge failure
                  "failed": 0 if n in ID_METRICS else sum(1 for v in per_item.values() if n in v and v[n] is None)}
    return out


def agreement(a: dict[str, dict], b: dict[str, dict], tol: float = 0.1) -> dict:
    """Judge noise between two runs on the same samples: mean |Δ|, share within `tol`, and for faithfulness the
    share of items on the same side of 0.5."""
    out = {}
    for n in LLM_METRICS + ("answer_relevancy",):
        pairs = [(a[i][n], b[i][n]) for i in a if i in b and a[i].get(n) is not None and b[i].get(n) is not None]
        if not pairs:
            continue
        d = [abs(x - y) for x, y in pairs]
        out[n] = {"n": len(pairs), "mean_abs_diff": round(sum(d) / len(d), 4),
                  "within_tol": round(sum(x <= tol for x in d) / len(d), 4), "tol": tol,
                  "same_side_of_0.5": round(sum((x >= 0.5) == (y >= 0.5) for x, y in pairs) / len(pairs), 4)}
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("result")
    ap.add_argument("--testset", default="data/testset.jsonl")
    ap.add_argument("--out")
    ap.add_argument("--relevancy", type=int, default=0, metavar="N",
                    help="also answer_relevancy on the first N samples (slow: ~60 s/sample; lead: N=20)")
    ap.add_argument("--noise", type=int, default=0, help="re-run the LLM metrics on the first N samples")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--judge-model", help="override the judge (e.g. gpt-oss for a cross-family check); default qwen3.6")
    a = ap.parse_args(argv)
    forbid_openai()
    shim_ragas_imports()
    import ragas
    result = json.loads(Path(a.result).read_text(encoding="utf-8"))
    variant = result.get("config", {}).get("variant") or Path(a.result).stem
    samples, cov = build_samples(result, load_testset(a.testset))
    samples = samples[: a.limit] if a.limit else samples
    if a.judge_model:
        os.environ["APP_JUDGE_MODEL"] = a.judge_model  # read by src.llm.get_judge at first call
    llm, emb = judge_wrappers()
    judge_model = getattr(getattr(llm, "langchain_llm", None), "model", None)
    t0 = dt.datetime.now(dt.timezone.utc)
    per_item = score(samples, make_metrics(), llm, emb, workers=a.workers)
    if a.relevancy:
        from ragas.metrics._answer_relevance import ResponseRelevancy
        rel = score(samples[: a.relevancy], [ResponseRelevancy(strictness=1)], llm, emb, workers=a.workers)
        for tid, v in rel.items():
            per_item[tid]["answer_relevancy"] = v["answer_relevancy"]
    out = {"meta": {"variant": variant, "result_file": a.result, "ragas_version": ragas.__version__,
                    "judge_model": judge_model or os.environ.get("APP_JUDGE_MODEL", "qwen3.6"),
                    "embed_model": result.get("config", {}).get("embed_model") or "bge-m3",
                    "started_at": t0.isoformat(timespec="seconds"),
                    "relevancy_subset": a.relevancy, "context_budget_chars": CONTEXT_BUDGET_CHARS, "max_context_chars": MAX_CONTEXT_CHARS,
                    "contexts": "faithfulness/relevancy: cited evidence (all retrieved if none cited); precision/recall: "
                                "all evidence in graph order",
                    "shim": "langchain_community.chat_models.vertexai stubbed (ragas 0.4.3 vs langchain-community 0.4)"},
           "coverage": cov, "summary": summarise(per_item), "per_item": per_item}
    if a.noise:
        sub = samples[: a.noise]
        rerun = score(sub, make_metrics(), llm, emb, workers=a.workers)
        out["noise"] = {"n_samples": len(sub), "rerun": rerun,
                        "agreement": agreement({s["id"]: per_item[s["id"]] for s in sub}, rerun)}
    out["meta"]["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    path = Path(a.out or Path(a.result).with_name(f"ragas_{variant}.json"))
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"coverage": cov, "summary": out["summary"], "noise": out.get("noise", {}).get("agreement")},
                     ensure_ascii=False, indent=1))
    print("wrote", path)


if __name__ == "__main__":
    main()
