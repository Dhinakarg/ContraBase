import math
import re
import uuid
from datetime import datetime
from typing import List, Dict, Optional

# Approved Corporate Chart of Accounts (COA)
ALLOWED_ACCOUNTS = {
    "Cash",
    "Bank Fees",
    "Rounding Variance",
    "Accounts Receivable",
    "Accounts Payable",
    "FX Gain/Loss",
    "Unallocated Suspense",
    "Bank Fees/Rounding"
}

SUPPORTED_REASON_CODES = {
    "amount_variance",
    "reference_typo",
    "date_shift",
    "exact_match"
}

ALLOWED_CURRENCIES = {"INR", "USD"}

class JournalEntryValidator:
    @staticmethod
    def parse_entry_text(entry_text: str) -> dict:
        """
        Parses text like 'Debit Bank Fees ₹450.00, Credit Cash ₹450.00' into structured debit/credit fields.
        """
        if not entry_text or not isinstance(entry_text, str):
            return {}

        # Regex for 'Debit <Account> ₹/<Amount>, Credit <Account> ₹/<Amount>'
        pattern = r"Debit\s+(?P<dr_acc>.+?)\s+[\$₹]?(?P<dr_amt>[\d\.,]+),\s*Credit\s+(?P<cr_acc>.+?)\s+[\$₹]?(?P<cr_amt>[\d\.,]+)"
        match = re.search(pattern, entry_text, re.IGNORECASE)
        
        if match:
            try:
                dr_acc = match.group("dr_acc").strip()
                cr_acc = match.group("cr_acc").strip()
                dr_amt = float(match.group("dr_amt").replace(",", ""))
                cr_amt = float(match.group("cr_amt").replace(",", ""))
                return {
                    "debit_account": dr_acc,
                    "credit_account": cr_acc,
                    "debit_amount": dr_amt,
                    "credit_amount": cr_amt,
                    "amount": dr_amt
                }
            except Exception:
                pass

        return {}

    @classmethod
    def validate_entry(
        cls,
        source_decision_id: str,
        debit_account: str,
        credit_account: str,
        debit_amount: float,
        credit_amount: float,
        currency: str = "INR",
        reason_code: str = "amount_variance",
        materiality_threshold_inr: float = 400000.0,
        journal_auto_post_variance_cap_inr: float = 4000.0,
        existing_signatures: Optional[set] = None,
        **kwargs
    ) -> dict:
        """
        Deterministically validates a proposed journal entry against compliance, COA, balance, and materiality rules (Gate B).
        
        Gate B enforces that corrective journal entries are safe to auto-post ONLY if:
        1. Corrective variance amount is below journal_auto_post_variance_cap_inr (₹4,000.00).
        2. Source transaction amount is below materiality_threshold_inr (₹4,00,000.00).
        3. All accounting double-entry (Debits = Credits) and approved COA rules pass.
        """
        if "materiality_threshold" in kwargs:
            materiality_threshold_inr = kwargs["materiality_threshold"]

        errors = []
        existing_signatures = existing_signatures or set()
        
        # 1. Total debits equal total credits
        try:
            dr_val = float(debit_amount)
            cr_val = float(credit_amount)
            if math.isnan(dr_val) or math.isinf(dr_val) or math.isnan(cr_val) or math.isinf(cr_val):
                errors.append("Amounts must be finite numbers")
            elif abs(dr_val - cr_val) > 0.001:
                errors.append(f"Unbalanced entry: Debits (₹{dr_val:.2f}) != Credits (₹{cr_val:.2f})")
            elif dr_val <= 0 or cr_val <= 0:
                errors.append("Amounts must be strictly positive (> ₹0.00)")
        except (ValueError, TypeError):
            errors.append("Invalid numerical amount specified")
            dr_val, cr_val = 0.0, 0.0

        amount = dr_val

        # 2. Valid Accounts in COA
        if debit_account not in ALLOWED_ACCOUNTS:
            errors.append(f"Unsupported AI-generated debit account: '{debit_account}'")
        if credit_account not in ALLOWED_ACCOUNTS:
            errors.append(f"Unsupported AI-generated credit account: '{credit_account}'")

        # 3. Currency consistency
        if currency not in ALLOWED_CURRENCIES:
            errors.append(f"Invalid currency '{currency}'. Must be one of {ALLOWED_CURRENCIES}")

        # 4. Source-record evidence presence
        if not source_decision_id or str(source_decision_id).strip() == "":
            errors.append("Missing source-record evidence ID")

        # 5. Reason code support
        if reason_code not in SUPPORTED_REASON_CODES:
            errors.append(f"Reason code '{reason_code}' does not support corrective journal entries")

        # 6. Duplicate prevention check
        sig = (source_decision_id, debit_account, credit_account, round(amount, 2), currency)
        if sig in existing_signatures:
            errors.append("Duplicate journal entry detected for source record")

        # 7. Materiality Policy & Auto-Post Rule (Gate B)
        # Entries >= journal_auto_post_variance_cap_inr or >= materiality_threshold_inr cannot be auto-posted
        auto_post_eligible = True
        if amount >= journal_auto_post_variance_cap_inr or amount >= materiality_threshold_inr:
            auto_post_eligible = False
            if amount >= materiality_threshold_inr:
                errors.append(f"High-materiality adjustment (₹{amount:.2f} >= ₹{materiality_threshold_inr:.2f}) requires human sign-off")

        validation_status = "valid" if len(errors) == 0 else "invalid"
        if validation_status == "invalid":
            auto_post_eligible = False

        # Generate deterministic entry ID
        entry_id = f"JE_{source_decision_id}_{abs(hash(sig)) % 10000:04d}"

        return {
            "journal_entry_id": entry_id,
            "source_decision_id": source_decision_id,
            "debit_account": debit_account,
            "credit_account": credit_account,
            "amount": round(amount, 2),
            "currency": currency,
            "reason_code": reason_code,
            "validation_status": validation_status,
            "validation_errors": errors,
            "auto_post": auto_post_eligible,
            "created_at": datetime.now().isoformat()
        }

    @classmethod
    def validate_from_suggestion(
        cls,
        source_decision_id: str,
        suggestion_text: str,
        amount_delta: float,
        currency: str = "INR",
        reason_code: str = "amount_variance",
        materiality_threshold_inr: float = 400000.0,
        journal_auto_post_variance_cap_inr: float = 4000.0,
        existing_signatures: Optional[set] = None,
        **kwargs
    ) -> dict:
        """
        Parses an AI-suggested text string and validates it against system safety rules.
        """
        if "materiality_threshold" in kwargs:
            materiality_threshold_inr = kwargs["materiality_threshold"]

        parsed = cls.parse_entry_text(suggestion_text)
        if not parsed:
            # Could not parse AI text properly
            return {
                "journal_entry_id": f"JE_{source_decision_id}_ERR",
                "source_decision_id": source_decision_id,
                "debit_account": "Unknown",
                "credit_account": "Unknown",
                "amount": round(float(amount_delta or 0.0), 2),
                "currency": currency,
                "reason_code": reason_code,
                "validation_status": "invalid",
                "validation_errors": [f"Could not parse AI suggestion text: '{suggestion_text}'"],
                "auto_post": False,
                "created_at": datetime.now().isoformat()
            }

        return cls.validate_entry(
            source_decision_id=source_decision_id,
            debit_account=parsed["debit_account"],
            credit_account=parsed["credit_account"],
            debit_amount=parsed["debit_amount"],
            credit_amount=parsed["credit_amount"],
            currency=currency,
            reason_code=reason_code,
            materiality_threshold_inr=materiality_threshold_inr,
            journal_auto_post_variance_cap_inr=journal_auto_post_variance_cap_inr,
            existing_signatures=existing_signatures
        )
