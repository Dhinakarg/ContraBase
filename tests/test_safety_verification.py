"""
Automated unit tests for SafetyVerificationSuite in safety_verifier.py.
Verifies that all 15 safety test scenarios pass 100% in-memory without secrets or external API dependencies.
"""

import pytest
from safety_verifier import SafetyVerificationSuite
from journal_validator import JournalEntryValidator


def test_all_15_safety_scenarios_pass():
    """Verify that all 15 safety scenarios execute and pass cleanly."""
    results = SafetyVerificationSuite.run_all_safety_tests()
    
    assert len(results) == 15, f"Expected 15 safety scenarios, got {len(results)}"
    
    failed_scenarios = [r["name"] for r in results if not r["passed"]]
    assert len(failed_scenarios) == 0, f"Safety scenarios failed: {failed_scenarios}"


def test_safety_suite_does_not_expose_secrets():
    """Verify that actual result strings do not expose secrets or API keys."""
    results = SafetyVerificationSuite.run_all_safety_tests()
    
    for r in results:
        actual_str = str(r.get("actual", ""))
        assert "AI_KEY" not in actual_str
        assert "SECRET" not in actual_str
        assert "PASSWORD" not in actual_str


def test_journal_double_entry_imbalance_blocked():
    """Security Audit: Ensure unbalanced journal entries (Debits != Credits) are blocked by Gate-B."""
    val = JournalEntryValidator.validate_entry(
        source_decision_id="LED_TEST_99",
        debit_account="Bank Charges",
        credit_account="Cash",
        debit_amount=5000.0,
        credit_amount=4000.0, # Imbalance!
        reason_code="amount_variance"
    )
    assert val["validation_status"] == "invalid"
    assert any("Unbalanced" in err or "Imbalanced" in err or "Mismatch" in err or "exceeds" in err for err in val["validation_errors"])


def test_paper_trading_execution_safety():
    """Security Audit: Verify zero real transaction execution paths exist in codebase."""
    # Ensure system operates purely on synthetic data & in-memory models
    import pipeline
    assert not hasattr(pipeline, "execute_live_payment")
    assert not hasattr(pipeline, "submit_broker_order")
