"""
Benchmark tests — verifies benchmark runner with mock Gemini.
No live API calls.
"""
import os
import inspect
import tempfile
import pytest
from unittest.mock import patch
from benchmark import BenchmarkRunner, DEFAULT_SEEDS
from tests.conftest import create_mock_gemini_client


def test_aggregate_calculation():
    vals = [0.80, 0.85, 0.90, 0.95, 1.00]
    stats = BenchmarkRunner.compute_stats(vals)
    assert stats["mean"] == 0.90
    assert stats["median"] == 0.90
    assert stats["min"] == 0.80
    assert stats["max"] == 1.00
    assert stats["std_dev"] > 0.0


def test_reproducibility():
    """
    Verifies that running the benchmark for seed 42 twice produces identical results.
    Uses mock Gemini (conftest strips API key, so pipeline runs Pass 1 only).
    """
    res1 = BenchmarkRunner.run_seed_benchmark(seed=42, n_records=50)
    res2 = BenchmarkRunner.run_seed_benchmark(seed=42, n_records=50)
    
    assert res1["f1_score"] == res2["f1_score"]
    assert res1["precision"] == res2["precision"]
    assert res1["recall"] == res2["recall"]
    assert res1["match_rate"] == res2["match_rate"]


def test_no_ground_truth_leakage():
    """
    Verifies that ground truth is not a parameter of the pipeline.
    """
    from pipeline import ReconciliationPipeline
    sig = inspect.signature(ReconciliationPipeline.run_reconciliation)
    param_names = list(sig.parameters.keys())
    
    assert "ground_truth" not in param_names
    assert "truth_path" not in param_names
    assert "ground_truth_path" not in param_names


def test_benchmark_completion_and_failure_handling():
    """
    Verifies multi-seed benchmark completes without live Gemini.
    Pipeline runs Pass 1 only (conftest strips API key).
    """
    res = BenchmarkRunner.run_full_benchmark(seeds=[42, 101], n_records=40)
    assert "runs" in res
    assert "aggregates" in res
    assert len(res["runs"]) == 2
    assert "f1_score" in res["aggregates"]
    assert res["aggregates"]["f1_score"]["mean"] >= 0.0
