import os
import time
import json
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
import hashlib
from candidates import generate_candidates_for_record
from policy import ResolutionPolicyEngine
from journal_validator import JournalEntryValidator
from persistence import compute_candidate_set_hash, compute_gemini_cache_key, GeminiCache

load_dotenv()

def compute_source_hash(src_dict: dict) -> str:
    """Computes a stable SHA-256 hash of a source record's financial properties."""
    raw = f"{src_dict.get('ledger_id') or src_dict.get('bank_id')}_{src_dict.get('amount')}_{src_dict.get('date')}_{src_dict.get('reference_id') or src_dict.get('vendor')}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

# Fixed FX rate for USD/INR conversion (must match generator: 1 USD = 83.50 INR)
FX_RATE_USD_INR = 83.50

# Schema for Gemini Structured Output
class DecisionItem(BaseModel):
    source_record_id: str = Field(..., description="The ID of the unmatched source record (ledger_id or bank_id) being adjudicated")
    candidate_ids: List[str] = Field(..., description="List of ALL candidate IDs supplied to the AI in this query")
    selected_candidate_ids: List[str] = Field(..., description="List of candidate IDs the AI chose to match. Empty if no match.")
    rejected_candidate_ids: List[str] = Field(..., description="List of candidate IDs the AI evaluated but rejected.")
    evidence_features: str = Field(..., description="A short summary of the key evidence used to make this decision (e.g. 'amount matched exactly, date shifted 2 days')")
    decision: str = Field(..., description="Decision: must be 'match', 'no_match', or 'exception'")
    confidence: int = Field(..., description="Confidence score from 0 to 100")
    reason_code: str = Field(..., description="Reason category: 'reference_typo', 'date_shift', 'amount_variance', 'likely_duplicate', 'split_payment', 'no_counterpart_found', or 'ambiguous'")
    rationale: str = Field(..., description="A one-sentence rationale explaining the decision")
    suggested_corrective_entry: Optional[str] = Field(None, description="For amount_variance with delta < ₹4000: a one-line corrective journal entry, e.g. 'Debit Bank Fees ₹450.00, Credit Cash ₹450.00'. Null otherwise.")

class BatchDecision(BaseModel):
    decisions: List[DecisionItem] = Field(..., description="List of reconciliation decisions for each transaction group in the batch")


