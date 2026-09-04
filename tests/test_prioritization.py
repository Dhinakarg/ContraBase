"""
Unit tests for Deterministic Risk Prioritization Layer in prioritization.py.
Verifies determinism, ranking rules, resilience to missing fields, zero-review state, and review action persistence.
"""

import pytest
from prioritization import RiskPrioritizer
from review_engine import HumanReviewEngine


def test_deterministic_prioritization_same_input_same_order():
    """Verify that identical input always produces the exact same ordering and priority score."""
    items = [
        {"ID": "REC_01", "Amount": 500000.0, "Materiality": "⚠️ High", "Reason Code": "amount_variance", "System Confidence": 85.0, "Currency": "INR"},
        {"ID": "REC_02", "Amount": 10000.0, "Materiality": "Normal", "Reason Code": "date_shift", "System Confidence": 92.0, "Currency": "INR"},
        {"ID": "REC_03", "Amount": 1200000.0, "Materiality": "⚠️ High", "Reason Code": "duplicate", "System Confidence": 70.0, "Currency": "USD"}
    ]

    res1 = RiskPrioritizer.sort_items(items, sort_key="Highest Risk")
    res2 = RiskPrioritizer.sort_items(items, sort_key="Highest Risk")

    assert [x["ID"] for x in res1] == [x["ID"] for x in res2]
    assert [x["_priority"]["score"] for x in res1] == [x["_priority"]["score"] for x in res2]


def test_high_risk_ranks_above_low_risk():
    """Verify high-risk transactions (high value, amount variance, duplicate) rank above low-risk transactions."""
    high_risk_item = {
        "ID": "HIGH_01",
        "Amount": 1840000.0,
        "Materiality": "⚠️ High",
        "Reason Code": "amount_variance",
        "Policy Reason": "High materiality with amount variance and duplicate candidate",
        "System Confidence": 75.0,
        "Currency": "INR"
    }

    low_risk_item = {
        "ID": "LOW_01",
        "Amount": 1500.0,
        "Materiality": "Normal",
        "Reason Code": "date_shift",
        "Policy Reason": "Minor date shift",
        "System Confidence": 94.0,
        "Currency": "INR"
    }

    sorted_list = RiskPrioritizer.sort_items([low_risk_item, high_risk_item], sort_key="Highest Risk")

    assert sorted_list[0]["ID"] == "HIGH_01"
    assert sorted_list[0]["_priority"]["priority_band"] == "HIGH PRIORITY"
    assert sorted_list[1]["ID"] == "LOW_01"


def test_missing_optional_signals_do_not_crash():
    """Verify that minimal or missing fields do not crash the evaluation."""
    sparse_item = {"ID": "SPARSE_01"}
    
    p_info = RiskPrioritizer.evaluate_priority(sparse_item)
    assert "score" in p_info
    assert "priority_band" in p_info
    assert "explanation" in p_info

    sorted_sparse = RiskPrioritizer.sort_items([sparse_item], sort_key="Highest Risk")
    assert len(sorted_sparse) == 1
    assert sorted_sparse[0]["ID"] == "SPARSE_01"


def test_zero_review_state_remains_clean():
    """Verify that an empty review list returns an empty list without errors."""
    empty_result = RiskPrioritizer.sort_items([], sort_key="Highest Risk")
    assert empty_result == []


def test_review_actions_continue_to_persist(tmp_path):
    """Verify that human review actions (Approve, Reject, Escalate) persist cleanly."""
    file_p = str(tmp_path / "test_human_reviews.json")
    
    rev_app = HumanReviewEngine.process_human_review("REC_100", "Approve", original_ai_decision="match")
    rev_db = {"REC_100": rev_app}
    
    HumanReviewEngine.save_human_reviews(rev_db, file_path=file_p)
    loaded_db = HumanReviewEngine.load_human_reviews(file_path=file_p)
    
    assert "REC_100" in loaded_db
    assert loaded_db["REC_100"]["human_reviewer_action"] == "Approve"
    assert loaded_db["REC_100"]["human_override"] is False

    rev_rej = HumanReviewEngine.process_human_review("REC_101", "Reject", original_ai_decision="match")
    loaded_db["REC_101"] = rev_rej
    HumanReviewEngine.save_human_reviews(loaded_db, file_path=file_p)
    
    reloaded_db = HumanReviewEngine.load_human_reviews(file_path=file_p)
    assert "REC_101" in reloaded_db
    assert reloaded_db["REC_101"]["human_override"] is True
