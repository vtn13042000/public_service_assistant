"""The full evaluation sequence (lead order, 2026-10-10), graph runs under one data/.RUNLOCK, then RAGAS, safety, report.

    uv run python -m eval.run_all [--skip-ragas] [--only-graph]

Every step is resumable (run_variant skips finished items; a finished RAGAS output is not recomputed), so re-running
after an interruption continues where it stopped.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from eval.run_variant import ROOT, runlock, run_one

R = Path("eval/results")
MAIN, ADV, HELD = Path("data/testset.jsonl"), Path("data/testset_adversarial.jsonl"), Path("data/testset_heldout.jsonl")
GRAPH_RUNS = [  # (variant, test set, output) in the lead's order
    ("baseline", MAIN, R / "baseline.json"), ("baseline", ADV, R / "adversarial_baseline.json"),
    ("guardrailed", MAIN, R / "guardrailed.json"), ("guardrailed", ADV, R / "adversarial_guardrailed.json"),
    ("guardrailed", HELD, R / "heldout_guardrailed.json"),
    ("abl_no_resolve", MAIN, R / "abl_no_resolve.json"), ("abl_llm_support", MAIN, R / "abl_llm_support.json"),
]
RAGAS_RUNS = [  # (result, testset, extra args)
    (R / "baseline.json", MAIN, ["--relevancy", "20"]),
    (R / "guardrailed.json", MAIN, ["--relevancy", "20", "--noise", "15"]),
    (R / "heldout_guardrailed.json", HELD, []),
    (R / "abl_no_resolve.json", MAIN, []), (R / "abl_llm_support.json", MAIN, []),
]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ragas", action="store_true")
    ap.add_argument("--only-graph", action="store_true")
    ap.add_argument("--ragas-only", action="store_true", help="skip the graph runs (they are finished); RAGAS, safety, report")
    a = ap.parse_args(argv)
    if not a.ragas_only:
        _graph_runs()
    if a.only_graph:
        return
    _post(a)


def _graph_runs() -> None:
    with runlock("eval run_all (baseline, guardrailed, heldout, ablations)"):
        for variant, ts, out in GRAPH_RUNS:
            t0 = time.time()
            res = run_one(variant, ROOT / ts, ROOT / out)
            n = len(res["items"])
            log(f"DONE {variant} {ts.name}: {n} items in {time.time() - t0:.0f}s")


def _post(a) -> None:
    if not a.skip_ragas:
        for res, ts, extra in RAGAS_RUNS:
            variant = json.loads((ROOT / res).read_text())["config"]["variant"]
            prefix = "heldout_" if ts == HELD else ""
            out = R / f"ragas_{prefix}{variant}.json"
            if (ROOT / out).exists():
                log(f"skip RAGAS {out} (exists)")
                continue
            t0 = time.time()
            subprocess.run([sys.executable, "-W", "ignore", "-m", "eval.ragas_run", str(res), "--testset", str(ts),
                            "--out", str(out), *extra], cwd=ROOT, check=True)
            log(f"DONE RAGAS {out} in {time.time() - t0:.0f}s")
    for res, ts in [(o, t) for _, t, o in GRAPH_RUNS]:
        subprocess.run([sys.executable, "-m", "eval.safety", str(res), "--testset", str(ts)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "eval.report"], cwd=ROOT, check=True)
    log("ALL DONE")


if __name__ == "__main__":
    main()
