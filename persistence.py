import os
import json
import hashlib
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List

RUNS_DIR = os.path.join("data", "runs")
CURRENT_RUN_FILE = os.path.join("data", "current_run.json")
CACHE_FILE = os.path.join("data", "gemini_cache.json")

_cache_lock = threading.RLock()
_store_lock = threading.RLock()

def compute_config_hash(
    seed: int,
    n_records: int,
    anomaly_rate: float,
    multi_currency: bool,
    materiality_threshold_inr: float = 400000.0,
    model_name: str = "gemini-2.5-flash"
) -> str:
    """Computes a deterministic SHA256 signature for a generation and reconciliation configuration."""
    raw = f"{seed}_{n_records}_{round(float(anomaly_rate), 4)}_{bool(multi_currency)}_{round(float(materiality_threshold_inr), 2)}_{str(model_name)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()

def compute_candidate_set_hash(candidates: List[dict]) -> str:
    """Computes a deterministic SHA256 signature for a list of candidate records."""
    cand_sigs = []
    for c in candidates:
        c_id = str(c.get("invoice_id") or c.get("bank_id") or c.get("ledger_id") or "")
        amt = round(float(c.get("amount") or 0.0), 2)
        dt = str(c.get("date") or c.get("due_date") or "")
        cand_sigs.append(f"{c_id}:{amt}:{dt}")
    cand_sigs.sort()
    raw = "|".join(cand_sigs)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()

def compute_gemini_cache_key(
    source_record_hash: str,
    candidate_set_hash: str,
    model_name: str = "gemini-2.5-flash",
    prompt_version: str = "v1.0"
) -> str:
    """Computes a robust, immutable cache key for Gemini adjudication."""
    raw = f"{source_record_hash}_{candidate_set_hash}_{model_name}_{prompt_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


CACHE_SCHEMA_VERSION = "v2"

class GeminiCache:
    """Persistent, thread-safe cache for Gemini AI adjudication decisions."""
    
    @classmethod
    def _load_cache(cls) -> Dict[str, dict]:
        if not os.path.exists(CACHE_FILE):
            return {}
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @classmethod
    def _save_cache(cls, data: Dict[str, dict]) -> None:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp_file = f"{CACHE_FILE}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_file, CACHE_FILE)

    @classmethod
    def get(cls, cache_key: str) -> Optional[dict]:
        with _cache_lock:
            cache = cls._load_cache()
            item = cache.get(cache_key)
            if not item or not isinstance(item, dict):
                return None
            
            # Enforce schema version v2 for persistent cache validity
            if item.get("version") != CACHE_SCHEMA_VERSION:
                return None

            dec_item = item.get("decision_item") or item.get("decision")
            if isinstance(dec_item, dict) and "source_record_id" in dec_item:
                return dec_item

            return None

    @classmethod
    def set(cls, cache_key: str, decision: dict) -> None:
        with _cache_lock:
            cache = cls._load_cache()
            cache[cache_key] = {
                "version": CACHE_SCHEMA_VERSION,
                "decision_item": decision,
                "cached_at": datetime.now().isoformat()
            }
            cls._save_cache(cache)

    @classmethod
    def get_many(cls, cache_keys: List[str]) -> Dict[str, dict]:
        with _cache_lock:
            cache = cls._load_cache()
            return {k: cache[k]["decision"] for k in cache_keys if k in cache and "decision" in cache[k]}

    @classmethod
    def clear(cls) -> None:
        with _cache_lock:
            if os.path.exists(CACHE_FILE):
                try:
                    os.remove(CACHE_FILE)
                except Exception:
                    pass


class RunStore:
    """Persistent, filesystem-backed store for completed reconciliation runs."""

    @classmethod
    def save_run(
        cls,
        run_id: str,
        metadata: dict,
        dataset_manifest: dict,
        predictions: List[dict],
        metrics: dict,
        log_records: List[dict]
    ) -> str:
        with _store_lock:
            run_dir = os.path.join(RUNS_DIR, run_id)
            os.makedirs(run_dir, exist_ok=True)

            metadata["completed_at"] = datetime.now().isoformat()
            metadata["status"] = "completed"

            # Save metadata.json
            with open(os.path.join(run_dir, "metadata.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            # Save dataset_manifest.json
            with open(os.path.join(run_dir, "dataset_manifest.json"), "w", encoding="utf-8") as f:
                json.dump(dataset_manifest, f, indent=2)

            # Save reconciliation_results.json
            results = {
                "run_id": run_id,
                "metrics": metrics,
                "predictions": predictions
            }
            with open(os.path.join(run_dir, "reconciliation_results.json"), "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)

            # Save decisions.jsonl
            with open(os.path.join(run_dir, "decisions.jsonl"), "w", encoding="utf-8") as f:
                for rec in log_records:
                    f.write(json.dumps(rec) + "\n")

            # Update current_run.json
            current_info = {
                "run_id": run_id,
                "configuration_hash": metadata.get("configuration_hash"),
                "status": "completed",
                "updated_at": datetime.now().isoformat()
            }
            os.makedirs(os.path.dirname(CURRENT_RUN_FILE), exist_ok=True)
            tmp_cur = f"{CURRENT_RUN_FILE}.tmp"
            with open(tmp_cur, "w", encoding="utf-8") as f:
                json.dump(current_info, f, indent=2)
            os.replace(tmp_cur, CURRENT_RUN_FILE)

            return run_dir

    @classmethod
    def load_run(cls, run_id: str) -> Optional[dict]:
        with _store_lock:
            run_dir = os.path.join(RUNS_DIR, run_id)
            if not os.path.exists(run_dir):
                return None
            try:
                meta_path = os.path.join(run_dir, "metadata.json")
                res_path = os.path.join(run_dir, "reconciliation_results.json")
                man_path = os.path.join(run_dir, "dataset_manifest.json")
                log_path = os.path.join(run_dir, "decisions.jsonl")

                if not os.path.exists(meta_path) or not os.path.exists(res_path):
                    return None

                with open(meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)

                with open(res_path, "r", encoding="utf-8") as f:
                    results = json.load(f)

                dataset_manifest = {}
                if os.path.exists(man_path):
                    with open(man_path, "r", encoding="utf-8") as f:
                        dataset_manifest = json.load(f)

                log_records = []
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                log_records.append(json.loads(line))

                return {
                    "run_id": run_id,
                    "metadata": metadata,
                    "dataset_manifest": dataset_manifest,
                    "predictions": results.get("predictions", []),
                    "metrics": results.get("metrics", {}),
                    "log_records": log_records
                }
            except Exception:
                return None

    @classmethod
    def load_current_run(cls) -> Optional[dict]:
        with _store_lock:
            if not os.path.exists(CURRENT_RUN_FILE):
                return None
            try:
                with open(CURRENT_RUN_FILE, "r", encoding="utf-8") as f:
                    info = json.load(f)
                run_id = info.get("run_id")
                if not run_id:
                    return None
                return cls.load_run(run_id)
            except Exception:
                return None

    @classmethod
    def find_run_by_config_hash(cls, config_hash: str) -> Optional[dict]:
        with _store_lock:
            if not os.path.exists(RUNS_DIR):
                return None
            try:
                for entry in os.listdir(RUNS_DIR):
                    run_dir = os.path.join(RUNS_DIR, entry)
                    meta_path = os.path.join(run_dir, "metadata.json")
                    if os.path.isdir(run_dir) and os.path.exists(meta_path):
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        if meta.get("configuration_hash") == config_hash and meta.get("status") == "completed":
                            return cls.load_run(entry)
            except Exception:
                pass
            return None
