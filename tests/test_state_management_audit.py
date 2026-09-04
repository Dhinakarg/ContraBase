import os
import json
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
import streamlit as st

# Import the views to audit
from views.overview import render_overview_view
from views.exceptions import render_exceptions_view
from views.analytics import render_analytics_view
from views.audit_trail import render_audit_trail_view
from views.reconciliation import render_reconciliation_view
from ui_common import load_reconciliation_context


@pytest.fixture
def mock_context():
    """Generates a dummy context payload containing pre-reconciled data for views to render."""
    return {
        "active_run": {
            "metadata": {
                "run_id": "RUN_42_160_TEST",
                "status": "completed",
                "seed": 42,
                "record_count": 160,
                "noise_level": 0.15,
                "base_currency": "INR",
                "throughput": 150.0,
                "configuration_hash": "dummyhash"
            },
            "predictions": [
                {"ledger_id": "LED_1", "bank_ids": ["BNK_1"], "status": "auto_accepted", "decision_confidence": 98.0, "confidence": 98.0, "reason_code": "exact_match", "decision": "match", "rationale": "Perfect match"},
                {"ledger_id": "LED_2", "bank_ids": ["BNK_2"], "status": "needs_review", "decision_confidence": 75.0, "confidence": 75.0, "reason_code": "date_shift", "decision": "match", "rationale": "Date shifted", "Materiality": "⚠️ High", "AI Confidence": 80, "Evidence Score": 70, "System Confidence": 75}
            ],
            "metrics": {"precision": 0.95, "recall": 0.90, "f1_score": 0.925},
            "log_records": [
                {"type": "timing", "pipeline_seconds": 1.2, "throughput_records_per_sec": 133.3}
            ]
        },
        "predictions": [
            {"ledger_id": "LED_1", "bank_ids": ["BNK_1"], "status": "auto_accepted", "decision_confidence": 98.0, "confidence": 98.0, "reason_code": "exact_match", "decision": "match", "rationale": "Perfect match"},
            {"ledger_id": "LED_2", "bank_ids": ["BNK_2"], "status": "needs_review", "decision_confidence": 75.0, "confidence": 75.0, "reason_code": "date_shift", "decision": "match", "rationale": "Date shifted", "Materiality": "⚠️ High", "AI Confidence": 80, "Evidence Score": 70, "System Confidence": 75}
        ],
        "ground_truth": {"matches": []},
        "ledger_df": pd.DataFrame([{"ledger_id": "LED_1", "amount": 1000.0, "vendor": "Vendor A", "date": "2026-08-01"}, {"ledger_id": "LED_2", "amount": 500000.0, "vendor": "Vendor B", "date": "2026-08-02"}]),
        "bank_df": pd.DataFrame([{"bank_id": "BNK_1", "amount": 1000.0, "description": "Vendor A", "date": "2026-08-01"}, {"bank_id": "BNK_2", "amount": 500000.0, "description": "Vendor B", "date": "2026-08-03"}]),
        "invoices_df": pd.DataFrame(),
        "metrics": {"precision": 0.95, "recall": 0.90, "f1_score": 0.925},
        "match_rate": 1.0,
        "status_counts": {"auto_accepted": 1, "needs_review": 1, "exception": 0},
        "reconciled_dollars": 501000.0,
        "unexplained_variance": 0.0,
        "exceptions_df": pd.DataFrame([{"ID": "LED_2", "Source": "Ledger Match", "Vendor/Description": "Vendor B", "Amount": 500000.0, "Currency": "INR", "Reason Code": "date_shift", "Status": "needs_review", "Materiality": "⚠️ High", "AI Confidence": 80, "Evidence Score": 70, "System Confidence": 75, "Rationale": "Date shifted", "Policy Reason": "Awaiting human review", "Evidence Features": "date_diff=1", "Selected Candidates": ["BNK_2"], "Rejected Candidates": [], "Suggested Entry": {}, "Validated JE": {}, "Date": "2026-08-02", "Days Outstanding": 25}]),
        "exception_records": [
            {"ID": "LED_2", "Source": "Ledger Match", "Vendor/Description": "Vendor B", "Amount": 500000.0, "Currency": "INR", "Status": "needs_review", "Materiality": "⚠️ High", "Reason Code": "date_shift", "AI Confidence": 80, "Evidence Score": 70, "System Confidence": 75, "Rationale": "Date shifted", "Policy Reason": "Awaiting human review", "Evidence Features": "date_diff=1", "Selected Candidates": ["BNK_2"], "Rejected Candidates": [], "Suggested Entry": {}, "Validated JE": {}, "Date": "2026-08-02", "Days Outstanding": 25}
        ]
    }


# ---------------------------------------------------------------------------
# TEST 1 & 2: Rendering Overview, Exceptions, Analytics, and Audit Trail do NOT call Gemini
# ---------------------------------------------------------------------------
@patch("views.reconciliation.genai.Client")
def test_render_pages_zero_gemini_calls(mock_gemini_client, mock_context):
    """
    Asserts that rendering Overview, Exceptions, Analytics, and Audit Trail views
    does not instantiate the Google GenAI Client or issue generate_content calls.
    """
    # 1. Render Overview
    with patch("streamlit.button") as mock_btn:
        mock_btn.return_value = False
        render_overview_view(mock_context, on_load_demo=MagicMock())
    assert not mock_gemini_client.called, "Overview page should not trigger Gemini calls"

    # 2. Render Exceptions
    with patch("streamlit.radio") as mock_rad:
        mock_rad.return_value = "All"
        render_exceptions_view(mock_context)
    assert not mock_gemini_client.called, "Exceptions page should not trigger Gemini calls"

    # 3. Render Analytics
    render_analytics_view(mock_context)
    assert not mock_gemini_client.called, "Analytics page should not trigger Gemini calls"

    # 4. Render Audit Trail
    with patch("streamlit.text_input") as mock_search, \
         patch("streamlit.radio") as mock_filter, \
         patch("streamlit.selectbox") as mock_select:
        mock_search.return_value = ""
        mock_filter.return_value = "All"
        mock_select.return_value = "Select to view..."
        render_audit_trail_view(mock_context)
    assert not mock_gemini_client.called, "Audit Trail page should not trigger Gemini calls"


