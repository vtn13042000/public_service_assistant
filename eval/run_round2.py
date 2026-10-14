"""ROUND-2 item 7 (docs/05_log/ROUND-2.md): guardrailed_v2 and guardrailed_v2_q36, held-out first, then main + adversarial,
then RAGAS core on held-out and main, safety, report. One data/.RUNLOCK for all graph runs; each graph run is a fresh
process so its environment (RAG_ABBREV unset, APP_GENERATOR_MODEL) is in place before src is imported.

    uv run python -m eval.run_round2                         # guardrailed_v2, guardrailed_v2_q36
    uv run python -m eval.run_round2 guardrailed_v3          # Round 3: any variants, same order
    uv run python -m eval.run_round2 guardrailed_v4 --no-ragas   # graph runs + safety + report only
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from eval.run_variant import ROOT, VARIANTS, runlock

R = os.environ.get("EVAL_RESULTS", "eval/results")  # corpus v2: EVAL_CORPUS=v2 EVAL_RESULTS=eval/results/corpus_v2
V2 = ["guardrailed_v2", "guardrailed_v2_q36"]
MAIN, ADV, HELD = "data/testset.jsonl", "data/testset_adversarial.jsonl", "data/testset_heldout.jsonl"


def graph_runs(vs: list[str]) -> list[tuple[str, str, str]]:
    return [(v, HELD, f"{R}/heldout_{v}.json") for v in vs] + \
        [x for v in vs for x in ((v, MAIN, f"{R}/{v}.json"), (v, ADV, f"{R}/adversarial_{v}.json"))]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def sh(*args: str, env: dict | None = None) -> None:
    subprocess.run([sys.executable, "-W", "ignore", "-u", *args], cwd=ROOT, check=True, env=env)


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    ragas = "--no-ragas" not in args  # safety-only rounds (e.g. Round-4 v4)
    vs = [x for x in args if x != "--no-ragas"] or V2
    unknown = [v for v in vs if v not in VARIANTS]
    if unknown:
        raise SystemExit(f"unknown variants {unknown}")
    GRAPH = graph_runs(vs)
    with runlock(os.environ.get("EVAL_RUN_PURPOSE") or f"eval round ({', '.join(vs)})") as lock:
        env = {**os.environ, "EVAL_RUNLOCK_TOKEN": lock.read_text(encoding="utf-8")}
        for v, ts, out in GRAPH:
            t0 = time.time()
            sh("-m", "eval.run_variant", "--variant", v, "--testset", ts, "--out", out, env=env)
            n = len(json.loads((ROOT / out).read_text())["items"])
            log(f"DONE {v} {Path(ts).name}: {n} items in {time.time() - t0:.0f}s")
    for v in vs if ragas else []:
        for res, ts, out in ((f"{R}/heldout_{v}.json", HELD, f"{R}/ragas_heldout_{v}.json"),
                             (f"{R}/{v}.json", MAIN, f"{R}/ragas_{v}.json")):
            if (ROOT / out).exists():
                continue
            t0 = time.time()
            sh("-m", "eval.ragas_run", res, "--testset", ts, "--out", out)
            log(f"DONE RAGAS {out} in {time.time() - t0:.0f}s")
    for v, ts, out in GRAPH:
        sh("-m", "eval.safety", out, "--testset", ts)
    sh("-m", "eval.report")
    log("ALL DONE")


if __name__ == "__main__":
    main()
