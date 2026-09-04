import pandas as pd
from faker import Faker
import random

def generate_synthetic_data(num_records=100, anomaly_rate=0.1, seed=42):
    """
    Generates synthetic internal ledger records and corresponding bank statement transactions.
    Introduces anomalies/discrepancies based on anomaly_rate for Gemini adjudication testing.
    """
    Faker.seed(seed)
    random.seed(seed)
    fake = Faker()
    
    # Placeholder lists
    ledger_data = []
    bank_data = []
    ground_truth = []
    
    # Skeleton generation logic
    for i in range(num_records):
        tx_id = f"TX-{1000 + i}"
        amount = round(random.uniform(10.0, 5000.0), 2)
        date = fake.date_between(start_date="-30d", end_date="today")
        company = fake.company()
        
        # Add to ledger
        ledger_data.append({
            "ledger_id": tx_id,
            "date": date,
            "amount": amount,
            "description": f"Payment to {company}",
            "reference": f"REF-{random.randint(100000, 999999)}"
        })
        
        # Introduce matching/mismatching variations
        is_anomaly = random.random() < anomaly_rate
        if is_anomaly:
            # Vary description or amount slightly
            bank_amount = amount if random.random() > 0.5 else round(amount + random.uniform(-5.0, 5.0), 2)
            bank_desc = f"{company.upper()} INC TXN"
            match_status = "mismatch"
        else:
            bank_amount = amount
            bank_desc = f"PURCHASE {company}"
            match_status = "match"
            
        bank_data.append({
            "bank_id": f"BANK-{2000 + i}",
            "date": date,
            "amount": bank_amount,
            "description": bank_desc
        })
        
        ground_truth.append({
            "ledger_id": tx_id,
            "bank_id": f"BANK-{2000 + i}",
            "status": match_status
        })
        
    return pd.DataFrame(ledger_data), pd.DataFrame(bank_data), pd.DataFrame(ground_truth)

if __name__ == "__main__":
    ledger, bank, truth = generate_synthetic_data(10)
    print("Generated ledger head:")
    print(ledger.head())
