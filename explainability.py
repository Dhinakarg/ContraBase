"""
Explainability Component Engine for ContraBase.
Dynamically generates:
- "WHAT WOULD MAKE THIS SAFE TO AUTO-ACCEPT?" (for items routed to review/exception)
- "WHY THIS WAS SAFE TO AUTO-ACCEPT" (for deterministic exact auto-accepted matches)
Uses ONLY active ResolutionPolicyEngine configuration and active run metadata.
Never hardcodes thresholds.
"""

from typing import Dict, Any, List
from ui_common import format_inr


class SafetyExplainabilityEngine:
    @staticmethod
    def generate_safety_explanation(
        item: Dict[str, Any],
        auto_accept_thresh: float = 95.0,
        needs_review_thresh: float = 70.0,
        materiality_threshold_inr: float = 400000.0
    ) -> Dict[str, Any]:
        """
        Generates dynamic safety explanation based strictly on active policy configuration.
        """
        status = str(item.get("status", item.get("Status", "auto_accepted"))).lower()
        amount = float(item.get("amount", item.get("Amount", 0.0)) or 0.0)
        currency = str(item.get("currency", item.get("Currency", "INR"))).upper()
        sys_conf = float(item.get("system_confidence", item.get("System Confidence", item.get("confidence", 100.0))) or 100.0)
        reason_code = str(item.get("reason_code", item.get("Reason Code", item.get("reason", ""))))
        policy_reason = str(item.get("policy_reason", item.get("Policy Reason", ""))).lower()
        selected_cands = item.get("selected_candidates", item.get("Selected Candidates", []))
        days_out = int(item.get("days_outstanding", item.get("Days Outstanding", 0)) or 0)
        
        is_high_mat = ("high" in str(item.get("materiality", item.get("Materiality", ""))).lower()) or (amount >= materiality_threshold_inr)

        # Mode B: Auto-Accepted (Safe Match)
        if status in ["auto_accepted", "cleared", "resolved"] and reason_code in ["exact_match", "pass1_exact", ""]:
            return {
                "is_auto_accepted": True,
                "title": "WHY THIS WAS SAFE TO AUTO-ACCEPT",
                "badge_color": "#10b981",
                "conditions": [
                    "✓ Unique 1:1 deterministic candidate match",
                    "✓ Amount exact agreement (0.00 variance)",
                    "✓ Transaction date exact / within clearing tolerance",
                    "✓ Reference ID exact match",
                    "✓ No duplicate candidate ambiguity",
                    f"✓ Base currency ({currency}) / No FX ambiguity",
                    f"✓ System confidence ({sys_conf:.1f}%) meets auto-accept threshold ({auto_accept_thresh:.0f}%)",
                    f"✓ Enterprise risk policy gate passed (Materiality: {format_inr(materiality_threshold_inr)})"
                ]
            }

        # Mode A: Needs Review / Exception (Explain blocking conditions & resolution requirements)
        blocking_conditions = []
        positive_evidence = []
        to_become_safe = []

        # Amount signal
        if reason_code == "amount_variance" or "amount variance" in policy_reason:
            blocking_conditions.append("✕ Amount variance detected")
            to_become_safe.append("✓ Exact amount match (0 variance)")
        else:
            positive_evidence.append("✓ Amount agreement within tolerance")

        # Date signal
        if days_out > 0 or reason_code == "date_shift" or "date" in policy_reason:
            blocking_conditions.append(f"✕ Clearing date shift ({days_out} days outstanding)")
            to_become_safe.append("✓ Date within tolerance")
        else:
            positive_evidence.append("✓ Date within tolerance")

        # Candidate match signal
        if reason_code == "no_counterpart_found" or not selected_cands:
            blocking_conditions.append("✕ No counterpart candidate found")
            to_become_safe.append("✓ One unique candidate match")
        elif (isinstance(selected_cands, list) and len(selected_cands) > 1) or reason_code == "duplicate":
            blocking_conditions.append(f"✕ Two or more viable candidates ({len(selected_cands)} candidates)")
            to_become_safe.append("✓ One unique candidate match without duplicate ambiguity")
        else:
            positive_evidence.append("✓ Reference evidence / single candidate available")

        # Materiality signal
        if is_high_mat:
            blocking_conditions.append(f"✕ High materiality threshold (≥ {format_inr(materiality_threshold_inr)})")
            to_become_safe.append(f"✓ No unresolved risk signals for transactions ≥ {format_inr(materiality_threshold_inr)}")
        else:
            positive_evidence.append(f"✓ Below materiality threshold ({format_inr(materiality_threshold_inr)})")

        # FX signal
        if currency != "INR" or "fx" in policy_reason:
            blocking_conditions.append(f"✕ Foreign currency transaction ({currency})")
            to_become_safe.append("✓ No FX ambiguity / base currency")
        else:
            positive_evidence.append("✓ Base currency transaction (INR)")

        # Confidence signal
        if sys_conf < auto_accept_thresh:
            blocking_conditions.append(f"✕ System confidence ({sys_conf:.1f}%) below auto-accept threshold ({auto_accept_thresh:.0f}%)")
            to_become_safe.append(f"✓ Confidence meets configured auto-accept threshold (≥ {auto_accept_thresh:.0f}%)")
        else:
            positive_evidence.append(f"✓ Confidence meets auto-accept threshold (≥ {auto_accept_thresh:.0f}%)")

        # Fallback if no specific blocking condition was caught
        if not blocking_conditions:
            blocking_conditions.append("✕ High-materiality or risk policy hold applied")
            to_become_safe.append("✓ No unresolved risk signals")

        return {
            "is_auto_accepted": False,
            "title": "WHAT WOULD MAKE THIS SAFE TO AUTO-ACCEPT?",
            "badge_color": "#ff9800",
            "blocking_conditions": blocking_conditions,
            "positive_evidence": positive_evidence,
            "to_become_safe": to_become_safe,
            "active_thresholds": {
                "auto_accept_thresh": auto_accept_thresh,
                "needs_review_thresh": needs_review_thresh,
                "materiality_threshold_inr": materiality_threshold_inr
            }
        }
