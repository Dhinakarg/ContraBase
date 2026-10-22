import json

def calculate_precision_recall_f1(predicted_matches, ground_truth):
    """
    Computes precision, recall, and F1 score for reconciliation matching.
    predicted_matches: list of dicts with ['invoice_id', 'ledger_id', 'bank_ids']
    ground_truth: dict representing ground_truth.json containing {"matches": [...]}
    """
    # Create signatures for ground truth matches
    # Normalize ID keys to string, map None to empty string
    gt_signatures = set()
    for m in ground_truth.get("matches", []):
        inv = str(m.get("invoice_id")) if m.get("invoice_id") else ""
        led = str(m.get("ledger_id")) if m.get("ledger_id") else ""
        banks = tuple(sorted([str(b) for b in m.get("bank_ids", []) if b]))
        # We only track groups that have at least some link
        if inv or led or banks:
            gt_signatures.add((inv, led, banks))

    # Create signatures for predictions
    pred_signatures = set()
    for m in predicted_matches:
        inv = str(m.get("invoice_id")) if m.get("invoice_id") else ""
        led = str(m.get("ledger_id")) if m.get("ledger_id") else ""
        banks = tuple(sorted([str(b) for b in m.get("bank_ids", []) if b]))
        if inv or led or banks:
            pred_signatures.add((inv, led, banks))

    tp = len(pred_signatures.intersection(gt_signatures))
    fp = len(pred_signatures - gt_signatures)
    fn = len(gt_signatures - pred_signatures)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1_score": f1
    }

def compute_ai_confidence_metrics(predictions):
    """
    Computes average confidence across all predictions.
    """
    if not predictions:
        return 0.0
    confidences = [p.get("ai_confidence", p.get("confidence", 100)) for p in predictions]
    return sum(confidences) / len(confidences) if confidences else 0.0

def compute_system_confidence_metrics(predictions):
    """
    Computes average system decision confidence across all predictions.
    """
    if not predictions:
        return 0.0
    confidences = [p.get("decision_confidence", p.get("confidence", 100)) for p in predictions]
    return sum(confidences) / len(confidences) if confidences else 0.0

def calculate_calibration(predictions, ground_truth, bins=None):
    """
    Calculates calibration stats: actual ground-truth accuracy by decision confidence bin.
    """
    if bins is None:
        bins = [
            {"label": "95-100%", "min": 95.0, "max": 100.0},
            {"label": "90-95%", "min": 90.0, "max": 95.0},
            {"label": "80-90%", "min": 80.0, "max": 90.0},
            {"label": "< 80%", "min": 0.0, "max": 80.0}
        ]

    # Map ground truth signatures
    gt_signatures = set()
    for m in ground_truth.get("matches", []):
        inv = str(m.get("invoice_id")) if m.get("invoice_id") else ""
        led = str(m.get("ledger_id")) if m.get("ledger_id") else ""
        banks = tuple(sorted([str(b) for b in m.get("bank_ids", []) if b]))
        if inv or led or banks:
            gt_signatures.add((inv, led, banks))

    results = []
    for b in bins:
        # Filter predictions in bin
        bin_preds = []
        for p in predictions:
            conf = p.get("decision_confidence", p.get("confidence", 100.0))
            # Handle boundary
            if b["min"] <= conf <= b["max"] if b["max"] == 100.0 else b["min"] <= conf < b["max"]:
                bin_preds.append(p)

        total_in_bin = len(bin_preds)
        if total_in_bin == 0:
            results.append({
                "bin_label": b["label"],
                "sample_count": 0,
                "accuracy": 0.0,
                "precision": 0.0
            })
            continue

        correct_count = 0
        for p in bin_preds:
            inv = str(p.get("invoice_id")) if p.get("invoice_id") else ""
            led = str(p.get("ledger_id")) if p.get("ledger_id") else ""
            banks = tuple(sorted([str(b) for b in p.get("bank_ids", []) if b]))
            sig = (inv, led, banks)
            src_id = str(p.get("source_record_id")) if p.get("source_record_id") else ""
            
            if inv or led or banks:
                # Match decision correctness
                if sig in gt_signatures:
                    correct_count += 1
            else:
                # Non-match / exception decision correctness
                has_gt_match = any(src_id == g[0] or src_id == g[1] or src_id in g[2] for g in gt_signatures)
                if not has_gt_match:
                    correct_count += 1

        accuracy = (correct_count / total_in_bin) * 100.0
        results.append({
            "bin_label": b["label"],
            "sample_count": total_in_bin,
            "accuracy": round(accuracy, 1),
            "precision": round(accuracy / 100.0, 3)
        })

    return results

def score_reconciliation_files(predictions_path: str, ground_truth_path: str):
    """
    Scores predicted matches file against ground truth file.
    """
    with open(predictions_path, "r") as f:
        preds = json.load(f)
    with open(ground_truth_path, "r") as f:
        truth = json.load(f)
    return calculate_precision_recall_f1(preds, truth)

if __name__ == "__main__":
    # Small test stub
    mock_preds = [
        {"invoice_id": "INV_10001", "ledger_id": "LED_20001", "bank_ids": ["BNK_30001"]},
        {"invoice_id": "INV_10002", "ledger_id": "LED_20002", "bank_ids": ["BNK_30002"]}
    ]
    mock_truth = {
        "matches": [
            {"invoice_id": "INV_10001", "ledger_id": "LED_20001", "bank_ids": ["BNK_30001"]},
            {"invoice_id": "INV_10002", "ledger_id": "LED_20002", "bank_ids": ["BNK_30002", "BNK_30003"]}
        ]
    }
    print("Scoring metrics test output:")
    print(calculate_precision_recall_f1(mock_preds, mock_truth))
