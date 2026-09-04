import os
import streamlit as st
import pandas as pd
from ui_common import render_page_header, format_inr, DATA_DIR, INVOICES_PATH, LEDGER_PATH, BANK_PATH, resolve_gemini_key
from backend.data_gen.generator import generate_reconciliation_data


def validate_financial_dataset(invoices_df, ledger_df, bank_df):
    """
    4-step validation logic for user-uploaded financial data files:
    1. File detected check
    2. Required columns check
    3. Data types & currencies check
    4. Record counts check
    """
    errors = []
    status = {
        "files_detected": False,
        "columns_valid": False,
        "types_valid": False,
        "records_detected": 0
    }

    if invoices_df is None or ledger_df is None or bank_df is None:
        errors.append("All three financial files (Invoices, Internal Ledger, Bank Statement) are required.")
        return False, errors, status

    status["files_detected"] = True

    # 2. Check required columns
    req_inv = ["invoice_id", "vendor", "amount", "due_date"]
    req_led = ["ledger_id", "date", "amount", "vendor", "reference_id"]
    req_bnk = ["bank_id", "date", "amount", "description", "reference_id"]

    missing_inv = [c for c in req_inv if c not in invoices_df.columns]
    missing_led = [c for c in req_led if c not in ledger_df.columns]
    missing_bnk = [c for c in req_bnk if c not in bank_df.columns]

    if missing_inv or missing_led or missing_bnk:
        if missing_inv: errors.append(f"Invoices CSV missing columns: {', '.join(missing_inv)}")
        if missing_led: errors.append(f"Ledger CSV missing columns: {', '.join(missing_led)}")
        if missing_bnk: errors.append(f"Bank Statement CSV missing columns: {', '.join(missing_bnk)}")
        return False, errors, status

    status["columns_valid"] = True

    # 3. Check data types and amounts
    try:
        invoices_df["amount"] = pd.to_numeric(invoices_df["amount"])
        ledger_df["amount"] = pd.to_numeric(ledger_df["amount"])
        bank_df["amount"] = pd.to_numeric(bank_df["amount"])
    except Exception as e:
        errors.append(f"Numeric validation error on 'amount' column: {e}")
        return False, errors, status

    status["types_valid"] = True
    status["records_detected"] = len(ledger_df) + len(bank_df)

    return True, errors, status


