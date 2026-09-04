import streamlit as st
import pandas as pd
from ui_common import render_page_header, format_inr, format_inr_compact, render_empty_state


def generate_exception_intelligence(row: dict, context: dict) -> dict:
    """
    Generates structured Exception Intelligence metadata for a given exception row.
    Calculates positive (✓) and negative (✕) evidence signals, recommended action,
    and resolution conditions derived from active run policy thresholds.
    """
    auto_accept_thresh = float(st.session_state.get("auto_accept_thresh", 95.0))
    needs_review_thresh = float(st.session_state.get("needs_review_thresh", 70.0))
    mat_threshold_val = float(context.get("materiality_threshold_inr") or st.session_state.get("materiality_threshold_inr", 400000.0))

    amount = float(row.get("Amount", 0.0) or 0.0)
    sys_conf = float(row.get("System Confidence", 100.0) or 100.0)
    reason = str(row.get("Reason", ""))
    policy_reason = str(row.get("Policy Reason", "")).lower()
    currency = str(row.get("Currency", "INR")).upper()
    selected_cands = row.get("Selected Candidates", [])
    days_out = int(row.get("Days Outstanding", 0) or 0)
    
    is_high_mat = ("High" in str(row.get("Materiality", ""))) or (amount >= mat_threshold_val)

    positive_signals = []
    negative_signals = []

    # Amount Signal
    if reason == "amount_variance" or "amount variance" in policy_reason:
        negative_signals.append("✕ Amount variance detected between ledger and candidate")
    else:
        positive_signals.append("✓ Exact amount agreement")

    # Date Signal
    if days_out > 0 or reason == "date_shift" or "date" in policy_reason:
        negative_signals.append(f"✕ Clearing date shift ({days_out} days outstanding)")
    else:
        positive_signals.append("✓ Transaction date within clearing tolerance")

    # Candidate Match Signal
    if reason == "no_counterpart_found" or not selected_cands:
        negative_signals.append("✕ No counterpart candidate found in target statement")
    elif len(selected_cands) > 1 or reason == "duplicate":
        negative_signals.append(f"✕ Multiple candidate matches ({len(selected_cands)} candidates)")
    else:
        positive_signals.append("✓ Unique single candidate identified")

    # Materiality Signal
    if is_high_mat:
        negative_signals.append(f"✕ High materiality transaction (≥ {format_inr(mat_threshold_val)})")
    else:
        positive_signals.append(f"✓ Below materiality threshold ({format_inr(mat_threshold_val)})")

    # Currency Signal
    if currency != "INR" or "fx" in policy_reason:
        negative_signals.append(f"✕ FX / Multi-currency transaction ({currency})")
    else:
        positive_signals.append("✓ Base currency transaction (INR)")

    # System Confidence Signal
    if sys_conf < auto_accept_thresh:
        negative_signals.append(f"✕ System confidence ({sys_conf:.1f}%) below auto-accept threshold ({auto_accept_thresh:.0f}%)")
    else:
        positive_signals.append(f"✓ System confidence ({sys_conf:.1f}%) meets auto-accept threshold ({auto_accept_thresh:.0f}%)")

    # Recommended Action Determination
    if sys_conf < needs_review_thresh and not selected_cands:
        recommended_action = "Insufficient evidence — manual investigation required."
    elif reason == "no_counterpart_found" or not selected_cands:
        recommended_action = "Investigate missing bank statement counterpart or missing invoice entry"
    elif reason == "amount_variance":
        recommended_action = "Review amount variance and validate corrective journal adjustment"
    elif reason == "date_shift":
        recommended_action = "Validate timing difference / bank clearing date shift"
    elif len(selected_cands) > 1:
        recommended_action = "Review candidate selection to resolve duplicate match ambiguity"
    elif currency != "INR":
        recommended_action = "Validate exchange rate variance and currency conversion"
    elif is_high_mat:
        recommended_action = "Conduct mandatory high-materiality controller sign-off review"
    else:
        recommended_action = "Review AI decision rationale and confirm resolution status"

    # Resolution Conditions Derived from Active Policy
    resolution_conditions = []
    if reason == "no_counterpart_found" or not selected_cands:
        resolution_conditions.append("• Locate or ingest missing counterpart statement transaction")
    if reason == "amount_variance" or "amount variance" in policy_reason:
        resolution_conditions.append("• Resolve amount variance or post Gate-B validated journal adjustment")
    if len(selected_cands) > 1:
        resolution_conditions.append("• Select single unique candidate match")
    if sys_conf < auto_accept_thresh:
        resolution_conditions.append(f"• System confidence reaches or exceeds {auto_accept_thresh:.0f}% (Current: {sys_conf:.1f}%)")
    if is_high_mat:
        resolution_conditions.append(f"• Controller explicit sign-off for transactions ≥ {format_inr(mat_threshold_val)}")
    if currency != "INR":
        resolution_conditions.append("• Confirm spot FX rate or enter currency variance adjustment")

    if not resolution_conditions:
        resolution_conditions.append("• Controller explicit sign-off in review queue")

    # Risk Level
    if is_high_mat or len(negative_signals) >= 3:
        risk_level = "HIGH"
        risk_color = "#ef4444"
    elif len(negative_signals) == 2:
        risk_level = "MEDIUM"
        risk_color = "#f59e0b"
    else:
        risk_level = "NORMAL"
        risk_color = "#10b981"

    return {
        "positive_signals": positive_signals,
        "negative_signals": negative_signals,
        "recommended_action": recommended_action,
        "resolution_conditions": resolution_conditions,
        "risk_level": risk_level,
        "risk_color": risk_color
    }


