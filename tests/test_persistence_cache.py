import os
import json
import pytest
import pandas as pd
from persistence import compute_config_hash, compute_candidate_set_hash, compute_gemini_cache_key, GeminiCache, RunStore, CACHE_FILE
from pipeline import ReconciliationPipeline, DecisionItem, compute_source_hash
from backend.data_gen.generator import generate_reconciliation_data

@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    """Isolate persistence files for testing."""
    runs_dir = str(tmp_path / "runs")
    current_run_file = str(tmp_path / "current_run.json")
    cache_file = str(tmp_path / "gemini_cache.json")
    
    monkeypatch.setattr("persistence.RUNS_DIR", runs_dir)
    monkeypatch.setattr("persistence.CURRENT_RUN_FILE", current_run_file)
    monkeypatch.setattr("persistence.CACHE_FILE", cache_file)
    
    # Clear cache before each test
    GeminiCache.clear()

def test_config_hash_deterministic():
    h1 = compute_config_hash(42, 80, 0.15, False, 400000.0)
    h2 = compute_config_hash(42, 80, 0.15, False, 400000.0)
    h3 = compute_config_hash(42, 80, 0.20, False, 400000.0)
    
    assert h1 == h2
    assert h1 != h3

def test_gemini_cache_hit_and_miss():
    src_hash = compute_source_hash({"ledger_id": "LED_101", "amount": 50000.0, "date": "2026-03-01", "reference_id": "REF123"})
    cand_hash = compute_candidate_set_hash([{"bank_id": "BNK_101", "amount": 50000.0, "date": "2026-03-01"}])
    cache_key = compute_gemini_cache_key(src_hash, cand_hash)

    assert GeminiCache.get(cache_key) is None

    mock_decision = {
        "source_record_id": "LED_101",
        "candidate_ids": ["BNK_101"],
        "selected_candidate_ids": ["BNK_101"],
        "rejected_candidate_ids": [],
        "evidence_features": "exact match",
        "decision": "match",
        "confidence": 98,
        "reason_code": "reference_typo",
        "rationale": "High candidate score match",
        "suggested_corrective_entry": None
    }

    GeminiCache.set(cache_key, mock_decision)
    cached = GeminiCache.get(cache_key)

    assert cached is not None
    assert isinstance(cached, dict)
    assert cached["decision"] == "match"
    assert cached["reason_code"] == "reference_typo"
    
    # Pydantic validation succeeds on clean cached dictionary
    validated = DecisionItem.model_validate(cached)
    assert validated.source_record_id == "LED_101"

def test_malformed_string_cache_entry_invalidated():
    """Test that a string value like 'match' is safely treated as cache miss without crashing Pydantic."""
    src_hash = compute_source_hash({"ledger_id": "LED_999", "amount": 100.0})
    cand_hash = compute_candidate_set_hash([])
    cache_key = compute_gemini_cache_key(src_hash, cand_hash)

    # Manually inject malformed string cache item
    raw_cache = {cache_key: "match"}
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(raw_cache, f)

    res = GeminiCache.get(cache_key)
    assert res is None  # Treated safely as cache miss!

def test_legacy_cache_schema_invalidated():
    """Test that cache entry without v2 schema version is safely ignored."""
    src_hash = compute_source_hash({"ledger_id": "LED_888", "amount": 200.0})
    cand_hash = compute_candidate_set_hash([])
    cache_key = compute_gemini_cache_key(src_hash, cand_hash)

    legacy_cache = {
        cache_key: {
            "decision": {"source_record_id": "LED_888", "decision": "match"},
            "cached_at": "2026-01-01"
        }
    }
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(legacy_cache, f)

    res = GeminiCache.get(cache_key)
    assert res is None  # Legacy version ignored safely!

