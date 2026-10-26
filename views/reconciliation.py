import os
import json
import pandas as pd
import streamlit as st
from google import genai
from ui_common import render_page_header, format_inr, format_inr_compact, resolve_gemini_key


def render_reconciliation_view(context: dict, on_run_reconciliation, on_load_demo):
    """
    Renders the Reconciliation Page.
    Primary Question Answered: 'What did the system reconcile?'
    """
    render_page_header(
        title="Reconciliation Engine",
        subtitle="Transaction-level matching evidence",
        badge="RECONCILIATION & GOVERNANCE • 🔄 RECONCILIATION"
    )

    predictions = context.get("predictions", [])
    ledger_df = context.get("ledger_df", pd.DataFrame())
    bank_df = context.get("bank_df", pd.DataFrame())
    invoices_df = context.get("invoices_df", pd.DataFrame())
    reconciled_dollars = context.get("reconciled_dollars", 0.0)
    unexplained_variance = context.get("unexplained_variance", 0.0)
    exceptions_df = context.get("exceptions_df", pd.DataFrame())
    match_rate = context.get("match_rate", 0.0)
    status_counts = context.get("status_counts", {"auto_accepted": 0, "needs_review": 0, "exception": 0})
    exception_records = context.get("exception_records", [])
    active_run = context.get("active_run", {})

    meta = active_run.get("metadata", {}) if (active_run and st.session_state.get("reconciled", False)) else {}
    is_reconciled = st.session_state.get("reconciled", False)

    # 1. Current Run Status card
    st.markdown("### 📊 Current Run")
    run_col1, run_col2 = st.columns([3, 1])
    with run_col1:
        if is_reconciled:
            status_html = '<span style="color: #66bb6a; font-weight: bold;">● Complete</span>'
            tput_text = f"Throughput: {meta.get('throughput', 0.0)} rec/sec"
        else:
            status_html = '<span style="color: #e57373; font-weight: bold;">● Out of Sync (Requires Run)</span>'
            tput_text = "Throughput: N/A"

        st.markdown(f"""
        <div style="background: rgba(255, 255, 255, 0.03); padding: 12px 18px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.08); line-height: 1.6;">
            • Run ID: <code>{meta.get('run_id', 'N/A')}</code><br>
            • Dataset: <strong>{st.session_state.get('n_records', 80) if not is_reconciled else meta.get('record_count', 0)} records</strong><br>
            • Seed: <code>{st.session_state.get('seed', 42)}</code> &nbsp;|&nbsp; Noise: <code>{int(st.session_state.get('noise_level', 0.15) * 100)}%</code> &nbsp;|&nbsp; Currency: <code>INR</code><br>
            • Status: {status_html} ({tput_text})
        </div>
        """, unsafe_allow_html=True)
    with run_col2:
        st.write("")
        if st.button("▶ Run Reconciliation", type="primary", use_container_width=True, help="Execute reconciliation"):
            on_run_reconciliation()
            st.rerun()
        if st.button("🎭 Load Demo Dataset", use_container_width=True, help="Reset to demo dataset parameters"):
            on_load_demo()
            st.rerun()

    if not is_reconciled:
        st.warning("⚠️ System configuration changed. Click 'Run Reconciliation' to execute the reconciliation pipeline and generate audit decisions.")

    st.markdown("---")

    # 2. Reconciliation Outcome (Mutually Exclusive Record Counts)
    st.markdown("### 🏆 Reconciliation Outcome (Record Counts)")
    st.caption("Mutually-exclusive transaction record status breakdown (Sum == Total Processed Records).")
    
    total_recs = len(ledger_df) + len(bank_df)
    auto_acc_recs = status_counts.get("auto_accepted", 0)
    review_recs = status_counts.get("needs_review", 0)
    exc_recs = status_counts.get("exception", 0)

    oc_col1, oc_col2, oc_col3, oc_col4 = st.columns(4)
    with oc_col1:
        st.metric("Total Processed", f"{total_recs}", help="Sum of internal ledger and bank statement records")
    with oc_col2:
        st.metric("Auto-Accepted", f"{auto_acc_recs}", help="Records cleared automatically by safety policy")
    with oc_col3:
        st.metric("Human Review", f"{review_recs}", help="Records routed to human verification queue")
    with oc_col4:
        st.metric("Exceptions", f"{exc_recs}", help="Unresolved orphan records")

    st.markdown("---")

    # 3. Match Method & Scenario Breakdown (Match Groups)
    st.markdown("### 📊 Match Method & Scenario Breakdown")
    st.caption("ℹ️ Note: Match method categories represent match generation scenarios and are listed separately from mutually-exclusive reconciliation outcome counts.")

    split_count = len([p for p in predictions if "split" in p.get("match_type", "").lower() or (p.get("bank_ids") and len(p["bank_ids"]) > 1)])
    pass1_count = len([p for p in predictions if p.get("match_type") == "exact_match" or not str(p.get("match_type", "")).startswith("ai_")])
    pass2_count = len([p for p in predictions if str(p.get("match_type", "")).startswith("ai_")])

    s_col1, s_col2, s_col3 = st.columns(3)
    with s_col1:
        st.metric("Deterministic Exact Matches", f"{pass1_count} groups", help="1:1 exact matches cleared in Pass 1")
    with s_col2:
        st.metric("AI-Assisted Adjudications", f"{pass2_count} groups", help="Fuzzy & candidate-bounded matches evaluated by Pass 2 AI")
    with s_col3:
        st.metric("Split Payments (Many-to-One)", f"{split_count} groups", help="Multi-bank transaction split matches")

    st.markdown("---")

    # 4. Reconciled Matches detail table
    st.markdown("### 📋 Reconciled Transactions Detail")
    
    if predictions:
        matches_records = []
        for m in predictions:
            invoice_id = m.get("invoice_id") or "N/A"
            ledger_id = m.get("ledger_id") or "N/A"
            bank_ids_str = ", ".join(m.get("bank_ids", [])) if m.get("bank_ids") else "N/A"
            match_type = m.get("match_type", "exact_match")
            status = m.get("status", "auto_accepted")
            confidence = m.get("decision_confidence", m.get("confidence", 100))
            ai_confidence_val = m.get("ai_confidence", 100)
            
            # Find rupee amount from ledger if available
            amt = 0.0
            if ledger_id != "N/A" and not ledger_df.empty:
                rows = ledger_df.loc[ledger_df["ledger_id"].astype(str) == str(ledger_id), "amount"].values
                if len(rows) > 0:
                    amt = float(rows[0])
            
            is_split = "split" in match_type.lower() or (m.get("bank_ids") and len(m["bank_ids"]) > 1)
            split_indicator = "🔀 Split (Many-to-One)" if is_split else "1:1 Match"
            
            matches_records.append({
                "Invoice ID": invoice_id,
                "Ledger ID": ledger_id,
                "Bank Statement IDs": bank_ids_str,
                "Amount": amt,
                "Match Scenario": match_type.replace("ai_", "").replace("_", " ").title(),
                "Routing Status": status.replace("_", " ").title(),
                "Reconciliation Type": split_indicator,
                "System Confidence": confidence,
                "AI Confidence": ai_confidence_val
            })
            
        matches_df = pd.DataFrame(matches_records)
        
        show_splits_only = st.checkbox("Show Split Payments Only", value=False, key="rec_splits_filter")
        if show_splits_only:
            matches_df = matches_df[matches_df["Reconciliation Type"] == "🔀 Split (Many-to-One)"]
            
        if not matches_df.empty:
            display_df = matches_df.copy()
            display_df["Amount"] = display_df["Amount"].apply(format_inr)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("No reconciled matches found matching the filters.")
    else:
        st.info("No matches reconciled yet.")

    st.markdown("---")

    # 5. Expandable Decision Details Selector (7-part structure)
    st.markdown("### 🔍 Decision Details Inspector")
    st.caption("Inspect the evidence-first 7-part routing structure for any reconciled transaction or exception.")

    # Combine prediction ledger IDs and exception record IDs for lookup
    choice_list = []
    if predictions:
        for p in predictions:
            lid = p.get("ledger_id")
            if lid:
                choice_list.append((f"Match: {lid}", "Match", str(lid)))
    if exception_records:
        for exc in exception_records:
            eid = exc.get("ID")
            if eid:
                choice_list.append((f"Exception: {eid}", "Exception", str(eid)))
                
    if choice_list:
        sel_label = st.selectbox(
            "Select Transaction / Exception Record to Trace",
            options=[c[0] for c in choice_list],
            key="rec_trace_selector"
        )
        
        sel_choice = next(c for c in choice_list if c[0] == sel_label)
        choice_type, target_id = sel_choice[1], sel_choice[2]
        
        # Build 7-part evidence cards dynamically
        if choice_type == "Match":
            pred_item = next((p for p in predictions if str(p.get("ledger_id")) == target_id or target_id in [str(b) for b in p.get("bank_ids", [])]), None)
            dec_item = next((d.get("decision", d) for d in context.get("decisions", []) if isinstance(d, dict) and (str(d.get("decision", d).get("ledger_id")) == target_id or str(d.get("decision", d).get("source_record_id")) == target_id)), None)
            
            if pred_item:
                with st.expander(f"🔍 DECISION TRACE — Target `{target_id}`", expanded=True):
                    st.markdown("#### 📌 1. SOURCE RECORD")
                    st.write(f"• **ID:** `{target_id}`")
                    st.markdown("<div style='text-align:center; color:#6b7280; margin:4px 0;'>↓</div>", unsafe_allow_html=True)
                    
                    st.markdown("#### 🎯 2. SELECTED MATCH / CANDIDATE")
                    st.write(f"• **Candidate IDs:** `{pred_item.get('invoice_id') or pred_item.get('bank_ids')}`")
                    st.markdown("<div style='text-align:center; color:#6b7280; margin:4px 0;'>↓</div>", unsafe_allow_html=True)
                    
                    st.markdown("#### 🔬 3. EVIDENCE SIGNALS")
                    ev_feats = pred_item.get("evidence_features") if isinstance(pred_item, dict) else None
                    if isinstance(ev_feats, dict) and ev_feats:
                        for k, v in ev_feats.items():
                            label = k.replace("_", " ").title()
                            st.write(f"✓ **{label}:** `{v}`")
                    elif isinstance(ev_feats, str) and ev_feats and ev_feats != "N/A":
                        st.write(f"✓ **Evidence Signals:** `{ev_feats}`")
                    elif pred_item.get("match_type") == "exact_match":
                        st.write("✓ **Amount Match:** `Exact` &nbsp;|&nbsp; **Date Match:** `Exact` &nbsp;|&nbsp; **Reference:** `Exact` &nbsp;|&nbsp; **Currency:** `INR`")
                        st.write("✓ **Match Type:** `Unique deterministic exact match` (Score: 100%)")
                    else:
                        st.write("No additional evidence required.")
                    st.markdown("<div style='text-align:center; color:#6b7280; margin:4px 0;'>↓</div>", unsafe_allow_html=True)
                    
                    st.markdown("#### 🛡️ 4. POLICY & AI ROUTING")
                    st.write(f"• **Match Scenario:** `{pred_item.get('match_type')}` | **Status:** `{pred_item.get('status')}`")
                    st.write(f"• **Policy Reason:** *{pred_item.get('policy_reason', 'Auto accepted')}*")
                    
                    from explainability import SafetyExplainabilityEngine
                    safety_info = SafetyExplainabilityEngine.generate_safety_explanation(
                        pred_item,
                        auto_accept_thresh=float(st.session_state.get("auto_accept_thresh", 95.0)),
                        needs_review_thresh=float(st.session_state.get("needs_review_thresh", 70.0)),
                        materiality_threshold_inr=float(context.get("materiality_threshold_inr") or st.session_state.get("materiality_threshold_inr", 400000.0))
                    )
                    
                    if safety_info.get("is_auto_accepted"):
                        cond_html = "<br>".join(safety_info.get("conditions", []))
                        st.markdown(f"""
                        <div style="background: rgba(16, 185, 129, 0.08); border-left: 4px solid #10b981; padding: 10px 14px; border-radius: 6px; margin: 8px 0;">
                            <div style="font-weight: 700; color: #10b981; font-size: 13px;">✓ WHY THIS WAS SAFE TO AUTO-ACCEPT</div>
                            <div style="font-size: 12.5px; color: #d1d5db; margin-top: 4px; line-height: 1.6;">
                                {cond_html}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        block_html = "<br>".join(safety_info.get("blocking_conditions", []))
                        safe_html = "<br>".join(safety_info.get("to_become_safe", []))
                        st.markdown(f"""
                        <div style="background: rgba(255, 152, 0, 0.08); border-left: 4px solid #ff9800; padding: 10px 14px; border-radius: 6px; margin: 8px 0;">
                            <div style="font-weight: 700; color: #ff9800; font-size: 13px;">⚡ WHAT WOULD MAKE THIS SAFE TO AUTO-ACCEPT?</div>
                            <div style="font-size: 12.5px; margin-top: 4px; line-height: 1.6;">
                                <strong style="color: #ef4444;">BLOCKING CONDITIONS:</strong><br>
                                {block_html}<br><br>
                                <strong style="color: #10b981;">TO BECOME AUTO-ACCEPTABLE:</strong><br>
                                {safe_html}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.markdown("<div style='text-align:center; color:#6b7280; margin:4px 0;'>↓</div>", unsafe_allow_html=True)
                    
                    st.markdown("#### ❌ 5. REJECTED CANDIDATES")
                    rej_ids = pred_item.get("rejected_candidate_ids")
                    if isinstance(rej_ids, list) and len(rej_ids) > 0:
                        formatted_ids = ", ".join([f"`{rid}`" for rid in rej_ids])
                        st.write(f"• **Rejected Candidate IDs:** {formatted_ids}")
                    else:
                        st.write("• *No rejected candidates — deterministic path did not evaluate alternate candidates.*")
                    st.markdown("<div style='text-align:center; color:#6b7280; margin:4px 0;'>↓</div>", unsafe_allow_html=True)
                    
                    st.markdown("#### 📝 6. AI RATIONALE")
                    st.write(f"*{pred_item.get('rationale', 'N/A')}*")
                    st.markdown("<div style='text-align:center; color:#6b7280; margin:4px 0;'>↓</div>", unsafe_allow_html=True)
                    
                    st.markdown("#### ⚖️ 7. ACCOUNTING EVIDENCE")
                    val_je = pred_item.get("validated_journal_entry")
                    if val_je:
                        st.code(f"Suggested Entry: Debit {val_je.get('debit_account')} {format_inr(val_je.get('amount'))}, Credit {val_je.get('credit_account')} {format_inr(val_je.get('amount'))}\nValidation: {val_je.get('validation_status')}", language="text")
                    else:
                        st.write("None required for 1:1 Exact Match.")

        else:
            # Exception record lookup
            exc_item = next((exc for exc in exception_records if exc["ID"] == target_id), None)
            if exc_item:
                with st.expander(f"🔍 Inspecting Exception Decision for target `{target_id}`", expanded=True):
                    st.markdown("#### 📌 1. SOURCE RECORD")
                    st.write(f"• ID: `{target_id}` | Source: `{exc_item['Source']}` | Amount: `{format_inr(exc_item['Amount'])}`")
                    
                    st.markdown("#### 🎯 2. SELECTED CANDIDATES")
                    st.write(f"• Candidates Selected: `{exc_item.get('Selected Candidates', 'None')}`")
                    
                    st.markdown("#### 🔬 3. DETERMINISTIC EVIDENCE SIGNALS")
                    exc_ev = exc_item.get("Evidence Features") or exc_item.get("evidence_features")
                    if isinstance(exc_ev, dict) and exc_ev:
                        for k, v in exc_ev.items():
                            label = k.replace("_", " ").title()
                            st.write(f"• **{label}:** `{v}`")
                    elif isinstance(exc_ev, str) and exc_ev and exc_ev != "N/A":
                        st.write(f"• **Evidence Features:** `{exc_ev}`")
                    else:
                        st.write("Not available for this decision type")
                    
                    st.markdown("#### ⚙️ 4. DECISION & POLICY ROUTING")
                    st.write(f"• Reason Code: `{exc_item.get('Reason Code')}` | Status: `{exc_item.get('Status')}`")
                    st.write(f"• Policy Reason: *{exc_item.get('Policy Reason')}*")
                    
                    st.markdown("#### ❌ 5. REJECTED CANDIDATES")
                    exc_rej = exc_item.get("Rejected Candidates") or exc_item.get("rejected_candidate_ids")
                    if isinstance(exc_rej, list) and len(exc_rej) > 0:
                        formatted_rej = ", ".join([f"`{r}`" for r in exc_rej])
                        st.write(f"• **Rejected Candidates:** {formatted_rej}")
                    elif isinstance(exc_rej, str) and exc_rej and exc_rej not in ["None", "[]", "N/A"]:
                        st.write(f"• **Rejected Candidates:** `{exc_rej}`")
                    elif exc_rej in ["[]", "None", None] or (isinstance(exc_rej, list) and len(exc_rej) == 0):
                        st.write("No rejected candidates.")
                        st.caption("Reason: No competing candidates were bounded for this unresolved exception.")
                    else:
                        st.write("Not available for this decision type")
                    
                    st.markdown("#### 📝 6. AI RATIONALE")
                    st.write(f"*{exc_item.get('Rationale')}*")
                    
                    st.markdown("#### ⚖️ 7. VALIDATED JOURNAL ENTRY")
                    val_je = exc_item.get("Validated JE")
                    if val_je:
                        st.code(f"Suggested Entry: Debit {val_je.get('debit_account')} {format_inr(val_je.get('amount'))}, Credit {val_je.get('credit_account')} {format_inr(val_je.get('amount'))}\nValidation: {val_je.get('validation_status')}", language="text")
                    else:
                        st.write("No journal entry suggested.")
    else:
        st.info("No decisions to inspect.")

    st.markdown("---")

    # 6. Ask Gemini About Reconciliations Grounded Q&A
    st.subheader("💬 Ask Gemini About Reconciliations")
    st.caption("Ask questions about reconciliation decisions, anomalies, splits, or variance allocations.")
    
    gemini_key = resolve_gemini_key()
    gemini_key_exists = bool(gemini_key)
    
    with st.form(key="gemini_qa_form", clear_on_submit=False):
        q_input = st.text_input("Ask a question:", placeholder="e.g. 'Are there duplicate bank transaction decoys?' or 'Why wasn't Ryan PLC transaction matched?'")
        submitted = st.form_submit_button("Submit Question")
        
    if submitted and q_input:
        if not gemini_key_exists:
            st.error("Cannot query Gemini: GEMINI_API_KEY environment variable is missing.")
        else:
            with st.spinner("Analyzing context with Gemini..."):
                try:
                    audit_context = {
                        "total_invoices": len(invoices_df),
                        "total_ledger": len(ledger_df),
                        "total_bank": len(bank_df),
                        "reconciled_capital": reconciled_dollars,
                        "variance": unexplained_variance,
                        "exceptions": exceptions_df.head(20).to_dict(orient="records") if not exceptions_df.empty else []
                    }
                    
                    prompt = f"""
                    You are a professional financial auditor. You have access to the following reconciliation audit summary:
                    
                    {json.dumps(audit_context, indent=2)}
                    
                    Answer the auditor's question grounded in this context. Be precise, professional, and concise.
                    
                    User Question: {q_input}
                    """
                    
                    client = genai.Client(api_key=gemini_key)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt
                    )
                    st.write("### 🤖 Gemini Auditor Response")
                    st.write(response.text)
                except Exception as e:
                    st.error(f"Error communicating with Gemini API: {e}")
