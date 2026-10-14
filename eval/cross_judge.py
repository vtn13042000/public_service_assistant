"""Agreement between two RAGAS outputs on the same items, e.g. the qwen3.6 judge vs a gpt-oss re-judge (judge-independence check).

    uv run python -m eval.ragas_run eval/results/guardrailed.json --limit 15 --judge-model gpt-oss \
        --out eval/results/crossjudge_gptoss_guardrailed.json
    uv run python -m eval.cross_judge eval/results/ragas_guardrailed.json eval/results/crossjudge_gptoss_guardrailed.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.ragas_run import agreement


def compare(a: dict, b: dict) -> dict:
    common = sorted(set(a["per_item"]) & set(b["per_item"]))
    pa = {i: a["per_item"][i] for i in common}
    pb = {i: b["per_item"][i] for i in common}
    means = {}
    for m in ("faithfulness", "context_precision", "context_recall"):
        for tag, p in (("a", pa), ("b", pb)):
            v = [x[m] for x in p.values() if x.get(m) is not None]
            means.setdefault(m, {})[tag] = round(sum(v) / len(v), 4) if v else None
    return {"judge_a": a["meta"]["judge_model"], "judge_b": b["meta"]["judge_model"], "items": common,
            "means_on_common_items": means, "agreement": agreement(pa, pb)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--out")
    x = ap.parse_args(argv)
    res = compare(json.loads(Path(x.a).read_text(encoding="utf-8")), json.loads(Path(x.b).read_text(encoding="utf-8")))
    out = Path(x.out or Path(x.b).with_suffix(".agreement.json"))
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "items"}, ensure_ascii=False, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
