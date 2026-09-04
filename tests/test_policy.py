import pytest
from policy import ResolutionPolicyEngine
from journal_validator import JournalEntryValidator

def test_auto_resolve_low_materiality_high_conf():
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=98.0,
        evidence_score=95.0,
        amount=15000.0,
        materiality_threshold=400000.0,
        reason_code="exact_match"
    )
    assert res["routing_status"] == "auto_accepted"

def test_high_materiality_safety_override():
    # If no duplicate, no variance, etc., it should now auto-accept
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=99.0,
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold=400000.0,
        reason_code="exact_match",
        has_duplicates=False,
        date_variance_days=0,
        amount_variance=0.0,
        is_split=False,
        has_fx_ambiguity=False
    )
    assert res["routing_status"] == "auto_accepted"
    assert "permitted for automatic reconciliation" in res["policy_reason"]
    assert res["is_high_risk"] is False

def test_low_evidence_force_exception():
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=96.0,
        evidence_score=30.0,
        amount=15000.0,
        materiality_threshold=400000.0
    )
    assert res["routing_status"] == "exception"
    assert "evidence score" in res["policy_reason"]

def test_medium_confidence():
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=82.0,
        evidence_score=85.0,
        amount=15000.0,
        materiality_threshold=400000.0
    )
    assert res["routing_status"] == "needs_review"
    assert "Medium decision confidence" in res["policy_reason"]

def test_low_confidence():
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=60.0,
        evidence_score=60.0,
        amount=15000.0,
        materiality_threshold=400000.0
    )
    assert res["routing_status"] == "exception"
    assert "Low decision confidence" in res["policy_reason"]

def test_complex_split_payment_cap():
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=96.0,
        evidence_score=90.0,
        amount=250000.0,
        materiality_threshold=400000.0,
        reason_code="split_payment"
    )
    assert res["routing_status"] == "needs_review"
    assert "Complex split_payment" in res["policy_reason"]


# ---------------------------------------------------------------------------
# NEW RISK-AWARE POLICY TESTS (A through K)
# ---------------------------------------------------------------------------

def test_high_value_exact_deterministic_unique_match():
    # A. High-value exact deterministic unique match -> auto_accepted
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=100.0,
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold_inr=400000.0,
        reason_code="exact_match",
        currency="INR",
        has_duplicates=False,
        date_variance_days=0,
        amount_variance=0.0,
        is_split=False,
        has_fx_ambiguity=False,
        unresolved_ambiguity=False,
        has_high_risk_flag=False
    )
    assert res["routing_status"] == "auto_accepted"
    assert "unique deterministic exact match" in res["policy_reason"]

def test_high_value_exact_match_with_duplicate_candidates():
    # B. High-value exact match with duplicate candidates -> needs_review
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=100.0,
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold_inr=400000.0,
        reason_code="exact_match",
        currency="INR",
        has_duplicates=True, # DUPLICATES PRESENT!
        date_variance_days=0,
        amount_variance=0.0,
        is_split=False,
        has_fx_ambiguity=False
    )
    assert res["routing_status"] == "needs_review"
    assert "multiple plausible candidates remain" in res["policy_reason"]

def test_high_value_reference_mismatch():
    # C. High-value reference mismatch -> needs_review
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=100.0,
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold_inr=400000.0,
        reason_code="reference_typo", # reference typo / mismatch!
        currency="INR",
        has_duplicates=False,
        date_variance_days=0,
        amount_variance=0.0,
        is_split=False,
        has_fx_ambiguity=False
    )
    assert res["routing_status"] == "needs_review"
    assert "reference ID mismatch exists" in res["policy_reason"]

def test_high_value_date_variance():
    # D. High-value date variance -> needs_review
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=100.0,
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold_inr=400000.0,
        reason_code="exact_match",
        currency="INR",
        has_duplicates=False,
        date_variance_days=2, # DATE VARIANCE!
        amount_variance=0.0,
        is_split=False,
        has_fx_ambiguity=False
    )
    assert res["routing_status"] == "needs_review"
    assert "date variance of 2 day(s)" in res["policy_reason"]

