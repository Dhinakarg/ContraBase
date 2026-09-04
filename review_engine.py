import os
import json
from datetime import datetime

class HumanReviewEngine:
    @staticmethod
    def process_human_review(record_id: str, action: str, original_ai_decision: str, reviewer_id: str = "Auditor_1") -> dict:
        """
        Processes a human reviewer action (Approve, Reject, Escalate).
        Determines override status without mutating the original AI decision.
        """
        action = action.title()
        if action not in ["Approve", "Reject", "Escalate"]:
            raise ValueError(f"Invalid human action: {action}. Must be Approve, Reject, or Escalate.")

        # Determine final decision & override status
        if action == "Approve":
            human_decision = "approved"
            final_decision = original_ai_decision if original_ai_decision else "match"
            human_override = False
        elif action == "Reject":
            human_decision = "rejected"
            final_decision = "no_match" if original_ai_decision == "match" else "exception"
            human_override = True
        else: # Escalate
            human_decision = "escalated"
            final_decision = "exception_escalated"
            human_override = True

        return {
            "record_id": record_id,
            "reviewer_id": reviewer_id,
            "original_ai_decision": original_ai_decision or "match",
            "final_decision": final_decision,
            "human_reviewed": True,
            "human_decision": human_decision,
            "human_reviewer_action": action,
            "human_override": human_override,
            "review_timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def save_human_reviews(reviews: dict, file_path: str = "data/human_reviews.json"):
        """
        Persists human reviews dictionary to disk.
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(reviews, f, indent=4)

    @staticmethod
    def load_human_reviews(file_path: str = "data/human_reviews.json") -> dict:
        """
        Loads persisted human reviews from disk.
        """
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    @staticmethod
    def calculate_override_rate(reviews: dict) -> float:
        """
        Computes Human Override Rate: (human_overrides / total_human_reviewed) * 100.
        """
        if not reviews:
            return 0.0
        total_reviewed = len(reviews)
        overrides = sum(1 for r in reviews.values() if r.get("human_override", False))
        return round((overrides / total_reviewed) * 100.0, 1) if total_reviewed > 0 else 0.0
