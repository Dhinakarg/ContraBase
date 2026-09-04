import os
import time
import json
import hashlib
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from backend.data_gen.generator import generate_reconciliation_data
from pipeline import ReconciliationPipeline
from scoring import calculate_precision_recall_f1
from review_engine import HumanReviewEngine
from persistence import compute_config_hash, RunStore
from ui_common import (
    DATA_DIR, INVOICES_PATH, LEDGER_PATH, BANK_PATH, TRUTH_PATH, LOG_PATH,
    inject_custom_styles, load_reconciliation_context, trigger_scroll_to_top,
    resolve_gemini_key
)
from views.overview import render_overview_view
from views.reconciliation import render_reconciliation_view
from views.exceptions import render_exceptions_view
from views.review_queue import render_review_queue_view
from views.analytics import render_analytics_view
from views.audit_trail import render_audit_trail_view
from views.settings import render_settings_view
from views.safety_verification import render_safety_verification_view

load_dotenv()

# Resolve Gemini API key from environment, session state, or Streamlit Cloud Secrets
resolve_gemini_key()

# Page config
st.set_page_config(
    page_title="ContraBase",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styles
inject_custom_styles()

PAGE_SLUG_MAP = {
    "overview": "🏠 Overview",
    "reconciliation": "🔄 Reconciliation",
    "exceptions": "🚨 Exceptions",
    "review": "👤 Review Queue",
    "analytics": "📊 Analytics",
    "audit": "🔍 Audit Trail",
    "settings": "⚙ Settings",
    "safety": "🛡️ Safety Verification"
}
SLUG_PAGE_MAP = {v: k for k, v in PAGE_SLUG_MAP.items()}

# Initialize session state parameters with query param persistence (Defect 1)
url_page_slug = st.query_params.get("page")
if "current_page" not in st.session_state:
    if url_page_slug and url_page_slug in PAGE_SLUG_MAP:
        st.session_state.current_page = PAGE_SLUG_MAP[url_page_slug]
    else:
        st.session_state.current_page = "🏠 Overview"
if "previous_page" not in st.session_state:
    st.session_state.previous_page = None
if "seed" not in st.session_state:
    st.session_state.seed = 42
if "n_records" not in st.session_state:
    st.session_state.n_records = 80
if "noise_level" not in st.session_state:
    st.session_state.noise_level = 0.15
if "multi_currency" not in st.session_state:
    st.session_state.multi_currency = False
if "materiality_threshold_inr" not in st.session_state:
    st.session_state.materiality_threshold_inr = 400000.0
if "auto_accept_thresh" not in st.session_state:
    st.session_state.auto_accept_thresh = 95.0
if "needs_review_thresh" not in st.session_state:
    st.session_state.needs_review_thresh = 70.0
if "human_reviews" not in st.session_state:
    st.session_state.human_reviews = HumanReviewEngine.load_human_reviews()
if "reconciled" not in st.session_state:
    st.session_state.reconciled = False
if "throughput" not in st.session_state:
    st.session_state.throughput = 0.0
if "exec_time" not in st.session_state:
    st.session_state.exec_time = 0.0
if "total_records" not in st.session_state:
    st.session_state.total_records = 0


def execute_reconciliation(force_new: bool = False):
    """
    Executes or loads reconciliation pipeline idempotently based on active configuration hash.
    Never duplicates Gemini API calls for already-cached runs.
    """
    config_hash = compute_config_hash(
        seed=st.session_state.seed,
        n_records=st.session_state.n_records,
        anomaly_rate=st.session_state.noise_level,
        multi_currency=st.session_state.multi_currency,
        materiality_threshold_inr=st.session_state.materiality_threshold_inr
    )

    existing_run = RunStore.find_run_by_config_hash(config_hash)
    if existing_run and not force_new:
        RunStore.save_run(
            run_id=existing_run["run_id"],
            metadata=existing_run["metadata"],
            dataset_manifest=existing_run["dataset_manifest"],
            predictions=existing_run["predictions"],
            metrics=existing_run["metrics"],
            log_records=existing_run["log_records"]
        )
        st.toast("Loaded matching completed run from persistent store!", icon="📁")
        return existing_run

    with st.spinner("Executing persistent reconciliation pipeline..."):
        generate_reconciliation_data(
            n_records=st.session_state.n_records,
            seed=st.session_state.seed,
            anomaly_rate=st.session_state.noise_level,
            output_dir=DATA_DIR,
            multi_currency=st.session_state.multi_currency
        )

        pipeline_start = time.time()
        pipeline = ReconciliationPipeline()
        predictions = pipeline.run_reconciliation(
            invoices_path=INVOICES_PATH,
            ledger_path=LEDGER_PATH,
            bank_path=BANK_PATH,
            log_path=LOG_PATH,
            auto_accept_thresh=st.session_state.auto_accept_thresh,
            needs_review_thresh=st.session_state.needs_review_thresh,
            materiality_threshold_inr=st.session_state.materiality_threshold_inr
        )
        pipeline_time = time.time() - pipeline_start

        invoices_df = pd.read_csv(INVOICES_PATH)
        ledger_df = pd.read_csv(LEDGER_PATH)
        bank_df = pd.read_csv(BANK_PATH)
        with open(TRUTH_PATH, "r", encoding="utf-8") as f:
            ground_truth = json.load(f)

        metrics = calculate_precision_recall_f1(predictions, ground_truth)
        total_records = len(ledger_df) + len(bank_df)
        throughput = total_records / pipeline_time if pipeline_time > 0 else 0.0

        run_id = f"RUN_{st.session_state.seed}_{total_records}_{hashlib.sha256(config_hash.encode('utf-8')).hexdigest()[:6].upper()}"

        metadata = {
            "run_id": run_id,
            "seed": st.session_state.seed,
            "record_count": total_records,
            "noise_level": st.session_state.noise_level,
            "multi_currency": st.session_state.multi_currency,
            "base_currency": "INR",
            "materiality_threshold_inr": st.session_state.materiality_threshold_inr,
            "pipeline_version": "1.0",
            "prompt_version": "v1.0",
            "model_name": pipeline.model_name,
            "created_at": datetime.now().isoformat(),
            "status": "completed",
            "configuration_hash": config_hash,
            "exec_time": round(pipeline_time, 3),
            "throughput": round(throughput, 1),
            "gemini_calls": pipeline.gemini_calls,
            "cached_ai_decisions": pipeline.cached_ai_decisions
        }

        dataset_manifest = {
            "invoices_count": len(invoices_df),
            "ledger_count": len(ledger_df),
            "bank_count": len(bank_df)
        }

        log_records = []
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        log_records.append(json.loads(line))

        timing_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "pipeline_timing",
            "seed": st.session_state.seed,
            "n_records": st.session_state.n_records,
            "noise_level": st.session_state.noise_level,
            "total_records_processed": total_records,
            "pipeline_seconds": round(pipeline_time, 3),
            "throughput_records_per_sec": round(throughput, 1)
        }
        log_records.append(timing_entry)

        RunStore.save_run(
            run_id=run_id,
            metadata=metadata,
            dataset_manifest=dataset_manifest,
            predictions=predictions,
            metrics=metrics,
            log_records=log_records
        )
        st.session_state.reconciled = True
        st.session_state.exec_time = round(pipeline_time, 3)
        st.session_state.throughput = round(throughput, 1)
        st.session_state.total_records = total_records
        st.toast(f"Reconciliation completed in {pipeline_time:.1f}s (Calls: {pipeline.gemini_calls}, Cached: {pipeline.cached_ai_decisions})", icon="⚡")
        return RunStore.load_run(run_id)


