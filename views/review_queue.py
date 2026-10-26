import textwrap
import streamlit as st
import pandas as pd
from ui_common import render_page_header, format_inr, format_inr_compact, render_empty_state
from review_engine import HumanReviewEngine
from prioritization import RiskPrioritizer


def render_review_queue_view(context: dict):
    """
    Renders the Finance Controller Review Workbench.
    A calm, progressive-disclosure workspace for reviewing and adjudicating
    policy-flagged transactions without visual fatigue or dashboard noise.
    """
    # 1. Initialize UI-only queue state (non-destructive, zero financial impact)
    if "rq_expanded_records" not in st.session_state:
        st.session_state.rq_expanded_records = set()
    if "rq_held_records" not in st.session_state:
        st.session_state.rq_held_records = set()
    if "rq_status_filter" not in st.session_state:
        st.session_state.rq_status_filter = "All"

    exception_records = context.get("exception_records", [])
    human_reviews_db = st.session_state.get("human_reviews", {})
    mat_threshold_val = context.get("materiality_threshold_inr") or st.session_state.get("materiality_threshold_inr", 400000.0)
    
    # Filter needs_review items from exception records
    needs_review_items = [exc for exc in exception_records if exc["Status"] == "needs_review"]
    needs_review_dollars = sum(exc["Amount"] for exc in needs_review_items)
    
    # Counts for human reviews
    approved_cnt = sum(1 for rev in human_reviews_db.values() if rev.get("human_reviewer_action") == "Approve")
    rejected_cnt = sum(1 for rev in human_reviews_db.values() if rev.get("human_reviewer_action") == "Reject")
    escalated_cnt = sum(1 for rev in human_reviews_db.values() if rev.get("human_reviewer_action") == "Escalate")
    completed_cnt = len(human_reviews_db)
    held_cnt = len([r for r in st.session_state.rq_held_records if r in {it["ID"] for it in needs_review_items} and r not in human_reviews_db])
    pending_cnt = max(len(needs_review_items) - completed_cnt - held_cnt, 0)

    # Risk counts
    high_cnt = sum(1 for it in needs_review_items if "HIGH" in str(it.get("_priority", RiskPrioritizer.evaluate_priority(it, mat_threshold_val)).get("priority_band", "")))
    med_cnt = sum(1 for it in needs_review_items if "MEDIUM" in str(it.get("_priority", RiskPrioritizer.evaluate_priority(it, mat_threshold_val)).get("priority_band", "")))
    low_cnt = sum(1 for it in needs_review_items if "LOW" in str(it.get("_priority", RiskPrioritizer.evaluate_priority(it, mat_threshold_val)).get("priority_band", "")))

    # Page Header (Calm, institutional header)
    render_page_header(
        title="Review Queue",
        subtitle="Finance Controller Review Workbench",
        badge="PRIMARY WORKFLOW • 👤 REVIEW QUEUE"
    )

    # 2. Compact Workbench Summary Bar (Restrained, professional summary)
    summary_html = textwrap.dedent(f"""
        <div style="background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 14px 20px; margin-bottom: 1.2rem; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 14px;">
            <div>
                <div style="font-size: 15px; font-weight: 700; color: #f8fafc; letter-spacing: -0.2px;">
                    {len(needs_review_items)} items require controller attention
                </div>
                <div style="font-size: 12.5px; color: #94a3b8; margin-top: 3px;">
                    Total Exposure: <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #f1f5f9;">{format_inr(needs_review_dollars)}</span>
                </div>
            </div>
            <div style="display: flex; gap: 18px; align-items: center; font-size: 12px;">
                <span style="color: #ef4444; font-weight: 600;">● High Risk: <strong style="color: #ffffff;">{high_cnt}</strong></span>
                <span style="color: #f59e0b; font-weight: 600;">● Medium Risk: <strong style="color: #ffffff;">{med_cnt}</strong></span>
                <span style="color: #94a3b8; font-weight: 600;">● Low Risk: <strong style="color: #ffffff;">{low_cnt}</strong></span>
                <span style="color: #10b981; font-weight: 600;">✓ Completed: <strong style="color: #ffffff;">{completed_cnt}</strong></span>
            </div>
        </div>
    """).strip()
    st.markdown(summary_html, unsafe_allow_html=True)

    # 3. Filter & Sort Bar (Clean horizontal alignment)
    fc1, fc2 = st.columns([3, 2])
    with fc1:
        filter_tabs = [
            f"All ({len(needs_review_items)})",
            f"Pending ({pending_cnt})",
            f"On Hold ({held_cnt})",
            f"Completed ({completed_cnt})"
        ]
        chosen_filter_label = st.radio(
            "Filter Queue",
            filter_tabs,
            index=0,
            horizontal=True,
            label_visibility="collapsed"
        )
    with fc2:
        sort_option = st.selectbox(
            "Sort Review Queue",
            ["Highest Risk", "Highest Value", "Lowest Confidence", "Oldest"],
            index=0,
            label_visibility="collapsed"
        )

    # Map filter selection to clean category
    active_filter = "All"
    if "Pending" in chosen_filter_label:
        active_filter = "Pending"
    elif "On Hold" in chosen_filter_label:
        active_filter = "On Hold"
    elif "Completed" in chosen_filter_label:
        active_filter = "Completed"

    # Sort items deterministically
    sorted_items = RiskPrioritizer.sort_items(
        needs_review_items,
        sort_key=sort_option,
        materiality_threshold_inr=mat_threshold_val
    )

    # Apply view filter
    filtered_items = []
    for item in sorted_items:
        rec_id = item["ID"]
        is_completed = rec_id in human_reviews_db
        is_held = rec_id in st.session_state.rq_held_records and not is_completed

        if active_filter == "All":
            filtered_items.append(item)
        elif active_filter == "Pending" and not is_completed and not is_held:
            filtered_items.append(item)
        elif active_filter == "On Hold" and is_held:
            filtered_items.append(item)
        elif active_filter == "Completed" and is_completed:
            filtered_items.append(item)

    REASON_MAP = {
        "exact_match": "Exact Match",
        "reference_typo": "Reference Mismatch",
        "amount_variance": "Amount Variance",
        "date_shift": "Clearing Date Shift",
        "split_payment": "Split Payment",
        "no_counterpart_found": "Unmatched Record",
        "ambiguous": "Candidate Ambiguity"
    }

    # 4. Work Queue Header
    st.markdown(f"<div style='font-size: 13px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.8px; margin: 1.2rem 0 0.6rem 0;'>Review Items ({len(filtered_items)})</div>", unsafe_allow_html=True)

    if not filtered_items:
        if active_filter == "On Hold":
            render_empty_state("No items currently on hold. Use 'Hold / Minimize' on any record to defer it.", icon="⏸")
        elif active_filter == "Completed":
            render_empty_state("No items completed yet. Review and adjudicate pending items to complete reviews.", icon="📋")
        else:
            render_empty_state("No items currently pending human review.", icon="✓")
    else:
        for idx, item in enumerate(filtered_items, start=1):
            rec_id = item["ID"]
            existing_rev = human_reviews_db.get(rec_id)
            is_held = rec_id in st.session_state.rq_held_records and not existing_rev
            is_expanded = rec_id in st.session_state.rq_expanded_records

            p_info = item.get("_priority", RiskPrioritizer.evaluate_priority(item, mat_threshold_val))
            rank = p_info.get("rank", idx)
            p_band = p_info.get("priority_band", "MEDIUM PRIORITY")
            p_explanation = p_info.get("explanation", "")

            # Subtle, professional color palette
            if "HIGH" in p_band:
                band_label = "HIGH PRIORITY"
                band_color = "#f87171"
                band_bg = "rgba(239, 68, 68, 0.1)"
                border_accent = "#ef4444"
            elif "MEDIUM" in p_band:
                band_label = "MEDIUM PRIORITY"
                band_color = "#fbbf24"
                band_bg = "rgba(245, 158, 11, 0.1)"
                border_accent = "#f59e0b"
            else:
                band_label = "LOW PRIORITY"
                band_color = "#94a3b8"
                band_bg = "rgba(148, 163, 184, 0.1)"
                border_accent = "#64748b"

            # Status determination
            if existing_rev:
                act = existing_rev.get("human_reviewer_action")
                if act == "Approve":
                    status_label = "Approved"
                    status_color = "#34d399"
                    status_bg = "rgba(16, 185, 129, 0.12)"
                elif act == "Reject":
                    status_label = "Rejected"
                    status_color = "#f87171"
                    status_bg = "rgba(239, 68, 68, 0.12)"
                else:
                    status_label = "Escalated"
                    status_color = "#f472b6"
                    status_bg = "rgba(244, 114, 182, 0.12)"
            elif is_held:
                status_label = "On Hold"
                status_color = "#93c5fd"
                status_bg = "rgba(59, 130, 246, 0.12)"
            else:
                status_label = "Pending"
                status_color = "#fbbf24"
                status_bg = "rgba(245, 158, 11, 0.12)"

            ai_rec = "Match" if item["Reason Code"] != "no_counterpart_found" else "No Match"
            human_reason = REASON_MAP.get(item["Reason Code"], item["Reason Code"].replace('_', ' ').title())
            conf_val = item.get("System Confidence", item.get("AI Confidence", 0))

            # Render Workbench Card Container
            with st.container(border=True):
                # -------------------------------------------------------------
                # 1. COLLAPSED / SCAN ROW (Calm, structured, 1-line hierarchy)
                # -------------------------------------------------------------
                c_name, c_amt, c_rec, c_status, c_btn = st.columns([3.0, 1.8, 2.0, 1.2, 1.1])

                with c_name:
                    st.markdown(f"""
                        <div style="line-height: 1.25;">
                            <span style="font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700; color: #94a3b8;">#{rank}</span>
                            <span style="font-size: 14px; font-weight: 700; color: #f8fafc; margin-left: 4px;">{item['Vendor/Description']}</span>
                            <div style="margin-top: 3px;">
                                <span style="background: {band_bg}; color: {band_color}; padding: 2px 7px; border-radius: 4px; font-size: 10.5px; font-weight: 700; letter-spacing: 0.4px;">
                                    {band_label}
                                </span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                with c_amt:
                    st.markdown(f"""
                        <div style="line-height: 1.25;">
                            <div style="font-size: 10.5px; color: #64748b; font-weight: 600; text-transform: uppercase;">Exposure</div>
                            <div style="font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 13.5px; color: #f1f5f9;">
                                {format_inr(item['Amount'])}
                            </div>
                            <div style="font-size: 11px; color: #64748b;">{rec_id}</div>
                        </div>
                    """, unsafe_allow_html=True)

                with c_rec:
                    st.markdown(f"""
                        <div style="line-height: 1.25;">
                            <div style="font-size: 10.5px; color: #64748b; font-weight: 600; text-transform: uppercase;">AI & Policy</div>
                            <div style="font-size: 13px; font-weight: 600; color: #cbd5e1;">
                                {ai_rec} · {conf_val}%
                            </div>
                            <div style="font-size: 11px; color: #94a3b8;">{human_reason}</div>
                        </div>
                    """, unsafe_allow_html=True)

                with c_status:
                    st.markdown(f"""
                        <div style="line-height: 1.25; margin-top: 4px;">
                            <span style="background: {status_bg}; color: {status_color}; padding: 3px 9px; border-radius: 4px; font-size: 11.5px; font-weight: 700; display: inline-block;">
                                {status_label}
                            </span>
                        </div>
                    """, unsafe_allow_html=True)

                with c_btn:
                    btn_label = "Minimize" if is_expanded else "Review"
                    btn_type = "secondary"
                    if st.button(btn_label, key=f"tgl_{rec_id}", use_container_width=True, type=btn_type):
                        if is_expanded:
                            st.session_state.rq_expanded_records.discard(rec_id)
                        else:
                            st.session_state.rq_expanded_records.add(rec_id)
                        st.rerun()

                # -------------------------------------------------------------
                # 2. EXPANDED WORKBENCH VIEW (Progressive Disclosure)
                # -------------------------------------------------------------
                if is_expanded:
                    st.markdown("<div style='border-top: 1px solid #1e293b; margin: 12px 0 14px 0;'></div>", unsafe_allow_html=True)

                    # A. Why This Needs Review (Concise, calm prompt)
                    st.markdown(f"""
                        <div style="background: #0f172a; border-left: 3px solid {border_accent}; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
                            <div style="font-size: 11px; font-weight: 700; color: {band_color}; text-transform: uppercase; letter-spacing: 0.5px;">
                                Why Review is Required
                            </div>
                            <div style="font-size: 13px; color: #e2e8f0; margin-top: 3px; line-height: 1.5;">
                                {p_explanation}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    # B. Evidence Summary
                    ev_text = item.get("Evidence Features", "N/A")
                    st.markdown(f"""
                        <div style="background: #0f172a; border: 1px solid #1e293b; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
                            <div style="font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">
                                Key Evidence Signals
                            </div>
                            <div style="font-size: 12.5px; color: #cbd5e1; line-height: 1.5;">
                                {ev_text}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    # Optional Gate-B Journal Entry Preview
                    val_je = item.get('Validated JE')
                    if val_je and val_je.get('validation_status') == 'valid':
                        st.markdown(f"""
                            <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); padding: 8px 12px; border-radius: 4px; font-size: 12px; color: #34d399; margin-bottom: 12px;">
                                ⚖️ <strong>Gate-B Journal Entry:</strong> Debit {val_je.get('debit_account')} {format_inr(val_je.get('amount'))} / Credit {val_je.get('credit_account')} {format_inr(val_je.get('amount'))} (Validated Safe)
                            </div>
                        """, unsafe_allow_html=True)

                    # C. Secondary Technical Trace (Expander keeps technical details available but tucked away)
                    with st.expander("View decision trace & audit evidence", expanded=False):
                        d_col1, d_col2 = st.columns(2)
                        with d_col1:
                            st.markdown("**Source & Candidates**")
                            st.write(f"• **Source ID:** `{rec_id}` ({item['Source']})")
                            st.write(f"• **Date:** {item['Date']} ({item['Days Outstanding']}d outstanding)")
                            cands = item.get('Selected Candidates', [])
                            st.write(f"• **Candidates Evaluated:** {', '.join([f'`{c}`' for c in cands]) if cands else 'None'}")
                            rejs = item.get('Rejected Candidates', [])
                            st.write(f"• **Rejected Candidates:** {', '.join([f'`{c}`' for c in rejs]) if rejs else 'None'}")
                        with d_col2:
                            st.markdown("**Policy & AI Adjudication**")
                            st.write(f"• **Policy Reason:** *{item.get('Policy Reason')}*")
                            st.write(f"• **AI Rationale:** *{item.get('Rationale', 'N/A')}*")
                            st.write(f"• **Confidence:** System {conf_val}% · AI {item.get('AI Confidence', 0)}% · Evidence {item.get('Evidence Score', 0)}%")

                    # D. Controller Actions (Clean, balanced, non-aggressive actions)
                    st.markdown("<div style='margin-top: 14px; margin-bottom: 8px; font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px;'>Controller Decision</div>", unsafe_allow_html=True)

                    if existing_rev:
                        act_name = existing_rev.get("human_reviewer_action", "").upper()
                        rev_time = existing_rev.get("review_timestamp", "")[:19].replace("T", " ")
                        is_ovr = " (Human Override Logged)" if existing_rev.get("human_override") else ""
                        st.markdown(f"""
                            <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid #10b981; padding: 8px 12px; border-radius: 4px; margin-bottom: 10px; font-size: 12.5px; color: #10b981; font-weight: 600;">
                                ✓ Controller Decision Recorded: {act_name} at {rev_time}{is_ovr}
                            </div>
                        """, unsafe_allow_html=True)

                    act_c1, act_c2, act_c3, act_c4 = st.columns(4)
                    with act_c1:
                        if st.button("Approve", key=f"btn_app_{rec_id}", use_container_width=True, type="primary" if not existing_rev else "secondary"):
                            rev = HumanReviewEngine.process_human_review(
                                rec_id, "Approve",
                                original_ai_decision="match" if item['Reason Code'] != "no_counterpart_found" else "no_match"
                            )
                            st.session_state.human_reviews[rec_id] = rev
                            HumanReviewEngine.save_human_reviews(st.session_state.human_reviews)
                            st.session_state.rq_held_records.discard(rec_id)
                            st.toast(f"Record {rec_id} Approved!", icon="✅")
                            st.rerun()

                    with act_c2:
                        if st.button("Reject", key=f"btn_rej_{rec_id}", use_container_width=True):
                            rev = HumanReviewEngine.process_human_review(
                                rec_id, "Reject",
                                original_ai_decision="match" if item['Reason Code'] != "no_counterpart_found" else "no_match"
                            )
                            st.session_state.human_reviews[rec_id] = rev
                            HumanReviewEngine.save_human_reviews(st.session_state.human_reviews)
                            st.session_state.rq_held_records.discard(rec_id)
                            st.toast(f"Record {rec_id} Rejected (Override Logged)!", icon="❌")
                            st.rerun()

                    with act_c3:
                        if st.button("Escalate", key=f"btn_esc_{rec_id}", use_container_width=True):
                            rev = HumanReviewEngine.process_human_review(
                                rec_id, "Escalate",
                                original_ai_decision="match" if item['Reason Code'] != "no_counterpart_found" else "no_match"
                            )
                            st.session_state.human_reviews[rec_id] = rev
                            HumanReviewEngine.save_human_reviews(st.session_state.human_reviews)
                            st.session_state.rq_held_records.discard(rec_id)
                            st.toast(f"Record {rec_id} Escalated!", icon="🚨")
                            st.rerun()

                    with act_c4:
                        hold_button_label = "Resume" if is_held else "Hold / Minimize"
                        if st.button(hold_button_label, key=f"btn_hold_{rec_id}", use_container_width=True):
                            if is_held:
                                st.session_state.rq_held_records.discard(rec_id)
                                st.toast(f"Record {rec_id} resumed in active queue.")
                            else:
                                st.session_state.rq_held_records.add(rec_id)
                                st.session_state.rq_expanded_records.discard(rec_id)
                                st.toast(f"Record {rec_id} placed on hold (deferred).", icon="⏸")
                            st.rerun()

    # 5. Auditor Override History Table (Subtle, professional)
    st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)
    st.markdown("### Auditor Override History")
    st.caption("Controller decisions recorded in the audit trail.")
    
    if human_reviews_db:
        override_records = []
        for rec_id, info in human_reviews_db.items():
            override_records.append({
                "Record ID": rec_id,
                "Original AI Decision": info.get("original_ai_decision", "").upper(),
                "Final Human Decision": info.get("final_decision", "").upper(),
                "Human Action": info.get("human_reviewer_action", "").upper(),
                "Override": "Yes" if info.get("human_override", False) else "No",
                "Timestamp": info.get("review_timestamp", "")[:19].replace("T", " ")
            })
            
        override_df = pd.DataFrame(override_records)
        st.dataframe(override_df, use_container_width=True, hide_index=True)
    else:
        st.info("No auditor overrides logged yet. Review pending items to track override history.")
