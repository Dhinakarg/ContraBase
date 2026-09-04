import os
import json
from datetime import datetime
from typing import Dict, Any, Tuple
import pandas as pd
import streamlit as st

from scoring import calculate_precision_recall_f1, compute_ai_confidence_metrics, compute_system_confidence_metrics
from persistence import RunStore, compute_config_hash
from journal_validator import JournalEntryValidator

DATA_DIR = "data"
INVOICES_PATH = os.path.join(DATA_DIR, "invoices.csv")
LEDGER_PATH = os.path.join(DATA_DIR, "internal_ledger.csv")
BANK_PATH = os.path.join(DATA_DIR, "bank_statement.csv")
TRUTH_PATH = os.path.join(DATA_DIR, "ground_truth.json")
LOG_PATH = os.path.join(DATA_DIR, "decisions_log.jsonl")


def format_inr(amount: float) -> str:
    """Formats a currency amount into Indian Rupee style with lakhs/crores commas (e.g. ₹12,34,567.89)."""
    try:
        if pd.isna(amount):
            return "₹0.00"
        num_val = float(amount)
        is_neg = num_val < 0
        num_val = abs(num_val)
        
        s, *d = f"{num_val:.2f}".split(".")
        decimals = d[0] if d else "00"
        
        if len(s) <= 3:
            res = s
        else:
            last3 = s[-3:]
            other = s[:-3]
            res = ""
            for i in range(len(other)):
                if i > 0 and (len(other) - i) % 2 == 0:
                    res += ","
                res += other[i]
            res += "," + last3
            
        prefix = "-₹" if is_neg else "₹"
        return f"{prefix}{res}.{decimals}"
    except Exception:
        return f"₹{amount}"


def format_inr_compact(amount: float) -> str:
    """Formats an executive KPI amount into compact Lakh/Crore notation (e.g. ₹1.25 Cr, ₹8.50 L)."""
    try:
        if pd.isna(amount):
            return "₹0.00"
        num = float(amount)
        abs_num = abs(num)
        sign = "-" if num < 0 else ""
        if abs_num >= 10000000:
            return f"{sign}₹{abs_num/10000000:.2f} Cr"
        elif abs_num >= 100000:
            return f"{sign}₹{abs_num/100000:.2f} L"
        else:
            return format_inr(num)
    except Exception:
        return f"₹{amount}"