def load_demo_preset_handler():
    """Preset data parameters loader callback."""
    st.session_state.n_records = 80
    st.session_state.seed = 42
    st.session_state.noise_level = 0.15
    st.session_state.multi_currency = False
    execute_reconciliation(force_new=True)


# Ensure dataset exists on first boot
data_missing = not (os.path.exists(INVOICES_PATH) and os.path.exists(LEDGER_PATH) and os.path.exists(BANK_PATH) and os.path.exists(TRUTH_PATH))
active_run = RunStore.load_current_run()
if not active_run or data_missing:
    active_run = execute_reconciliation(force_new=False)

if active_run:
    meta = active_run.get("metadata", {})
    expected_records = meta.get("record_count", 0)
    curr_records = 0
    if os.path.exists(LEDGER_PATH) and os.path.exists(BANK_PATH):
        try:
            curr_records = len(pd.read_csv(LEDGER_PATH)) + len(pd.read_csv(BANK_PATH))
        except Exception:
            pass
    if expected_records > 0 and curr_records != expected_records:
        generate_reconciliation_data(
            n_records=expected_records // 2,
            seed=meta.get("seed", 42),
            anomaly_rate=meta.get("anomaly_rate", 0.15),
            output_dir=DATA_DIR,
            multi_currency=meta.get("multi_currency", False)
        )
    st.session_state.reconciled = True
    st.session_state.exec_time = meta.get("exec_time", 0.0)
    st.session_state.throughput = meta.get("throughput", 0.0)
    st.session_state.total_records = meta.get("record_count", 0)


# =============================================================================
# SIDEBAR NAVIGATION
# =============================================================================
st.sidebar.markdown("""
    <div style="padding: 0.2rem 0; margin-bottom: 0.8rem;">
        <h2 style="font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 1.55rem; margin: 0; line-height: 1.2; letter-spacing: -0.5px;">
            <span style="color: #10b981;">Contra</span><span style="color: #ffffff;">Base</span>
        </h2>
        <div style="font-size: 11px; color: #6b7280; margin-top: 4px; font-weight: 500;">
            Institutional Finance Control Console
        </div>
    </div>
""", unsafe_allow_html=True)

