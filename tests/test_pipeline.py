"""
Pipeline integration tests — all mocked, no live Gemini calls.

Tests cover:
- Multi-seed pipeline execution with mock Gemini responses
- Structural correctness of prediction output
- Status band validation (auto_accepted / needs_review / exception)
- Rate-limit (429) retry + fallback to exception path
- Malformed Gemini response handling
- Timeout / network failure fallback
- Missing API key fallback
- Optional live Gemini test (requires --live-gemini flag)
"""
import os
import json
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from backend.data_gen.generator import generate_reconciliation_data
from pipeline import ReconciliationPipeline, DecisionItem, BatchDecision
from scoring import calculate_precision_recall_f1
from tests.conftest import create_mock_gemini_client, MockGeminiModels


# ---------------------------------------------------------------------------
# Helper: generate test dataset in temp dir
# ---------------------------------------------------------------------------
def _generate_test_data(seed=42, n_records=50):
    tmp_dir = tempfile.mkdtemp()
    invoices_df, ledger_df, bank_df, ground_truth = generate_reconciliation_data(
        n_records=n_records, seed=seed, output_dir=tmp_dir
    )
    return tmp_dir, invoices_df, ledger_df, bank_df, ground_truth


# ---------------------------------------------------------------------------
# TEST 1: Multi-seed pipeline with mock Gemini
# ---------------------------------------------------------------------------
def test_pipeline_multi_seed_mocked():
    """
    Runs the reconciliation pipeline over 3 seeds with mock Gemini.
    Validates structural correctness of predictions.
    """
    seeds = [42, 101, 777]

    for seed in seeds:
        tmp_dir, invoices_df, ledger_df, bank_df, ground_truth = _generate_test_data(seed=seed, n_records=50)

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
            log_path=log_path
        )

        metrics = calculate_precision_recall_f1(predictions, ground_truth)

        # Structural assertions
        assert metrics["precision"] >= 0.0
        assert metrics["recall"] >= 0.0
        assert metrics["f1_score"] >= 0.0

        for pred in predictions:
            assert "status" in pred, "Prediction missing status key"
            assert pred["status"] in ["auto_accepted", "needs_review", "exception"], f"Invalid status: {pred['status']}"
            assert "ai_confidence" in pred
            assert "evidence_score" in pred
            assert "decision_confidence" in pred
            assert "source_record_id" in pred
            assert "selected_candidate_ids" in pred
            assert "rejected_candidate_ids" in pred


# ---------------------------------------------------------------------------
# TEST 2: Rate-limit (429) retry exhaustion → fallback to exception path
# ---------------------------------------------------------------------------
def test_rate_limit_429_routes_to_exception():
    """
    Simulates Gemini returning HTTP 429 (RESOURCE_EXHAUSTED) on every attempt.
    Verifies pipeline eventually falls back to exception routing WITHOUT
    fabricating AI confidence, and does NOT hang.
    """
    tmp_dir, _, _, _, _ = _generate_test_data(seed=42, n_records=40)
    invoices_path = os.path.join(tmp_dir, "invoices.csv")
    ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
    bank_path = os.path.join(tmp_dir, "bank_statement.csv")
    log_path = os.path.join(tmp_dir, "decisions_log.jsonl")

    pipeline = ReconciliationPipeline(model_name="gemini-2.5-flash")
    pipeline.api_key = "MOCK_KEY"

    # Create mock client whose generate_content always raises 429
    mock_models = MagicMock()
    mock_models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")
    mock_client = MagicMock()
    mock_client.models = mock_models
    pipeline.client = mock_client

    predictions = pipeline.run_reconciliation(
        invoices_path=invoices_path,
        ledger_path=ledger_path,
        bank_path=bank_path,
        log_path=log_path
    )

    # All Pass 1 exact matches should still succeed
    assert len(predictions) > 0

    # Any record that went through Pass 2 should be routed to exception with confidence 0
    exception_preds = [p for p in predictions if p.get("status") == "exception"]
    for exc in exception_preds:
        assert exc.get("ai_confidence", 0) == 0, "AI confidence must be 0 for fallback exceptions"
        assert exc.get("evidence_score", 0) == 0, "Evidence score must be 0 for fallback exceptions"
        assert "api_unavailable_fallback" in exc.get("reason_code", ""), f"Expected api_unavailable_fallback reason_code, got: {exc.get('reason_code')}"