def inject_custom_styles():
    """Injects high-contrast, modern Digital Ledger / Finance Control Room styles into the Streamlit app."""
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            background-color: #0b0f17;
            color: #f3f4f6;
        }
        
        .mono-text {
            font-family: 'JetBrains Mono', monospace !important;
        }
        
        .nav-category {
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            color: #6b7280;
            text-transform: uppercase;
            margin-top: 14px;
            margin-bottom: 4px;
        }
        
        .page-header-card {
            background: #111827;
            border: 1px solid #1f2937;
            border-left: 4px solid #10b981;
            padding: 1.2rem 1.6rem;
            border-radius: 8px;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
        }
        
        .ledger-divider {
            border-top: 1px solid #1f2937;
            margin: 1.5rem 0;
        }

        .metric-card {
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 8px;
            padding: 1rem 1.2rem;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
        }
        
        .stMetric {
            background: #111827;
            border: none;
            border-radius: 8px;
            padding: 12px 16px;
            min-width: 0;
            word-wrap: break-word;
            overflow: hidden;
        }

        /* Status Indicator Labels */
        .status-badge-auto {
            color: #10b981;
            font-weight: 600;
            font-size: 12px;
            letter-spacing: 0.5px;
        }
        .status-badge-review {
            color: #f59e0b;
            font-weight: 600;
            font-size: 12px;
            letter-spacing: 0.5px;
        }
        .status-badge-exception {
            color: #ef4444;
            font-weight: 600;
            font-size: 12px;
            letter-spacing: 0.5px;
        }

        /* Responsive Typography */
        .page-header-card, .metric-card {
            word-wrap: break-word;
            overflow-wrap: break-word;
            min-width: 0;
        }

        [data-testid="stMetricValue"] {
            font-family: 'JetBrains Mono', monospace !important;
            font-size: clamp(1.1rem, 1.8vw, 1.7rem) !important;
            white-space: normal !important;
            word-break: break-word !important;
            line-height: 1.25 !important;
            color: #f9fafb !important;
        }

        [data-testid="stMetricLabel"] {
            font-size: clamp(0.7rem, 0.85vw, 0.8rem) !important;
            text-transform: uppercase !important;
            letter-spacing: 0.8px !important;
            color: #9ca3af !important;
            white-space: normal !important;
            word-break: break-word !important;
            line-height: 1.2 !important;
        }

        .stDataFrame {
            overflow-x: auto !important;
        }

        /* Number Input Controls & Stepper Buttons Fix */
        div[data-testid="stNumberInput"] {
            margin-bottom: 0.5rem;
        }

        div[data-testid="stNumberInputContainer"] {
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
            gap: 10px !important;
            display: flex !important;
            align-items: center !important;
        }

        div[data-testid="stNumberInputContainer"] [data-baseweb="input"] {
            background-color: #111827 !important;
            border: 1px solid #374151 !important;
            border-radius: 8px !important;
            padding: 2px 6px !important;
            flex-grow: 1 !important;
        }

        div[data-testid="stNumberInputContainer"] [data-baseweb="input"]:focus-within {
            border-color: #10b981 !important;
            box-shadow: 0 0 0 1px #10b981 !important;
        }

        button[data-testid="stNumberInputStepDown"],
        button[data-testid="stNumberInputStepUp"],
        button[aria-label="Decrease value"],
        button[aria-label="Increase value"],
        div[data-testid="stNumberInput"] button {
            border-radius: 8px !important;
            background-color: #1f2937 !important;
            border: 1px solid #4b5563 !important;
            color: #10b981 !important;
            margin: 0 2px !important;
            padding: 6px 14px !important;
            min-width: 42px !important;
            height: 42px !important;
            font-size: 20px !important;
            font-weight: 700 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            cursor: pointer !important;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3) !important;
            transition: all 0.15s ease-in-out !important;
        }

        button[data-testid="stNumberInputStepDown"]:hover,
        button[data-testid="stNumberInputStepUp"]:hover,
        button[aria-label="Decrease value"]:hover,
        button[aria-label="Increase value"]:hover,
        div[data-testid="stNumberInput"] button:hover {
            background-color: #374151 !important;
            color: #34d399 !important;
            border-color: #10b981 !important;
            transform: translateY(-1px) scale(1.04) !important;
            box-shadow: 0 4px 8px rgba(16, 185, 129, 0.2) !important;
        }

        div[data-testid="stNumberInput"] input {
            color: #f9fafb !important;
            font-family: 'JetBrains Mono', monospace !important;
            font-weight: 600 !important;
            font-size: 15px !important;
            padding: 6px 10px !important;
        }
        </style>
    """, unsafe_allow_html=True)


def render_page_header(title: str, subtitle: str, badge: str = "CONTRABASE"):
    """Renders a standardized executive page header with Digital Ledger styling."""
    st.markdown(f"""
        <div id="top-page-header" class="page-header-card">
            <div style="font-size: 11px; font-weight: 700; letter-spacing: 1.5px; color: #10b981; text-transform: uppercase; margin-bottom: 4px;">
                {badge}
            </div>
            <h1 style="margin: 0; font-family: 'Outfit', sans-serif; font-size: 2.0rem; color: #f9fafb; font-weight: 700; letter-spacing: -0.5px;">
                {title}
            </h1>
            <p style="margin: 4px 0 0 0; color: #9ca3af; font-size: 0.92rem;">
                {subtitle}
            </p>
        </div>
    """, unsafe_allow_html=True)


def trigger_scroll_to_top():
    """
    Triggers a DOM-native scroll-to-top reset targeting top-level parent window scroll containers
    when transitioning between primary pages (`current_page != previous_page`).
    Runs after page content rendering so all DOM elements are present.
    Does NOT run on same-page widget reruns.
    """
    js_code = """
        <script>
            (function() {
                function scrollAll() {
                    try {
                        const pWin = window.parent;
                        if (!pWin) return;
                        const pDoc = pWin.document;
                        if (!pDoc) return;

                        // 1. Scroll window
                        if (pWin.scrollTo) pWin.scrollTo(0, 0);
                        if (window.scrollTo) window.scrollTo(0, 0);

                        // 2. Scroll all potential container elements in parent DOM
                        const selectors = [
                            '[data-testid="stAppViewContainer"]',
                            '[data-testid="stMain"]',
                            '[data-testid="stMainBlockContainer"]',
                            'section.main',
                            '.stMain',
                            '.main',
                            '.block-container',
                            'html',
                            'body'
                        ];
                        selectors.forEach(function(sel) {
                            const els = pDoc.querySelectorAll(sel);
                            els.forEach(function(el) {
                                if (el && typeof el.scrollTop !== 'undefined') {
                                    el.scrollTop = 0;
                                }
                            });
                        });

                        // 3. Scroll top page header into view
                        const topHeader = pDoc.querySelector('#top-page-header') || pDoc.querySelector('.page-header-card') || pDoc.querySelector('h1');
                        if (topHeader && topHeader.scrollIntoView) {
                            topHeader.scrollIntoView({ block: 'start', behavior: 'instant' });
                        }
                    } catch (e) {}
                }

                // Execute immediately and across multiple animation frames / timeouts
                scrollAll();
                if (typeof requestAnimationFrame === 'function') {
                    requestAnimationFrame(scrollAll);
                }
                [30, 100, 250, 500, 800, 1200].forEach(function(delay) {
                    setTimeout(scrollAll, delay);
                });

                // Attach MutationObserver to parent DOM for 1.5s
                try {
                    const pDoc = window.parent ? window.parent.document : document;
                    const targetNode = pDoc.querySelector('[data-testid="stAppViewContainer"]') || pDoc.body;
                    if (targetNode && typeof MutationObserver !== 'undefined') {
                        const observer = new MutationObserver(function() {
                            scrollAll();
                        });
                        observer.observe(targetNode, { childList: true, subtree: true });
                        setTimeout(function() {
                            observer.disconnect();
                        }, 1500);
                    }
                } catch(err) {}
            })();
        </script>
    """
    try:
        import streamlit.components.v1 as components
        components.html(js_code, height=0, width=0)
    except Exception:
        pass


def load_reconciliation_context(materiality_threshold_inr: float = 400000.0) -> Dict[str, Any]:
    """
    Loads all datasets, active run predictions, ground truth, and builds
    precomputed exception records and metrics without calling Gemini.
    """
    active_run = RunStore.load_current_run()
    if active_run:
        current_hash = compute_config_hash(
            seed=st.session_state.get("seed", 42),
            n_records=st.session_state.get("n_records", 80),
            anomaly_rate=st.session_state.get("noise_level", 0.15),
            multi_currency=st.session_state.get("multi_currency", False),
            materiality_threshold_inr=st.session_state.get("materiality_threshold_inr", 400000.0)
        )
        if active_run.get("metadata", {}).get("configuration_hash") != current_hash:
            active_run = None
            st.session_state.reconciled = False
        else:
            st.session_state.reconciled = True
            st.session_state.exec_time = active_run.get("metadata", {}).get("exec_time", 0.0)
            st.session_state.throughput = active_run.get("metadata", {}).get("throughput", 0.0)
            st.session_state.total_records = active_run.get("metadata", {}).get("record_count", 0)
    
    invoices_df = pd.read_csv(INVOICES_PATH) if os.path.exists(INVOICES_PATH) else pd.DataFrame()
    ledger_df = pd.read_csv(LEDGER_PATH) if os.path.exists(LEDGER_PATH) else pd.DataFrame()
    bank_df = pd.read_csv(BANK_PATH) if os.path.exists(BANK_PATH) else pd.DataFrame()
    
    ground_truth = {"matches": []}
    if os.path.exists(TRUTH_PATH):
        try:
            with open(TRUTH_PATH, "r", encoding="utf-8") as f:
                ground_truth = json.load(f)
        except Exception:
            pass

    if active_run:
        predictions = active_run.get("predictions", [])
        metrics = active_run.get("metrics", calculate_precision_recall_f1(predictions, ground_truth))
        decisions = active_run.get("log_records", [])
    else:
        predictions = []
        metrics = calculate_precision_recall_f1(predictions, ground_truth)
        decisions = []

    # Ensure evidence_features populated for exact matches (Part 1)
    for p in predictions:
        if isinstance(p, dict) and p.get("match_type") == "exact_match" and not p.get("evidence_features"):
            p["evidence_features"] = {
                "amount_match": "Exact",
                "date_match": "Exact",
                "reference_match": "Exact",
                "currency_match": "Exact",
                "match_type": "Unique deterministic exact match",
                "evidence_score": "100%"
            }

    # Parse decisions
    parsed_decisions = []
    for entry in decisions:
        if isinstance(entry, dict) and "decision" in entry:
            dec = entry["decision"]
            if isinstance(dec, dict):
                inv_id, led_id, bnk_ids = None, None, []
                src = dec.get("source_record_id", "")
                if "INV_" in src: inv_id = src
                elif "LED_" in src: led_id = src
                elif "BNK_" in src: bnk_ids.append(src)
                
                for c_id in dec.get("selected_candidate_ids", []):
                    if "INV_" in c_id: inv_id = c_id
                    elif "LED_" in c_id: led_id = c_id
                    elif "BNK_" in c_id: bnk_ids.append(c_id)
                    
                dec["ledger_id"] = led_id
                dec["invoice_id"] = inv_id
                dec["bank_ids"] = bnk_ids
                parsed_decisions.append(entry)
    decisions = parsed_decisions

    # Financial & Match rate calculations
    total_ledger = len(ledger_df)
    matched_ledger = len([m for m in predictions if m.get("ledger_id")])
    match_rate = matched_ledger / total_ledger if total_ledger > 0 else 0.0

    predicted_led_set = {str(m["ledger_id"]) for m in predictions if m.get("ledger_id")}
    reconciled_dollars = sum(float(row["amount"]) for _, row in ledger_df.iterrows() if str(row["ledger_id"]) in predicted_led_set) if not ledger_df.empty else 0.0
    total_ledger_dollars = float(ledger_df["amount"].sum()) if not ledger_df.empty else 0.0
    unexplained_variance = total_ledger_dollars - reconciled_dollars

    # Exception records compilation
    exception_records = []
    
    # Add matched predictions that are not auto_accepted (needs_review or exception status)
    for m in predictions:
        status = m.get("status")
        if status in ["needs_review", "exception"]:
            led_id = m.get("ledger_id")
            bank_ids = m.get("bank_ids", [])
            
            amt = 0.0
            vendor = "Unknown"
            curr = "INR"
            dt = ""
            days_out = 0
            
            if led_id and not ledger_df.empty:
                rows = ledger_df.loc[ledger_df["ledger_id"].astype(str) == str(led_id)]
                if not rows.empty:
                    amt = float(rows["amount"].values[0])
                    vendor = rows["vendor"].values[0]
                    curr = rows.get("currency", ["INR"]).values[0]
                    dt = str(rows["date"].values[0])
                    try:
                        days_out = (datetime.now() - pd.to_datetime(dt)).days
                    except:
                        pass
            elif bank_ids and not bank_df.empty:
                b_id = bank_ids[0]
                rows = bank_df.loc[bank_df["bank_id"].astype(str) == str(b_id)]
                if not rows.empty:
                    amt = float(rows["amount"].values[0])
                    vendor = rows["description"].values[0]
                    curr = rows.get("currency", ["INR"]).values[0]
                    dt = str(rows["date"].values[0])
                    try:
                        days_out = (datetime.now() - pd.to_datetime(dt)).days
                    except:
                        pass
                        
            is_high_materiality = amt >= materiality_threshold_inr
            materiality_flag = "⚠️ High" if is_high_materiality else "Normal"
            
            exception_records.append({
                "ID": led_id or (bank_ids[0] if bank_ids else "N/A"),
                "Source": "Ledger Match" if led_id else "Bank Match",
                "Vendor/Description": vendor,
                "Amount": amt,
                "Currency": curr,
                "Reference ID": "N/A",
                "Reason Code": m.get("reason_code", m.get("match_type", "unknown")),
                "AI Confidence": m.get("ai_confidence", 0),
                "Evidence Score": m.get("evidence_score", 0),
                "System Confidence": m.get("decision_confidence", m.get("confidence", 0)),
                "Rationale": m.get("rationale", "N/A"),
                "Policy Reason": m.get("policy_reason", "Awaiting human review"),
                "Evidence Features": m.get("evidence_features", "N/A"),
                "Selected Candidates": m.get("selected_candidate_ids", []),
                "Rejected Candidates": m.get("rejected_candidate_ids", []),
                "Date": dt,
                "Status": status,
                "Materiality": materiality_flag,
                "Days Outstanding": days_out,
                "Suggested Entry": m.get("suggested_corrective_entry"),
                "Validated JE": m.get("validated_journal_entry")
            })

    predicted_ledger_ids = {str(m.get("ledger_id")) for m in predictions if m.get("ledger_id")}
    predicted_bank_ids = set()
    for m in predictions:
        if m.get("bank_ids"):
            predicted_bank_ids.update([str(b) for b in m.get("bank_ids")])

    if not ledger_df.empty:
        for _, row in ledger_df.iterrows():
            led_id = str(row["ledger_id"])
            if led_id not in predicted_ledger_ids:
                decision_info = next((d.get("decision", d) for d in decisions if isinstance(d, dict) and (str(d.get("decision", d).get("ledger_id")) == led_id or str(d.get("decision", d).get("source_record_id")) == led_id)), None)
                status = decision_info.get("status", "exception") if isinstance(decision_info, dict) else "exception"
                
                amt = float(row["amount"])
                is_high_materiality = amt >= materiality_threshold_inr
                materiality_flag = "⚠️ High" if is_high_materiality else "Normal"
                
                try:
                    days_out = (datetime.now() - pd.to_datetime(row["date"])).days
                except Exception:
                    days_out = 0

                ai_conf = decision_info.get("ai_confidence", decision_info.get("confidence", 0)) if isinstance(decision_info, dict) else 0
                sys_conf = decision_info.get("decision_confidence", decision_info.get("confidence", 0)) if isinstance(decision_info, dict) else 0
                ev_score = decision_info.get("evidence_score", 0) if isinstance(decision_info, dict) else 0
                pol_reason = decision_info.get("policy_reason", "Unmatched record default policy") if isinstance(decision_info, dict) else "No match counterpart found"
                val_je = decision_info.get("validated_journal_entry") if isinstance(decision_info, dict) else None
                ev_feat = decision_info.get("evidence_features", "No candidate matched") if isinstance(decision_info, dict) else "No counterpart found"
                sel_cands = decision_info.get("selected_candidate_ids", []) if isinstance(decision_info, dict) else []
                rej_cands = decision_info.get("rejected_candidate_ids", []) if isinstance(decision_info, dict) else []

                exception_records.append({
                    "ID": led_id,
                    "Source": "Ledger",
                    "Vendor/Description": row.get("vendor", "N/A"),
                    "Amount": amt,
                    "Currency": row.get("currency", "INR"),
                    "Reference ID": row.get("reference_id", "N/A"),
                    "Reason Code": decision_info.get("reason_code", "no_counterpart_found") if isinstance(decision_info, dict) else "no_counterpart_found",
                    "AI Confidence": ai_conf,
                    "Evidence Score": ev_score,
                    "System Confidence": sys_conf,
                    "Rationale": decision_info.get("rationale", "No counterpart found during analysis") if isinstance(decision_info, dict) else "No counterpart found during analysis",
                    "Policy Reason": pol_reason,
                    "Evidence Features": ev_feat,
                    "Selected Candidates": sel_cands,
                    "Rejected Candidates": rej_cands,
                    "Date": str(row.get("date", "")),
                    "Status": status,
                    "Materiality": materiality_flag,
                    "Days Outstanding": days_out,
                    "Suggested Entry": decision_info.get("suggested_corrective_entry") if isinstance(decision_info, dict) else None,
                    "Validated JE": val_je
                })

    if not bank_df.empty:
        for _, row in bank_df.iterrows():
            bnk_id = str(row["bank_id"])
            if bnk_id not in predicted_bank_ids:
                decision_info = next((d.get("decision", d) for d in decisions if isinstance(d, dict) and bnk_id in [str(b) for b in d.get("decision", d).get("bank_ids", [])]), None)
                status = decision_info.get("status", "exception") if isinstance(decision_info, dict) else "exception"
                
                amt = float(row["amount"])
                is_high_materiality = amt >= materiality_threshold_inr
                materiality_flag = "⚠️ High" if is_high_materiality else "Normal"
                
                try:
                    days_out = (datetime.now() - pd.to_datetime(row["date"])).days
                except Exception:
                    days_out = 0

                ai_conf = decision_info.get("ai_confidence", decision_info.get("confidence", 0)) if isinstance(decision_info, dict) else 0
                sys_conf = decision_info.get("decision_confidence", decision_info.get("confidence", 0)) if isinstance(decision_info, dict) else 0
                ev_score = decision_info.get("evidence_score", 0) if isinstance(decision_info, dict) else 0
                pol_reason = decision_info.get("policy_reason", "Unmatched record default policy") if isinstance(decision_info, dict) else "No matching ledger entry found"
                val_je = decision_info.get("validated_journal_entry") if isinstance(decision_info, dict) else None
                ev_feat = decision_info.get("evidence_features", "No candidate matched") if isinstance(decision_info, dict) else "No counterpart found"
                sel_cands = decision_info.get("selected_candidate_ids", []) if isinstance(decision_info, dict) else []
                rej_cands = decision_info.get("rejected_candidate_ids", []) if isinstance(decision_info, dict) else []

                exception_records.append({
                    "ID": bnk_id,
                    "Source": "Bank Statement",
                    "Vendor/Description": row.get("description", "N/A"),
                    "Amount": amt,
                    "Currency": row.get("currency", "INR"),
                    "Reference ID": row.get("reference_id", "N/A"),
                    "Reason Code": decision_info.get("reason_code", "no_counterpart_found") if isinstance(decision_info, dict) else "no_counterpart_found",
                    "AI Confidence": ai_conf,
                    "Evidence Score": ev_score,
                    "System Confidence": sys_conf,
                    "Rationale": decision_info.get("rationale", "No matching ledger entry found") if isinstance(decision_info, dict) else "No matching ledger entry found",
                    "Policy Reason": pol_reason,
                    "Evidence Features": ev_feat,
                    "Selected Candidates": sel_cands,
                    "Rejected Candidates": rej_cands,
                    "Date": str(row.get("date", "")),
                    "Status": status,
                    "Materiality": materiality_flag,
                    "Days Outstanding": days_out,
                    "Suggested Entry": decision_info.get("suggested_corrective_entry") if isinstance(decision_info, dict) else None,
                    "Validated JE": val_je
                })

    # High materiality and needs review dollar exposure
    pred_nr_dollars = 0.0
    pred_hm_dollars = 0.0
    for m in predictions:
        status = m.get("status")
        led_id = m.get("ledger_id")
        amt = 0.0
        if led_id and not ledger_df.empty:
            matching_rows = ledger_df.loc[ledger_df["ledger_id"].astype(str) == str(led_id), "amount"].values
            if len(matching_rows) > 0:
                amt = float(matching_rows[0])
        if amt == 0.0 and m.get("bank_ids") and len(m.get("bank_ids")) > 0 and not bank_df.empty:
            b_id = str(m["bank_ids"][0])
            matching_rows = bank_df.loc[bank_df["bank_id"].astype(str) == b_id, "amount"].values
            if len(matching_rows) > 0:
                amt = float(matching_rows[0])
        
        if status == "needs_review":
            pred_nr_dollars += amt
        if amt >= materiality_threshold_inr:
            pred_hm_dollars += amt

    exc_nr_dollars = sum(exc["Amount"] for exc in exception_records if exc.get("Status") == "needs_review")
    exc_hm_dollars = sum(exc["Amount"] for exc in exception_records if exc.get("Materiality") == "⚠️ High")

    needs_review_dollars = pred_nr_dollars + exc_nr_dollars
    high_materiality_dollars = pred_hm_dollars + exc_hm_dollars

    # Status band counts (Record-level status aggregation)
    all_ledger_ids = set(str(x) for x in ledger_df["ledger_id"]) if not ledger_df.empty else set()
    all_bank_ids = set(str(x) for x in bank_df["bank_id"]) if not bank_df.empty else set()

    auto_accepted_led = set()
    auto_accepted_bnk = set()
    for p in predictions:
        if p.get("status") == "auto_accepted":
            if p.get("ledger_id"):
                auto_accepted_led.add(str(p["ledger_id"]))
            for b_id in p.get("bank_ids", []):
                if b_id:
                    auto_accepted_bnk.add(str(b_id))

    needs_review_led = set()
    needs_review_bnk = set()
    for p in predictions:
        if p.get("status") == "needs_review":
            l_id = p.get("ledger_id")
            if l_id and str(l_id) not in auto_accepted_led:
                needs_review_led.add(str(l_id))
            for b_id in p.get("bank_ids", []):
                if b_id and str(b_id) not in auto_accepted_bnk:
                    needs_review_bnk.add(str(b_id))

    exceptions_led = all_ledger_ids - auto_accepted_led - needs_review_led
    exceptions_bank = all_bank_ids - auto_accepted_bnk - needs_review_bnk

    status_counts = {
        "auto_accepted": len(auto_accepted_led) + len(auto_accepted_bnk),
        "needs_review": len(needs_review_led) + len(needs_review_bnk),
        "exception": len(exceptions_led) + len(exceptions_bank)
    }

    exceptions_df = pd.DataFrame(exception_records)

    return {
        "active_run": active_run,
        "invoices_df": invoices_df,
        "ledger_df": ledger_df,
        "bank_df": bank_df,
        "ground_truth": ground_truth,
        "predictions": predictions,
        "metrics": metrics,
        "decisions": decisions,
        "exception_records": exception_records,
        "exceptions_df": exceptions_df,
        "status_counts": status_counts,
        "reconciled_dollars": reconciled_dollars,
        "unexplained_variance": unexplained_variance,
        "needs_review_dollars": needs_review_dollars,
        "high_materiality_dollars": high_materiality_dollars,
        "match_rate": match_rate,
        "total_ledger": total_ledger,
        "matched_ledger": matched_ledger
    }


def render_kpi_card(label: str, value: str, help_text: str = ""):
    """Renders a reusable, highly polished KPI card."""
    st.metric(label=label, value=value, help=help_text)


def render_status_badge(status: str) -> str:
    """Returns HTML for a styled status badge based on status value."""
    status_lower = status.lower().replace(" ", "_")
    if status_lower in ["auto_accepted", "approved", "valid", "reconciled"]:
        bg, color = "rgba(76, 175, 80, 0.12)", "#4caf50"
    elif status_lower in ["needs_review", "pending", "escalated"]:
        bg, color = "rgba(255, 152, 0, 0.12)", "#ff9800"
    else:
        bg, color = "rgba(244, 67, 54, 0.12)", "#f44336"
    
    return f"""
    <span style="background-color: {bg}; color: {color}; border: 1px solid {color};
                 padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; display: inline-block;">
        {status.replace('_', ' ').upper()}
    </span>
    """


def render_empty_state(message: str, icon: str = "🔍"):
    """Renders a consistent, clean empty state container."""
    st.markdown(f"""
        <div style="text-align: center; padding: 3rem 2rem; background: #11151e; border: 1px dashed #222b3c; border-radius: 10px;">
            <div style="font-size: 3rem; margin-bottom: 1rem;">{icon}</div>
            <div style="color: #b0c4de; font-size: 1.1rem; font-weight: 500;">{message}</div>
        </div>
    """, unsafe_allow_html=True)


def render_section_header(title: str):
    """Renders a section header with visual separation."""
    st.markdown(f"""
        <h3 style="font-family: 'Outfit', sans-serif; font-weight: 700; color: #ffffff; margin-top: 1.5rem; margin-bottom: 0.8rem; border-bottom: 2px solid #222b3c; padding-bottom: 6px;">
            {title}
        </h3>
    """, unsafe_allow_html=True)
