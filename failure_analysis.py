import pandas as pd
from typing import List, Dict

CATEGORIES = [
    "ambiguous_duplicate",
    "missing_source_record",
    "reference_mismatch",
    "date_variance",
    "amount_variance",
    "split_payment",
    "currency_fx_issue",
    "insufficient_evidence",
    "incorrect_candidate_selection",
    "unsupported_scenario"
]

class FailureAnalyzer:
    @staticmethod
    def classify_failure_category(record_info: dict) -> str:
        """
        Classifies a reconciliation failure into one of 10 structured taxonomy categories based on record features.
        """
        reason = str(record_info.get("reason_code", "")).lower()
        currency = str(record_info.get("currency", "USD")).upper()
        confidence = float(record_info.get("confidence", 100))
        vendor = str(record_info.get("vendor", "")).lower()
        amount = float(record_info.get("amount", 0.0))

        if confidence < 50.0:
            return "insufficient_evidence"

        if currency == "EUR" and "fx" in reason:
            return "currency_fx_issue"

        if "split" in reason or "split" in vendor:
            return "split_payment"

        if "duplicate" in reason or "decoy" in vendor or "duplicate" in vendor:
            return "ambiguous_duplicate"

        if "typo" in reason or "ref" in reason:
            return "reference_mismatch"

        if "date" in reason or "shift" in reason:
            return "date_variance"

        if "amount" in reason or "variance" in reason or "fee" in reason:
            return "amount_variance"

        if reason in ["no_counterpart_found", "unmatched"]:
            return "missing_source_record"

        if record_info.get("failure_type") == "False Positive":
            return "incorrect_candidate_selection"

        return "unsupported_scenario"

    @classmethod
    def analyze_failures(
        cls,
        predictions: List[dict],
        ground_truth: dict,
        ledger_df: pd.DataFrame,
        bank_df: pd.DataFrame,
        invoices_df: pd.DataFrame
    ) -> dict:
        """
        Performs post-inference failure analysis by comparing predictions against ground truth.
        DOES NOT expose ground truth during inference.
        """
        # Ground truth signatures
        gt_signatures = set()
        for m in ground_truth.get("matches", []):
            inv = str(m.get("invoice_id")) if m.get("invoice_id") else ""
            led = str(m.get("ledger_id")) if m.get("ledger_id") else ""
            banks = tuple(sorted([str(b) for b in m.get("bank_ids", []) if b]))
            if inv or led or banks:
                gt_signatures.add((inv, led, banks))

        # Prediction signatures
        pred_signatures = set()
        for m in predictions:
            inv = str(m.get("invoice_id")) if m.get("invoice_id") else ""
            led = str(m.get("ledger_id")) if m.get("ledger_id") else ""
            banks = tuple(sorted([str(b) for b in m.get("bank_ids", []) if b]))
            if inv or led or banks:
                pred_signatures.add((inv, led, banks))

        failures = []

        # 1. False Positives (Predicted matches that are not in GT)
        for pred in predictions:
            inv = str(pred.get("invoice_id")) if pred.get("invoice_id") else ""
            led = str(pred.get("ledger_id")) if pred.get("ledger_id") else ""
            banks = tuple(sorted([str(b) for b in pred.get("bank_ids", []) if b]))
            sig = (inv, led, banks)
            if (inv or led or banks) and sig not in gt_signatures:
                # Find amount and vendor info from dataframes
                amt = 0.0
                curr = "USD"
                vendor = "Unknown"
                if led and not ledger_df.empty and led in ledger_df["ledger_id"].astype(str).values:
                    row = ledger_df.loc[ledger_df["ledger_id"].astype(str) == led].iloc[0]
                    amt = float(row["amount"])
                    curr = str(row.get("currency", "USD"))
                    vendor = str(row.get("vendor", ""))
                elif banks and not bank_df.empty and banks[0] in bank_df["bank_id"].astype(str).values:
                    row = bank_df.loc[bank_df["bank_id"].astype(str) == banks[0]].iloc[0]
                    amt = float(row["amount"])
                    curr = str(row.get("currency", "USD"))
                    vendor = str(row.get("description", ""))

                rec_info = {
                    "record_id": led or (banks[0] if banks else inv),
                    "failure_type": "False Positive",
                    "vendor": vendor,
                    "amount": amt,
                    "currency": curr,
                    "confidence": pred.get("decision_confidence", pred.get("confidence", 0)),
                    "reason_code": pred.get("reason_code", "incorrect_match"),
                    "rationale": pred.get("rationale", "AI predicted match not present in ground truth"),
                    "details": f"Predicted ({inv}, {led}, {banks}) not in ground truth"
                }
                rec_info["category"] = cls.classify_failure_category(rec_info)
                failures.append(rec_info)

        # 2. False Negatives (Ground truth matches that were missed or unmatched in predictions)
        for gt in ground_truth.get("matches", []):
            inv = str(gt.get("invoice_id")) if gt.get("invoice_id") else ""
            led = str(gt.get("ledger_id")) if gt.get("ledger_id") else ""
            banks = tuple(sorted([str(b) for b in gt.get("bank_ids", []) if b]))
            sig = (inv, led, banks)
            if sig not in pred_signatures:
                amt = 0.0
                curr = "USD"
                vendor = "Unknown"
                if led and not ledger_df.empty and led in ledger_df["ledger_id"].astype(str).values:
                    row = ledger_df.loc[ledger_df["ledger_id"].astype(str) == led].iloc[0]
                    amt = float(row["amount"])
                    curr = str(row.get("currency", "USD"))
                    vendor = str(row.get("vendor", ""))

                rec_info = {
                    "record_id": led or (banks[0] if banks else inv),
                    "failure_type": "False Negative",
                    "vendor": vendor,
                    "amount": amt,
                    "currency": curr,
                    "confidence": 0,
                    "reason_code": "missed_match",
                    "rationale": "Ground truth match was missed or unresolved by system",
                    "details": f"Ground truth ({inv}, {led}, {banks}) was not reconciled"
                }
                rec_info["category"] = cls.classify_failure_category(rec_info)
                failures.append(rec_info)

        # Statistics computation
        total_records = len(ledger_df) + len(bank_df)
        total_failures = len(failures)
        failure_rate = round((total_failures / total_records) * 100.0, 1) if total_records > 0 else 0.0

        fp_count = len([f for f in failures if f["failure_type"] == "False Positive"])
        fn_count = len([f for f in failures if f["failure_type"] == "False Negative"])

        # Category breakdown
        category_counts = {cat: 0 for cat in CATEGORIES}
        for f in failures:
            cat = f["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Confidence distribution
        conf_dist = {"< 50%": 0, "50-70%": 0, "70-90%": 0, "90-100%": 0}
        for f in failures:
            c = f["confidence"]
            if c < 50: conf_dist["< 50%"] += 1
            elif c < 70: conf_dist["50-70%"] += 1
            elif c < 90: conf_dist["70-90%"] += 1
            else: conf_dist["90-100%"] += 1

        # Worst cases sorted by dollar amount descending
        worst_cases = sorted(failures, key=lambda x: x["amount"], reverse=True)[:10]

        return {
            "total_failures": total_failures,
            "total_records": total_records,
            "failure_rate": failure_rate,
            "false_positives_count": fp_count,
            "false_negatives_count": fn_count,
            "category_counts": category_counts,
            "confidence_distribution": conf_dist,
            "failures": failures,
            "worst_cases": worst_cases
        }
