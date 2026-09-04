import pandas as pd

def calculate_similarity_score(source, candidate, source_type="ledger", cand_type="bank"):
    score = 0
    evidence = []
    
    # 1. Amount Proximity (using normalized INR amount)
    source_amt = float(source.get("amount_inr", source.get("amount_usd", source.get("amount", 0))))
    cand_amt = float(candidate.get("amount_inr", candidate.get("amount_usd", candidate.get("amount", 0))))
    
    delta = abs(source_amt - cand_amt)
    if delta < 0.01:
        score += 40
        evidence.append("Exact amount match")
    elif delta <= 4000.00:
        score += 20
        evidence.append(f"Amount within ₹4,000 (delta: ₹{delta:.2f})")
    elif source_amt > 0 and (delta / source_amt) <= 0.10:
        score += 10
        evidence.append("Amount within 10%")
        
    # Check for split payment potential: Candidate amount is strictly less than source, but > 0
    if cand_amt > 0 and cand_amt < (source_amt - 0.01):
        score += 5
        evidence.append("Potential split component")

    # 2. Date Proximity
    try:
        src_date = pd.to_datetime(source.get("date"))
        cand_date = pd.to_datetime(candidate.get("date"))
        days_diff = abs((cand_date - src_date).days)
        if days_diff == 0:
            score += 30
            evidence.append("Exact date match")
        elif days_diff <= 7:
            score += 15
            evidence.append(f"Date within 7 days ({days_diff}d shift)")
    except Exception:
        pass
        
    # 3. Vendor / Description Similarity
    src_vendor = str(source.get("vendor", source.get("description", ""))).lower()
    cand_vendor = str(candidate.get("vendor", candidate.get("description", ""))).lower()
    
    if src_vendor and cand_vendor:
        src_first_word = src_vendor.split()[0] if src_vendor.split() else ""
        cand_first_word = cand_vendor.split()[0] if cand_vendor.split() else ""
        if src_first_word and src_first_word in cand_vendor:
            score += 30
            evidence.append("Vendor name overlap")
            
    # 4. Reference Similarity
    src_ref = str(source.get("reference_id", ""))
    cand_ref = str(candidate.get("reference_id", ""))
    if src_ref and cand_ref and str(src_ref) != "nan" and str(cand_ref) != "nan":
        if src_ref == cand_ref:
            score += 30
            evidence.append("Exact reference match")
        elif len(src_ref) >= 5 and src_ref[:5] in cand_ref:
            score += 15
            evidence.append("Partial reference match")
            
    # 5. Currency Match
    if source.get("currency") == candidate.get("currency"):
        score += 10
        evidence.append("Currency matched")
        
    return score, ", ".join(evidence)

def generate_candidates_for_record(source_record, unmatched_df, source_type, cand_type, top_n=5):
    candidates = []
    
    if unmatched_df.empty:
        return []
        
    for _, row in unmatched_df.iterrows():
        cand_dict = row.to_dict()
        score, evidence = calculate_similarity_score(source_record, cand_dict, source_type, cand_type)
        if score > 0:  # Only include plausible candidates
            # Clean up the dict to not pass full nan records or internal helper keys unnecessarily
            clean_cand = {k: v for k, v in cand_dict.items() if pd.notna(v) and k != "_parsed_date"}
            clean_cand["_candidate_score"] = score
            clean_cand["_evidence_features"] = evidence
            candidates.append(clean_cand)
            
    # Sort by score descending
    candidates.sort(key=lambda x: x["_candidate_score"], reverse=True)
    
    # Return bounded top N
    return candidates[:top_n]
