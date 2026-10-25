"""
Unit tests for CloseReadinessEvaluator in close_readiness.py.
Verifies the 3 deterministic operational states:
1. 🔴 EXCEPTIONS BLOCK CLOSE
2. 🟡 CONTROLLER REVIEW REQUIRED
3. 🟢 CLOSE READY
"""

import pytest
from close_readiness import CloseReadinessEvaluator


def test_exceptions_block_close_state():
    """Verify State 1: EXCEPTIONS BLOCK CLOSE triggers when unresolved exceptions exist."""
    context = {
        "status_counts": {"auto_accepted": 100, "needs_review": 5, "exception": 3},
        "active_run": {"metadata": {"record_count": 108}}
    }
    
    res = CloseReadinessEvaluator.evaluate_close_readiness(context)

    assert res["state"] == "EXCEPTIONS BLOCK CLOSE"
    assert res["symbol"] == "🔴"
    assert "3 unresolved exception" in res["reason"]
    assert res["target_page"] == "🚨 Exceptions"
    assert "RESOLVE 3 EXCEPTIONS" in res["next_action_label"]


def test_controller_review_required_state():
    """Verify State 2: CONTROLLER REVIEW REQUIRED triggers when pending reviews remain with 0 exceptions."""
    context = {
        "status_counts": {"auto_accepted": 147, "needs_review": 13, "exception": 0},
        "active_run": {"metadata": {"record_count": 160}}
    }
    session_state = {"human_reviews": {}}
    
    res = CloseReadinessEvaluator.evaluate_close_readiness(context, session_state)

    assert res["state"] == "CONTROLLER REVIEW REQUIRED"
    assert res["symbol"] == "🟡"
    assert "13 transactions still require controller review" in res["reason"]
    assert res["target_page"] == "👤 Review Queue"
    assert "REVIEW 13 ITEMS" in res["next_action_label"]


def test_close_ready_state_all_resolved():
    """Verify State 3: CLOSE READY triggers when 0 exceptions and 0 pending unreviewed items remain."""
    context = {
        "status_counts": {"auto_accepted": 160, "needs_review": 0, "exception": 0},
        "active_run": {"metadata": {"record_count": 160}}
    }
    
    res = CloseReadinessEvaluator.evaluate_close_readiness(context)

    assert res["state"] == "CLOSE READY"
    assert res["symbol"] == "🟢"
    assert "Audit trail complete" in res["reason"]
    assert res["target_page"] == "🔍 Audit Trail"
    assert res["next_action_label"] == "VIEW AUDIT TRAIL →"


def test_close_ready_state_after_human_verification():
    """Verify State 3: CLOSE READY triggers after all needs_review items are reviewed by auditor."""
    context = {
        "status_counts": {"auto_accepted": 147, "needs_review": 2, "exception": 0},
        "active_run": {"metadata": {"record_count": 149}}
    }
    # Simulate 2 human review actions logged in session state
    session_state = {
        "human_reviews": {
            "REC_01": {"human_reviewer_action": "Approve"},
            "REC_02": {"human_reviewer_action": "Reject"}
        }
    }

    res = CloseReadinessEvaluator.evaluate_close_readiness(context, session_state)

    assert res["state"] == "CLOSE READY"
    assert res["symbol"] == "🟢"
    assert "controller verified" in res["reason"]
    assert res["target_page"] == "🔍 Audit Trail"
