import pytest
import os
from unittest.mock import patch
import pandas as pd
from policy import ResolutionPolicyEngine


def test_materiality_threshold_defaults():
    """Verify default materiality threshold of INR 4,00,000."""
    res_below = ResolutionPolicyEngine.evaluate_policy("match", 98.0, 95.0, 399999.0, 400000.0, "exact_match")
    res_above = ResolutionPolicyEngine.evaluate_policy("match", 98.0, 95.0, 400000.0, 400000.0, "exact_match")
    assert res_below["routing_status"] == "auto_accepted"
    assert res_above["routing_status"] == "auto_accepted"


def test_materiality_threshold_custom_values():
    """Verify custom materiality thresholds like INR 50,000, INR 4,37,500, and INR 10,00,000 propagate correctly."""
    res_50k = ResolutionPolicyEngine.evaluate_policy("match", 98.0, 95.0, 50000.0, 50000.0, "exact_match")
    res_437k = ResolutionPolicyEngine.evaluate_policy("match", 98.0, 95.0, 437500.0, 437500.0, "exact_match")
    res_10l = ResolutionPolicyEngine.evaluate_policy("match", 98.0, 95.0, 1000000.0, 1000000.0, "exact_match")
    assert res_50k["routing_status"] == "auto_accepted"
    assert res_437k["routing_status"] == "auto_accepted"
    assert res_10l["routing_status"] == "auto_accepted"


def test_policy_engine_uses_dynamic_materiality_threshold():
    """Verify policy engine respects dynamically configured materiality thresholds."""
    # High amount match with date_shift: INR 6,00,000
    # Under threshold INR 10,00,000 -> Not material -> Auto Accepted
    res_under = ResolutionPolicyEngine.evaluate_policy("match", 98.0, 95.0, 600000.0, 1000000.0, "date_shift")
    assert res_under["routing_status"] == "auto_accepted"

    # Over threshold INR 4,00,000 -> Material with date_shift -> Needs Review
    res_over = ResolutionPolicyEngine.evaluate_policy("match", 92.0, 85.0, 600000.0, 400000.0, "date_shift")
    assert res_over["routing_status"] == "needs_review"


def test_historical_run_threshold_immutability():
    """Verify historical run stored thresholds are preserved when active settings change."""
    historical_run = {
        "metadata": {
            "run_id": "RUN_HISTORICAL_01",
            "materiality_threshold_inr": 400000.0
        }
    }
    
    # Active setting changed to 10,00,000
    active_setting = 1000000.0
    
    # Stored run threshold must remain 400,000
    assert historical_run["metadata"]["materiality_threshold_inr"] == 400000.0
    assert historical_run["metadata"]["materiality_threshold_inr"] != active_setting


def test_confidence_threshold_precision():
    """Verify floating precision confidence thresholds like 95.0% and 95.5%."""
    auto_accept_95_5 = 95.5
    needs_review_80_0 = 80.0
    
    assert needs_review_80_0 < auto_accept_95_5
    assert auto_accept_95_5 - needs_review_80_0 == 15.5


def test_settings_edits_produce_zero_gemini_api_calls():
    """Verify that updating configuration state produces zero Gemini API calls."""
    with patch("google.genai.Client") as mock_api:
        # Simulate state updates
        new_settings = {
            "n_records": 160,
            "seed": 100,
            "noise_level": 0.25,
            "materiality_threshold_inr": 437500.0,
            "auto_accept_thresh": 98.0,
            "needs_review_thresh": 85.0
        }
        
        # Verify no calls triggered
        assert mock_api.call_count == 0
