"""Named graph presets: the one place that says which flags make v1, v2, v3 and the baseline.

The product (src/cli.py, src/web/app.py) and the evaluation (eval/run_variant.py) both read this table, so a demo run
and a reported number cannot use different flags. Every run records the preset name (state `preset`, LangFuse
metadata/tags, CLI and JSON output).

- v1: the release graph as first evaluated (draft prompt v1, strict citation parsing).
- v2: ROUND-2 item 7 (docs/05_log/ROUND-2.md): draft prompt v2, tolerant citations, story_rewrite, f2_rule.
- v3: ROUND-3 (docs/05_log/ROUND-3.md): v2 + base_title_preference. The default until 2026-10-10 15:36Z.
- v4: ROUND-4 items (c) and (d) (docs/05_log/ROUND-4-DATA.md): v3 + scope_gate + citation_repair. The live default
  from 2026-10-10 15:36Z to 19:29Z.
- v5: Round 5 (ROUND-4-DATA.md item (f)): v4 + head_noun_guard. The live default since 2026-10-10 19:29Z
  (owner's decision; official v5 run identical to v4 on every set, fixes the owner's khai sinh question).
- baseline: the professor's skeleton graph (src/baseline), no flags.
`env` lists environment variables a preset needs; None = must be unset (RAG_ABBREV stayed off, ROUND-2 item 4).
They are read when src.tools.rag is imported, so `apply_env` must run before that import.
"""
from __future__ import annotations

import os

V1 = {"draft_prompt": "v1", "citation_parse": "strict"}
V2 = {"draft_prompt": "v2", "citation_parse": "tolerant", "story_rewrite": True, "f2_rule": "distinguishing_words"}
V3 = {**V2, "base_title_preference": True}
V4 = {**V3, "scope_gate": "in_scope", "citation_repair": "tier"}
V5 = {**V4, "head_noun_guard": True}

GRAPH_PRESETS: dict[str, dict] = {
    "v1": {"graph": "guardrailed", "config": V1, "env": {}},
    "v2": {"graph": "guardrailed", "config": V2, "env": {"RAG_ABBREV": None}},
    "v3": {"graph": "guardrailed", "config": V3, "env": {"RAG_ABBREV": None}},
    "v4": {"graph": "guardrailed", "config": V4, "env": {"RAG_ABBREV": None}},
    "v5": {"graph": "guardrailed", "config": V5, "env": {"RAG_ABBREV": None}},
    "baseline": {"graph": "baseline", "config": {}, "env": {}},
}
DEFAULT_PRESET = "v5"
GUARDRAILED_PRESETS = tuple(k for k, v in GRAPH_PRESETS.items() if v["graph"] == "guardrailed")


def resolve_preset(variant: str = "guardrailed", preset: str | None = None) -> str:
    """Preset name for a (variant, preset) choice: baseline → 'baseline'; guardrailed → `preset` or DEFAULT_PRESET."""
    if variant == "baseline":
        if preset not in (None, "baseline"):
            raise ValueError(f"preset {preset!r} does not apply to the baseline graph")
        return "baseline"
    if variant != "guardrailed":
        raise ValueError(f"unknown variant {variant!r}")
    name = preset or DEFAULT_PRESET
    if name not in GUARDRAILED_PRESETS:
        raise ValueError(f"unknown preset {name!r}; expected one of {GUARDRAILED_PRESETS}")
    return name


def graph_config(name: str) -> dict:
    """A fresh copy of the preset's graph config (callers may add keys without touching the table)."""
    return dict(GRAPH_PRESETS[name]["config"])


def apply_env(name: str) -> None:
    """Set (or, for None, unset) the preset's environment variables."""
    for k, v in GRAPH_PRESETS[name]["env"].items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