class ReconciliationPipeline:
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_calls = 0
        self.cached_ai_decisions = 0
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
            print("Warning: GEMINI_API_KEY environment variable not found. Pass 2 (Gemini) will fail if run.")

    def run_reconciliation(self, invoices_path: str, ledger_path: str, bank_path: str, log_path="decisions_log.jsonl", auto_accept_thresh=95, needs_review_thresh=70, materiality_threshold_inr=400000.0, **kwargs):
        """
        Executes Pass 1 (pandas deterministic) and Pass 2 (Gemini batch adjudication)
        to reconcile the transactions across the three datasets.
        """
        if "materiality_threshold" in kwargs:
            materiality_threshold_inr = kwargs["materiality_threshold"]
        
        self.gemini_calls = 0
        self.cached_ai_decisions = 0

        # Load CSVs
        invoices_df = pd.read_csv(invoices_path)
        ledger_df = pd.read_csv(ledger_path)
        bank_df = pd.read_csv(bank_path)

        # Generate stable run_id for batch
        batch_sig = f"{len(ledger_df)}_{len(bank_df)}_{len(invoices_df)}"
        run_id = f"RUN_{hashlib.sha256(batch_sig.encode('utf-8')).hexdigest()[:10].upper()}"

        # Output structure
        predictions = []

        # Ensure all ID fields are strings for consistency
        invoices_df["invoice_id"] = invoices_df["invoice_id"].astype(str)
        ledger_df["ledger_id"] = ledger_df["ledger_id"].astype(str)
        bank_df["bank_id"] = bank_df["bank_id"].astype(str)

        # Ensure currency column exists (backward compat with old CSVs)
        if "currency" not in ledger_df.columns:
            ledger_df["currency"] = "INR"
        if "currency" not in bank_df.columns:
            bank_df["currency"] = "INR"
        if "currency" not in invoices_df.columns:
            invoices_df["currency"] = "INR"

        # Add INR-normalized amount for cross-currency matching (USD converted to INR)
        ledger_df["amount_inr"] = ledger_df.apply(
            lambda r: r["amount"] * FX_RATE_USD_INR if r["currency"] == "USD" else r["amount"], axis=1
        )
        bank_df["amount_inr"] = bank_df.apply(
            lambda r: r["amount"] * FX_RATE_USD_INR if r["currency"] == "USD" else r["amount"], axis=1
        )
        invoices_df["amount_inr"] = invoices_df.apply(
            lambda r: r["amount"] * FX_RATE_USD_INR if r["currency"] == "USD" else r["amount"], axis=1
        )
        
        # Keep amount_usd as alias for candidate compatibility
        ledger_df["amount_usd"] = ledger_df["amount_inr"]
        bank_df["amount_usd"] = bank_df["amount_inr"]
        invoices_df["amount_usd"] = invoices_df["amount_inr"]

        # ---------------------------------------------------------
        # PASS 1: Deterministic Match
        # Exact match on amount, date, reference_id, and currency
        # ---------------------------------------------------------
        join_keys = ["amount", "date", "reference_id"]
        if "currency" in ledger_df.columns and "currency" in bank_df.columns:
            join_keys.append("currency")
        exact_joins = pd.merge(
            ledger_df,
            bank_df,
            on=join_keys,
            suffixes=("_ledger", "_bank")
        )

        matched_ledger_ids = set()
        matched_bank_ids = set()
        matched_invoice_ids = set()

        for _, row in exact_joins.iterrows():
            led_id = str(row["ledger_id"])
            bnk_id = str(row["bank_id"])
            amount = float(row["amount"])
            vendor = str(row["vendor"])
            led_date_str = str(row["date"])
            
            # Find candidate matching invoices
            # Matches vendor name exactly, amount exactly, and due_date >= ledger_date (within 7 days)
            led_date = pd.to_datetime(led_date_str)
            
            # Filter invoice candidates
            inv_candidates = invoices_df[
                (invoices_df["vendor"] == vendor) &
                (invoices_df["amount"] == amount)
            ].copy()
            
            inv_candidates["due_date_dt"] = pd.to_datetime(inv_candidates["due_date"])
            inv_candidates = inv_candidates[
                (inv_candidates["due_date_dt"] >= led_date) &
                (inv_candidates["due_date_dt"] <= led_date + pd.Timedelta(days=7))
            ]

            inv_id = None
            if not inv_candidates.empty:
                # Take the closest invoice by date
                inv_candidates["date_diff"] = (inv_candidates["due_date_dt"] - led_date).abs()
                best_inv = inv_candidates.sort_values(by="date_diff").iloc[0]
                inv_id = str(best_inv["invoice_id"])
                matched_invoice_ids.add(inv_id)

            curr = str(row.get("currency", "INR"))
            policy_eval = ResolutionPolicyEngine.evaluate_policy(
                decision="match",
                decision_confidence=100.0,
                evidence_score=100.0,
                amount=amount,
                materiality_threshold_inr=materiality_threshold_inr,
                reason_code="exact_match",
                currency=curr,
                has_duplicates=False,
                date_variance_days=0,
                amount_variance=0.0,
                is_split=False,
                has_fx_ambiguity=False,
                unresolved_ambiguity=False,
                has_high_risk_flag=False
            )

            src_hash = compute_source_hash({"ledger_id": led_id, "amount": amount, "date": led_date_str, "reference_id": str(row["reference_id"])})
            dec_id = f"DEC_{led_id}"

            predictions.append({
                "run_id": run_id,
                "decision_id": dec_id,
                "source_record_hash": src_hash,
                "invoice_id": inv_id,
                "ledger_id": led_id,
                "bank_ids": [bnk_id],
                "source_record_id": led_id,
                "selected_candidate_ids": [bnk_id] + ([inv_id] if inv_id else []),
                "rejected_candidate_ids": [],
                "match_type": "exact_match",
                "status": policy_eval["routing_status"],
                "ai_confidence": 100,
                "evidence_score": 100.0,
                "decision_confidence": 100.0,
                "confidence": 100,
                "reason_code": "exact_match",
                "rationale": "Exact match on amount, date, and reference_id.",
                "policy_reason": policy_eval["policy_reason"],
                "evidence_features": {
                    "amount_match": "Exact",
                    "date_match": "Exact",
                    "reference_match": "Exact",
                    "currency_match": "Exact",
                    "match_type": "Unique deterministic exact match",
                    "evidence_score": "100%"
                }
            })
            matched_ledger_ids.add(led_id)
            matched_bank_ids.add(bnk_id)

        # Remove Pass 1 matched rows to get unmatched sets
        unmatched_ledger = ledger_df[~ledger_df["ledger_id"].isin(matched_ledger_ids)].copy()
        unmatched_bank = bank_df[~bank_df["bank_id"].isin(matched_bank_ids)].copy()
        unmatched_invoices = invoices_df[~invoices_df["invoice_id"].isin(matched_invoice_ids)].copy()

        # ---------------------------------------------------------
        # PASS 2: Gemini AI Adjudication (Batch)
        # For unmatched items, we construct matching batches
        # ---------------------------------------------------------
        if unmatched_ledger.empty and unmatched_bank.empty:
            return predictions

        # Prepare queries for Pass 2
        # We group unmatched records. For each unmatched ledger record, we find potential bank/invoice candidates.
        queries = []
        for _, led_row in unmatched_ledger.iterrows():
            led_id = str(led_row["ledger_id"])
            vendor = str(led_row["vendor"])
            amount = float(led_row["amount"])
            amount_usd = float(led_row["amount_usd"])
            ref_id = str(led_row["reference_id"])
            led_date = str(led_row["date"])
            led_currency = str(led_row.get("currency", "INR"))

            # Build source record
            src_record = {
                "ledger_id": led_id,
                "date": led_date,
                "amount": amount,
                "currency": led_currency,
                "amount_usd": round(amount_usd, 2),
                "vendor": vendor,
                "reference_id": ref_id
            }

            # Generate bounded candidates deterministically
            bank_candidates = generate_candidates_for_record(src_record, unmatched_bank, "ledger", "bank", top_n=5)
            inv_candidates = generate_candidates_for_record(src_record, unmatched_invoices, "ledger", "invoice", top_n=3)

            queries.append({
                "source_record": src_record,
                "bank_candidates": bank_candidates,
                "invoice_candidates": inv_candidates
            })

        # Also find any unmatched bank statement transactions that weren't captured by unmatched ledgers
        # (e.g. unmatchable bank transactions or bank charges)
        for _, bnk_row in unmatched_bank.iterrows():
            bnk_id = str(bnk_row["bank_id"])
            if any(bnk_id in [b["bank_id"] for b in q.get("bank_candidates", [])] for q in queries):
                continue
            
            # This is an orphaned bank transaction. Find candidates for it.
            amount = float(bnk_row["amount"])
            amount_usd = float(bnk_row["amount_usd"])
            ref_id = str(bnk_row["reference_id"])
            bnk_date = str(bnk_row["date"])
            desc = str(bnk_row["description"])
            bnk_currency = str(bnk_row.get("currency", "INR"))

            src_bnk = {
                "bank_id": bnk_id,
                "date": bnk_date,
                "amount": amount,
                "currency": bnk_currency,
                "amount_usd": round(amount_usd, 2),
                "description": desc,
                "reference_id": ref_id
            }

            led_candidates = generate_candidates_for_record(src_bnk, unmatched_ledger, "bank", "ledger", top_n=5)
            inv_candidates = generate_candidates_for_record(src_bnk, unmatched_invoices, "bank", "invoice", top_n=3)

            queries.append({
                "source_record": src_bnk,
                "ledger_candidates": led_candidates,
                "invoice_candidates": inv_candidates
            })

        # Process queries in batches of 5 to 10
        batch_size = 5
        for i in range(0, len(queries), batch_size):
            batch = queries[i:i+batch_size]
            self._adjudicate_batch_with_gemini(batch, predictions, log_path, auto_accept_thresh, needs_review_thresh, materiality_threshold_inr, run_id)

        return predictions

    def _process_single_decision(self, decision: DecisionItem, query_obj: dict, batch: List[dict], log_path: str, auto_accept_thresh: float, needs_review_thresh: float, materiality_threshold_inr: float, run_id: str, predictions: List[dict], raw_text: str):
        cand_list = query_obj.get("bank_candidates", []) + query_obj.get("ledger_candidates", []) + query_obj.get("invoice_candidates", [])
        
        if decision.decision == "match" and decision.selected_candidate_ids:
            matched_scores = [c.get("_candidate_score", 50) for c in cand_list if (c.get("invoice_id") in decision.selected_candidate_ids or c.get("bank_id") in decision.selected_candidate_ids or c.get("ledger_id") in decision.selected_candidate_ids)]
            max_score = max(matched_scores) if matched_scores else 50
            evidence_score = round(min(100.0, (max_score / 140.0) * 100.0), 1)
        else:
            all_scores = [c.get("_candidate_score", 0) for c in cand_list]
            max_avail = max(all_scores) if all_scores else 0
            evidence_score = round(max(0.0, 100.0 - (max_avail / 140.0 * 100.0)), 1)
            
        ai_conf = float(decision.confidence)
        decision_conf = round(0.6 * evidence_score + 0.4 * ai_conf, 1)

        src_rec = query_obj.get("source_record", {})
        rec_amount = float(src_rec.get("amount", 0.0))
        rec_currency = str(src_rec.get("currency", "INR"))
        
        # Extract safety features from candidate lists and decision
        bank_cands = query_obj.get("bank_candidates", [])
        ledger_cands = query_obj.get("ledger_candidates", [])
        invoice_cands = query_obj.get("invoice_candidates", [])
        has_duplicates = len(bank_cands) > 1 or len(ledger_cands) > 1 or len(invoice_cands) > 1

        date_variance_days = 0
        amount_variance = 0.0
        is_split = (decision.reason_code == "split_payment")
        has_fx_ambiguity = False

        src_date_str = src_rec.get("date")
        src_amt = float(src_rec.get("amount", 0.0))
        src_curr = src_rec.get("currency", "INR")

        selected_cands = []
        for c in cand_list:
            c_id = c.get("invoice_id") or c.get("bank_id") or c.get("ledger_id")
            if c_id in decision.selected_candidate_ids:
                selected_cands.append(c)

        if selected_cands:
            dates = []
            amounts = []
            for sc in selected_cands:
                sc_date_str = sc.get("date") or sc.get("due_date")
                if src_date_str and sc_date_str:
                    try:
                        d1 = pd.to_datetime(src_date_str)
                        d2 = pd.to_datetime(sc_date_str)
                        dates.append(abs((d2 - d1).days))
                    except Exception:
                        pass
                sc_amt = float(sc.get("amount", 0.0))
                amounts.append(sc_amt)
                if sc.get("currency") != src_curr:
                    has_fx_ambiguity = True
            if dates:
                date_variance_days = max(dates)
            if amounts:
                sum_cands = sum(amounts)
                amount_variance = abs(src_amt - sum_cands)

        unresolved_ambiguity = (decision.reason_code == "ambiguous")
        has_high_risk_flag = (decision.decision == "exception" or decision_conf < needs_review_thresh)

        policy_eval = ResolutionPolicyEngine.evaluate_policy(
            decision=decision.decision,
            decision_confidence=decision_conf,
            evidence_score=evidence_score,
            amount=rec_amount,
            materiality_threshold_inr=materiality_threshold_inr,
            reason_code=decision.reason_code,
            currency=rec_currency,
            suggested_corrective_entry=decision.suggested_corrective_entry,
            auto_accept_thresh=auto_accept_thresh,
            needs_review_thresh=needs_review_thresh,
            has_duplicates=has_duplicates,
            date_variance_days=date_variance_days,
            amount_variance=amount_variance,
            is_split=is_split,
            has_fx_ambiguity=has_fx_ambiguity,
            unresolved_ambiguity=unresolved_ambiguity,
            has_high_risk_flag=has_high_risk_flag
        )
        status = policy_eval["routing_status"]
        policy_reason = policy_eval["policy_reason"]

        val_je = None
        if decision.suggested_corrective_entry:
            val_je = JournalEntryValidator.validate_from_suggestion(
                source_decision_id=decision.source_record_id,
                suggestion_text=decision.suggested_corrective_entry,
                amount_delta=rec_amount,
                currency=rec_currency,
                reason_code=decision.reason_code,
                materiality_threshold_inr=materiality_threshold_inr
            )

        src_hash = compute_source_hash(src_rec)
        dec_id = f"DEC_{decision.source_record_id}"

        self._log_decision(batch, decision, raw_text, log_path, status, ai_conf, evidence_score, decision_conf, policy_reason, val_je, run_id, dec_id, src_hash)

        if decision.decision == "match":
            inv_id = None
            led_id = None
            bnk_ids = []
            
            if "INV_" in decision.source_record_id: inv_id = decision.source_record_id
            elif "LED_" in decision.source_record_id: led_id = decision.source_record_id
            elif "BNK_" in decision.source_record_id: bnk_ids.append(decision.source_record_id)
            
            for c_id in decision.selected_candidate_ids:
                if "INV_" in c_id: inv_id = c_id
                elif "LED_" in c_id: led_id = c_id
                elif "BNK_" in c_id: bnk_ids.append(c_id)

            predictions.append({
                "run_id": run_id,
                "decision_id": dec_id,
                "source_record_hash": src_hash,
                "invoice_id": inv_id,
                "ledger_id": led_id,
                "bank_ids": bnk_ids,
                "source_record_id": decision.source_record_id,
                "selected_candidate_ids": decision.selected_candidate_ids,
                "rejected_candidate_ids": decision.rejected_candidate_ids,
                "match_type": f"ai_{decision.reason_code}",
                "status": status,
                "ai_confidence": ai_conf,
                "evidence_score": evidence_score,
                "decision_confidence": decision_conf,
                "confidence": decision_conf,
                "reason_code": decision.reason_code,
                "rationale": decision.rationale,
                "policy_reason": policy_reason,
                "evidence_features": decision.evidence_features,
                "suggested_corrective_entry": decision.suggested_corrective_entry,
                "validated_journal_entry": val_je
            })

    def _adjudicate_batch_with_gemini(self, batch: List[dict], predictions: List[dict], log_path: str, auto_accept_thresh: float = 95.0, needs_review_thresh: float = 70.0, materiality_threshold_inr: float = 400000.0, run_id: str = "RUN_DEFAULT", **kwargs):
        if "materiality_threshold" in kwargs:
            materiality_threshold_inr = kwargs["materiality_threshold"]

        # Check cache for queries in this batch
        uncached_batch = []
        for q in batch:
            src_rec = q["source_record"]
            src_hash = compute_source_hash(src_rec)
            cand_list = q.get("bank_candidates", []) + q.get("ledger_candidates", []) + q.get("invoice_candidates", [])
            cand_hash = compute_candidate_set_hash(cand_list)
            cache_key = compute_gemini_cache_key(src_hash, cand_hash, self.model_name)
            
            cached_dec_dict = GeminiCache.get(cache_key)
            loaded_from_cache = False
            if isinstance(cached_dec_dict, dict) and "source_record_id" in cached_dec_dict:
                try:
                    decision = DecisionItem.model_validate(cached_dec_dict)
                    self.cached_ai_decisions += 1
                    self._process_single_decision(decision, q, [q], log_path, auto_accept_thresh, needs_review_thresh, materiality_threshold_inr, run_id, predictions, json.dumps(cached_dec_dict))
                    loaded_from_cache = True
                except Exception as parse_err:
                    print(f"Warning: Cached decision invalid for key {cache_key}: {parse_err}")

            if not loaded_from_cache:
                uncached_batch.append((q, cache_key))

        if not uncached_batch:
            return

        if not self.client:
            self._handle_batch_fallback([item[0] for item in uncached_batch], predictions, log_path, run_id, "API key unconfigured")
            return

        prompt_queries = [item[0] for item in uncached_batch]
        prompt = f"""
        You are a financial reconciliation assistant. Your job is to adjudicate matches for orphaned source records.
        For each query in the batch below, you are given a `source_record` and a bounded list of top plausible candidates.
        
        CRITICAL RULES:
        - You MUST ONLY select candidates that are explicitly provided in the candidate lists for that query.
        - You MUST evaluate the candidates using the `_evidence_features` provided.
        - In the response, correctly populate `selected_candidate_ids` with the ones you match, and `rejected_candidate_ids` with those you ignore.
        - The `source_record_id` must match the ledger_id or bank_id of the `source_record`.
        
        Note the following matching scenarios:
        1. 'reference_typo': Reference IDs match with small typos, and amounts/vendors align.
        2. 'date_shift': Bank statement cleared 2-5 days after ledger entry date.
        3. 'amount_variance': Small amount discrepancies due to bank fees or rounding. For variances under ₹4000, also suggest a one-line corrective journal entry (e.g. 'Debit Bank Fees ₹450.00, Credit Cash ₹450.00') in the suggested_corrective_entry field.
        4. 'split_payment': One invoice/ledger payment is split into multiple bank transactions (summing to ledger amount). You can select multiple bank_ids.
        5. 'likely_duplicate': A decoy or duplicate record that matches an already reconciled set.
        6. 'no_counterpart_found': Legitimate unmatchable entry.
        
        Adjudicate each query and return a match, no_match, or exception.
        For amount_variance decisions with small deltas (under ₹4000), always populate suggested_corrective_entry with a proper double-entry journal suggestion.
        
        Queries Batch:
        {json.dumps(prompt_queries, indent=2)}
        """

        try:
            response = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=BatchDecision,
                            temperature=0.0
                        ),
                    )
                    break
                except Exception as model_err:
                    err_msg = str(model_err)
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                        sleep_delay = 0.001 if os.getenv("PYTEST_CURRENT_TEST") else (2 ** attempt)
                        time.sleep(sleep_delay)
                        continue
                    if attempt == max_retries - 1:
                        try:
                            print(f"Primary model {self.model_name} failed: {model_err}. Falling back to gemini-2.5-flash.")
                            response = self.client.models.generate_content(
                                model="gemini-2.5-flash",
                                contents=prompt,
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json",
                                    response_schema=BatchDecision,
                                    temperature=0.0
                                ),
                            )
                        except Exception as fb_err:
                            print(f"Secondary model attempt failed: {fb_err}")
                            raise fb_err
            
            if not response or not response.text:
                raise ValueError("Empty response received from Gemini model")

            self.gemini_calls += 1
            result = BatchDecision.model_validate_json(response.text)
            
            for decision in result.decisions:
                pair = next((item for item in uncached_batch if item[0]["source_record"].get("ledger_id") == decision.source_record_id or item[0]["source_record"].get("bank_id") == decision.source_record_id), None)
                if pair:
                    q_obj, c_key = pair
                    GeminiCache.set(c_key, decision.model_dump())
                    self._process_single_decision(decision, q_obj, prompt_queries, log_path, auto_accept_thresh, needs_review_thresh, materiality_threshold_inr, run_id, predictions, response.text)

        except Exception as e:
            print(f"Error adjudicating batch with Gemini: {e}")
            self._handle_batch_fallback([item[0] for item in uncached_batch], predictions, log_path, run_id, str(e))

    def _handle_batch_fallback(self, batch: List[dict], predictions: List[dict], log_path: str, run_id: str, reason_detail: str):
        """Routes records to exception without fabricating AI decisions when API is unavailable or fails."""
        for item in batch:
            src = item.get("source_record", {})
            src_id = src.get("ledger_id") or src.get("bank_id") or "UNKNOWN"
            src_hash = compute_source_hash(src)
            dec_id = f"DEC_{src_id}"
            
            # Record explicit fallback decision object
            fb_decision = DecisionItem(
                source_record_id=src_id,
                candidate_ids=[],
                selected_candidate_ids=[],
                rejected_candidate_ids=[],
                decision="no_match",
                confidence=0,
                reason_code="api_unavailable_fallback",
                rationale=f"Gemini API unavailable or call failed ({reason_detail}). Record safely routed to exception queue for manual human review.",
                evidence_features=f"API call failed: {reason_detail}"
            )
            
            self._log_decision(
                input_batch=[item],
                decision=fb_decision,
                raw_output=f"{{\"error\": \"{reason_detail}\"}}",
                log_path=log_path,
                status="exception",
                ai_conf=0.0,
                evidence_score=0.0,
                decision_conf=0.0,
                policy_reason="Gemini API unconfigured or call failed; record routed to exception queue for human auditor review",
                validated_journal_entry=None,
                run_id=run_id,
                decision_id=dec_id,
                source_record_hash=src_hash
            )

            inv_id = None
            led_id = src_id if "LED_" in src_id else None
            bnk_ids = [src_id] if "BNK_" in src_id else []

            predictions.append({
                "run_id": run_id,
                "decision_id": dec_id,
                "source_record_hash": src_hash,
                "invoice_id": inv_id,
                "ledger_id": led_id,
                "bank_ids": bnk_ids,
                "source_record_id": src_id,
                "selected_candidate_ids": [],
                "rejected_candidate_ids": [],
                "match_type": "fallback_no_match",
                "status": "exception",
                "ai_confidence": 0.0,
                "evidence_score": 0.0,
                "decision_confidence": 0.0,
                "confidence": 0.0,
                "reason_code": "api_unavailable_fallback",
                "rationale": f"Gemini API unavailable or call failed ({reason_detail}). Record safely routed to exception queue for manual human review.",
                "evidence_features": f"API call failed: {reason_detail}",
                "policy_reason": "Gemini API unconfigured or call failed; record routed to exception queue for human auditor review",
                "validated_journal_entry": None
            })

    def _log_decision(
        self,
        input_batch: List[dict],
        decision: DecisionItem,
        raw_output: str,
        log_path: str,
        status: str,
        ai_conf: float,
        evidence_score: float,
        decision_conf: float,
        policy_reason: str,
        validated_journal_entry: dict = None,
        run_id: str = "RUN_DEFAULT",
        decision_id: str = None,
        source_record_hash: str = None
    ):
        decision_dict = decision.model_dump()
        decision_dict["run_id"] = run_id
        decision_dict["decision_id"] = decision_id or f"DEC_{decision.source_record_id}"
        decision_dict["source_record_hash"] = source_record_hash
        decision_dict["status"] = status
        decision_dict["ai_confidence"] = ai_conf
        decision_dict["evidence_score"] = evidence_score
        decision_dict["decision_confidence"] = decision_conf
        decision_dict["policy_reason"] = policy_reason
        decision_dict["validated_journal_entry"] = validated_journal_entry

        new_entry = {
            "timestamp": pd.Timestamp.now().isoformat(),
            "input_batch_summary": [
                {
                    "source_record_id": q.get("source_record", {}).get("ledger_id") or q.get("source_record", {}).get("bank_id"),
                    "type": "ledger" if "ledger_id" in q.get("source_record", {}) else "bank"
                } for q in input_batch
            ],
            "decision": decision_dict,
            "raw_api_output": raw_output
        }

        # Idempotent logging: Read existing log and update decision by decision_id if present
        existing_log_entries = []
        if os.path.exists(log_path):
            try:
                with open(log_path, "r") as f:
                    for line in f:
                        if line.strip():
                            existing_log_entries.append(json.loads(line))
            except Exception:
                existing_log_entries = []

        # Find if decision_id already logged
        found_idx = -1
        target_dec_id = decision_dict["decision_id"]
        for idx, entry in enumerate(existing_log_entries):
            if entry.get("decision", {}).get("decision_id") == target_dec_id:
                found_idx = idx
                break

        if found_idx >= 0:
            existing_log_entries[found_idx] = new_entry
        else:
            existing_log_entries.append(new_entry)

        # Rewrite log file cleanly
        with open(log_path, "w") as f:
            for entry in existing_log_entries:
                f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    pipeline = ReconciliationPipeline()
    print("Pipeline loaded.")
