import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(r"D:\Finance Controller")
import os
import json
import pandas as pd
from backend.data_gen.generator import generate_reconciliation_data
from pipeline import ReconciliationPipeline
from scoring import calculate_precision_recall_f1

SEEDS = [42, 101, 777, 1234, 2026]

print("="*80)
print("MULTI-SEED RISK-AWARE POLICY BENCHMARK RUN (IN-MEMORY EVALUATION)")
print("="*80)

summary_data = []

for seed in SEEDS:
    print(f"\nProcessing Seed {seed}...")
    
    # 1. Generate data for seed
    ledger_file = "data/internal_ledger.csv"
    bank_file = "data/bank_statement.csv"
    invoice_file = "data/invoices.csv"
    gt_file = "data/ground_truth.json"
    
    generate_reconciliation_data(
        seed=seed,
        n_records=80,
        anomaly_rate=0.15,
        multi_currency=False,
        output_dir="data"
    )
    
    # 2. Run pipeline
    pipeline = ReconciliationPipeline()
    predictions = pipeline.run_reconciliation(
        invoices_path=invoice_file,
        ledger_path=ledger_file,
        bank_path=bank_file,
        materiality_threshold_inr=400000.0,
        force_run=True # Force run to execute pipeline and apply new policy
    )
    
    # 3. Load files to calculate in-memory stats
    ledger_df = pd.read_csv(ledger_file)
    bank_df = pd.read_csv(bank_file)
    total_records = len(ledger_df) + len(bank_df)
    
    with open(gt_file, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)
        
    predicted_ledger_ids = {p.get("ledger_id") for p in predictions if p.get("ledger_id")}
    predicted_bank_ids = set()
    for p in predictions:
        if p.get("bank_ids"):
            predicted_bank_ids.update([str(b) for b in p.get("bank_ids")])
            
    # Calculate record stats in-memory using sets to prevent double-counting
    all_ledger_ids = set(str(x) for x in ledger_df["ledger_id"]) if not ledger_df.empty else set()
    all_bank_ids = set(str(x) for x in bank_df["bank_id"]) if not bank_df.empty else set()

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

    auto_accepted_records = len(auto_accepted_led) + len(auto_accepted_bnk)
    human_review_records = len(needs_review_led) + len(needs_review_bnk)
    exceptions_records = len(exceptions_led) + len(exceptions_bank)

    automation_rate = (auto_accepted_records / total_records) * 100 if total_records else 0.0
    human_review_rate = (human_review_records / total_records) * 100 if total_records else 0.0
    exceptions_rate = (exceptions_records / total_records) * 100 if total_records else 0.0
    
    # Calculate Precision, Recall, F1
    metrics = calculate_precision_recall_f1(predictions, ground_truth)
    
    # High materiality stats (Reconciliations involving >= 400k amount)
    high_mat_matches = []
    for p in predictions:
        l_id = p.get("ledger_id")
        amt = 0.0
        if l_id:
            amt_series = ledger_df[ledger_df["ledger_id"] == l_id]["amount"]
            if not amt_series.empty:
                amt = float(amt_series.values[0])
        if amt >= 400000.0:
            high_mat_matches.append(p)
            
    hm_auto_accepted = sum(1 for m in high_mat_matches if m.get("status") == "auto_accepted")
    hm_needs_review = sum(1 for m in high_mat_matches if m.get("status") == "needs_review")
    hm_exceptions = sum(1 for m in high_mat_matches if m.get("status") == "exception")
    
    # High-materiality unmatched records count towards exceptions
    unmatched_ledger_hm = sum(1 for _, row in ledger_df.iterrows() if str(row["ledger_id"]) not in predicted_ledger_ids and float(row["amount"]) >= 400000.0)
    unmatched_bank_hm = sum(1 for _, row in bank_df.iterrows() if str(row["bank_id"]) not in predicted_bank_ids and float(row["amount"]) >= 400000.0)
    hm_exceptions += unmatched_ledger_hm + unmatched_bank_hm
    
    print(f"  Total Processed: {total_records} records")
    print(f"  Auto-accepted: {auto_accepted_records} records ({automation_rate:.2f}%)")
    print(f"  Human review: {human_review_records} records ({human_review_rate:.2f}%)")
    print(f"  Exceptions: {exceptions_records} records ({exceptions_rate:.2f}%)")
    print(f"  F1 Score: {metrics.get('f1_score', 0.0)*100:.2f}%")
    print(f"  Precision: {metrics.get('precision', 0.0)*100:.2f}%")
    print(f"  Recall: {metrics.get('recall', 0.0)*100:.2f}%")
    print(f"  High-Mat Auto-Accepted (Matches): {hm_auto_accepted}")
    print(f"  High-Mat Routed to Review (Matches): {hm_needs_review}")
    
    summary_data.append({
        "Seed": seed,
        "Total Records": total_records,
        "Auto-Accepted": auto_accepted_records,
        "Human Review": human_review_records,
        "Exceptions": exceptions_records,
        "Automation Rate (%)": round(automation_rate, 2),
        "Human Review Rate (%)": round(human_review_rate, 2),
        "Precision (%)": round(metrics.get("precision", 0.0)*100, 2),
        "Recall (%)": round(metrics.get("recall", 0.0)*100, 2),
        "F1 (%)": round(metrics.get("f1_score", 0.0)*100, 2),
        "High-Mat Auto": hm_auto_accepted,
        "High-Mat Review": hm_needs_review
    })

print("\n" + "="*95)
print("BENCHMARK SUMMARY COMPARISON TABLE")
print("="*95)
df_summary = pd.DataFrame(summary_data)
print(df_summary.to_string(index=False))
print("="*95)
