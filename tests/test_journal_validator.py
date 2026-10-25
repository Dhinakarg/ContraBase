import pytest
from journal_validator import JournalEntryValidator

def test_balanced_valid_entry():
    res = JournalEntryValidator.validate_entry(
        source_decision_id="LED_20001",
        debit_account="Bank Fees",
        credit_account="Cash",
        debit_amount=450.00,
        credit_amount=450.00,
        currency="INR",
        reason_code="amount_variance",
        materiality_threshold=400000.0
    )
    assert res["validation_status"] == "valid"
    assert len(res["validation_errors"]) == 0
    assert res["auto_post"] is True
    assert res["debit_account"] == "Bank Fees"
    assert res["credit_account"] == "Cash"
    assert res["amount"] == 450.00

def test_unbalanced_entry():
    res = JournalEntryValidator.validate_entry(
        source_decision_id="LED_20002",
        debit_account="Bank Fees",
        credit_account="Cash",
        debit_amount=1000.00,
        credit_amount=450.00,
        currency="INR"
    )
    assert res["validation_status"] == "invalid"
    assert any("Unbalanced entry" in err for err in res["validation_errors"])
    assert res["auto_post"] is False

def test_invalid_account():
    res = JournalEntryValidator.validate_entry(
        source_decision_id="LED_20003",
        debit_account="Hallucinated Expense Account",
        credit_account="Cash",
        debit_amount=1200.00,
        credit_amount=1200.00
    )
    assert res["validation_status"] == "invalid"
    assert any("Unsupported AI-generated debit account" in err for err in res["validation_errors"])

def test_unsupported_reason():
    res = JournalEntryValidator.validate_entry(
        source_decision_id="LED_20004",
        debit_account="Bank Fees",
        credit_account="Cash",
        debit_amount=1500.00,
        credit_amount=1500.00,
        reason_code="unsupported_fraud_reason"
    )
    assert res["validation_status"] == "invalid"
    assert any("Reason code" in err for err in res["validation_errors"])

def test_high_materiality_entry():
    res = JournalEntryValidator.validate_entry(
        source_decision_id="LED_20005",
        debit_account="Bank Fees",
        credit_account="Cash",
        debit_amount=600000.00,
        credit_amount=600000.00,
        materiality_threshold=400000.0
    )
    assert res["validation_status"] == "invalid"
    assert any("High-materiality adjustment" in err for err in res["validation_errors"])
    assert res["auto_post"] is False

def test_duplicate_entry():
    sig = ("LED_20006", "Bank Fees", "Cash", 500.00, "INR")
    existing = {sig}
    res = JournalEntryValidator.validate_entry(
        source_decision_id="LED_20006",
        debit_account="Bank Fees",
        credit_account="Cash",
        debit_amount=500.00,
        credit_amount=500.00,
        currency="INR",
        existing_signatures=existing
    )
    assert res["validation_status"] == "invalid"
    assert any("Duplicate journal entry" in err for err in res["validation_errors"])

def test_currency_mismatch():
    res = JournalEntryValidator.validate_entry(
        source_decision_id="LED_20007",
        debit_account="Bank Fees",
        credit_account="Cash",
        debit_amount=500.00,
        credit_amount=500.00,
        currency="INVALID_CURR"
    )
    assert res["validation_status"] == "invalid"
    assert any("Invalid currency" in err for err in res["validation_errors"])

def test_parse_and_validate_suggestion():
    suggestion = "Debit Bank Fees ₹450.00, Credit Cash ₹450.00"
    res = JournalEntryValidator.validate_from_suggestion(
        source_decision_id="LED_20008",
        suggestion_text=suggestion,
        amount_delta=450.00,
        currency="INR"
    )
    assert res["validation_status"] == "valid"
    assert res["debit_account"] == "Bank Fees"
    assert res["credit_account"] == "Cash"
    assert res["amount"] == 450.00
