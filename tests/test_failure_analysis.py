import pytest
import pandas as pd
from failure_analysis import FailureAnalyzer

def test_classify_failure_categories():
    assert FailureAnalyzer.classify_failure_category({"confidence": 40}) == "insufficient_evidence"
    assert FailureAnalyzer.classify_failure_category({"confidence": 80, "currency": "EUR", "reason_code": "fx_mismatch"}) == "currency_fx_issue"
    assert FailureAnalyzer.classify_failure_category({"confidence": 80, "reason_code": "split_payment"}) == "split_payment"
    assert FailureAnalyzer.classify_failure_category({"confidence": 80, "reason_code": "reference_typo"}) == "reference_mismatch"
    assert FailureAnalyzer.classify_failure_category({"confidence": 80, "reason_code": "date_shift"}) == "date_variance"
    assert FailureAnalyzer.classify_failure_category({"confidence": 80, "reason_code": "amount_variance"}) == "amount_variance"
    assert FailureAnalyzer.classify_failure_category({"confidence": 80, "reason_code": "no_counterpart_found"}) == "missing_source_record"

def test_analyze_failures_metrics():
    preds = [
        {"invoice_id": "INV_1", "ledger_id": "LED_1", "bank_ids": ["BNK_1"], "confidence": 98.0}, # True positive
        {"invoice_id": "INV_2", "ledger_id": "LED_2", "bank_ids": ["BNK_WRONG"], "confidence": 80.0, "reason_code": "amount_variance"} # False positive
    ]
    gt = {
        "matches": [
            {"invoice_id": "INV_1", "ledger_id": "LED_1", "bank_ids": ["BNK_1"]},
            {"invoice_id": "INV_2", "ledger_id": "LED_2", "bank_ids": ["BNK_2"]} # Missed match (False negative)
        ]
    }
    
    ledger_df = pd.DataFrame([
        {"ledger_id": "LED_1", "amount": 100, "vendor": "Acme", "currency": "USD"},
        {"ledger_id": "LED_2", "amount": 7500, "vendor": "Zeta", "currency": "USD"}
    ])
    bank_df = pd.DataFrame([
        {"bank_id": "BNK_1", "amount": 100, "description": "Acme", "currency": "USD"},
        {"bank_id": "BNK_2", "amount": 7500, "description": "Zeta", "currency": "USD"}
    ])
    invoices_df = pd.DataFrame([])

    res = FailureAnalyzer.analyze_failures(preds, gt, ledger_df, bank_df, invoices_df)

    assert res["total_failures"] == 2 # 1 FP + 1 FN
    assert res["false_positives_count"] == 1
    assert res["false_negatives_count"] == 1
    assert res["failure_rate"] > 0.0
    assert len(res["worst_cases"]) == 2
    # Highest materiality ($7500) should be first in worst_cases
    assert res["worst_cases"][0]["amount"] == 7500.0