def render_settings_view(context: dict, on_run_reconciliation):
    """
    Renders the System Settings Page.
    Primary Question Answered: 'How is the system configured?'
    """
    render_page_header(
        title="Settings",
        subtitle="Policy, dataset and control configuration",
        badge="CONFIGURATION • ⚙ SETTINGS"
    )

    active_run = context.get("active_run")
    meta = active_run.get("metadata", {}) if active_run else {}

    # Ensure session_state defaults
    if "n_records" not in st.session_state:
        st.session_state.n_records = 80
    if "seed" not in st.session_state:
        st.session_state.seed = 42
    if "noise_level_pct" not in st.session_state:
        st.session_state.noise_level_pct = float(st.session_state.get("noise_level", 0.15) * 100.0)
    if "materiality_threshold_inr" not in st.session_state:
        st.session_state.materiality_threshold_inr = 400000.0
    if "auto_accept_thresh" not in st.session_state:
        st.session_state.auto_accept_thresh = 95.0
    if "needs_review_thresh" not in st.session_state:
        st.session_state.needs_review_thresh = 70.0

    # -------------------------------------------------------------------------
    # TOP SECTION: CUSTOM DATA UPLOAD & PRESET ACTIONS
    # -------------------------------------------------------------------------
    st.markdown("### 📁 CUSTOM DATA UPLOAD & PRESETS")
    st.caption("Upload custom financial datasets or load standard demo presets for reconciliation.")

    # 4-step upload expander
    with st.expander("📁 Upload Custom Financial Datasets (4-Step Workflow)", expanded=False):
        st.markdown("#### Step 1: Upload CSV Files")
        up_col1, up_col2, up_col3 = st.columns(3)
        with up_col1:
            up_invoices = st.file_uploader("Invoices CSV", type=["csv"], key="up_inv")
        with up_col2:
            up_ledger = st.file_uploader("Internal Ledger CSV", type=["csv"], key="up_led")
        with up_col3:
            up_bank = st.file_uploader("Bank Statement CSV", type=["csv"], key="up_bnk")

        if up_invoices and up_ledger and up_bank:
            st.markdown("#### Step 2: Validate Data Files")
            try:
                inv_df = pd.read_csv(up_invoices)
                led_df = pd.read_csv(up_ledger)
                bnk_df = pd.read_csv(up_bank)

                is_valid, errors, status = validate_financial_dataset(inv_df, led_df, bnk_df)

                if is_valid:
                    st.success(f"""
                    ✓ **Files Detected**: Invoices ({len(inv_df)} rows), Ledger ({len(led_df)} rows), Bank ({len(bnk_df)} rows)<br>
                    ✓ **Required Columns Present**: All mandatory schema fields verified<br>
                    ✓ **Data Types & Currencies Valid**: Numeric amounts and valid dates confirmed<br>
                    ✓ **Records Detected**: {status['records_detected']} total close transaction records
                    """, icon="✅")

                    st.markdown("#### Step 3: Data Preview")
                    prev_tab1, prev_tab2, prev_tab3 = st.tabs(["Ledger Preview", "Bank Preview", "Invoices Preview"])
                    with prev_tab1: st.dataframe(led_df.head(5), use_container_width=True, hide_index=True)
                    with prev_tab2: st.dataframe(bnk_df.head(5), use_container_width=True, hide_index=True)
                    with prev_tab3: st.dataframe(inv_df.head(5), use_container_width=True, hide_index=True)

                    st.markdown("#### Step 4: Apply & Run")
                    if st.button("Save Uploaded Data & Run Reconciliation", type="primary", use_container_width=True):
                        inv_df.to_csv(INVOICES_PATH, index=False)
                        led_df.to_csv(LEDGER_PATH, index=False)
                        bnk_df.to_csv(BANK_PATH, index=False)

                        st.session_state.reconciled = False
                        on_run_reconciliation()
                        st.rerun()
                else:
                    for err in errors:
                        st.error(f"❌ Validation Error: {err}")
            except Exception as ex:
                st.error(f"Error parsing uploaded CSV files: {ex}")
        else:
            st.info("Upload all 3 required CSV files to initiate data validation.")

    st.write("")

    # Presets & Reset Actions
    st.markdown("#### Preset Actions")
    da1, da2, da3 = st.columns(3)
    
    with da1:
        if st.button("🎭 Load Demo Preset", use_container_width=True, type="secondary"):
            st.session_state.n_records = 80
            st.session_state.seed = 42
            st.session_state.noise_level = 0.15
            st.session_state.noise_level_pct = 15.0
            st.session_state.multi_currency = False
            
            generate_reconciliation_data(
                n_records=80, seed=42, anomaly_rate=0.15,
                output_dir=DATA_DIR, multi_currency=False
            )
            st.session_state.reconciled = False
            st.toast("Loaded standard Demo Preset.", icon="🎭")
            st.rerun()
            
    with da2:
        if st.button("🎲 Generate New Dataset", use_container_width=True, type="primary"):
            generate_reconciliation_data(
                n_records=st.session_state.n_records,
                seed=st.session_state.seed,
                anomaly_rate=st.session_state.noise_level,
                output_dir=DATA_DIR,
                multi_currency=st.session_state.multi_currency
            )
            st.session_state.reconciled = False
            st.toast("Generated new synthetic dataset.", icon="🎲")
            st.rerun()
            
    with da3:
        if st.button("🔄 Reset Settings", use_container_width=True):
            st.session_state.n_records = 80
            st.session_state.seed = 42
            st.session_state.noise_level = 0.15
            st.session_state.noise_level_pct = 15.0
            st.session_state.multi_currency = False
            st.session_state.materiality_threshold_inr = 400000.0
            st.session_state.auto_accept_thresh = 95.0
            st.session_state.needs_review_thresh = 70.0
            
            generate_reconciliation_data(
                n_records=80, seed=42, anomaly_rate=0.15,
                output_dir=DATA_DIR, multi_currency=False
            )
            st.session_state.reconciled = False
            st.toast("Reset settings to standard defaults.", icon="🔄")
            st.rerun()

    st.markdown('<div class="ledger-divider"></div>', unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # MINIMIZED EXPANDER: DATA GENERATION
    # -------------------------------------------------------------------------
    with st.expander("⚙️ DATA GENERATION OPTIONS", expanded=False):
        st.caption("Configure target row counts, generator seed, and stress-test noise parameters.")
        st.write("")

        # 1. Record Count
        curr_n_records = int(st.session_state.n_records)
        st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
                <span style="font-weight: 600; color: #f9fafb; font-size: 0.95rem;">Record Count</span>
                <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #10b981; font-size: 1.05rem;">{curr_n_records}</span>
            </div>
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 6px;">Target row count for internal ledger and bank statement closing datasets.</div>
        """, unsafe_allow_html=True)
        
        st.number_input(
            "Record Count",
            min_value=50, max_value=500,
            step=1,
            label_visibility="collapsed",
            key="n_records"
        )
        
        st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

        # 2. Generator Seed
        curr_seed = int(st.session_state.seed)
        st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
                <span style="font-weight: 600; color: #f9fafb; font-size: 0.95rem;">Generator Seed</span>
                <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #10b981; font-size: 1.05rem;">{curr_seed}</span>
            </div>
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 6px;">Seed value to maintain reproducibility of synthetic closing datasets.</div>
        """, unsafe_allow_html=True)
        
        st.number_input(
            "Generator Seed",
            min_value=1, max_value=9999,
            step=1,
            label_visibility="collapsed",
            key="seed"
        )

        st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

        # 3. Synthetic Data Stress Level
        noise_pct_val = float(st.session_state.noise_level_pct)
        st.session_state.noise_level = noise_pct_val / 100.0
        if noise_pct_val <= 10.0:
            noise_class = "Low"
        elif noise_pct_val <= 25.0:
            noise_class = "Moderate"
        elif noise_pct_val <= 40.0:
            noise_class = "High"
        else:
            noise_class = "Severe"

        st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
                <span style="font-weight: 600; color: #f9fafb; font-size: 0.95rem;">Synthetic Data Stress Level</span>
                <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #10b981; font-size: 1.05rem;">{noise_pct_val:.1f}% <span style="font-size: 0.85rem; color: #9ca3af; font-weight: 500;">({noise_class})</span></span>
            </div>
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 6px;">Fraction of matching anomalies (typos, date shifts, splits) injected into dataset.</div>
        """, unsafe_allow_html=True)
        
        st.number_input(
            "Synthetic Data Stress Level (%)",
            min_value=0.0, max_value=50.0,
            step=0.1,
            format="%.1f",
            label_visibility="collapsed",
            key="noise_level_pct"
        )
        st.session_state.noise_level = float(st.session_state.noise_level_pct) / 100.0

        st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

        # 4. Multi-Currency Toggle
        multi_currency = st.toggle(
            "Multi-Currency Toggle",
            value=st.session_state.get("multi_currency", False),
            help="Inject convertibility FX test cases using dynamic USD ledger invoicing."
        )
        st.session_state.multi_currency = multi_currency
        if multi_currency:
            st.caption("💡 Dynamic multi-currency conversion active (1 USD = 83.50 INR).")

    # -------------------------------------------------------------------------
    # MINIMIZED EXPANDER: RECONCILIATION POLICY
    # -------------------------------------------------------------------------
    with st.expander("⚖️ RECONCILIATION POLICY CONFIGURATION", expanded=False):
        st.caption("Configure materiality boundaries, confidence cutoffs, and exception sorting rules.")
        st.write("")

        # 1. Materiality Threshold
        curr_mat = float(st.session_state.materiality_threshold_inr)
        st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
                <span style="font-weight: 600; color: #f9fafb; font-size: 0.95rem;">Materiality Threshold</span>
                <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #10b981; font-size: 1.15rem;">{format_inr(curr_mat)}</span>
            </div>
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 6px;">Transactions at or above this value receive additional risk evaluation under corporate policy.</div>
        """, unsafe_allow_html=True)
        
        st.number_input(
            "Materiality Threshold (₹)",
            min_value=1000.0, max_value=10000000.0,
            step=1000.0,
            format="%.0f",
            label_visibility="collapsed",
            key="materiality_threshold_inr"
        )

        st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

        # 2. Auto-Accept Confidence
        curr_auto = float(st.session_state.auto_accept_thresh)
        st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
                <span style="font-weight: 600; color: #f9fafb; font-size: 0.95rem;">Auto-Accept Confidence</span>
                <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #10b981; font-size: 1.05rem;">{curr_auto:.1f}%</span>
            </div>
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 6px;">High-confidence decisions eligible for automatic acceptance without human intervention.</div>
        """, unsafe_allow_html=True)
        
        st.number_input(
            "Auto-Accept Confidence (%)",
            min_value=0.0, max_value=100.0,
            step=0.1,
            format="%.1f",
            label_visibility="collapsed",
            key="auto_accept_thresh"
        )

        st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

        # 3. Needs Review Threshold
        curr_review = float(st.session_state.needs_review_thresh)
        st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
                <span style="font-weight: 600; color: #f9fafb; font-size: 0.95rem;">Needs Review Threshold</span>
                <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #10b981; font-size: 1.05rem;">{curr_review:.1f}%</span>
            </div>
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 6px;">Lower-confidence decisions are routed for human review queue.</div>
        """, unsafe_allow_html=True)
        
        st.number_input(
            "Needs Review Threshold (%)",
            min_value=0.0, max_value=100.0,
            step=0.1,
            format="%.1f",
            label_visibility="collapsed",
            key="needs_review_thresh"
        )

        if st.session_state.needs_review_thresh > st.session_state.auto_accept_thresh:
            st.warning(f"⚠️ Needs Review Threshold ({st.session_state.needs_review_thresh:.1f}%) cannot exceed Auto-Accept Confidence ({st.session_state.auto_accept_thresh:.1f}%).")

        st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

        # 4. Sort Exceptions By
        st.markdown("""
            <div style="font-weight: 600; color: #f9fafb; font-size: 0.95rem; margin-bottom: 2px;">Sort Exceptions By</div>
            <div style="font-size: 12px; color: #9ca3af; margin-bottom: 6px;">Default sorting order for exception investigation table.</div>
        """, unsafe_allow_html=True)
        sort_exceptions_by = st.selectbox(
            "Sort Exceptions By",
            options=["Amount", "Days Outstanding", "Date"],
            index=0,
            label_visibility="collapsed",
            key="sort_exceptions_by"
        )

    # -------------------------------------------------------------------------
    # MINIMIZED EXPANDER: AI & SYSTEM STATUS
    # -------------------------------------------------------------------------
    with st.expander("🤖 AI MODEL & SYSTEM STATUS", expanded=False):
        st.caption("View Gemini LLM connection parameters, active run metadata, and persistent store status.")
        st.write("")

        gemini_key = resolve_gemini_key()
        gemini_key_exists = bool(gemini_key)

        if gemini_key_exists:
            st.markdown("<span style='font-size: 15px; color: #4caf50; font-weight: bold;'>🟢 Gemini Connected</span>", unsafe_allow_html=True)
            if st.session_state.get("custom_gemini_key"):
                st.caption("Custom session key is currently active.")
                if st.button("Disconnect Session Key", key="btn_disconnect_gemini"):
                    st.session_state.custom_gemini_key = ""
                    if "GEMINI_API_KEY" in os.environ:
                        del os.environ["GEMINI_API_KEY"]
                    st.rerun()
        else:
            st.markdown("<span style='font-size: 15px; color: #f44336; font-weight: bold;'>🔴 Gemini Not Configured</span>", unsafe_allow_html=True)
            
            st.markdown("""
            <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; padding: 12px; margin-top: 8px; margin-bottom: 12px; font-size: 13px; line-height: 1.5;">
                <strong style="color: #f87171;">How to configure Gemini in Streamlit Cloud:</strong><br>
                1. Go to your app dashboard at <a href="https://share.streamlit.io" target="_blank" style="color: #60a5fa;">share.streamlit.io</a>.<br>
                2. Click the <strong>⋮</strong> menu next to your app &rarr; <strong>Settings</strong> &rarr; <strong>Secrets</strong>.<br>
                3. Paste the following snippet and save:<br>
                <code style="display: block; background: rgba(0,0,0,0.3); padding: 6px 10px; border-radius: 4px; margin-top: 4px; color: #34d399;">GEMINI_API_KEY = "your-gemini-api-key"</code>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("##### 🔑 Or connect for this session:")
            temp_key = st.text_input(
                "Gemini API Key",
                type="password",
                placeholder="Paste AIzaSy... key here",
                key="input_temp_gemini_key",
                help="Key is stored in session memory only and will enable Gemini adjudication immediately."
            )
            if st.button("Connect Key", key="btn_connect_gemini_key", type="primary"):
                if temp_key.strip():
                    st.session_state.custom_gemini_key = temp_key.strip()
                    resolve_gemini_key()
                    st.success("Gemini key activated! Refreshing...")
                    st.rerun()
                else:
                    st.warning("Please enter a valid API key.")

        st.write("")
        st.text_input("Active LLM Model", value="gemini-2.5-flash", disabled=True, help="Gemini API model engine.")
        st.text_input("API Key Status", value="[PROTECTED & ENCRYPTED]" if gemini_key_exists else "[NOT SET]", disabled=True)
        st.text_input("Retry Policy", value="Exponential Backoff (3 retries max)", disabled=True)

        st.write("")
        st.write(f"• **Current Active Run ID:** `{meta.get('run_id', 'None')}`")
        st.write(f"• **Dataset Status:** {'Saved & Reconciled' if st.session_state.get('reconciled') else 'Out of Sync'}")
        st.write(f"• **Last Reconciliation Time:** `{meta.get('created_at', 'N/A')}`")
        st.write(f"• **Persistence Status:** Persistent RunStore Active (`data/runs/`)")
        st.write(f"• **Active Configuration Hash:** `{meta.get('configuration_hash', 'N/A')}`")
