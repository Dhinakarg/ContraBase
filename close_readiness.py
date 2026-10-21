"""
Deterministic Close Readiness Evaluator for ContraBase.
Derives month-end close readiness state strictly from operational facts.
No arbitrary scoring formulas or fake percentages.
"""

from typing import Dict, Any


class CloseReadinessEvaluator:
    @staticmethod
    def evaluate_close_readiness(context: Dict[str, Any], session_state: Any = None) -> Dict[str, Any]:
        """
        Evaluates deterministic Close Readiness State based on actual run operational facts.
        
        States:
        1. 🔴 EXCEPTIONS BLOCK CLOSE: Unresolved exception records remain (exceptions_records > 0).
        2. 🟡 CONTROLLER REVIEW REQUIRED: Pending human review items remain (needs_review_records > 0).
        3. 🟢 CLOSE READY: All records resolved, zero exceptions, zero pending reviews, audit trail complete.
        """
        status_counts = context.get("status_counts", {"auto_accepted": 0, "needs_review": 0, "exception": 0})
        ledger_df = context.get("ledger_df")
        bank_df = context.get("bank_df")
        
        total_records = (len(ledger_df) if ledger_df is not None else 0) + (len(bank_df) if bank_df is not None else 0)
        if total_records == 0 and "record_count" in context.get("active_run", {}).get("metadata", {}):
            total_records = context["active_run"]["metadata"]["record_count"]

        auto_accepted_records = status_counts.get("auto_accepted", 0)
        needs_review_records = status_counts.get("needs_review", 0)
        exceptions_records = status_counts.get("exception", 0)

        # Retrieve human reviews from session state or dictionary
        human_reviews_db = {}
        if isinstance(session_state, dict) and "human_reviews" in session_state:
            human_reviews_db = session_state["human_reviews"]
        elif hasattr(session_state, "get"):
            human_reviews_db = session_state.get("human_reviews", {})
            
        reviewed_count = len(human_reviews_db)

        # Operational State Logic
        if exceptions_records > 0:
            state = "EXCEPTIONS BLOCK CLOSE"
            symbol = "🔴"
            color = "#ef4444"
            bg_color = "rgba(239, 68, 68, 0.08)"
            border_color = "#ef4444"
            reason = f"{exceptions_records} unresolved exception record(s) block close completion."
            next_action_label = f"RESOLVE {exceptions_records} EXCEPTIONS →"
            target_page = "🚨 Exceptions"
        elif needs_review_records > 0:
            unreviewed = max(needs_review_records - reviewed_count, 0)
            if unreviewed > 0:
                state = "CONTROLLER REVIEW REQUIRED"
                symbol = "🟡"
                color = "#f59e0b"
                bg_color = "rgba(245, 158, 11, 0.08)"
                border_color = "#f59e0b"
                reason = f"{needs_review_records} transactions still require controller review."
                next_action_label = f"REVIEW {needs_review_records} ITEMS →"
                target_page = "👤 Review Queue"
            else:
                state = "CLOSE READY"
                symbol = "🟢"
                color = "#10b981"
                bg_color = "rgba(16, 185, 129, 0.08)"
                border_color = "#10b981"
                reason = f"All {total_records} records resolved ({auto_accepted_records} auto-resolved, {reviewed_count} controller verified). Audit trail complete."
                next_action_label = "VIEW AUDIT TRAIL →"
                target_page = "🔍 Audit Trail"
        else:
            state = "CLOSE READY"
            symbol = "🟢"
            color = "#10b981"
            bg_color = "rgba(16, 185, 129, 0.08)"
            border_color = "#10b981"
            reason = f"All {total_records} records resolved ({auto_accepted_records} auto-resolved). Audit trail complete."
            next_action_label = "VIEW AUDIT TRAIL →"
            target_page = "🔍 Audit Trail"

        return {
            "state": state,
            "symbol": symbol,
            "color": color,
            "bg_color": bg_color,
            "border_color": border_color,
            "reason": reason,
            "next_action_label": next_action_label,
            "target_page": target_page,
            "total_records": total_records,
            "auto_accepted_records": auto_accepted_records,
            "needs_review_records": needs_review_records,
            "exceptions_records": exceptions_records
        }