def render_exceptions_view(context: dict):
    """
    Renders the Exception Intelligence Page.
    Primary Question Answered: 'What went wrong and how can it be resolved?'
    """
    exceptions_df = context.get("exceptions_df", pd.DataFrame())

    if exceptions_df.empty:
        render_page_header(
            title="Exceptions",
            subtitle="Corporate Month-End Close",
            badge="ACTION • 🚨 EXCEPTIONS"
        )
        st.write("")
        render_empty_state("All transactions reconciled perfectly! Zero exceptions in current run.", icon="✅")
        return

    # Task 1 Data Model: Original run exception count is immutable
    total_exceptions = len(exceptions_df)
    total_exposure = exceptions_df["Amount"].sum() if not exceptions_df.empty else 0.0

    # Count verified exceptions from persisted human reviews for this run's records
    human_reviews = st.session_state.get("human_reviews", {})
    verified_exceptions = 0
    exceptions_list = []
    
    for idx, row in exceptions_df.iterrows():
        row_id = row["ID"]
        rev_info = human_reviews.get(row_id)
        
        status = row["Status"]
        is_resolved = False
        
        if rev_info:
            status = "Resolved"
            is_resolved = True
            verified_exceptions += 1
            
        exceptions_list.append({
            "ID": row["ID"],
            "Source": row["Source"],
            "Date": row["Date"],
            "Days Outstanding": row["Days Outstanding"],
            "Vendor/Description": row["Vendor/Description"],
            "Amount": row["Amount"],
            "Currency": row["Currency"],
            "Reason": row["Reason Code"],
            "Status": status,
            "Materiality": row["Materiality"],
            "AI Confidence": row["AI Confidence"],
            "Evidence Score": row["Evidence Score"],
            "System Confidence": row["System Confidence"],
            "Rationale": row["Rationale"],
            "Policy Reason": row["Policy Reason"],
            "Evidence Features": row["Evidence Features"],
            "Selected Candidates": row["Selected Candidates"],
            "Rejected Candidates": row["Rejected Candidates"],
            "Suggested Entry": row["Suggested Entry"],
            "Validated JE": row["Validated JE"],
            "is_resolved": is_resolved
        })
        
    updated_exceptions_df = pd.DataFrame(exceptions_list)
    remaining_exceptions = max(total_exceptions - verified_exceptions, 0)

    # Page Header (ALWAYS displays original run count: Task Requirement)
    render_page_header(
        title="Exceptions",
        subtitle=f"Unresolved records blocking close ({total_exceptions} items, {format_inr_compact(total_exposure)} exposure)",
        badge="PRIMARY WORKFLOW • 🚨 EXCEPTIONS"
    )

    # Review Progress Bar & Counter Cards (Immutable Total Requirement)
    if remaining_exceptions == 0 and total_exceptions > 0:
        st.success(f"✓ All Exceptions Verified! ({total_exceptions} exceptions reviewed)", icon="✅")
    else:
        review_pct = (verified_exceptions / total_exceptions * 100) if total_exceptions > 0 else 100.0
        st.markdown(f"""
        <div style="background: rgba(255, 152, 0, 0.08); border-left: 5px solid #ff9800; padding: 12px 16px; border-radius: 8px; margin-bottom: 1rem;">
            <span style="font-weight: 700; color: #ff9800; font-size: 14.5px;">⚡ {remaining_exceptions} exceptions still require attention</span>
            <span style="font-size: 13px; color: #a0aec0; margin-left: 10px;">({verified_exceptions} Verified / {total_exceptions} Total Population)</span>
        </div>
        """, unsafe_allow_html=True)
        st.progress(min(max(review_pct / 100.0, 0.0), 1.0))

    # Top Summary KPI Cards (Immutable run-level baseline metrics)
    high_mat_count = len(updated_exceptions_df[updated_exceptions_df["Materiality"].str.contains("High", na=False)])
    low_conf_count = len(updated_exceptions_df[updated_exceptions_df["System Confidence"] < 85.0])
    other_policy_count = max(total_exceptions - high_mat_count - low_conf_count, 0)

    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    with sc1:
        st.metric("Total Exceptions", total_exceptions, help="Immutable run-level total exceptions")
    with sc2:
        st.metric("Total Exposure", format_inr_compact(total_exposure), help="Immutable original total exposure")
    with sc3:
        st.metric("High Materiality", high_mat_count)
    with sc4:
        st.metric("Low Confidence", low_conf_count)
    with sc5:
        st.metric("Other Policy Excs", other_policy_count)

    st.markdown('<div class="ledger-divider"></div>', unsafe_allow_html=True)

    # 1. Multi-Dimensional Filtering Bar
    st.markdown("#### 🎯 Filter Exception Register")
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        f_risk = st.selectbox("Risk Level", ["All", "High Risk", "Medium Risk", "Normal Risk"], key="ex_f_risk")
    with fc2:
        f_mat = st.selectbox("Materiality", ["All", "High Materiality", "Normal Materiality"], key="ex_f_mat")
    with fc3:
        f_type = st.selectbox("Exception Type", ["All", "Amount Variance", "Date Shift", "Missing Match", "Duplicate", "Currency / FX"], key="ex_f_type")
    with fc4:
        f_status = st.selectbox("Review Status", ["All", "Unresolved Only", "Verified Only"], key="ex_f_status")

    # Apply multi-dimensional filters
    filtered_df = updated_exceptions_df.copy()
    
    if f_risk == "High Risk":
        filtered_df = filtered_df[filtered_df.apply(lambda r: generate_exception_intelligence(r.to_dict(), context)["risk_level"] == "HIGH", axis=1)]
    elif f_risk == "Medium Risk":
        filtered_df = filtered_df[filtered_df.apply(lambda r: generate_exception_intelligence(r.to_dict(), context)["risk_level"] == "MEDIUM", axis=1)]
    elif f_risk == "Normal Risk":
        filtered_df = filtered_df[filtered_df.apply(lambda r: generate_exception_intelligence(r.to_dict(), context)["risk_level"] == "NORMAL", axis=1)]

    if f_mat == "High Materiality":
        filtered_df = filtered_df[filtered_df["Materiality"].str.contains("High", na=False)]
    elif f_mat == "Normal Materiality":
        filtered_df = filtered_df[~filtered_df["Materiality"].str.contains("High", na=False)]

    if f_type == "Missing Match":
        filtered_df = filtered_df[filtered_df["Reason"] == "no_counterpart_found"]
    elif f_type == "Amount Variance":
        filtered_df = filtered_df[filtered_df["Reason"] == "amount_variance"]
    elif f_type == "Date Shift":
        filtered_df = filtered_df[filtered_df["Reason"] == "date_shift"]
    elif f_type == "Duplicate":
        filtered_df = filtered_df[filtered_df["Reason"] == "likely_duplicate"]
    elif f_type == "Currency / FX":
        filtered_df = filtered_df[filtered_df["Reason"] == "fx_mismatch"]

    if f_status == "Unresolved Only":
        filtered_df = filtered_df[~filtered_df["is_resolved"]]
    elif f_status == "Verified Only":
        filtered_df = filtered_df[filtered_df["is_resolved"]]

    # Search Bar
    search_query = st.text_input("Search Exceptions:", placeholder="Filter by transaction ID, vendor, or description...")
    if search_query:
        q = search_query.lower()
        filtered_df = filtered_df[
            filtered_df["ID"].astype(str).str.lower().str.contains(q) |
            filtered_df["Vendor/Description"].astype(str).str.lower().str.contains(q) |
            filtered_df["Source"].astype(str).str.lower().str.contains(q)
        ]

    # 2. EXCEPTION TABLE (Required by Task)
    st.markdown("### 📋 Exception Table")
    
    if filtered_df.empty:
        st.info("No exceptions matching search or category filter.")
        return

    table_df = filtered_df[[
        "Source", "Date", "Days Outstanding", "Vendor/Description", 
        "Amount", "Currency", "Reason", "Status", "Materiality", 
        "AI Confidence", "Evidence Score", "System Confidence"
    ]].copy()
    
    table_df.columns = [
        "Source", "Date", "Days Outstanding", "Vendor / Description", 
        "Amount", "Currency", "Reason", "Status", "Materiality", 
        "AI Confidence", "Evidence Score", "System Confidence"
    ]
    
    REASON_MAP = {
        "exact_match": "Deterministic Exact Match",
        "reference_typo": "Reference ID Mismatch",
        "amount_variance": "Material Amount Variance",
        "date_shift": "Clearing Date Shift",
        "split_payment": "Split Payment Risk",
        "no_counterpart_found": "Unmatched Orphan Record",
        "ambiguous": "Unresolved Candidate Ambiguity"
    }

    display_df = table_df.copy()
    display_df["Amount"] = display_df["Amount"].apply(format_inr)
    display_df["Reason"] = display_df["Reason"].apply(lambda x: REASON_MAP.get(str(x), str(x).replace("_", " ").title()))
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # 3. EXCEPTION INTELLIGENCE DETAILS
    st.markdown("### 🧠 Exception Intelligence & Decision Diagnostic")
    st.caption("Structured diagnostic answering: What happened? Why blocked? What evidence? Recommended action? How to resolve?")
    
    for idx, row in filtered_df.iterrows():
        status_text = row["Status"].upper()
        mat_text = " [⚠️ HIGH]" if "High" in str(row["Materiality"]) else ""
        reason_label = REASON_MAP.get(row["Reason"], row["Reason"].replace("_", " ").title())
        
        bullet = "🟢" if row["is_resolved"] else "🟡" if row["Status"].lower() == "needs_review" else "🔴"
        expander_title = f"{bullet} {row['Source'].upper()} | {row['Vendor/Description']} | {format_inr(row['Amount'])} {row['Currency']}{mat_text} | Policy: {reason_label} | Status: {status_text}"
        
        with st.expander(expander_title):
            intel = generate_exception_intelligence(row, context)
            rec_id = row["ID"]
            existing_rev = human_reviews.get(rec_id)
            
            c_top1, c_top2 = st.columns([3, 1])
            with c_top1:
                st.markdown(f"##### 🚨 Exception Record: `{rec_id}` — **{format_inr(row['Amount'])} {row['Currency']}**")
                st.markdown(f"**Vendor/Description:** {row['Vendor/Description']} ({row['Source']}) &nbsp;|&nbsp; Date: {row['Date']}")
            with c_top2:
                st.markdown(f"""
                <div style="text-align: right;">
                    <span style="background: {intel['risk_color']}22; color: {intel['risk_color']}; border: 1px solid {intel['risk_color']}; padding: 4px 10px; border-radius: 4px; font-weight: 800; font-size: 11.5px; letter-spacing: 0.5px;">
                        RISK: {intel['risk_level']}
                    </span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

            col_inf1, col_inf2 = st.columns(2)
            with col_inf1:
                st.markdown("#### ⚡ WHY BLOCKED (Evidence Signals)")
                for sig in intel["negative_signals"]:
                    st.markdown(f"<div style='color: #ef4444; font-weight: 600; font-size: 13px; margin-bottom: 3px;'>{sig}</div>", unsafe_allow_html=True)
                for sig in intel["positive_signals"]:
                    st.markdown(f"<div style='color: #10b981; font-size: 13px; margin-bottom: 3px;'>{sig}</div>", unsafe_allow_html=True)

                st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)
                st.markdown("#### 💡 RECOMMENDED ACTION")
                st.markdown(f"""
                <div style="background: rgba(245, 158, 11, 0.08); border-left: 4px solid #f59e0b; padding: 10px 14px; border-radius: 6px; font-size: 13.5px; color: #f9fafb;">
                    <strong>{intel['recommended_action']}</strong>
                </div>
                """, unsafe_allow_html=True)

            with col_inf2:
                st.markdown("#### 🔑 WHAT WOULD RESOLVE THIS?")
                st.markdown(f"""
                <div style="background: #111827; border: 1px solid #1f2937; border-left: 3px solid #10b981; padding: 12px 16px; border-radius: 6px; font-size: 13px; color: #d1d5db; line-height: 1.7;">
                    {'<br>'.join(intel['resolution_conditions'])}
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")

            # Progressive disclosure details
            col_det1, col_det2 = st.columns(2)
            with col_det1:
                st.markdown("#### 📌 1. Source Record")
                st.write(f"• **ID:** `{row['ID']}` &nbsp;|&nbsp; **Source:** {row['Source']}")
                st.write(f"• **Date:** {row['Date']} ({row['Days Outstanding']}d outstanding)")
                st.write(f"• **Vendor/Description:** {row['Vendor/Description']}")
                
                st.markdown("#### 🎯 2. Selected Candidates")
                sel_str = ", ".join([f"`{c}`" for c in row.get("Selected Candidates", [])]) if row.get("Selected Candidates") else "*None matched*"
                st.write(f"• **Candidates:** {sel_str}")

                st.markdown("#### 🔬 3. Deterministic Evidence")
                st.write(f"• **System Confidence:** **{row['System Confidence']}%**")
                st.write(f"• **AI Confidence:** {row['AI Confidence']}% &nbsp;|&nbsp; **Evidence Score:** {row['Evidence Score']}%")
                st.write(f"• **Signals:** `{row['Evidence Features']}`")

                st.markdown("#### 🛡️ 4. Policy Decision")
                st.write(f"• **Materiality Rating:** {row['Materiality']}")
                st.write(f"• **Policy Reason:** *{row['Policy Reason']}*")

            with col_det2:
                st.markdown("#### ❌ 5. Rejected Candidates")
                rej_str = ", ".join([f"`{c}`" for c in row.get("Rejected Candidates", [])]) if row.get("Rejected Candidates") else "*None rejected*"
                st.write(f"• **Rejected:** {rej_str}")

                st.markdown("#### 📝 6. AI Rationale")
                st.write(f"*{row['Rationale']}*")

                st.markdown("#### ⚖️ 7. Validated Journal Entry")
                val_je = row.get("Validated JE")
                if val_je:
                    is_val = val_je.get('validation_status') == 'valid'
                    val_b = "✅ Validated Safe" if is_val else f"❌ Failed: {', '.join(val_je.get('validation_errors', []))}"
                    st.code(f"Debit {val_je.get('debit_account')} {format_inr(val_je.get('amount'))}\nCredit {val_je.get('credit_account')} {format_inr(val_je.get('amount'))}\nValidation: {val_b}", language="text")
                else:
                    st.write("• *No corrective journal entry generated*")

            st.markdown("---")
            
            # Controller Action Adjudication Buttons
            from review_engine import HumanReviewEngine
            c_btn1, c_btn2, c_btn3 = st.columns(3)
            with c_btn1:
                if st.button("Approve", key=f"exc_app_{rec_id}", use_container_width=True, type="primary" if not existing_rev else "secondary"):
                    rev = HumanReviewEngine.process_human_review(rec_id, "Approve", original_ai_decision="match" if row['Reason'] != "no_counterpart_found" else "no_match")
                    st.session_state.human_reviews[rec_id] = rev
                    HumanReviewEngine.save_human_reviews(st.session_state.human_reviews)
                    st.toast(f"Exception {rec_id} Approved!", icon="✅")
                    st.rerun()
            with c_btn2:
                if st.button("Reject", key=f"exc_rej_{rec_id}", use_container_width=True):
                    rev = HumanReviewEngine.process_human_review(rec_id, "Reject", original_ai_decision="match" if row['Reason'] != "no_counterpart_found" else "no_match")
                    st.session_state.human_reviews[rec_id] = rev
                    HumanReviewEngine.save_human_reviews(st.session_state.human_reviews)
                    st.toast(f"Exception {rec_id} Rejected (Override Logged)!", icon="❌")
                    st.rerun()
            with c_btn3:
                if st.button("Escalate", key=f"exc_esc_{rec_id}", use_container_width=True):
                    rev = HumanReviewEngine.process_human_review(rec_id, "Escalate", original_ai_decision="match" if row['Reason'] != "no_counterpart_found" else "no_match")
                    st.session_state.human_reviews[rec_id] = rev
                    HumanReviewEngine.save_human_reviews(st.session_state.human_reviews)
                    st.toast(f"Exception {rec_id} Escalated!", icon="🚨")
                    st.rerun()


