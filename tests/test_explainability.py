"""
Unit tests for SafetyExplainabilityEngine in explainability.py.
Verifies dynamic policy threshold reflection, Mode A (blocked items) vs Mode B (safe items),
and non-mutative explainability.
"""

import pytest
from explainability import SafetyExplainabilityEngine


def test_auto_accepted_exact_match_mode_b():
    """Verify Mode B (WHY THIS WAS SAFE TO AUTO-ACCEPT) for clean 1:1 exact match."""
    exact_item = {
        "status": "auto_accepted",
        "reason_code": "exact_match",
        "amount": 50000.0,
        "currency": "INR",
        "system_confidence": 100.0
    }

    res = SafetyExplainabilityEngine.generate_safety_explanation(
        exact_item,
        auto_accept_thresh=95.0,
        materiality_threshold_inr=500000.0
    )

    assert res["is_auto_accepted"] is True
    assert res["title"] == "WHY THIS WAS SAFE TO AUTO-ACCEPT"
    assert any("Unique 1:1 deterministic candidate match" in c for c in res["conditions"])
    assert any("5,00,000" in c for c in res["conditions"])


def test_needs_review_mode_a_dynamic_thresholds():
    """Verify Mode A (WHAT WOULD MAKE THIS SAFE TO AUTO-ACCEPT?) reflects configured policy thresholds dynamically."""
    review_item = {
        "status": "needs_review",
        "reason_code": "amount_variance",
        "policy_reason": "High materiality with amount variance",
        "amount": 800000.0,
        "currency": "INR",
        "system_confidence": 85.0
    }

    # Test with Custom Threshold 1 (₹6,00,000 & 90% auto accept)
    res1 = SafetyExplainabilityEngine.generate_safety_explanation(
        review_item,
        auto_accept_thresh=90.0,
        materiality_threshold_inr=600000.0
    )

    assert res1["is_auto_accepted"] is False
    assert res1["title"] == "WHAT WOULD MAKE THIS SAFE TO AUTO-ACCEPT?"
    assert any("Amount variance" in b for b in res1["blocking_conditions"])
    assert any("6,00,000" in b for b in res1["blocking_conditions"])
    assert any("90%" in c for c in res1["to_become_safe"])

    # Test with Custom Threshold 2 (₹10,00,000 & 98% auto accept)
    res2 = SafetyExplainabilityEngine.generate_safety_explanation(
        review_item,
        auto_accept_thresh=98.0,
        materiality_threshold_inr=1000000.0
    )

    assert any("98%" in c for c in res2["to_become_safe"])
    assert res2["active_thresholds"]["materiality_threshold_inr"] == 1000000.0


def test_explainability_does_not_mutate_item():
    """Verify that generating explanations is strictly read-only and does not mutate the item dictionary."""
    orig_item = {
        "status": "needs_review",
        "reason_code": "date_shift",
        "amount": 250000.0,
        "currency": "INR",
        "system_confidence": 88.0
    }

    item_copy = dict(orig_item)
    SafetyExplainabilityEngine.generate_safety_explanation(orig_item)

    assert orig_item == item_copy
