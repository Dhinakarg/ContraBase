import pytest
import pandas as pd
from candidates import generate_candidates_for_record, calculate_similarity_score

def test_exact_candidate():
    src = {"amount": 100, "date": "2023-01-01", "vendor": "Acme", "reference_id": "REF123", "currency": "USD"}
    cand = {"amount": 100, "date": "2023-01-01", "vendor": "Acme", "reference_id": "REF123", "currency": "USD"}
    score, ev = calculate_similarity_score(src, cand)
    assert score >= 140 # 40 (amt) + 30 (date) + 30 (ven) + 30 (ref) + 10 (curr)
    assert "Exact amount match" in ev
    assert "Exact date match" in ev
    assert "Vendor name overlap" in ev
    assert "Exact reference match" in ev

def test_typo():
    src = {"amount": 100, "date": "2023-01-01", "vendor": "Acme", "reference_id": "REF123", "currency": "USD"}
    cand = {"amount": 100, "date": "2023-01-01", "vendor": "Acme Inc", "reference_id": "REF1234", "currency": "USD"}
    score, ev = calculate_similarity_score(src, cand)
    assert score >= 125 # 40 + 30 + 30 + 15 + 10
    assert "Vendor name overlap" in ev
    assert "Partial reference match" in ev

def test_date_shift():
    src = {"amount": 100, "date": "2023-01-01", "vendor": "Acme", "currency": "USD"}
    cand = {"amount": 100, "date": "2023-01-05", "vendor": "Acme", "currency": "USD"}
    score, ev = calculate_similarity_score(src, cand)
    assert score >= 95 # 40 + 15 + 30 + 10
    assert "Date within 7 days" in ev

def test_amount_variance():
    src = {"amount": 10000, "date": "2023-01-01", "vendor": "Acme", "currency": "INR"}
    cand = {"amount": 9950, "date": "2023-01-01", "vendor": "Acme", "currency": "INR"}
    score, ev = calculate_similarity_score(src, cand)
    assert score >= 90 # 20 (within ₹4,000) + 30 + 30 + 10
    assert "Amount within ₹4,000" in ev

def test_split_payment():
    src = {"amount": 1000, "date": "2023-01-01", "vendor": "Acme", "currency": "USD"}
    cand = {"amount": 600, "date": "2023-01-01", "vendor": "Acme", "currency": "USD"}
    score, ev = calculate_similarity_score(src, cand)
    # Should get 5 for split component, 30 date, 30 vendor, 10 currency
    assert score >= 75
    assert "Potential split component" in ev

def test_near_duplicate():
    src = {"amount": 1000, "date": "2023-01-01", "vendor": "Acme", "currency": "USD"}
    cand1 = {"amount": 1000, "date": "2023-01-01", "vendor": "Acme", "currency": "USD"}
    cand2 = {"amount": 1000, "date": "2023-01-02", "vendor": "Acme", "currency": "USD"}
    df = pd.DataFrame([cand1, cand2])
    candidates = generate_candidates_for_record(src, df, "ledger", "bank", top_n=5)
    assert len(candidates) == 2
    assert candidates[0]["_candidate_score"] > candidates[1]["_candidate_score"]

def test_currency_mismatch():
    src = {"amount": 8350, "amount_inr": 8350, "currency": "INR"}
    cand = {"amount": 100, "amount_inr": 8350, "currency": "USD"}
    score, ev = calculate_similarity_score(src, cand)
    assert score >= 40 # Exact amount match in INR
    assert "Currency matched" not in ev


def test_zero_candidate_threshold_bounding():
    """
    Tests candidate generator bounding threshold when no candidates match.
    Candidates with similarity score < 40 must be completely filtered out.
    """
    src = {"amount": 1000.0, "date": "2023-01-01", "vendor": "Company Alpha", "currency": "INR"}
    cand = {"amount": 99999.0, "date": "2024-12-31", "vendor": "Totally Unrelated Zebra", "currency": "USD"}
    df = pd.DataFrame([cand])
    candidates = generate_candidates_for_record(src, df, "ledger", "bank", top_n=5)
    assert len(candidates) == 0, "Candidates scoring below threshold 40 must be bounded and excluded."

def test_no_valid_candidate():
    src = {"amount": 10000, "date": "2023-01-01", "vendor": "Acme", "currency": "INR"}
    cand = {"amount": 500000, "date": "2023-06-01", "vendor": "Zeta", "currency": "USD"}
    df = pd.DataFrame([cand])
    candidates = generate_candidates_for_record(src, df, "ledger", "bank", top_n=5)
    assert len(candidates) == 0 # Score should be 0
