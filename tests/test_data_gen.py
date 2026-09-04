import os
import json
import tempfile
import pandas as pd
import pytest
from backend.data_gen.generator import generate_reconciliation_data

def test_ground_truth_completeness_and_uniqueness():
    """
    Generates a batch of synthetic reconciliation data and verifies that
    every generated record is accounted for in the ground truth JSON,
    with no gaps, no duplicates, and no overlapping categorization.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Generate dataset
        n_records = 150
        invoices_df, ledger_df, bank_df, ground_truth = generate_reconciliation_data(
            n_records=n_records, seed=123, output_dir=tmp_dir
        )

        # Get all unique IDs from the generated DataFrames
        csv_invoice_ids = set(invoices_df["invoice_id"].tolist())
        csv_ledger_ids = set(ledger_df["ledger_id"].tolist())
        csv_bank_ids = set(bank_df["bank_id"].tolist())

        # Assert no duplicates exist inside the files themselves
        assert len(csv_invoice_ids) == len(invoices_df)
        assert len(csv_ledger_ids) == len(ledger_df)
        assert len(csv_bank_ids) == len(bank_df)

        # Track records mapped in ground truth matches
        gt_matched_invoices = []
        gt_matched_ledgers = []
        gt_matched_banks = []

        for match in ground_truth["matches"]:
            if match.get("invoice_id"):
                gt_matched_invoices.append(match["invoice_id"])
            if match.get("ledger_id"):
                gt_matched_ledgers.append(match["ledger_id"])
            if match.get("bank_ids"):
                gt_matched_banks.extend(match["bank_ids"])

        # Track records mapped in ground truth unmatchables
        gt_unmatchable_invoices = ground_truth["unmatchable"]["invoice_ids"]
        gt_unmatchable_ledgers = ground_truth["unmatchable"]["ledger_ids"]
        gt_unmatchable_banks = ground_truth["unmatchable"]["bank_ids"]

        # Track records mapped in ground truth decoys
        gt_decoy_invoices = ground_truth["decoys"]["invoice_ids"]
        gt_decoy_ledgers = ground_truth["decoys"]["ledger_ids"]
        gt_decoy_banks = ground_truth["decoys"]["bank_ids"]

        # Combine all mapped lists to verify uniqueness and presence
        all_gt_invoices = gt_matched_invoices + gt_unmatchable_invoices + gt_decoy_invoices
        all_gt_ledgers = gt_matched_ledgers + gt_unmatchable_ledgers + gt_decoy_ledgers
        all_gt_banks = gt_matched_banks + gt_unmatchable_banks + gt_decoy_banks

        # Assert no duplicate IDs are referenced in the ground truth
        assert len(all_gt_invoices) == len(set(all_gt_invoices)), "Duplicate invoice ID referenced in ground truth"
        assert len(all_gt_ledgers) == len(set(all_gt_ledgers)), "Duplicate ledger ID referenced in ground truth"
        assert len(all_gt_banks) == len(set(all_gt_banks)), "Duplicate bank ID referenced in ground truth"

        # Convert to sets for comparison
        set_gt_invoices = set(all_gt_invoices)
        set_gt_ledgers = set(all_gt_ledgers)
        set_gt_banks = set(all_gt_banks)

        # Assert no gaps (CSV matches ground truth sets exactly)
        assert csv_invoice_ids == set_gt_invoices, f"Mismatch in invoices: {csv_invoice_ids.symmetric_difference(set_gt_invoices)}"
        assert csv_ledger_ids == set_gt_ledgers, f"Mismatch in ledger: {csv_ledger_ids.symmetric_difference(set_gt_ledgers)}"
        assert csv_bank_ids == set_gt_banks, f"Mismatch in bank statement: {csv_bank_ids.symmetric_difference(set_gt_banks)}"

        # Assert no overlaps between categories (redundant but double checks)
        # Matches vs Unmatchable
        assert not set(gt_matched_invoices).intersection(set(gt_unmatchable_invoices))
        assert not set(gt_matched_ledgers).intersection(set(gt_unmatchable_ledgers))
        assert not set(gt_matched_banks).intersection(set(gt_unmatchable_banks))
        # Matches vs Decoys
        assert not set(gt_matched_invoices).intersection(set(gt_decoy_invoices))
        assert not set(gt_matched_ledgers).intersection(set(gt_decoy_ledgers))
        assert not set(gt_matched_banks).intersection(set(gt_decoy_banks))
        # Unmatchable vs Decoys
        assert not set(gt_unmatchable_invoices).intersection(set(gt_decoy_invoices))
        assert not set(gt_unmatchable_ledgers).intersection(set(gt_decoy_ledgers))
        assert not set(gt_unmatchable_banks).intersection(set(gt_decoy_banks))

def test_demo_preset_guarantees_anomalies():
    """
    Asserts that the demo preset (seed 42, count 80, noise 0.15)
    always includes at least one split-payment group and one duplicate decoy.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        _, _, _, ground_truth = generate_reconciliation_data(
            n_records=80, seed=42, output_dir=tmp_dir, anomaly_rate=0.15
        )
        
        # Check split payment matches
        split_matches = [m for m in ground_truth["matches"] if m.get("match_type") == "split_payment"]
        assert len(split_matches) >= 1, "Demo preset did not include a split payment match"
        
        # Check duplicate decoy records
        has_ledger_decoy = len(ground_truth["decoys"]["ledger_ids"]) >= 1
        has_bank_decoy = len(ground_truth["decoys"]["bank_ids"]) >= 1
        assert has_ledger_decoy or has_bank_decoy, "Demo preset did not include a duplicate decoy"
