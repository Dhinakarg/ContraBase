class ResolutionPolicyEngine:
    @staticmethod
    def evaluate_policy(
        decision: str,
        decision_confidence: float,
        evidence_score: float,
        amount: float,
        materiality_threshold_inr: float = 400000.0,
        reason_code: str = "exact_match",
        currency: str = "INR",
        suggested_corrective_entry: str = None,
        auto_accept_thresh: float = 95.0,
        needs_review_thresh: float = 70.0,
        **kwargs
    ) -> dict:
        """
        Evaluates conservative enterprise resolution policy to govern transaction routing (Gate A).
        Prevents automatic resolution of high-risk / high-materiality financial actions.
        
        Foreign-currency transactions are evaluated for materiality using their INR-normalized exposure
        while preserving the original transaction currency.
        """
        # Handle backward compatibility if positional/kwarg used old name
        if "materiality_threshold" in kwargs:
            materiality_threshold_inr = kwargs["materiality_threshold"]

        amount = float(amount or 0.0)
        is_high_materiality = amount >= materiality_threshold_inr

        # Core Rule 1: Unsupported or Contradictory Evidence
        if evidence_score < 40.0:
            return {
                "routing_status": "exception",
                "policy_reason": f"Unsupported or contradictory evidence score ({evidence_score:.1f} < 40.0)",
                "is_high_risk": True,
                "is_reversible": True,
                "materiality": "⚠️ High" if is_high_materiality else "Normal"
            }

        # Core Rule 2: Low Confidence Routing
        if decision_confidence < needs_review_thresh:
            return {
                "routing_status": "exception",
                "policy_reason": f"Low decision confidence ({decision_confidence:.1f}% < {needs_review_thresh}%)",
                "is_high_risk": True,
                "is_reversible": True,
                "materiality": "⚠️ High" if is_high_materiality else "Normal"
            }

        # Risk-aware policy checks for High-Materiality transactions
        if is_high_materiality:
            # Extract safety flags from keyword arguments
            has_duplicates = kwargs.get("has_duplicates", False)
            date_variance_days = kwargs.get("date_variance_days", 0)
            amount_variance = kwargs.get("amount_variance", 0.0)
            is_split = kwargs.get("is_split", False) or (reason_code == "split_payment")
            has_fx_ambiguity = kwargs.get("has_fx_ambiguity", False) or (currency != "INR")
            unresolved_ambiguity = kwargs.get("unresolved_ambiguity", False) or (reason_code == "ambiguous")
            has_high_risk_flag = kwargs.get("has_high_risk_flag", False)

            # Evaluate each safety constraint sequentially for precise policy reasons
            if decision_confidence < auto_accept_thresh:
                return {
                    "routing_status": "needs_review",
                    "policy_reason": f"High-materiality transaction routed to human review because decision confidence ({decision_confidence:.1f}%) is below the auto-accept threshold ({auto_accept_thresh}%).",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }
            if evidence_score < 95.0:
                return {
                    "routing_status": "needs_review",
                    "policy_reason": f"High-materiality transaction routed to human review because evidence score ({evidence_score:.1f}%) is below the exceptionally strong requirement (95.0%).",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }
            if has_duplicates:
                return {
                    "routing_status": "needs_review",
                    "policy_reason": "High-materiality transaction routed to human review because multiple plausible candidates remain despite high AI confidence.",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }
            if amount_variance >= 0.01:
                return {
                    "routing_status": "needs_review",
                    "policy_reason": f"High-materiality transaction routed to human review because material amount variance (₹{amount_variance:.2f}) remains unresolved.",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }
            if date_variance_days > 0:
                return {
                    "routing_status": "needs_review",
                    "policy_reason": f"High-materiality transaction routed to human review because transaction has a date variance of {date_variance_days} day(s).",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }
            if is_split:
                return {
                    "routing_status": "needs_review",
                    "policy_reason": "High-materiality transaction routed to human review because complex split-payment risk exists.",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }
            if has_fx_ambiguity:
                return {
                    "routing_status": "needs_review",
                    "policy_reason": f"High-materiality transaction routed to human review because FX/currency ambiguity exists (currency: {currency}).",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }
            if unresolved_ambiguity:
                return {
                    "routing_status": "needs_review",
                    "policy_reason": "High-materiality transaction routed to human review because unresolved candidate ambiguity exists.",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }
            if has_high_risk_flag:
                return {
                    "routing_status": "needs_review",
                    "policy_reason": "High-materiality transaction routed to human review because the reconciliation has other high-risk conditions.",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }
            if reason_code == "reference_typo":
                return {
                    "routing_status": "needs_review",
                    "policy_reason": "High-materiality transaction routed to human review because reference ID mismatch exists.",
                    "is_high_risk": True,
                    "is_reversible": True,
                    "materiality": "⚠️ High"
                }

            # If all safety conditions are met, it is eligible for auto-acceptance
            return {
                "routing_status": "auto_accepted",
                "policy_reason": "High-materiality transaction permitted for automatic reconciliation because the match is a unique deterministic exact match with exact amount, date, reference, and currency agreement and no unresolved risk signals.",
                "is_high_risk": False,
                "is_reversible": True,
                "materiality": "⚠️ High"
            }

        # Rule 3: Medium Confidence Routing (Low-Materiality)
        if decision_confidence < auto_accept_thresh:
            return {
                "routing_status": "needs_review",
                "policy_reason": f"Medium decision confidence ({decision_confidence:.1f}%) requires human verification",
                "is_high_risk": False,
                "is_reversible": True,
                "materiality": "Normal"
            }

        # Rule 5: Complex / Multi-Currency / Split-Payment Safety Cap (Low-Materiality)
        if (reason_code == "split_payment" or currency == "USD") and amount >= (materiality_threshold_inr / 2.0):
            return {
                "routing_status": "needs_review",
                "policy_reason": f"Complex {reason_code}/FX transaction above exposure threshold requires review",
                "is_high_risk": False,
                "is_reversible": True,
                "materiality": "Normal"
            }

        # Rule 6: High Confidence + Low Materiality + Supported Evidence -> Auto Resolve (Low-Materiality)
        return {
            "routing_status": "auto_accepted",
            "policy_reason": "High confidence, low materiality, and verified evidence auto-approved",
            "is_high_risk": False,
            "is_reversible": True,
            "materiality": "Normal"
        }
