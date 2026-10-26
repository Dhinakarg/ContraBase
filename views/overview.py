import textwrap
import streamlit as st
import pandas as pd
from ui_common import render_page_header, format_inr, format_inr_compact, render_empty_state


def make_text_bar(count: int, total: int, fill_char: str = "█", empty_char: str = "░", width: int = 20) -> str:
    """Generates a text-based progress bar representing ratio of counts."""
    if total <= 0:
        return empty_char * width
    filled = int(round((count / total) * width))
    filled = max(0, min(width, filled))
    return (fill_char * filled) + (empty_char * (width - filled))


def render_overview_view(context: dict, on_load_demo):
    """
    Renders the Executive Month-End Close Controller Cockpit.
    Primary UX Principle: Focus directly on close status and actionable controller decisions.
    """
    active_run = context.get("active_run")
    predictions = context.get("predictions", [])
    status_counts = context.get("status_counts", {"auto_accepted": 0, "needs_review": 0, "exception": 0})
    reconciled_dollars = context.get("reconciled_dollars", 0.0)
    unexplained_variance = context.get("unexplained_variance", 0.0)
    needs_review_dollars = context.get("needs_review_dollars", 0.0)
    high_materiality_dollars = context.get("high_materiality_dollars", 0.0)
    match_rate = context.get("match_rate", 0.0)
    metrics = context.get("metrics", {})

    # Check empty state (if no run is processed or loaded)
    if not active_run or not st.session_state.get("reconciled", False):
        render_page_header(
            title="Month-End Close",
            subtitle="ContraBase Operations Console",
            badge="CONTRABASE • 🏠 OVERVIEW"
        )
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        render_empty_state("No active reconciliation run available. Execute a reconciliation to view executive close status.", icon="💼")
        
        st.markdown("<div style='text-align: center; margin-top: 1.5rem;'>", unsafe_allow_html=True)
        c_empty1, c_empty2 = st.columns(2)
        with c_empty1:
            if st.button("🎭 Load Demo Dataset", type="primary", use_container_width=True):
                on_load_demo()
                st.rerun()
        with c_empty2:
            if st.button("⚙ Open Settings", use_container_width=True):
                st.session_state.current_page = "⚙ Settings"
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    meta = active_run.get("metadata", {})
    run_id = meta.get('run_id', 'N/A')
    mat_threshold_val = context.get("materiality_threshold_inr") or st.session_state.get("materiality_threshold_inr", 400000.0)

    # -------------------------------------------------------------------------
    # HEADER & CONTEXT INFORMATION
    # -------------------------------------------------------------------------
    render_page_header(
        title="Month-End Close",
        subtitle=f"Month-end close health and actions (Run: {run_id})",
        badge="PRIMARY WORKFLOW • 🏠 OVERVIEW"
    )

    # Executive Run Audit Metadata Bar
    st.markdown(f"""
    <div style="background: rgba(17, 24, 39, 0.6); border: 1px solid #1f2937; padding: 8px 14px; border-radius: 6px; margin: 8px 0 1.2rem 0; font-size: 12px; color: #9ca3af; display: flex; flex-wrap: wrap; gap: 16px; align-items: center;">
        <span>🆔 <strong>RUN ID:</strong> <code style="color: #60a5fa;">{run_id}</code></span>
        <span>🌱 <strong>SEED:</strong> <code style="color: #f3f4f6;">{meta.get('seed', 42)}</code></span>
        <span>📊 <strong>POPULATION:</strong> <code style="color: #f3f4f6;">{meta.get('record_count', 160)} records</code></span>
        <span>⚡ <strong>ANOMALY RATE:</strong> <code style="color: #f3f4f6;">{int(meta.get('anomaly_rate', 0.15)*100)}%</code></span>
        <span>🛡️ <strong>MATERIALITY THRESHOLD:</strong> <code style="color: #10b981;">{format_inr(mat_threshold_val)}</code></span>
        <span>🕒 <strong>GENERATED:</strong> <code style="color: #d1d5db;">{str(meta.get('created_at', ''))[:19].replace('T', ' ')}</code></span>
    </div>
    """, unsafe_allow_html=True)

    # Calculate record-level statistics
    ledger_df = context.get("ledger_df", pd.DataFrame())
    bank_df = context.get("bank_df", pd.DataFrame())
    total_records = len(ledger_df) + len(bank_df)

    auto_accepted_records = status_counts.get("auto_accepted", 0)
    human_review_records = status_counts.get("needs_review", 0)
    exceptions_records = status_counts.get("exception", 0)

    automation_rate = (auto_accepted_records / total_records) * 100 if total_records else 0.0

    from close_readiness import CloseReadinessEvaluator
    readiness = CloseReadinessEvaluator.evaluate_close_readiness(context, st.session_state)

    # -------------------------------------------------------------------------
    # 1. CLOSE STATUS & OPERATIONAL DECISION
    # -------------------------------------------------------------------------
    st.markdown("### CLOSE READINESS")
    
    # Calculate blocking conditions and safe facts
    high_mat_items_cnt = sum(1 for p in predictions if float(p.get("amount", 0.0)) >= mat_threshold_val and p.get("status") != "auto_accepted")
    
    blocking_items = []
    if exceptions_records > 0:
        blocking_items.append(f"• {exceptions_records} exception records pending resolution")
    if human_review_records > 0:
        blocking_items.append(f"• {human_review_records} items requiring controller review")
    if high_mat_items_cnt > 0:
        blocking_items.append(f"• {high_mat_items_cnt} high-materiality items pending")
    if not blocking_items:
        blocking_items.append("• None (all blocking conditions cleared)")
    blocking_html = "<br>".join(blocking_items)
    
    readiness_html = textwrap.dedent(f"""
        <div style="background: {readiness['bg_color']}; border: 1px solid {readiness['border_color']}; border-left: 6px solid {readiness['color']}; padding: 20px 24px; border-radius: 8px; margin-bottom: 1.2rem;">
            <div style="font-size: 0.75rem; font-weight: 700; letter-spacing: 1.5px; color: #9ca3af; text-transform: uppercase; margin-bottom: 4px;">OPERATIONAL CLOSE STATUS</div>
            <div style="font-family: 'Outfit', sans-serif; font-size: 1.65rem; font-weight: 800; color: {readiness['color']}; letter-spacing: -0.5px; line-height: 1.2;">
                {readiness['symbol']} {readiness['state']}
            </div>
            <div style="font-size: 0.95rem; color: #d1d5db; margin-top: 6px; margin-bottom: 14px;">
                <strong>Decision Summary:</strong> {readiness['reason']}
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; background: rgba(0,0,0,0.25); padding: 14px 18px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);">
                <div>
                    <div style="font-size: 11px; font-weight: 700; color: #ef4444; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px;">BLOCKING CONDITIONS</div>
                    <div style="font-size: 12.5px; color: #e5e7eb; line-height: 1.6;">
                        {blocking_html}
                    </div>
                </div>
                <div>
                    <div style="font-size: 11px; font-weight: 700; color: #10b981; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px;">SAFE TO CLOSE</div>
                    <div style="font-size: 12.5px; color: #e5e7eb; line-height: 1.6;">
                        • {auto_accepted_records} records auto-resolved ({automation_rate:.1f}% rate)<br>
                        • Pass-1 exact 1:1 deterministic matches cleared<br>
                        • Gate-B double-entry journal validation active<br>
                    </div>
                </div>
                <div>
                    <div style="font-size: 11px; font-weight: 700; color: #60a5fa; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px;">REQUIRED ACTIONS</div>
                    <div style="font-size: 12.5px; color: #e5e7eb; line-height: 1.6;">
                        1. Review high-priority items in Review Queue<br>
                        2. Validate corrective journal entry proposals<br>
                        3. Re-evaluate Close Readiness status<br>
                    </div>
                </div>
            </div>
        </div>
    """).strip()
    st.markdown(readiness_html, unsafe_allow_html=True)

    with st.expander("🔍 Show Decision Basis & Operational Fact Matrix", expanded=False):
        st.markdown(f"""
        • **Run Identifier:** `{run_id}`<br>
        • **Total Population:** `{total_records}` transactions evaluated<br>
        • **Auto-Accepted:** `{auto_accepted_records}` records cleared via Gate-A policy rules<br>
        • **Pending Controller Review:** `{human_review_records}` records ({format_inr(needs_review_dollars)} exposure)<br>
        • **Unresolved Exceptions:** `{exceptions_records}` records ({format_inr(unexplained_variance)} variance)<br>
        • **Active Materiality Threshold:** `{format_inr(mat_threshold_val)}` (derived from active run configuration metadata)<br>
        • **Gate-B Auto-Post Variance Cap:** `₹4,000.00`
        """, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 2. ACTION REQUIRED (NEXT ACTION)
    # -------------------------------------------------------------------------
    st.markdown("#### NEXT ACTION")
    if st.button(readiness["next_action_label"], type="primary", use_container_width=True, key="cta_readiness_main"):
        st.session_state.current_page = readiness["target_page"]
        st.rerun()

    st.markdown('<div class="ledger-divider"></div>', unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 3. KEY FINANCIAL EXPOSURE
    # -------------------------------------------------------------------------
    st.markdown("### KEY FINANCIAL EXPOSURE")
    fe1, fe2, fe3 = st.columns(3)
    with fe1:
        st.metric("Cleared Volume Exposure", format_inr_compact(reconciled_dollars), help="Total value of cleared exact matches")
    with fe2:
        st.metric("Pending Review Exposure", format_inr_compact(needs_review_dollars), help="Total value of transactions requiring controller sign-off")
    with fe3:
        st.metric("High-Materiality Exposure", format_inr_compact(high_materiality_dollars), help=f"Total value of transactions ≥ {format_inr(mat_threshold_val)}")

    st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 4. RECONCILIATION HEALTH
    # -------------------------------------------------------------------------
    st.markdown("### RECONCILIATION HEALTH")
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.metric("Records Processed", total_records, help="Total internal ledger + bank statement records")
    with m_col2:
        st.metric("Auto-Resolved", auto_accepted_records, help="Clean matches cleared automatically")
    with m_col3:
        st.metric("Human Review", human_review_records, help="Items pending human controller sign-off")
    with m_col4:
        st.metric("Exceptions", exceptions_records, help="Unresolved orphan exception records")

    st.markdown('<div class="ledger-divider"></div>', unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 5. RISK / EXCEPTION SUMMARY
    # -------------------------------------------------------------------------
    st.markdown("### RISK / EXCEPTION SUMMARY")
    
    reason_counts = {}
    for p in predictions:
        st_val = p.get("status")
        if st_val in ["needs_review", "exception"]:
            rcode = p.get("reason_code") or p.get("reason") or ""
            policy_reason = p.get("policy_reason", "").lower()
            amt = float(p.get("amount", 0.0))
            
            if amt >= mat_threshold_val or "materiality" in policy_reason:
                reason_counts["High Materiality Policy Hold"] = reason_counts.get("High Materiality Policy Hold", 0) + 1
            elif rcode == "amount_variance" or "amount variance" in policy_reason:
                reason_counts["Material Amount Variance"] = reason_counts.get("Material Amount Variance", 0) + 1
            elif rcode == "date_shift" or "date" in policy_reason:
                reason_counts["Clearing Date Shift"] = reason_counts.get("Clearing Date Shift", 0) + 1
            elif rcode == "split_payment" or "split" in policy_reason:
                reason_counts["Split Payment Risk"] = reason_counts.get("Split Payment Risk", 0) + 1
            elif rcode == "no_counterpart_found" or "missing" in policy_reason:
                reason_counts["Unmatched Record / Missing Match"] = reason_counts.get("Unmatched Record / Missing Match", 0) + 1
            elif rcode == "ambiguous" or "ambiguity" in policy_reason:
                reason_counts["Candidate Ambiguity / FX Ambiguity"] = reason_counts.get("Candidate Ambiguity / FX Ambiguity", 0) + 1
            elif "confidence" in policy_reason:
                reason_counts["Low AI Confidence"] = reason_counts.get("Low AI Confidence", 0) + 1
            else:
                label = rcode.replace("_", " ").title() if rcode else "Policy Verification"
                reason_counts[label] = reason_counts.get(label, 0) + 1

    if not reason_counts:
        st.info("✓ Zero items blocked. 100% of transaction volume cleared policy safety checks.")
    else:
        st.markdown("<div style='background: #111827; border: 1px solid #1f2937; padding: 16px 20px; border-radius: 8px; margin-bottom: 1.2rem;'>", unsafe_allow_html=True)
        r_cols = st.columns(min(len(reason_counts), 3))
        col_idx = 0
        for reason_title, count_val in reason_counts.items():
            target_col = r_cols[col_idx % min(len(reason_counts), 3)]
            with target_col:
                st.markdown(f"""
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 12.5px; color: #9ca3af; font-weight: 500;">{reason_title}</div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 1.2rem; font-weight: 700; color: #f59e0b;">{count_val} records</div>
                </div>
                """, unsafe_allow_html=True)
            col_idx += 1
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="ledger-divider"></div>', unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 6. DETAILED ANALYTICS
    # -------------------------------------------------------------------------
    st.markdown("### DETAILED ANALYTICS")
    st.caption("Empirical pipeline performance measured against benchmark ground truth.")
    
    an1, an2, an3, an4 = st.columns(4)
    with an1:
        st.metric("Overall F1 Score", f"{metrics.get('f1_score', 0.0):.4f}" if metrics.get('f1_score') is not None else "N/A")
    with an2:
        st.metric("Precision", f"{metrics.get('precision', 0.0):.4f}" if metrics.get('precision') is not None else "N/A")
    with an3:
        st.metric("Recall", f"{metrics.get('recall', 0.0):.4f}" if metrics.get('recall') is not None else "N/A")
    with an4:
        tp_val = meta.get("throughput", 0.0)
        st.metric("Pipeline Throughput", f"{tp_val:.1f} recs/sec" if tp_val else "N/A")