# Navigation Options Map
PAGE_OPTIONS = [
    "🏠 Overview",
    "👤 Review Queue",
    "🚨 Exceptions",
    "🔄 Reconciliation",
    "🔍 Audit Trail",
    "📊 Analytics",
    "🛡️ Safety Verification",
    "⚙ Settings"
]

# Ensure valid page in state
if st.session_state.current_page not in PAGE_OPTIONS:
    st.session_state.current_page = "🏠 Overview"

# Navigation Categories formatted in sidebar
st.sidebar.markdown('<div class="nav-category">PRIMARY WORKFLOW</div>', unsafe_allow_html=True)
primary_pages = ["🏠 Overview", "👤 Review Queue", "🚨 Exceptions"]
for p in primary_pages:
    is_active = (st.session_state.current_page == p)
    btn_type = "primary" if is_active else "secondary"
    if st.sidebar.button(p, key=f"nav_{p}", use_container_width=True, type=btn_type):
        st.session_state.current_page = p
        st.rerun()

st.sidebar.markdown('<div class="nav-category">RECONCILIATION & GOVERNANCE</div>', unsafe_allow_html=True)
gov_pages = ["🔄 Reconciliation", "🔍 Audit Trail", "📊 Analytics", "🛡️ Safety Verification"]
for p in gov_pages:
    is_active = (st.session_state.current_page == p)
    btn_type = "primary" if is_active else "secondary"
    if st.sidebar.button(p, key=f"nav_{p}", use_container_width=True, type=btn_type):
        st.session_state.current_page = p
        st.rerun()

st.sidebar.markdown('<div class="nav-category">CONFIGURATION</div>', unsafe_allow_html=True)
config_pages = ["⚙ Settings"]
for p in config_pages:
    is_active = (st.session_state.current_page == p)
    btn_type = "primary" if is_active else "secondary"
    if st.sidebar.button(p, key=f"nav_{p}", use_container_width=True, type=btn_type):
        st.session_state.current_page = p
        st.rerun()

# Gemini connection status at bottom of sidebar (Required by Task)
gemini_key = resolve_gemini_key()
gemini_key_exists = bool(gemini_key)
st.sidebar.markdown("---")
if gemini_key_exists:
    st.sidebar.markdown("""
    <div style="font-weight: bold; font-size: 13px; color: #4caf50; padding-left: 0.5rem; margin-bottom: 6px;">
        ● Gemini Connected
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.markdown("""
    <div style="font-weight: bold; font-size: 13px; color: #f44336; padding-left: 0.5rem; margin-bottom: 6px;">
        ● Gemini Not Configured
    </div>
    """, unsafe_allow_html=True)

st.sidebar.markdown("""
<div style="padding: 10px 12px; background: rgba(16, 185, 129, 0.06); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 6px; margin-top: 8px; font-size: 11px; color: #9ca3af; line-height: 1.4;">
    <strong style="color: #10b981; font-size: 10.5px; letter-spacing: 0.5px;">GOVERNANCE PRINCIPLE</strong><br>
    <span style="color: #d1d5db; font-weight: 500;">AI proposes. Deterministic controls authorize.</span>
</div>
""", unsafe_allow_html=True)




# Sync URL query parameters with active page slug (Defect 1)
target_slug = SLUG_PAGE_MAP.get(st.session_state.current_page, "overview")
if st.query_params.get("page") != target_slug:
    st.query_params["page"] = target_slug

page_changed = (st.session_state.current_page != st.session_state.get("previous_page"))

context = load_reconciliation_context(
    materiality_threshold_inr=st.session_state.materiality_threshold_inr
)

if st.session_state.current_page == "🏠 Overview":
    render_overview_view(context, on_load_demo=load_demo_preset_handler)
elif st.session_state.current_page == "🔄 Reconciliation":
    render_reconciliation_view(
        context,
        on_run_reconciliation=lambda: execute_reconciliation(force_new=True),
        on_load_demo=load_demo_preset_handler
    )
elif st.session_state.current_page == "🚨 Exceptions":
    render_exceptions_view(context)
elif st.session_state.current_page == "👤 Review Queue":
    render_review_queue_view(context)
elif st.session_state.current_page == "📊 Analytics":
    render_analytics_view(context)
elif st.session_state.current_page == "🔍 Audit Trail":
    render_audit_trail_view(context)
elif st.session_state.current_page == "🛡️ Safety Verification":
    render_safety_verification_view(context)
elif st.session_state.current_page == "⚙ Settings":
    render_settings_view(context, on_run_reconciliation=lambda: execute_reconciliation(force_new=True))

if page_changed:
    trigger_scroll_to_top()
    st.session_state.previous_page = st.session_state.current_page
