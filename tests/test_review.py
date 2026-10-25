import os
import tempfile
import pytest
from review_engine import HumanReviewEngine

def test_approve_action():
    review = HumanReviewEngine.process_human_review(
        record_id="LED_20001",
        action="Approve",
        original_ai_decision="match"
    )
    assert review["human_reviewed"] is True
    assert review["human_decision"] == "approved"
    assert review["human_reviewer_action"] == "Approve"
    assert review["human_override"] is False
    assert review["original_ai_decision"] == "match"
    assert review["final_decision"] == "match"

def test_reject_action():
    review = HumanReviewEngine.process_human_review(
        record_id="LED_20002",
        action="Reject",
        original_ai_decision="match"
    )
    assert review["human_reviewed"] is True
    assert review["human_decision"] == "rejected"
    assert review["human_reviewer_action"] == "Reject"
    assert review["human_override"] is True
    assert review["original_ai_decision"] == "match"
    assert review["final_decision"] == "no_match"

def test_escalate_action():
    review = HumanReviewEngine.process_human_review(
        record_id="LED_20003",
        action="Escalate",
        original_ai_decision="match"
    )
    assert review["human_reviewed"] is True
    assert review["human_decision"] == "escalated"
    assert review["human_reviewer_action"] == "Escalate"
    assert review["human_override"] is True
    assert review["final_decision"] == "exception_escalated"

def test_override_rate_calculation():
    reviews = {
        "LED_1": {"human_override": False},
        "LED_2": {"human_override": True},
        "LED_3": {"human_override": True},
        "LED_4": {"human_override": False}
    }
    rate = HumanReviewEngine.calculate_override_rate(reviews)
    assert rate == 50.0 # 2 / 4 = 50%

def test_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "human_reviews.json")
        review = HumanReviewEngine.process_human_review("LED_999", "Reject", "match")
        reviews_dict = {"LED_999": review}
        
        HumanReviewEngine.save_human_reviews(reviews_dict, filepath)
        loaded = HumanReviewEngine.load_human_reviews(filepath)
        
        assert "LED_999" in loaded
        assert loaded["LED_999"]["human_reviewer_action"] == "Reject"
        assert loaded["LED_999"]["human_override"] is True

def test_repeated_decision_updates_action_cleanly():
    # Auditor approves item first
    rev1 = HumanReviewEngine.process_human_review("LED_20005", "Approve", "match")
    assert rev1["human_reviewer_action"] == "Approve"
    assert rev1["human_override"] is False
    
    # Auditor changes mind and rejects item (overriding AI match)
    rev2 = HumanReviewEngine.process_human_review("LED_20005", "Reject", "match")
    assert rev2["human_reviewer_action"] == "Reject"
    assert rev2["human_override"] is True
    assert rev2["original_ai_decision"] == "match"
    assert rev2["final_decision"] == "no_match"

def test_original_ai_decision_and_run_metrics_remain_immutable():
    # Ensure human review action does NOT mutate the original_ai_decision property
    rev = HumanReviewEngine.process_human_review("LED_20006", "Reject", original_ai_decision="match")
    assert rev["original_ai_decision"] == "match" # Preserved original AI proposal
    assert rev["final_decision"] == "no_match"    # Human override decision