def test_persistent_run_store_save_load():
    run_id = "RUN_TEST_101"
    config_hash = compute_config_hash(42, 50, 0.10, False)
    
    metadata = {
        "run_id": run_id,
        "seed": 42,
        "record_count": 100,
        "noise_level": 0.10,
        "multi_currency": False,
        "base_currency": "INR",
        "materiality_threshold_inr": 400000.0,
        "configuration_hash": config_hash,
        "gemini_calls": 0,
        "cached_ai_decisions": 10
    }
    manifest = {"invoices_count": 50, "ledger_count": 50, "bank_count": 50}
    predictions = [{"decision_id": "DEC_1", "status": "auto_accepted"}]
    metrics = {"precision": 1.0, "recall": 1.0, "f1_score": 1.0}
    logs = [{"type": "pipeline_timing", "total_records_processed": 100}]

    path = RunStore.save_run(run_id, metadata, manifest, predictions, metrics, logs)
    assert os.path.exists(path)

    loaded_current = RunStore.load_current_run()
    assert loaded_current is not None
    assert loaded_current["run_id"] == run_id
    assert loaded_current["metadata"]["base_currency"] == "INR"
    assert loaded_current["metadata"]["configuration_hash"] == config_hash

    found_run = RunStore.find_run_by_config_hash(config_hash)
    assert found_run is not None
    assert found_run["run_id"] == run_id

def test_pipeline_caching_and_zero_calls_on_repeat(tmp_path, monkeypatch):
    output_dir = str(tmp_path / "data")
    generate_reconciliation_data(n_records=40, seed=42, anomaly_rate=0.10, output_dir=output_dir)

    inv_path = os.path.join(output_dir, "invoices.csv")
    led_path = os.path.join(output_dir, "internal_ledger.csv")
    bnk_path = os.path.join(output_dir, "bank_statement.csv")
    log_path = os.path.join(output_dir, "decisions_log.jsonl")

    class MockGenModel:
        def generate_content(self, model, contents, config):
            class MockResp:
                pass
            try:
                queries_start = contents.find("Queries Batch:\n")
                json_str = contents[queries_start + len("Queries Batch:\n"):].strip()
                queries = json.loads(json_str)
            except Exception:
                queries = []

            decisions = []
            for q in queries:
                src = q.get("source_record", {})
                src_id = src.get("ledger_id") or src.get("bank_id") or "UNKNOWN"
                cands = q.get("bank_candidates", []) + q.get("ledger_candidates", []) + q.get("invoice_candidates", [])
                cand_ids = [c.get("invoice_id") or c.get("bank_id") or c.get("ledger_id") for c in cands if c]
                decisions.append({
                    "source_record_id": src_id,
                    "candidate_ids": cand_ids,
                    "selected_candidate_ids": cand_ids[:2],
                    "rejected_candidate_ids": cand_ids[2:],
                    "evidence_features": "mock features",
                    "decision": "match" if cand_ids else "no_match",
                    "confidence": 95,
                    "reason_code": "reference_typo",
                    "rationale": "mock rationale",
                    "suggested_corrective_entry": None
                })
            
            resp = MockResp()
            resp.text = json.dumps({"decisions": decisions})
            return resp

    pipeline1 = ReconciliationPipeline()
    monkeypatch.setattr(pipeline1, "client", type("MockClient", (), {"models": MockGenModel()})())
    res1 = pipeline1.run_reconciliation(inv_path, led_path, bnk_path, log_path=log_path)
    assert pipeline1.gemini_calls > 0

    # Run 2: Re-run exact same pipeline
    pipeline2 = ReconciliationPipeline()
    monkeypatch.setattr(pipeline2, "client", type("MockClient", (), {"models": MockGenModel()})())
    res2 = pipeline2.run_reconciliation(inv_path, led_path, bnk_path, log_path=log_path)
    
    assert pipeline2.gemini_calls == 0  # Zero new API calls on repeat run!
    assert pipeline2.cached_ai_decisions > 0
    assert len(res1) == len(res2)

def test_configuration_dirty_state_does_not_call_gemini():
    c_hash1 = compute_config_hash(42, 80, 0.15, False)
    c_hash2 = compute_config_hash(42, 80, 0.20, False)

    assert c_hash1 != c_hash2