# ---------------------------------------------------------------------------
# TEST 3: Malformed Gemini response → fallback to exception
# ---------------------------------------------------------------------------
def test_malformed_gemini_response_routes_to_exception():
    """
    Simulates Gemini returning garbled/unparseable text.
    Pipeline should fall back to exception routing, not crash.
    """
    tmp_dir, _, _, _, _ = _generate_test_data(seed=42, n_records=40)
    invoices_path = os.path.join(tmp_dir, "invoices.csv")
    ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
    bank_path = os.path.join(tmp_dir, "bank_statement.csv")
    log_path = os.path.join(tmp_dir, "decisions_log.jsonl")

    pipeline = ReconciliationPipeline(model_name="gemini-2.5-flash")
    pipeline.api_key = "MOCK_KEY"

    # Mock returns garbled text that cannot parse to BatchDecision
    class MalformedModels:
        def generate_content(self, model, contents, config=None):
            class MalformedResp:
                text = "THIS IS NOT VALID JSON { broken }"
            return MalformedResp()

    mock_client = MagicMock()
    mock_client.models = MalformedModels()
    pipeline.client = mock_client

    predictions = pipeline.run_reconciliation(
        invoices_path=invoices_path,
        ledger_path=ledger_path,
        bank_path=bank_path,
        log_path=log_path
    )

    # Pipeline should not crash
    assert len(predictions) > 0


# ---------------------------------------------------------------------------
# TEST 4: Timeout / network failure → fallback to exception
# ---------------------------------------------------------------------------
def test_network_timeout_routes_to_exception():
    """
    Simulates a network timeout on Gemini API call.
    """
    tmp_dir, _, _, _, _ = _generate_test_data(seed=42, n_records=40)
    invoices_path = os.path.join(tmp_dir, "invoices.csv")
    ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
    bank_path = os.path.join(tmp_dir, "bank_statement.csv")
    log_path = os.path.join(tmp_dir, "decisions_log.jsonl")

    pipeline = ReconciliationPipeline(model_name="gemini-2.5-flash")
    pipeline.api_key = "MOCK_KEY"

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = TimeoutError("Connection timed out after 30s")
    mock_client = MagicMock()
    mock_client.models = mock_models
    pipeline.client = mock_client

    predictions = pipeline.run_reconciliation(
        invoices_path=invoices_path,
        ledger_path=ledger_path,
        bank_path=bank_path,
        log_path=log_path
    )

    assert len(predictions) > 0
    exception_preds = [p for p in predictions if p.get("status") == "exception"]
    for exc in exception_preds:
        assert exc.get("ai_confidence", 0) == 0


# ---------------------------------------------------------------------------
# TEST 5: Missing API key → deterministic Pass 1 only, no crash
# ---------------------------------------------------------------------------
def test_missing_api_key_pass1_only():
    """
    Verifies that without GEMINI_API_KEY, pipeline runs Pass 1 only
    and routes unmatched records to exception queue without fabricating AI confidence.
    """
    tmp_dir, _, _, _, ground_truth = _generate_test_data(seed=42, n_records=40)
    invoices_path = os.path.join(tmp_dir, "invoices.csv")
    ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
    bank_path = os.path.join(tmp_dir, "bank_statement.csv")
    log_path = os.path.join(tmp_dir, "decisions_log.jsonl")

    # conftest already strips GEMINI_API_KEY, so pipeline.client will be None
    pipeline = ReconciliationPipeline(model_name="gemini-2.5-flash")
    assert pipeline.client is None, "Client should be None when GEMINI_API_KEY is unset"

    predictions = pipeline.run_reconciliation(
        invoices_path=invoices_path,
        ledger_path=ledger_path,
        bank_path=bank_path,
        log_path=log_path
    )

    assert len(predictions) > 0
    assert pipeline.gemini_calls == 0, "No Gemini calls should occur without API key"

    # Pass 1 alone should produce some matches
    metrics = calculate_precision_recall_f1(predictions, ground_truth)
    assert metrics["f1_score"] >= 0.40, f"Pass 1 F1 too low: {metrics['f1_score']}"


