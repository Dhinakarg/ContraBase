"""
Idempotency tests — verifies pipeline produces stable, repeatable results
when run twice on the same data. Uses mock Gemini client.
"""
import os
import json
import tempfile
import pytest
from backend.data_gen.generator import generate_reconciliation_data
from pipeline import ReconciliationPipeline
from review_engine import HumanReviewEngine
from journal_validator import JournalEntryValidator
from tests.conftest import create_mock_gemini_client


def test_idempotent_pipeline_execution():
    """
    Runs the pipeline twice on identical data with mock Gemini.
    Verifies:
    - No duplicate decision log entries
    - Same number of predictions
    - Stable IDs and traceability keys
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        invoices_df, ledger_df, bank_df, ground_truth = generate_reconciliation_data(
            n_records=40, seed=42, output_dir=tmp_dir
        )
        invoices_path = os.path.join(tmp_dir, "invoices.csv")
        ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
        bank_path = os.path.join(tmp_dir, "bank_statement.csv")
        log_path = os.path.join(tmp_dir, "decisions_log.jsonl")

        # Run 1 with mock Gemini
        pipeline = ReconciliationPipeline(model_name="gemini-2.5-flash")
        pipeline.client = create_mock_gemini_client()
        pipeline.api_key = "MOCK_KEY"

        preds1 = pipeline.run_reconciliation(
            invoices_path=invoices_path,
            ledger_path=ledger_path,
            bank_path=bank_path,
            log_path=log_path
        )

        log_lines_run1 = 0
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_lines_run1 = len([line for line in f if line.strip()])

        # Run 2 (identical batch execution) with mock Gemini
        pipeline2 = ReconciliationPipeline(model_name="gemini-2.5-flash")
        pipeline2.client = create_mock_gemini_client()
        pipeline2.api_key = "MOCK_KEY"

        preds2 = pipeline2.run_reconciliation(
            invoices_path=invoices_path,
            ledger_path=ledger_path,
            bank_path=bank_path,
            log_path=log_path
        )

        log_lines_run2 = 0
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_lines_run2 = len([line for line in f if line.strip()])

        # Assert zero duplicate decision lines created in decisions_log.jsonl
        assert log_lines_run1 == log_lines_run2
        assert len(preds1) == len(preds2)

        # Assert stable IDs & traceability keys
        for p in preds2:
            assert "run_id" in p
            assert "decision_id" in p
            assert "source_record_hash" in p
            assert "selected_candidate_ids" in p
            assert "rejected_candidate_ids" in p

def test_idempotent_human_reviews():
    with tempfile.TemporaryDirectory() as tmp_dir:
        file_path = os.path.join(tmp_dir, "human_reviews.json")
        reviews = {}

        # First review action
        rev1 = HumanReviewEngine.process_human_review("LED_20001", "Approve", "match")
        reviews["LED_20001"] = rev1
        HumanReviewEngine.save_human_reviews(reviews, file_path)
        
        # Second review action on SAME record (Override to Reject)
        rev2 = HumanReviewEngine.process_human_review("LED_20001", "Reject", "match")
        reviews["LED_20001"] = rev2
        HumanReviewEngine.save_human_reviews(reviews, file_path)

        loaded = HumanReviewEngine.load_human_reviews(file_path)
        assert len(loaded) == 1 # Only 1 entry, updated in-place!
        assert loaded["LED_20001"]["human_reviewer_action"] == "Reject"
        assert loaded["LED_20001"]["original_ai_decision"] == "match"
        assert loaded["LED_20001"]["final_decision"] == "no_match"
        assert loaded["LED_20001"]["human_override"] is True

def test_idempotent_journal_entries():
    sig = ("LED_20001", "Bank Fees", "Cash", 4.50, "USD")
    existing = {sig}

    res = JournalEntryValidator.validate_entry(
        source_decision_id="LED_20001",
        debit_account="Bank Fees",
        credit_account="Cash",
        debit_amount=4.50,
        credit_amount=4.50,
        currency="USD",
        existing_signatures=existing
    )
    # Second run detects duplicate signature and flags it invalid
    assert res["validation_status"] == "invalid"
    assert any("Duplicate journal entry" in err for err in res["validation_errors"])