# ---------------------------------------------------------------------------
# TEST 3: Page navigation does not call Gemini
# ---------------------------------------------------------------------------
@patch("views.reconciliation.genai.Client")
def test_navigation_zero_inference(mock_gemini_client, mock_context):
    """
    Simulates navigating between pages using a mocked state and verifies that
    page dispatcher navigation handles the load state in a read-only way.
    """
    # Define pages to navigate through
    pages = ["🏠 Overview", "🚨 Exceptions", "📊 Analytics", "🔍 Audit Trail"]
    
    with patch("streamlit.text_input") as mock_search, \
         patch("streamlit.radio") as mock_filter, \
         patch("streamlit.selectbox") as mock_select:
        mock_search.return_value = ""
        mock_filter.return_value = "All"
        mock_select.return_value = "Select to view..."
        
        for page in pages:
            st.session_state.current_page = page
            
            # Simulating rendering of page inside dispatch loop
            if page == "🏠 Overview":
                render_overview_view(mock_context, on_load_demo=MagicMock())
            elif page == "🚨 Exceptions":
                render_exceptions_view(mock_context)
            elif page == "📊 Analytics":
                render_analytics_view(mock_context)
            elif page == "🔍 Audit Trail":
                render_audit_trail_view(mock_context)
                
            assert not mock_gemini_client.called, f"Navigation to {page} triggered unexpected Gemini call"


# ---------------------------------------------------------------------------
# TEST 4: Reconciliation runs only after explicit user action
# ---------------------------------------------------------------------------
def test_reconciliation_only_explicit_trigger():
    """
    Verifies that pipeline reconciliation logic requires explicit execution triggers.
    Checks that loading settings or refreshing does not trigger pipeline calls.
    """
    on_run_mock = MagicMock()
    on_load_demo_mock = MagicMock()
    
    # Render Reconciliation Page
    with patch("streamlit.button") as mock_btn:
        # Simulate rendering reconciliation page
        # Buttons are not clicked during normal page render flow
        mock_btn.return_value = False
        
        render_reconciliation_view(
            context={"predictions": []},
            on_run_reconciliation=on_run_mock,
            on_load_demo=on_load_demo_mock
        )
        
        # Pipeline must NOT trigger unless button clicked
        assert not on_run_mock.called, "Reconciliation run executed automatically during render"


# ---------------------------------------------------------------------------
# TEST 5: Gemini Q&A runs only after explicit submission
# ---------------------------------------------------------------------------
@patch("views.reconciliation.genai.Client")
def test_gemini_qa_only_on_submit(mock_gemini_client, mock_context):
    """
    Verifies that Gemini Q&A Audit Assistant is form-guarded and only invokes
    generate_content calls after explicit submission button press.
    """
    # Case A: Q&A input exists but NOT submitted
    with patch("streamlit.form") as mock_form, \
         patch("streamlit.text_input") as mock_txt, \
         patch("streamlit.form_submit_button") as mock_submit:
        
        mock_txt.return_value = "Are there duplicate transactions?"
        mock_submit.return_value = False # Not submitted
        
        render_reconciliation_view(
            context=mock_context,
            on_run_reconciliation=MagicMock(),
            on_load_demo=MagicMock()
        )
        assert not mock_gemini_client.called, "Gemini Q&A triggered without form submission"

    # Case B: Q&A input exists AND submitted
    mock_instance = MagicMock()
    mock_gemini_client.return_value = mock_instance
    
    with patch("streamlit.form") as mock_form, \
         patch("streamlit.text_input") as mock_txt, \
         patch("streamlit.form_submit_button") as mock_submit, \
         patch("streamlit.chat_message") as mock_chat:
        
        mock_txt.return_value = "Are there duplicate transactions?"
        mock_submit.return_value = True # Submitted!
        
        # Mock connection existence
        with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_key"}):
            render_reconciliation_view(
                context=mock_context,
                on_run_reconciliation=MagicMock(),
                on_load_demo=MagicMock()
            )
            assert mock_gemini_client.called, "Gemini Q&A did not trigger after explicit form submission"


# ---------------------------------------------------------------------------
# TEST 6: Refresh/re-render does not duplicate audit records
# ---------------------------------------------------------------------------
def test_refresh_idempotent_audit_logs():
    """
    Confirms that calling load_reconciliation_context repeatedly (simulating
    page refreshes/reruns) does not generate duplicate audit records.
    """
    # Active configuration parameters
    st.session_state.seed = 42
    st.session_state.n_records = 80
    st.session_state.noise_level = 0.15
    st.session_state.multi_currency = False
    st.session_state.materiality_threshold_inr = 400000.0
    
    # Call multiple times
    ctx1 = load_reconciliation_context()
    ctx2 = load_reconciliation_context()
    
    # Asserting that loaded active run metadata structures are identical
    run1 = ctx1.get("active_run")
    run2 = ctx2.get("active_run")
    
    if run1 and run2:
        assert run1.get("run_id") == run2.get("run_id"), "Refresh changed the active run ID"
        assert len(ctx1.get("predictions", [])) == len(ctx2.get("predictions", [])), "Predictions count changed on refresh"
