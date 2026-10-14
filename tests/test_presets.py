"""Named presets (src/presets.py): the flag sets documented in ROUND-2.md / ROUND-3.md, used by product and eval."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.presets import DEFAULT_PRESET, GRAPH_PRESETS, apply_env, graph_config, resolve_preset  # noqa: E402

# documented flag sets: ROUND-2.md items 1, 2, 5, 8 (v2 = item 7's run), ROUND-3.md item 1 (v3); v1 = release flags
DOCUMENTED = {
    "v1": {"draft_prompt": "v1", "citation_parse": "strict"},
    "v2": {"draft_prompt": "v2", "citation_parse": "tolerant", "story_rewrite": True, "f2_rule": "distinguishing_words"},
    "v3": {"draft_prompt": "v2", "citation_parse": "tolerant", "story_rewrite": True, "f2_rule": "distinguishing_words",
           "base_title_preference": True},
    "v4": {"draft_prompt": "v2", "citation_parse": "tolerant", "story_rewrite": True, "f2_rule": "distinguishing_words",
           "base_title_preference": True, "scope_gate": "in_scope", "citation_repair": "tier"},
    "v5": {"draft_prompt": "v2", "citation_parse": "tolerant", "story_rewrite": True, "f2_rule": "distinguishing_words",
           "base_title_preference": True, "scope_gate": "in_scope", "citation_repair": "tier", "head_noun_guard": True},
    "baseline": {},
}


def _round_doc(name: str) -> str:
    """Text of a round log under docs/05_log; skip when the log is not in this checkout (it is not published)."""
    path = ROOT / "docs/05_log" / name
    if not path.exists():
        pytest.skip(f"{path.relative_to(ROOT)} not in this checkout (round logs are not published)")
    return path.read_text(encoding="utf-8")


def test_preset_table_equals_documented_flag_sets():
    assert {k: v["config"] for k, v in GRAPH_PRESETS.items()} == DOCUMENTED
    assert GRAPH_PRESETS["baseline"]["graph"] == "baseline"
    assert all(GRAPH_PRESETS[k]["graph"] == "guardrailed" for k in ("v1", "v2", "v3", "v4", "v5"))
    assert DEFAULT_PRESET == "v5"


def test_each_flag_is_named_in_the_round_documents():
    text = _round_doc("ROUND-2.md") + _round_doc("ROUND-3.md")
    for name in ("v2", "v3"):
        for k, v in GRAPH_PRESETS[name]["config"].items():
            if k == "draft_prompt":
                continue  # ROUND-2 item 2 names it in words ("Draft prompt v2", default on)
            assert f'"{k}"' in text and json.dumps(v) in text, (name, k)


def test_v4_flags_are_named_in_round_4_data():
    text = _round_doc("ROUND-4-DATA.md")
    extra = {k: v for k, v in GRAPH_PRESETS["v4"]["config"].items() if k not in GRAPH_PRESETS["v3"]["config"]}
    assert extra == {"scope_gate": "in_scope", "citation_repair": "tier"}
    for k, v in extra.items():
        assert f'{{"{k}": {json.dumps(v)}}}' in text, k


def test_v5_flag_is_named_in_round_4_data():
    text = _round_doc("ROUND-4-DATA.md")
    extra = {k: v for k, v in GRAPH_PRESETS["v5"]["config"].items() if k not in GRAPH_PRESETS["v4"]["config"]}
    assert extra == {"head_noun_guard": True}
    assert '{"head_noun_guard": true}' in text


def test_eval_variants_use_the_same_flags():
    pytest.importorskip("langchain_core")
    from eval.run_variant import VARIANTS
    assert VARIANTS["guardrailed"]["config"] == GRAPH_PRESETS["v1"]["config"]  # v1 = release flags
    assert VARIANTS["guardrailed_v2"]["config"] == GRAPH_PRESETS["v2"]["config"]
    assert VARIANTS["guardrailed_v3"]["config"] == GRAPH_PRESETS["v3"]["config"]
    if "guardrailed_v5" in VARIANTS:
        assert VARIANTS["guardrailed_v5"]["config"] == GRAPH_PRESETS["v5"]["config"]


def test_resolve_preset():
    assert resolve_preset() == "v5"
    assert resolve_preset("guardrailed", "v1") == "v1"
    assert resolve_preset("baseline") == "baseline"
    with pytest.raises(ValueError):
        resolve_preset("baseline", "v3")
    with pytest.raises(ValueError):
        resolve_preset("guardrailed", "v9")


def test_graph_config_is_a_copy_and_env_is_applied(monkeypatch):
    graph_config("v3")["base_title_preference"] = False
    assert GRAPH_PRESETS["v3"]["config"]["base_title_preference"] is True
    monkeypatch.setenv("RAG_ABBREV", "1")
    apply_env("v3")
    import os
    assert "RAG_ABBREV" not in os.environ


def test_cli_default_runs_v3_and_reports_it(monkeypatch, capsys):
    from src import cli
    from tests.fakes import FakeLLM, need, run
    seen = {}

    def fake_build_app(variant, callbacks=None, trace=None, preset=None):
        seen["preset"] = preset

        class App:
            def invoke(self, init):
                s, _ = run(init["query"], FakeLLM(need=need("agency", "đăng ký khai sinh")), init=init,
                           config=graph_config(preset))
                return s
        return App()
    monkeypatch.setattr(cli, "build_app", fake_build_app)
    monkeypatch.setattr(cli, "_tracing", lambda *a, **k: (None, None, None))
    assert cli.main(["Đăng ký khai sinh nộp ở đâu?"]) == 0
    assert seen["preset"] == "v5" and "preset: v5" in capsys.readouterr().out
    cli.main(["Đăng ký khai sinh nộp ở đâu?", "--preset", "v1", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert seen["preset"] == "v1" and out["preset"] == "v1"


def test_preset_is_in_state_and_trace():
    from tests.fakes import FakeLLM, need, run
    s, parts = run("Đăng ký khai sinh nộp ở đâu?", FakeLLM(need=need("agency", "đăng ký khai sinh")),
                   init={"preset": "v3"}, config=graph_config("v3"))
    assert s["preset"] == "v3"
    meta = next(m for n, m in parts["trace"] if n == "assess_need")
    assert meta["preset"] == "v3" and meta["graph_config"]["base_title_preference"] is True
