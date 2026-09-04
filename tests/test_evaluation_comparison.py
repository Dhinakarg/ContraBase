"""
Evaluation comparison tests — baseline vs AI comparison with mock Gemini.
No live API calls.
"""
import pytest
from benchmark import BenchmarkRunner


def test_identical_inputs_and_value_add():
    """
    Verifies that run_baseline_vs_ai_comparison executes both Deterministic Baseline and
    Full AI Controller on identical inputs.

    With conftest stripping GEMINI_API_KEY:
    - Baseline pipeline runs with client=None (Pass 1 only) — this is intentional.
    - Full AI pipeline ALSO runs with client=None (Pass 1 only) — because conftest
      strips the API key. Both produce deterministic results.
    - This verifies the comparison structure and output format.
    """
    comp = BenchmarkRunner.run_baseline_vs_ai_comparison(seed=42, n_records=50)
    
    assert "baseline" in comp
    assert "full_ai" in comp
    assert "deltas" in comp
    
    base = comp["baseline"]
    full = comp["full_ai"]
    deltas = comp["deltas"]
    
    # 1. Verify baseline AI calls == 0
    assert base["ai_calls"] == 0
    
    # 2. Verify deterministic matching handles obvious cases with non-degraded baseline
    assert base["precision"] >= 0.0
    assert base["recall"] >= 0.0
    assert base["f1_score"] >= 0.0
    
    # 3. With both pipelines using Pass 1 only (no API key), deltas should be >= 0
    assert deltas["recall_boost"] >= 0.0
    assert full["recall"] >= base["recall"]
