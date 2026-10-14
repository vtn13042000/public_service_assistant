"""Run every test item through one graph variant and store what the metrics need (evaluation.md §3).

    uv run python -m eval.run_variant --variant guardrailed --testset data/testset.jsonl \
        --out eval/results/guardrailed.json [--limit 3] [--ids T-001,T-002] [--no-trace]

Variants: guardrailed | baseline | abl_no_resolve | abl_llm_support. Ablations are the guardrailed graph built with
`config={"ablation": <name>}` (flag exposed by src.graph.build_graph). Models, num_ctx, temperature and seed are
the same for every variant and are written into the result file's `config`.

Holds `data/.RUNLOCK` for the whole run (PROTOCOL: no DB/index rebuild while it exists).
Resumable: items already in the output file are skipped; the file is rewritten atomically after every item.
Adversarial file: `--testset data/testset_adversarial.jsonl --out eval/results/adversarial_<variant>.json`; each item's
`fixture` is applied by eval/injection.py and the row records `injection_delivered` (0 = the attack never reached the graph).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import functools
import hashlib
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any, Callable

from langchain_core.callbacks import BaseCallbackHandler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Flag sets come from src/presets.py, the table the product (CLI, web) also reads, so eval and product cannot drift.
# V1 reproduces the pre-ROUND-2 graph; src.presets imports only `os`, so this does not import src.tools.rag early.
from src.presets import V1, V2, V3, V4, V5  # noqa: E402
VARIANTS = {
    "guardrailed": {"graph": "guardrailed", "config": dict(V1)},
    "baseline": {"graph": "baseline", "config": {}},
    "abl_no_resolve": {"graph": "guardrailed", "config": {**V1, "ablation": "no_resolve"}},
    "abl_llm_support": {"graph": "guardrailed", "config": {**V1, "ablation": "llm_support"}},
    # ROUND-2 item 7 (docs/05_log/ROUND-2.md). RAG_ABBREV stays unset: item 4 measured it as negative and left it OFF.
    # env value None = must be unset.
    "guardrailed_v2": {"graph": "guardrailed", "env": {"RAG_ABBREV": None}, "config": dict(V2)},
    "guardrailed_v2_q36": {"graph": "guardrailed", "env": {"RAG_ABBREV": None, "APP_GENERATOR_MODEL": "qwen3.6"},
                           "config": dict(V2)},
    # Round 3: v2 + w-graph's audit-finding-1 fix (docs/05_log/workers/w-graph/base_title/RESULTS.md)
    "guardrailed_v3": {"graph": "guardrailed", "env": {"RAG_ABBREV": None}, "config": dict(V3)},
    # Round 4 candidate: v3 + scope_gate + citation_repair (src/presets.py "v4"); safety-only run on corpus v2
    "guardrailed_v4": {"graph": "guardrailed", "env": {"RAG_ABBREV": None}, "config": dict(V4)},
    # Round 5 candidate (AIProject-Lead2, 2026-10-10): v4 + head_noun_guard (src/presets.py "v5"); safety-only
    "guardrailed_v5": {"graph": "guardrailed", "env": {"RAG_ABBREV": None}, "config": dict(V5)},
}


def apply_variant_env(variant: str) -> None:
    """Set (or, for None, unset) the variant's environment before any src module reads it. RAG_ABBREV is read at import
    of src.tools.rag and the models at first use, so a variant with env must run in its own process (eval.run_variant CLI)."""
    env = VARIANTS[variant].get("env") or {}
    for k, v in env.items():
        if os.environ.get(k) == v:
            continue
        if "src.tools.rag" in sys.modules or (v is not None and os.environ.get(k) is not None):
            raise SystemExit(f"{variant} needs {k}={'<unset>' if v is None else v} before src is imported; "
                             "run it in a fresh process")
        if v is None:
            os.environ.pop(k)
        else:
            os.environ[k] = v

SEED = 42
RECURSION_LIMIT = 50
PID_RE = re.compile(r"^(?:db:[a-z_]+:|doc:)([^:]+):")


class CallCounter(BaseCallbackHandler):
    """Counts LLM calls (chat and completion endpoints) for one question."""

    def __init__(self) -> None:
        self.calls = 0

    def on_llm_start(self, *a: Any, **k: Any) -> None:
        self.calls += 1

    def on_chat_model_start(self, *a: Any, **k: Any) -> None:
        self.calls += 1


# ---------------------------------------------------------------- building the app

def real_deps() -> dict:
    """Local Ollama models + the three tools. Seed fixed so variants differ only in the graph."""
    from src.llm import get_llm, get_structured_judge, get_structured_llm
    from src.tools import db, rag, web
    return {"llm": get_llm(seed=SEED), "retriever": rag, "db": db, "web": web.web_search,
            "judge": functools.partial(get_structured_judge, seed=SEED),
            "classifier": functools.partial(get_structured_llm, seed=SEED)}


def build_app(variant: str, deps: dict | None = None):
    spec = VARIANTS[variant]
    deps = deps if deps is not None else real_deps()
    if spec["graph"] == "baseline":
        from src.baseline.graph import build_graph
        return build_graph(deps["llm"], deps["retriever"], deps["db"], deps.get("web"))
    from src.graph import build_graph
    return build_graph(deps["llm"], deps["retriever"], deps["db"], deps.get("web"), judge=deps.get("judge"),
                       classifier=deps.get("classifier"), config=dict(spec["config"]))


FREEZE = ROOT / "data" / "testset" / "FREEZE.md"
# Corpus v1 = the DB every run before Round 4 used (sha256 recorded in all v1 result files) and its 572-chunk index.
CORPUS_V1 = {"db_sha256": "1d5931c79dd487055e01a12ab99a1e07ee48cbc970b2b976f0662322bd291a0b", "chunks": 572}


def db_path() -> Path:
    """The DB the tools read (src/tools/db.py: APP_DB, default data/app.db)."""
    p = Path(os.environ.get("APP_DB", "data/app.db"))
    return p if p.is_absolute() else ROOT / p


def chroma_path() -> Path:
    """The index the retriever reads (src/ingest.py:chroma_dir: CHROMA_DIR, default data/chroma)."""
    p = Path(os.environ.get("CHROMA_DIR", ROOT / "data" / "chroma"))
    return p if p.is_absolute() else ROOT / p


def shared_artifacts() -> tuple[Path, Path]:
    return db_path(), chroma_path() / "chroma.sqlite3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze(testset: Path, freeze: Path = FREEZE) -> str | None:
    """sha256 of `testset`; raises SystemExit if FREEZE.md lists the file with a different hash.
    Returns the frozen hash (None if the file is not listed, e.g. a scratch test set)."""
    if not freeze.exists():
        return None
    name = testset.name
    for line in freeze.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and len(parts[0]) == 64 and Path(parts[1]).name == name:
            if sha256(testset) != parts[0]:
                raise SystemExit(f"{testset} does not match its frozen sha256 in {freeze}; not running")
            return parts[0]
    return None


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def artifact_fingerprint() -> dict:
    """sha256 of the DB and the Chroma sqlite, so a rebuild during a run is detectable afterwards."""
    return {_rel(p): sha256(p) if p.exists() else None for p in shared_artifacts()}


def corpus_info() -> dict:
    """Which corpus this run reads: paths, DB table row counts, Chroma chunk count (both read-only), and a label.
    The label is "v1" only when the DB hash and chunk count equal corpus v1. Any other corpus needs EVAL_CORPUS
    (e.g. EVAL_CORPUS=v2), so a number can never be filed under the wrong corpus."""
    import sqlite3
    db, ch = db_path(), chroma_path()
    counts, chunks = {}, None
    if db.exists():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table' and name not like '%fts%' "
                                            "and name not like 'sqlite_%' order by name")]
        counts = {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tables}
        con.close()
    if (ch / "chroma.sqlite3").exists():
        con = sqlite3.connect(f"file:{ch / 'chroma.sqlite3'}?mode=ro", uri=True)
        chunks = con.execute("select count(*) from embeddings").fetchone()[0]
        con.close()
    db_sha = sha256(db) if db.exists() else None
    is_v1 = db_sha == CORPUS_V1["db_sha256"] and chunks == CORPUS_V1["chunks"]
    label = os.environ.get("EVAL_CORPUS") or ("v1" if is_v1 else None)
    if label is None:
        raise SystemExit(f"corpus at {_rel(db)} / {_rel(ch)} is not corpus v1 (db sha {db_sha and db_sha[:12]}, "
                         f"{chunks} chunks); set EVAL_CORPUS=<label> so results are labelled")
    if label == "v1" and not is_v1:
        raise SystemExit("EVAL_CORPUS=v1 but the DB/index do not match corpus v1")
    return {"label": label, "db_path": _rel(db), "chroma_path": _rel(ch), "db_sha256": db_sha,
            "db_counts": counts, "chunks": chunks}


def run_config(variant: str, testset: Path) -> dict:
    from src import llm
    return {
        "variant": variant, "graph": VARIANTS[variant]["graph"], "graph_config": VARIANTS[variant]["config"],
        "llm_model": llm.generator_model(), "judge_model": llm.judge_model(),
        # every behaviour switch in effect: graph flags above, plus APP_* / RAG_* environment variables
        "env_flags": {k: v for k, v in sorted(os.environ.items()) if k.startswith(("APP_", "RAG_"))},
        "embed_model": os.environ.get("APP_EMBED_MODEL", llm.EMBED_MODEL),
        "num_ctx": llm.NUM_CTX, "temperature": 0, "seed": SEED, "recursion_limit": RECURSION_LIMIT,
        "testset": str(testset), "testset_sha256": sha256(testset), "testset_frozen_sha256": verify_freeze(testset),
        "corpus": corpus_info(),
        "artifacts_at_start": artifact_fingerprint(),
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "langfuse_tag": f"variant={variant}",
    }


# ---------------------------------------------------------------- reading the final state

def _ev_list(state: dict) -> list[dict]:
    """Evidence the answer was drafted from, in graph order: `evidence` (guardrailed) or the professor's
    documents/db_results/web_results (baseline), normalised to {evidence_id, text, tier}."""
    if state.get("evidence"):
        return [{"evidence_id": e.get("evidence_id"), "text": e.get("text") or "", "tier": e.get("tier")}
                for e in state["evidence"]]
    out = []
    for key, tier in (("documents", "corpus"), ("db_results", "db"), ("web_results", "web")):
        for d in state.get(key) or []:
            meta = d.get("meta") or {}
            out.append({"evidence_id": meta.get("evidence_id") or (f"web:{meta['url']}" if meta.get("url") else None),
                        "text": d.get("text") or "", "tier": tier})
    return out


def extract(state: dict) -> dict:
    """One result row from a final graph state. Pure (tested with fakes)."""
    from eval.safety import cited_ids
    ev = _ev_list(state)
    ev_ids = [e["evidence_id"] for e in ev if e["evidence_id"]]
    pid, inferred = state.get("procedure_id"), False
    if not pid:  # baseline has no resolver: the procedure of the top-ranked evidence is what it answered about
        for i in ev_ids:
            m = PID_RE.match(i)
            if m:
                pid, inferred = m.group(1), True
                break
    claims = [{k: c.get(k) for k in ("text", "type", "evidence_ids", "verdict")} for c in state.get("claims") or []]
    cited = []
    for i in [x for c in claims for x in c.get("evidence_ids") or []] + cited_ids(state.get("generation")):
        if i not in cited:
            cited.append(i)
    refusal = state.get("refusal")
    fresh = state.get("freshness")
    return {
        "outcome": state.get("outcome"), "answer": state.get("generation"),
        "refusal_type": (refusal or {}).get("type"), "refusal": refusal,
        "procedure_id": pid, "procedure_id_inferred": inferred, "candidates": state.get("candidates"),
        "claims": claims, "cited_ids": cited, "state_evidence_ids": ev_ids,
        "contexts": [e["text"] for e in ev], "context_ids": [e["evidence_id"] for e in ev],
        "freshness": fresh,
        "web_called": any((e["tier"] or "").startswith("web") for e in ev) or bool((fresh or {}).get("web_checked"))
        or bool((fresh or {}).get("web_links")) or "web_error" in (fresh or {}),
        "errors": list(state.get("errors") or []),
    }


# ---------------------------------------------------------------- running

def load_result(out: Path) -> dict:
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    return {"config": {}, "items": {}}


def save_result(res: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out)


def make_callback(variant: str, item: dict, trace: bool):
    if not trace:
        return None
    from src.tracing import get_callback
    return get_callback(trace_name=item["id"], tags=[f"variant={variant}", f"testset_id={item['id']}"],
                        metadata={"test_id": item["id"], "category": item["category"], "variant": variant})


def run_items(app, variant: str, items: list[dict], out: Path, config: dict, trace: bool = True,
              log: Callable[[str], None] = print, deps: dict | None = None) -> dict:
    """Run and store each item not yet in `out`. An item with a `fixture` (adversarial file) gets its own app
    built from `deps` with the fixture applied (eval/injection.py); `src/` has no test hook."""
    from eval.injection import apply_fixture
    res = load_result(out)
    if res["items"] and res["config"].get("variant") not in (None, variant):
        raise SystemExit(f"{out} holds variant {res['config'].get('variant')!r}, not {variant!r}")
    res["config"] = res["config"] or config
    graph = VARIANTS[variant]["graph"]
    for n, it in enumerate(items, 1):
        if it["id"] in res["items"]:
            continue
        item_app, stats = app, None
        if it.get("fixture"):
            if deps is None:
                raise ValueError(f"{it['id']} has a fixture; run_items needs `deps` to build an injected app")
            fixed, stats = apply_fixture(deps, it["fixture"])
            item_app = build_app(variant, fixed)
        counter = CallCounter()
        cb = make_callback(variant, it, trace)
        inputs = {"query": it["question"]}
        if graph == "guardrailed" and it.get("locality"):
            inputs["locality"] = it["locality"]
        t0 = time.perf_counter()
        try:
            state = item_app.invoke(inputs, config={"callbacks": [h for h in (cb, counter) if h],
                                               "recursion_limit": RECURSION_LIMIT})
            row = extract(state)
        except Exception as e:  # noqa: BLE001 — record and continue; a crash is a result too
            row = {"outcome": None, "answer": None, "errors": [f"{type(e).__name__}: {e}"]}
        row.update({"question": it["question"], "category": it["category"],
                    "latency_s": round(time.perf_counter() - t0, 3), "llm_calls": counter.calls,
                    "trace_id": getattr(cb, "last_trace_id", None) if cb else None})
        if stats is not None:
            row.update({"fixture": it["fixture"], "injection_delivered": stats.delivered})
        res["items"][it["id"]] = row
        save_result(res, out)
        log(f"[{n}/{len(items)}] {it['id']} gold={it['gold']['outcome']} pred={row['outcome']} "
            f"{row['latency_s']}s calls={row['llm_calls']}")
    res["config"]["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if "artifacts_at_start" in res["config"]:
        res["config"]["artifacts_at_end"] = end = artifact_fingerprint()
        if end != res["config"]["artifacts_at_start"]:
            log(f"WARNING: DB/index changed during the run: {res['config']['artifacts_at_start']} -> {end}")
    save_result(res, out)
    return res


def select_items(items: list[dict], ids: str | None, limit: int | None) -> list[dict]:
    items = [it for it in items if it.get("status", "ready") == "ready"]
    if ids:
        want = set(ids.split(","))
        items = [it for it in items if it["id"] in want]
    return items[:limit] if limit else items


RUNLOCK = ROOT / "data" / ".RUNLOCK"


@contextlib.contextmanager
def runlock(purpose: str, path: Path = RUNLOCK):
    """PROTOCOL shared-artifacts lock: `data/.RUNLOCK` = "w-eval <ISO> <purpose>" while this run reads the DB/index.
    Refuses to start if another run holds it (one file cannot record two holders). Removed on any exit, including
    exceptions and SIGTERM, but only if it is still ours."""
    token = os.environ.get("EVAL_RUNLOCK_TOKEN")  # set by a parent driver (eval/run_round2.py) that holds the lock
    if token and path.exists() and path.read_text(encoding="utf-8") == token:
        yield path
        return
    stamp = f"w-eval {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {purpose}\n"
    try:
        with path.open("x", encoding="utf-8") as f:
            f.write(stamp)
    except FileExistsError:
        raise SystemExit(f"{path} is held: {path.read_text(encoding='utf-8').strip()!r}; not starting") from None
    prev = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # turn SIGTERM into SystemExit so `finally` runs
    try:
        yield path
    finally:
        signal.signal(signal.SIGTERM, prev)
        try:
            if path.read_text(encoding="utf-8") == stamp:
                path.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    ap.add_argument("--testset", default="data/testset.jsonl")
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids")
    ap.add_argument("--no-trace", action="store_true")
    a = ap.parse_args(argv)
    testset = Path(a.testset)
    with runlock(f"eval {a.variant} {testset.name}"):
        run_one(a.variant, testset, Path(a.out or f"eval/results/{a.variant}.json"), a.ids, a.limit, not a.no_trace)


V1_RESULTS = ROOT / "eval" / "results"


def check_out_dir(label: str, out: Path) -> None:
    """Corpus-v1 results live in eval/results/ (or a subfolder such as slice/); any other corpus must write under
    eval/results/corpus_<label>/. Out-of-tree paths (tests, scratch) are not checked."""
    parent = (out if out.is_absolute() else ROOT / out).resolve().parent
    try:
        rel = parent.relative_to(V1_RESULTS.resolve()).parts
    except ValueError:
        return
    in_corpus_dir = bool(rel) and rel[0].startswith("corpus_")
    if label == "v1" and in_corpus_dir or label != "v1" and (not rel or rel[0] != f"corpus_{label}"):
        raise SystemExit(f"corpus {label} results must go to "
                         f"{'eval/results/' if label == 'v1' else f'eval/results/corpus_{label}/'}, not {_rel(parent)}/")


def run_one(variant: str, testset: Path, out: Path, ids: str | None = None, limit: int | None = None,
            trace: bool = True) -> dict:
    """One variant × one test set. The caller holds data/.RUNLOCK (main, or eval/run_all.py for a whole sequence)."""
    from eval.safety import load_testset, verify_records
    apply_variant_env(variant)
    verify_records()
    verify_freeze(testset)
    check_out_dir(corpus_info()["label"], out)
    items = select_items(load_testset(testset), ids, limit)
    deps = real_deps()
    app = build_app(variant, deps)
    try:
        return run_items(app, variant, items, out, run_config(variant, testset), trace=trace, deps=deps)
    finally:
        if trace:
            from src.tracing import flush
            flush()


if __name__ == "__main__":
    main()
