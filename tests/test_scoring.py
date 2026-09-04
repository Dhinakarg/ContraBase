import pytest
from scoring import calculate_precision_recall_f1, compute_ai_confidence_metrics, compute_system_confidence_metrics, calculate_calibration

def test_confidence_metrics():
    preds = [
        {"ai_confidence": 90, "decision_confidence": 85},
        {"ai_confidence": 100, "decision_confidence": 95}
    ]
    assert compute_ai_confidence_metrics(preds) == 95.0
    assert compute_system_confidence_metrics(preds) == 90.0

def test_calculate_calibration():
    preds = [
        {"invoice_id": "INV_1", "ledger_id": "LED_1", "bank_ids": ["BNK_1"], "decision_confidence": 98.0},
        {"invoice_id": "INV_2", "ledger_id": "LED_2", "bank_ids": ["BNK_2"], "decision_confidence": 85.0},
        {"invoice_id": "INV_3", "ledger_id": "LED_3", "bank_ids": ["BNK_WRONG"], "decision_confidence": 82.0}
    ]
    gt = {
        "matches": [
            {"invoice_id": "INV_1", "ledger_id": "LED_1", "bank_ids": ["BNK_1"]},
            {"invoice_id": "INV_2", "ledger_id": "LED_2", "bank_ids": ["BNK_2"]}
        ]
    }
    
    calib = calculate_calibration(preds, gt)
    assert len(calib) == 4
    
    # Check 95-100% bin
    bin_top = next(b for b in calib if b["bin_label"] == "95-100%")
    assert bin_top["sample_count"] == 1
    assert bin_top["accuracy"] == 100.0
    
    # Check 80-90% bin
    bin_mid = next(b for b in calib if b["bin_label"] == "80-90%")
    assert bin_mid["sample_count"] == 2
    assert bin_mid["accuracy"] == 50.0 # 1 out of 2 is correct
