"""
Shared test fixtures and configuration for the Finance Controller test suite.

This conftest ensures:
1. NO test makes real Gemini API calls unless explicitly opted in via --live-gemini flag.
2. The pipeline's exponential backoff uses near-zero delays during tests.
3. Persistence state (cache, runs) is isolated per test.
4. GEMINI_API_KEY env var is unset during tests to prevent accidental live calls.
"""
import os
import json
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# CLI option: --live-gemini (opt-in for real API integration tests)
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    parser.addoption(
        "--live-gemini",
        action="store_true",
        default=False,
        help="Enable tests that make real Gemini API calls (requires GEMINI_API_KEY).",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live_gemini: marks tests requiring a real Gemini API call (deselect with '-m \"not live_gemini\"')"
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live-gemini"):
        skip_live = pytest.mark.skip(reason="Requires --live-gemini flag to run")
        for item in items:
            if "live_gemini" in item.keywords:
                item.add_marker(skip_live)


# ---------------------------------------------------------------------------
# Mock Gemini client factory — produces structured BatchDecision responses
# ---------------------------------------------------------------------------
def _build_mock_decisions(prompt_text: str) -> list:
    """Parse queries from the prompt and generate plausible mock decisions."""
    decisions = []
    try:
        queries_start = prompt_text.find("Queries Batch:\n")
        if queries_start < 0:
            queries_start = prompt_text.find("Queries Batch:\\n")
        if queries_start >= 0:
            json_str = prompt_text[queries_start + len("Queries Batch:\n"):].strip()
            queries = json.loads(json_str)
        else:
            queries = []
    except Exception:
        queries = []

    for q in queries:
        src = q.get("source_record", {})
        src_id = src.get("ledger_id") or src.get("bank_id") or "UNKNOWN"
        cands = (
            q.get("bank_candidates", [])
            + q.get("ledger_candidates", [])
            + q.get("invoice_candidates", [])
        )
        cand_ids = [
            c.get("invoice_id") or c.get("bank_id") or c.get("ledger_id")
            for c in cands
            if c
        ]
        decisions.append({
            "source_record_id": src_id,
            "candidate_ids": cand_ids,
            "selected_candidate_ids": cand_ids[:2],
            "rejected_candidate_ids": cand_ids[2:],
            "evidence_features": "mock: amount matched, date within 3 days",
            "decision": "match" if cand_ids else "no_match",
            "confidence": 92,
            "reason_code": "reference_typo" if cand_ids else "no_counterpart_found",
            "rationale": "Mock adjudication for testing",
            "suggested_corrective_entry": None,
        })
    return decisions


class MockGeminiModels:
    """Drop-in replacement for client.models with generate_content method."""

    def generate_content(self, model, contents, config=None):
        decisions = _build_mock_decisions(contents if isinstance(contents, str) else str(contents))

        class MockResponse:
            text = json.dumps({"decisions": decisions})

        return MockResponse()


def create_mock_gemini_client():
    """Create a mock Gemini client object matching the genai.Client interface."""
    client = MagicMock()
    client.models = MockGeminiModels()
    return client


# ---------------------------------------------------------------------------
# Auto-use fixture: isolate every test from real Gemini
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_gemini(monkeypatch):
    """
    Automatically applied to every test:
    1. Removes GEMINI_API_KEY from environment so ReconciliationPipeline.__init__
       sets self.client = None (prevents accidental real calls).
    2. Sets PYTEST_CURRENT_TEST so pipeline retry sleeps are near-zero.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "true")
    yield


# ---------------------------------------------------------------------------
# Explicit fixture: inject mock Gemini client into a pipeline instance
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_gemini_pipeline(monkeypatch):
    """
    Returns a ReconciliationPipeline with a mock Gemini client injected.
    The mock returns structurally valid BatchDecision JSON responses.

    Usage in tests:
        def test_something(mock_gemini_pipeline):
            pipeline = mock_gemini_pipeline
            preds = pipeline.run_reconciliation(...)
    """
    from pipeline import ReconciliationPipeline
    pipeline = ReconciliationPipeline()
    pipeline.client = create_mock_gemini_client()
    pipeline.api_key = "MOCK_KEY_FOR_TESTING"
    return pipeline
