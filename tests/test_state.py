"""AgentState keeps the professor's fields (guidance.md A1) and adds ours (architecture.md §3)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.state import INTENTS, OUTCOMES, REFUSAL_TYPES, AgentState  # noqa: E402

PROFESSOR = {"query", "sub_queries", "documents", "db_results", "web_results", "grades", "route", "iteration", "generation"}
ARCHITECTURE = {"need", "candidates", "procedure_id", "evidence", "draft", "claims", "outcome", "refusal", "freshness", "errors"}


def test_professor_fields_kept():
    assert PROFESSOR <= set(AgentState.__annotations__)


def test_architecture_fields_added():
    assert ARCHITECTURE <= set(AgentState.__annotations__)


def test_enums():
    assert set(OUTCOMES) == {"answer", "answer_partial", "clarify", "refuse", "out_of_scope"}
    assert len(REFUSAL_TYPES) == 5 and "system_error" in REFUSAL_TYPES
    assert "update" in INTENTS