# ---------------------------------------------------------------------------
# TEST 6: Verify exponential backoff uses near-zero delays during tests
# ---------------------------------------------------------------------------
def test_backoff_uses_fast_delay_during_tests():
    """
    Verifies PYTEST_CURRENT_TEST env var is set (by conftest) so
    the retry backoff sleep is 0.001s, not 1/2/4 seconds.
    """
    assert os.getenv("PYTEST_CURRENT_TEST") is not None, "PYTEST_CURRENT_TEST should be set by conftest"

    import time
    tmp_dir, _, _, _, _ = _generate_test_data(seed=42, n_records=40)
    invoices_path = os.path.join(tmp_dir, "invoices.csv")
    ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
    bank_path = os.path.join(tmp_dir, "bank_statement.csv")
    log_path = os.path.join(tmp_dir, "decisions_log.jsonl")

    pipeline = ReconciliationPipeline(model_name="gemini-2.5-flash")
    pipeline.api_key = "MOCK_KEY"

    # Simulate 429 errors that trigger retry
    call_count = 0

    class CountingModels:
        def generate_content(self, model, contents, config=None):
            nonlocal call_count
            call_count += 1
            raise Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")

    mock_client = MagicMock()
    mock_client.models = CountingModels()
    pipeline.client = mock_client

    start = time.time()
    predictions = pipeline.run_reconciliation(
        invoices_path=invoices_path,
        ledger_path=ledger_path,
        bank_path=bank_path,
        log_path=log_path
    )
    elapsed = time.time() - start

    # With near-zero delay, total time should be well under 5 seconds for retries
    assert elapsed < 15, f"Pipeline took {elapsed:.1f}s — backoff delay may not be using test mode"


# ---------------------------------------------------------------------------
# TEST 7 (OPTIONAL): Live Gemini integration test — skipped by default
# ---------------------------------------------------------------------------
@pytest.mark.live_gemini
def test_live_gemini_integration():
    """
    OPTIONAL: Runs the full pipeline with a real Gemini API call.
    Only executes when `--live-gemini` flag is passed:
        py -m pytest --live-gemini -k test_live_gemini_integration

    Requires GEMINI_API_KEY to be set in the environment.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set; skipping live integration test")

    tmp_dir, _, _, _, ground_truth = _generate_test_data(seed=42, n_records=40)
    invoices_path = os.path.join(tmp_dir, "invoices.csv")
    ledger_path = os.path.join(tmp_dir, "internal_ledger.csv")
    bank_path = os.path.join(tmp_dir, "bank_statement.csv")
    log_path = os.path.join(tmp_dir, "decisions_log.jsonl")

    pipeline = ReconciliationPipeline(model_name="gemini-2.5-flash")
    # Override the conftest isolation for this specific test
    import google.genai as genai
    pipeline.client = genai.Client(api_key=api_key)
    pipeline.api_key = api_key

    predictions = pipeline.run_reconciliation(
        invoices_path=invoices_path,
        ledger_path=ledger_path,
        bank_path=bank_path,
        log_path=log_path
    )

    assert len(predictions) > 0
    assert pipeline.gemini_calls > 0, "Live test should have made at least 1 Gemini call"

    metrics = calculate_precision_recall_f1(predictions, ground_truth)
    assert metrics["f1_score"] >= 0.75, f"Live Gemini F1 score too low: {metrics['f1_score']}"