def test_high_value_amount_variance():
    # E. High-value amount variance -> needs_review
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=100.0,
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold_inr=400000.0,
        reason_code="exact_match",
        currency="INR",
        has_duplicates=False,
        date_variance_days=0,
        amount_variance=150.0, # AMOUNT VARIANCE!
        is_split=False,
        has_fx_ambiguity=False
    )
    assert res["routing_status"] == "needs_review"
    assert "material amount variance (₹150.00)" in res["policy_reason"]

def test_high_value_split_payment():
    # F. High-value split payment -> needs_review
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=100.0,
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold_inr=400000.0,
        reason_code="split_payment",
        currency="INR",
        has_duplicates=False,
        date_variance_days=0,
        amount_variance=0.0,
        is_split=True, # SPLIT RISK!
        has_fx_ambiguity=False
    )
    assert res["routing_status"] == "needs_review"
    assert "complex split-payment risk exists" in res["policy_reason"]

def test_high_value_fx_ambiguity():
    # G. High-value FX ambiguity -> needs_review
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=100.0,
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold_inr=400000.0,
        reason_code="exact_match",
        currency="USD", # USD currency!
        has_duplicates=False,
        date_variance_days=0,
        amount_variance=0.0,
        is_split=False,
        has_fx_ambiguity=True
    )
    assert res["routing_status"] == "needs_review"
    assert "FX/currency ambiguity exists" in res["policy_reason"]

def test_high_value_low_confidence():
    # H. High-value low-confidence decision -> needs_review
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=85.0, # LOW CONFIDENCE!
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold_inr=400000.0,
        reason_code="exact_match",
        currency="INR",
        has_duplicates=False,
        date_variance_days=0,
        amount_variance=0.0,
        is_split=False,
        has_fx_ambiguity=False
    )
    assert res["routing_status"] == "needs_review"
    assert "decision confidence (85.0%) is below the auto-accept threshold" in res["policy_reason"]

def test_low_value_strong_match():
    # I. Low-value strong match -> existing behavior unchanged (auto_accepted)
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=98.0,
        evidence_score=95.0,
        amount=50000.0, # Below 400k
        materiality_threshold_inr=400000.0,
        reason_code="exact_match",
        currency="INR",
        has_duplicates=False,
        date_variance_days=0,
        amount_variance=0.0,
        is_split=False,
        has_fx_ambiguity=False
    )
    assert res["routing_status"] == "auto_accepted"
    assert "High confidence, low materiality" in res["policy_reason"]

def test_high_value_journal_safety():
    # J. High-value auto-accepted reconciliation -> journal validator still independently enforces journal safety
    # Evaluate policy to confirm the reconciliation matches are auto-accepted:
    res = ResolutionPolicyEngine.evaluate_policy(
        decision="match",
        decision_confidence=100.0,
        evidence_score=100.0,
        amount=500000.0,
        materiality_threshold_inr=400000.0,
        reason_code="exact_match",
        currency="INR",
        has_duplicates=False,
        date_variance_days=0,
        amount_variance=0.0,
        is_split=False,
        has_fx_ambiguity=False
    )
    assert res["routing_status"] == "auto_accepted"

    # Evaluate the journal validator for this match pairing to check compliance (Gate B):
    je_val = JournalEntryValidator.validate_entry(
        source_decision_id="DEC_LED_9999",
        debit_account="Bank Fees",
        credit_account="Cash",
        debit_amount=500000.0, # High value adjustment amount!
        credit_amount=500000.0,
        currency="INR",
        reason_code="amount_variance",
        materiality_threshold_inr=400000.0
    )
    # The journal must NOT be auto-post eligible
    assert je_val["validation_status"] == "invalid"
    assert je_val["auto_post"] is False
    assert any("High-materiality adjustment" in err for err in je_val["validation_errors"])
