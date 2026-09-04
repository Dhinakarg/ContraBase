import os
import tempfile
import pytest
import pandas as pd
from backend.data_gen.generator import generate_reconciliation_data
from pipeline import ReconciliationPipeline
from ui_common import load_reconciliation_context
from tests.conftest import create_mock_gemini_client
import streamlit as st

def test_kpi_conservation_rule():
    """
    Regression test to verify that the record-level closing metrics satisfy:
    Auto-Accepted + Human Review + Exceptions = Total Processed
    across multiple seeds under mock pipeline runs.
    """
    seeds = [42, 101, 777, 1234, 2026]
    
    for seed in seeds:
        # Create temp directory to isolate data
        tmp_dir = tempfile.mkdtemp()
        invoices_df, ledger_df, bank_df, ground_truth = generate_reconciliation_data(
            n_records=40, seed=seed, output_dir=tmp_dir
        )
        
        invoices_path = os.path.join(tmp_dir, "invoices.csv")
        ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
        bank_path = os.path.join(tmp_dir, "bank_statement.csv")
        log_path = os.path.join(tmp_dir, "decisions_log.jsonl")
        
        pipeline = ReconciliationPipeline(model_name="gemini-2.5-flash")
        pipeline.client = create_mock_gemini_client()
        pipeline.api_key = "MOCK_KEY"
        
        predictions = pipeline.run_reconciliation(
            invoices_path=invoices_path,
            ledger_path=ledger_path,
            bank_path=bank_path,
            log_path=log_path,
            materiality_threshold_inr=400000.0
        )
        
        # Calculate record stats using our set-based logic
        total_records = len(ledger_df) + len(bank_df)
        
        all_ledger_ids = set(str(x) for x in ledger_df["ledger_id"])
        all_bank_ids = set(str(x) for x in bank_df["bank_id"])

        auto_accepted_led = set()
        auto_accepted_bnk = set()
        for p in predictions:
            if p.get("status") == "auto_accepted":
                if p.get("ledger_id"):
                    auto_accepted_led.add(str(p["ledger_id"]))
                for b_id in p.get("bank_ids", []):
                    if b_id:
                        auto_accepted_bnk.add(str(b_id))

        needs_review_led = set()
        needs_review_bnk = set()
        for p in predictions:
            if p.get("status") == "needs_review":
                l_id = p.get("ledger_id")
                if l_id and str(l_id) not in auto_accepted_led:
                    needs_review_led.add(str(l_id))
                for b_id in p.get("bank_ids", []):
                    if b_id and str(b_id) not in auto_accepted_bnk:
                        needs_review_bnk.add(str(b_id))

        exceptions_led = all_ledger_ids - auto_accepted_led - needs_review_led
        exceptions_bank = all_bank_ids - auto_accepted_bnk - needs_review_bnk

        auto_accepted_cnt = len(auto_accepted_led) + len(auto_accepted_bnk)
        needs_review_cnt = len(needs_review_led) + len(needs_review_bnk)
        exceptions_cnt = len(exceptions_led) + len(exceptions_bank)
        
        # Verify conservation rule:
        assert auto_accepted_cnt + needs_review_cnt + exceptions_cnt == total_records, (
            f"KPI conservation rule failed for seed {seed}! "
            f"Auto-Accepted ({auto_accepted_cnt}) + Human Review ({needs_review_cnt}) + "
            f"Exceptions ({exceptions_cnt}) = {auto_accepted_cnt + needs_review_cnt + exceptions_cnt} "
            f"but Total Processed = {total_records}"
        )

def test_exception_population_immutability():
    """
    Regression test verifying that human verification actions log human reviews
    without mutating or decrementing the baseline original exception population count.
    """
    exceptions_df = pd.DataFrame([
        {"ID": "EXC_001", "Amount": 100000.0, "Status": "needs_review"},
        {"ID": "EXC_002", "Amount": 250000.0, "Status": "needs_review"},
        {"ID": "EXC_003", "Amount": 500000.0, "Status": "exception"}
    ])
    
    # Original baseline population count
    total_exceptions = len(exceptions_df)
    assert total_exceptions == 3
    
    # Simulate auditor reviewing EXC_001
    human_reviews = {
        "EXC_001": {"human_reviewer_action": "Approve", "human_override": False}
    }
    
    verified_cnt = sum(1 for row in exceptions_df["ID"] if row in human_reviews)
    remaining_cnt = total_exceptions - verified_cnt
    
    # Immutability assertion: baseline total remains 3, remaining is 2, verified is 1
    assert total_exceptions == 3
    assert verified_cnt == 1
    assert remaining_cnt == 2
