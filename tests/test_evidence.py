import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evidence import (  # noqa: E402
    MIN_TIER, TIERS, can_support, db_id, doc_id, make_evidence, sort_by_tier, tier_at_least, web_id,
)


def test_tier_order():
    assert TIERS == ("db", "corpus", "web_official", "web_other")
    assert tier_at_least("db", "corpus")
    assert tier_at_least("corpus", "corpus")
    assert not tier_at_least("web_official", "corpus")
    assert not tier_at_least("bogus", "web_other")


def test_min_tier_l2():
    for c in ("document_item", "fee", "agency", "deadline"):
        assert MIN_TIER[c] == "db"
        assert can_support("db", c) and not can_support("corpus", c)
    for c in ("steps", "conditions", "legal_basis"):
        assert can_support("corpus", c) and not can_support("web_official", c)
    assert can_support("web_official", "update_notice")
    assert not can_support("web_other", "update_notice")
    assert not can_support("web_official", "something_unclassified")


def test_ids():
    assert db_id("required_documents", "KS-01", 3) == "db:required_documents:KS-01:3"
    assert doc_id("KS-01", "required_documents", 2) == "doc:KS-01:required_documents:2"
    w = web_id("https://dichvucong.gov.vn/p/home/dvc-tthc-thu-tuc-hanh-chinh-chi-tiet.html?ma_thu_tuc=1.001193")
    assert w.startswith("web:") and len(w) == 16 and w == web_id(" https://dichvucong.gov.vn/p/home/dvc-tthc-thu-tuc-hanh-chinh-chi-tiet.html?ma_thu_tuc=1.001193 ")


def test_make_evidence_validates():
    e = make_evidence(db_id("fees", "KS-01", 1), "db", "  miễn lệ phí  ", procedure_id="KS-01", section="fees",
                      structured={"value": "miễn lệ phí"})
    assert e["text"] == "miễn lệ phí" and e["tier"] == "db" and e["source_url"] is None
    with pytest.raises(ValueError):
        make_evidence("doc:KS-01:fees:0", "db", "x")
    with pytest.raises(ValueError):
        make_evidence("db:fees:KS-01:1", "db", "x", section="nonsense")
    with pytest.raises(ValueError):
        make_evidence("db:fees:KS-01:1", "db", "   ")
    with pytest.raises(ValueError):
        make_evidence("web:abc", "web", "x")


def test_sort_by_tier():
    ev = [make_evidence("web:a", "web_other", "a"), make_evidence("doc:X:steps:0", "corpus", "b"),
          make_evidence("db:fees:X:1", "db", "c"), make_evidence("web:b", "web_official", "d")]
    assert [e["tier"] for e in sort_by_tier(ev)] == list(TIERS)
