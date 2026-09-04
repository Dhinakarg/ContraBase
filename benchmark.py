import os
import time
import json
import tempfile
import statistics
import pandas as pd
from typing import List, Dict

from backend.data_gen.generator import generate_reconciliation_data
from pipeline import ReconciliationPipeline
from scoring import calculate_precision_recall_f1
from failure_analysis import FailureAnalyzer

DEFAULT_SEEDS = [42, 101, 777, 1234, 2026]

class BenchmarkRunner:
    @staticmethod
    def compute_stats(values: List[float]) -> dict:
        """
        Calculates mean, median, std_dev, min, and max for a list of numerical metrics.
        """
        if not values:
            return {"mean": 0.0, "median": 0.0, "std_dev": 0.0, "min": 0.0, "max": 0.0}
        
        vals = [float(v) for v in values]
        std_val = statistics.stdev(vals) if len(vals) >= 2 else 0.0
        
        return {
            "mean": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "std_dev": round(std_val, 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4)
        }

    @classmethod
    def run_seed_benchmark(
        cls,
        seed: int,
        n_records: int = 500,
        anomaly_rate: float = 0.15,
        model_name: str = "gemini-2.5-flash",
        multi_currency: bool = False,
        auto_accept_thresh: float = 95.0,
        needs_review_thresh: float = 70.0,
        materiality_threshold_inr: float = 400000.0,
        **kwargs
    ) -> dict:
        """
        Executes an isolated, reproducible benchmark for a single seed.
        NO ground truth is exposed during inference.
        """
        if "materiality_threshold" in kwargs:
            materiality_threshold_inr = kwargs["materiality_threshold"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Generate synthetic dataset
            invoices_df, ledger_df, bank_df, ground_truth = generate_reconciliation_data(
                n_records=n_records,
                seed=seed,
                anomaly_rate=anomaly_rate,
                output_dir=tmp_dir,
                multi_currency=multi_currency
            )

            invoices_path = os.path.join(tmp_dir, "invoices.csv")
            ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
            bank_path = os.path.join(tmp_dir, "bank_statement.csv")
            log_path = os.path.join(tmp_dir, "decisions_log.jsonl")

            total_records = len(ledger_df) + len(bank_df)

            # 2. Run pipeline (TIMED INFERENCE - GROUND TRUTH IS NOT PASSED)
            start_time = time.time()
            pipeline = ReconciliationPipeline(model_name=model_name)
            predictions = pipeline.run_reconciliation(
                invoices_path=invoices_path,
                ledger_path=ledger_path,
                bank_path=bank_path,
                log_path=log_path,
                auto_accept_thresh=auto_accept_thresh,
                needs_review_thresh=needs_review_thresh,
                materiality_threshold_inr=materiality_threshold_inr
            )
            total_runtime = time.time() - start_time
            throughput = total_records / total_runtime if total_runtime > 0 else 0.0

            # 3. Post-Inference Ground Truth Evaluation (ONLY AFTER INFERENCE)
            metrics = calculate_precision_recall_f1(predictions, ground_truth)

            # 4. Detailed rate calculations
            matched_count = len([p for p in predictions if p.get("ledger_id")])
            total_ledger = len(ledger_df)
            match_rate = matched_count / total_ledger if total_ledger > 0 else 0.0
            unresolved_rate = 1.0 - match_rate

            # Calculate record-level status counts
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

            auto_accepted_cnt = len(auto_accepted_led) + len(auto_accepted_bnk)
            needs_review_cnt = len(needs_review_led) + len(needs_review_bnk)
            exceptions_cnt = len(exceptions_led) + len(exceptions_bank)
            total_records = len(ledger_df) + len(bank_df)

            auto_accepted_rate = auto_accepted_cnt / total_records if total_records > 0 else 0.0
            needs_review_rate = needs_review_cnt / total_records if total_records > 0 else 0.0
            exception_rate = exceptions_cnt / total_records if total_records > 0 else 0.0

            # 4. Perform post-inference failure analysis (POST-INFERENCE ONLY)
            failure_res = FailureAnalyzer.analyze_failures(predictions, ground_truth, ledger_df, bank_df, invoices_df)

            return {
                "seed": seed,
                "record_count": total_records,
                "precision": round(metrics["precision"], 4),
                "recall": round(metrics["recall"], 4),
                "f1_score": round(metrics["f1_score"], 4),
                "match_rate": round(match_rate, 4),
                "unresolved_rate": round(unresolved_rate, 4),
                "auto_accepted_rate": round(auto_accepted_rate, 4),
                "needs_review_rate": round(needs_review_rate, 4),
                "exception_rate": round(exception_rate, 4),
                "throughput_records_per_sec": round(throughput, 1),
                "total_runtime": round(total_runtime, 3)
            }

    @classmethod
    def run_multi_seed_benchmark(
        cls,
        seeds: List[int] = None,
        n_records: int = 500,
        anomaly_rate: float = 0.15,
        model_name: str = "gemini-2.5-flash",
        multi_currency: bool = False,
        auto_accept_thresh: float = 95.0,
        needs_review_thresh: float = 70.0,
        materiality_threshold_inr: float = 400000.0,
        **kwargs
    ) -> dict:
        """
        Runs multi-seed benchmarks and computes aggregate statistics.
        """
        if "materiality_threshold" in kwargs:
            materiality_threshold_inr = kwargs["materiality_threshold"]

        seeds = seeds or DEFAULT_SEEDS
        runs = []

        for seed in seeds:
            try:
                run_res = cls.run_seed_benchmark(
                    seed=seed,
                    n_records=n_records,
                    anomaly_rate=anomaly_rate,
                    model_name=model_name,
                    multi_currency=multi_currency,
                    auto_accept_thresh=auto_accept_thresh,
                    needs_review_thresh=needs_review_thresh,
                    materiality_threshold_inr=materiality_threshold_inr
                )
                runs.append(run_res)
            except Exception as e:
                print(f"Error executing benchmark for seed {seed}: {e}")
                runs.append({
                    "seed": seed,
                    "record_count": n_records,
                    "precision": 0.0,
                    "recall": 0.0,
                    "f1_score": 0.0,
                    "match_rate": 0.0,
                    "unresolved_rate": 1.0,
                    "auto_accepted_rate": 0.0,
                    "needs_review_rate": 0.0,
                    "exception_rate": 1.0,
                    "throughput_records_per_sec": 0.0,
                    "total_runtime": 0.0,
                    "error": str(e)
                })

        valid_runs = [r for r in runs if "error" not in r]
        
        aggregates = {
            "precision": cls.compute_stats([r["precision"] for r in valid_runs]),
            "recall": cls.compute_stats([r["recall"] for r in valid_runs]),
            "f1_score": cls.compute_stats([r["f1_score"] for r in valid_runs]),
            "match_rate": cls.compute_stats([r["match_rate"] for r in valid_runs]),
            "throughput_records_per_sec": cls.compute_stats([r["throughput_records_per_sec"] for r in valid_runs]),
            "auto_accepted_rate": cls.compute_stats([r["auto_accepted_rate"] for r in valid_runs])
        }

        return {
            "seeds_tested": seeds,
            "n_records_per_seed": n_records,
            "runs": runs,
            "aggregates": aggregates
        }

    run_full_benchmark = run_multi_seed_benchmark

    @classmethod
    def run_baseline_vs_ai_comparison(
        cls,
        seed: int = 42,
        n_records: int = 100,
        anomaly_rate: float = 0.15,
        model_name: str = "gemini-2.5-flash",
        multi_currency: bool = False,
        auto_accept_thresh: float = 95.0,
        needs_review_thresh: float = 70.0,
        materiality_threshold_inr: float = 400000.0,
        **kwargs
    ) -> dict:
        """
        Executes head-to-head evaluation comparison between:
        A. Deterministic-only baseline (Pass 1 exact match only)
        B. Full ContraBase (Pass 1 + Pass 2 Gemini adjudication)
        
        Both systems execute on the EXACT SAME generated dataset and ground truth.
        """
        if "materiality_threshold" in kwargs:
            materiality_threshold_inr = kwargs["materiality_threshold"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Generate synthetic dataset once
            invoices_df, ledger_df, bank_df, ground_truth = generate_reconciliation_data(
                n_records=n_records,
                seed=seed,
                anomaly_rate=anomaly_rate,
                output_dir=tmp_dir,
                multi_currency=multi_currency
            )

            invoices_path = os.path.join(tmp_dir, "invoices.csv")
            ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
            bank_path = os.path.join(tmp_dir, "bank_statement.csv")
            
            total_records = len(ledger_df) + len(bank_df)
            total_ledger = len(ledger_df)

            # --- SYSTEM A: Deterministic Baseline (Pass 1 Only) ---
            log_path_base = os.path.join(tmp_dir, "decisions_log_base.jsonl")
            pipeline_base = ReconciliationPipeline(model_name=model_name)
            pipeline_base.client = None # Force deterministic pass only (no AI calls)

            start_base = time.time()
            preds_base = pipeline_base.run_reconciliation(
                invoices_path=invoices_path,
                ledger_path=ledger_path,
                bank_path=bank_path,
                log_path=log_path_base,
                auto_accept_thresh=auto_accept_thresh,
                needs_review_thresh=needs_review_thresh,
                materiality_threshold_inr=materiality_threshold_inr
            )
            runtime_base = time.time() - start_base
            throughput_base = total_records / runtime_base if runtime_base > 0 else 0.0
            metrics_base = calculate_precision_recall_f1(preds_base, ground_truth)
            matched_base = len([p for p in preds_base if p.get("ledger_id")])
            match_rate_base = matched_base / total_ledger if total_ledger > 0 else 0.0

            # --- SYSTEM B: Full ContraBase (Pass 1 + Pass 2) ---
            log_path_ai = os.path.join(tmp_dir, "decisions_log_ai.jsonl")
            pipeline_ai = ReconciliationPipeline(model_name=model_name)

            start_ai = time.time()
            preds_ai = pipeline_ai.run_reconciliation(
                invoices_path=invoices_path,
                ledger_path=ledger_path,
                bank_path=bank_path,
                log_path=log_path_ai,
                auto_accept_thresh=auto_accept_thresh,
                needs_review_thresh=needs_review_thresh,
                materiality_threshold_inr=materiality_threshold_inr
            )
            runtime_ai = time.time() - start_ai
            throughput_ai = total_records / runtime_ai if runtime_ai > 0 else 0.0
            metrics_ai = calculate_precision_recall_f1(preds_ai, ground_truth)
            matched_ai = len([p for p in preds_ai if p.get("ledger_id")])
            match_rate_ai = matched_ai / total_ledger if total_ledger > 0 else 0.0
            ai_calls_ai = len([p for p in preds_ai if p.get("match_type", "").startswith("ai_")])

            return {
                "seed": seed,
                "total_records": total_records,
                "baseline": {
                    "name": "Deterministic Baseline (Pass 1)",
                    "precision": round(metrics_base["precision"], 4),
                    "recall": round(metrics_base["recall"], 4),
                    "f1_score": round(metrics_base["f1_score"], 4),
                    "match_rate": round(match_rate_base, 4),
                    "unresolved_rate": round(1.0 - match_rate_base, 4),
                    "throughput_records_per_sec": round(throughput_base, 1),
                    "ai_calls": 0,
                    "runtime_seconds": round(runtime_base, 3)
                },
                "full_ai": {
                    "name": "Full AI Controller (Pass 1 + Pass 2)",
                    "precision": round(metrics_ai["precision"], 4),
                    "recall": round(metrics_ai["recall"], 4),
                    "f1_score": round(metrics_ai["f1_score"], 4),
                    "match_rate": round(match_rate_ai, 4),
                    "unresolved_rate": round(1.0 - match_rate_ai, 4),
                    "throughput_records_per_sec": round(throughput_ai, 1),
                    "ai_calls": ai_calls_ai,
                    "runtime_seconds": round(runtime_ai, 3)
                },
                "deltas": {
                    "recall_boost": round(metrics_ai["recall"] - metrics_base["recall"], 4),
                    "f1_boost": round(metrics_ai["f1_score"] - metrics_base["f1_score"], 4),
                    "match_rate_boost": round(match_rate_ai - match_rate_base, 4)
                }
            }

    @classmethod
    def run_five_seed_comparison(
        cls,
        seeds: List[int] = None,
        n_records: int = 500,
        anomaly_rate: float = 0.15,
        model_name: str = "gemini-2.5-flash",
        multi_currency: bool = False,
        auto_accept_thresh: float = 95.0,
        needs_review_thresh: float = 70.0,
        materiality_threshold_inr: float = 400000.0
    ) -> dict:
        """
        Runs head-to-head comparison of System A (Deterministic Baseline) vs System B (Full AI Controller)
        across the official five seeds (42, 101, 777, 1234, 2026).
        """
        seeds = seeds or DEFAULT_SEEDS
        base_runs = []
        ai_runs = []

        for seed in seeds:
            comp = cls.run_baseline_vs_ai_comparison(
                seed=seed,
                n_records=n_records,
                anomaly_rate=anomaly_rate,
                model_name=model_name,
                multi_currency=multi_currency,
                auto_accept_thresh=auto_accept_thresh,
                needs_review_thresh=needs_review_thresh,
                materiality_threshold_inr=materiality_threshold_inr
            )
            base_runs.append(comp["baseline"])
            ai_runs.append(comp["full_ai"])

        base_aggregates = {
            "precision": cls.compute_stats([r["precision"] for r in base_runs]),
            "recall": cls.compute_stats([r["recall"] for r in base_runs]),
            "f1_score": cls.compute_stats([r["f1_score"] for r in base_runs]),
            "match_rate": cls.compute_stats([r["match_rate"] for r in base_runs]),
            "throughput_records_per_sec": cls.compute_stats([r["throughput_records_per_sec"] for r in base_runs])
        }

        ai_aggregates = {
            "precision": cls.compute_stats([r["precision"] for r in ai_runs]),
            "recall": cls.compute_stats([r["recall"] for r in ai_runs]),
            "f1_score": cls.compute_stats([r["f1_score"] for r in ai_runs]),
            "match_rate": cls.compute_stats([r["match_rate"] for r in ai_runs]),
            "throughput_records_per_sec": cls.compute_stats([r["throughput_records_per_sec"] for r in ai_runs])
        }

        # Calculate percentage point lifts
        recall_lift_pp = round((ai_aggregates["recall"]["mean"] - base_aggregates["recall"]["mean"]) * 100, 2)
        f1_lift_pp = round((ai_aggregates["f1_score"]["mean"] - base_aggregates["f1_score"]["mean"]) * 100, 2)
        match_rate_lift_pp = round((ai_aggregates["match_rate"]["mean"] - base_aggregates["match_rate"]["mean"]) * 100, 2)

        return {
            "seeds_tested": seeds,
            "n_records_per_seed": n_records,
            "baseline_aggregates": base_aggregates,
            "ai_aggregates": ai_aggregates,
            "lifts": {
                "recall_lift_percentage_points": recall_lift_pp,
                "f1_lift_percentage_points": f1_lift_pp,
                "match_rate_lift_percentage_points": match_rate_lift_pp
            }
        }

    @staticmethod
    def save_benchmark_results(results: dict, file_path: str = "data/benchmark_results.json"):
        """
        Saves benchmark results to disk.
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(results, f, indent=4)

    @staticmethod
    def load_benchmark_results(file_path: str = "data/benchmark_results.json") -> dict:
        """
        Loads saved benchmark results from disk.
        """
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
