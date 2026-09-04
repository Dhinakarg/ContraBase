"""
Deterministic Risk Prioritization Layer for Controller Review Queue.
Evaluates risk signals dynamically from transaction records and policy metadata
to generate an explainable, deterministic priority score, rank, and priority band.
"""

import json
from typing import Dict, Any, List


class RiskPrioritizer:
    @staticmethod
    def evaluate_priority(item: Dict[str, Any], materiality_threshold_inr: float = 400000.0) -> Dict[str, Any]:
        """
        Calculates a deterministic risk priority score (0-100) and priority band for a review item.
        
        Risk signals evaluated:
        1. Materiality: High materiality (>= threshold) adds +35 points.
        2. Amount Variance: Unresolved material variance adds +25 points.
        3. Duplicate Candidate / Candidate Ambiguity: Multiple candidates or ambiguous match adds +20 points.
        4. Date Variance: Date shift > 0 days adds +15 points.
        5. FX / Multi-Currency Ambiguity: Foreign currency adds +15 points.
        6. Split Payment: Many-to-one payment structure adds +15 points.
        7. Low Confidence: System confidence < 95% adds proportional risk points.
        8. Unresolved Ambiguity / Missing Match: No counterpart found adds +10 points.
        
        Score is capped at 100.
        Priority Bands:
        - 🔴 HIGH PRIORITY: Score >= 65 or (High Materiality + at least 1 other risk signal)
        - 🟠 MEDIUM PRIORITY: Score >= 35
        - 🟢 LOWER PRIORITY: Score < 35
        """
        amount = float(item.get("Amount", item.get("amount", 0.0)) or 0.0)
        currency = str(item.get("Currency", item.get("currency", "INR"))).upper()
        mat_str = str(item.get("Materiality", item.get("materiality", "")))
        is_high_mat = ("High" in mat_str) or (amount >= materiality_threshold_inr)
        
        reason_code = str(item.get("Reason Code", item.get("reason_code", item.get("reason", ""))))
        policy_reason = str(item.get("Policy Reason", item.get("policy_reason", ""))).lower()
        
        evidence_features = item.get("Evidence Features", item.get("evidence_features", ""))
        if isinstance(evidence_features, dict):
            evidence_features_str = json.dumps(evidence_features).lower()
        else:
            evidence_features_str = str(evidence_features).lower()
            
        sys_conf = float(item.get("System Confidence", item.get("system_confidence", item.get("confidence", 100.0))) or 100.0)

        # Detect Risk Signals
        risk_signals = []
        score = 0.0

        # Signal 1: Materiality
        if is_high_mat:
            score += 35.0
            risk_signals.append("high materiality threshold")

        # Signal 2: Amount Variance
        has_amount_var = (reason_code == "amount_variance") or ("amount variance" in policy_reason) or ("amount_diff" in evidence_features_str)
        if has_amount_var:
            score += 25.0
            risk_signals.append("amount variance")

        # Signal 3: Candidate Ambiguity / Duplicate Risk
        sel_cands = item.get("Selected Candidates", item.get("selected_candidates", []))
        has_dup = (reason_code == "duplicate") or ("duplicate" in policy_reason) or ("multiple plausible" in policy_reason) or (isinstance(sel_cands, list) and len(sel_cands) > 1)
        if has_dup:
            score += 20.0
            risk_signals.append("duplicate candidate risk")

        # Signal 4: Date Variance
        days_out = int(item.get("Days Outstanding", item.get("days_outstanding", 0)) or 0)
        has_date_shift = (reason_code == "date_shift") or ("date" in policy_reason) or (days_out > 0)
        if has_date_shift:
            score += 15.0
            risk_signals.append("clearing date shift")

        # Signal 5: FX Ambiguity
        has_fx = (currency != "INR") or ("fx" in policy_reason) or ("currency" in policy_reason)
        if has_fx:
            score += 15.0
            risk_signals.append(f"FX ambiguity ({currency})")

        # Signal 6: Split Payment
        has_split = (reason_code == "split_payment") or ("split" in policy_reason)
        if has_split:
            score += 15.0
            risk_signals.append("split payment structure")

        # Signal 7: Low System Confidence
        if sys_conf < 95.0:
            score += max(5.0, (95.0 - sys_conf) * 0.5)
            risk_signals.append(f"low confidence ({sys_conf:.0f}%)")

        # Signal 8: Unresolved Ambiguity / Missing Match
        has_ambig = (reason_code in ["ambiguous", "no_counterpart_found"]) or ("ambiguity" in policy_reason) or ("missing" in policy_reason)
        if has_ambig:
            score += 10.0
            risk_signals.append("unresolved candidate ambiguity")

        score = min(100.0, score)

        # Priority Band Determination
        if score >= 65.0 or (is_high_mat and len(risk_signals) >= 2):
            priority_band = "HIGH PRIORITY"
            band_color = "#ef4444"
            band_symbol = "🔴"
        elif score >= 35.0:
            priority_band = "MEDIUM PRIORITY"
            band_color = "#f59e0b"
            band_symbol = "🟠"
        else:
            priority_band = "LOWER PRIORITY"
            band_color = "#10b981"
            band_symbol = "🟢"

        # Generate Compact Explanation
        if not risk_signals:
            explanation = "Standard human policy review required."
        elif len(risk_signals) == 1:
            explanation = f"Prioritized because this transaction has {risk_signals[0]}."
        elif len(risk_signals) == 2:
            explanation = f"Prioritized because this transaction combines {risk_signals[0]} with {risk_signals[1]}."
        else:
            joined_signals = ", ".join(risk_signals[:-1]) + f" and {risk_signals[-1]}"
            explanation = f"Prioritized because this transaction combines {joined_signals}."

        drivers_short = " + ".join([s.replace("threshold", "").strip() for s in risk_signals[:3]])

        return {
            "score": round(score, 1),
            "priority_band": priority_band,
            "band_color": band_color,
            "band_symbol": band_symbol,
            "risk_signals": risk_signals,
            "drivers_short": drivers_short,
            "explanation": explanation
        }

    @staticmethod
    def sort_items(items: List[Dict[str, Any]], sort_key: str = "Highest Risk", materiality_threshold_inr: float = 400000.0) -> List[Dict[str, Any]]:
        """
        Sorts items deterministically.
        Default: Highest Risk (priority score descending, then amount descending, then ID).
        """
        decorated = []
        for idx, item in enumerate(items):
            p_info = RiskPrioritizer.evaluate_priority(item, materiality_threshold_inr)
            item_copy = dict(item)
            item_copy["_priority"] = p_info
            decorated.append(item_copy)

        if sort_key in ["Highest Risk", "Risk"]:
            sorted_items = sorted(
                decorated,
                key=lambda x: (
                    -x["_priority"]["score"],
                    -float(x.get("Amount", x.get("amount", 0.0)) or 0.0),
                    str(x.get("ID", x.get("id", "")))
                )
            )
        elif sort_key in ["Highest Value", "Amount"]:
            sorted_items = sorted(
                decorated,
                key=lambda x: (
                    -float(x.get("Amount", x.get("amount", 0.0)) or 0.0),
                    -x["_priority"]["score"],
                    str(x.get("ID", x.get("id", "")))
                )
            )
        elif sort_key in ["Oldest", "Date"]:
            sorted_items = sorted(
                decorated,
                key=lambda x: (
                    -int(x.get("Days Outstanding", x.get("days_outstanding", 0)) or 0),
                    -x["_priority"]["score"],
                    str(x.get("ID", x.get("id", "")))
                )
            )
        elif sort_key in ["Lowest Confidence", "Confidence"]:
            sorted_items = sorted(
                decorated,
                key=lambda x: (
                    float(x.get("System Confidence", x.get("system_confidence", x.get("confidence", 100.0))) or 100.0),
                    -x["_priority"]["score"],
                    str(x.get("ID", x.get("id", "")))
                )
            )
        else:
            sorted_items = decorated

        # Attach rank #1, #2, #3...
        for rank_idx, item in enumerate(sorted_items, start=1):
            item["_priority"]["rank"] = rank_idx

        return sorted_items
