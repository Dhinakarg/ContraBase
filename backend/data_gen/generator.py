import os
import json
import random
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker

def generate_reconciliation_data(n_records=100, seed=42, anomaly_rate=0.10, output_dir="data", multi_currency=False):
    """
    Generates synthetic bank statements, internal ledger entries, and invoice records.
    Injects noise such as typos, date shifts, fees/FX rounding, split payments,
    and decoys, and outputs a ground_truth.json file mapping all records.
    
    If multi_currency=True, ~30% of records are generated in EUR (rest USD)
    with a fixed FX rate of 0.92 EUR/USD.
    """
INDIAN_COMPANY_PREFIXES = ["Sharma", "Reliance", "Kumar", "Tata", "Infosys", "Mahindra", "Patel", "Gupta", "Verma", "Mehta", "Chawla", "Bajaj", "Reddy", "Singhania", "Agarwal", "Godrej", "Birla", "Wipro", "HCL", "Kirloskar"]
INDIAN_COMPANY_SUFFIXES = ["& Sons", "Textiles Pvt Ltd", "Enterprises", "Logistics", "Technologies", "Spares Pvt Ltd", "Financials", "Steel", "Trading", "Solutions", "Exports", "Industries", "Holdings", "Services"]

def generate_reconciliation_data(n_records=100, seed=42, anomaly_rate=0.10, output_dir="data", multi_currency=False):
    """
    Generates synthetic bank statements, internal ledger entries, and invoice records.
    Injects noise such as typos, date shifts, fees/FX rounding, split payments,
    and decoys, and outputs a ground_truth.json file mapping all records.
    
    Uses INR (₹) as the base currency with amounts in realistic Indian B2B scale (₹15,000 to ₹8,00,000).
    If multi_currency=True, ~30% of records are generated in USD (foreign currency)
    with a fixed FX rate of 83.50 INR/USD.
    """
    # Fixed FX rate for USD/INR conversion (1 USD = 83.50 INR)
    FX_RATE_USD_INR = 83.50  # 1 USD = 83.50 INR
    # Seed for reproducibility
    random_state = random.Random(seed)
    Faker.seed(seed)
    fake = Faker("en_IN")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Output lists for dataframes
    invoices = []
    ledger = []
    bank_statement = []

    # Ground truth tracking structure
    ground_truth = {
        "matches": [],
        "unmatchable": {
            "invoice_ids": [],
            "ledger_ids": [],
            "bank_ids": []
        },
        "decoys": {
            "invoice_ids": [],
            "ledger_ids": [],
            "bank_ids": []
        }
    }

    exact_rate = max(0.0, 1.0 - anomaly_rate)
    counts = {
        "exact_match": int(n_records * exact_rate),
        "date_shift": int(n_records * anomaly_rate * 0.25),
        "amount_mismatch": int(n_records * anomaly_rate * 0.15),
        "reference_typo": int(n_records * anomaly_rate * 0.15),
        "split_payment": int(n_records * anomaly_rate * 0.15),
        "duplicate_decoy": int(n_records * anomaly_rate * 0.10),
        "unmatchable_invoice": int(n_records * anomaly_rate * 0.10),
        "unmatchable_ledger": int(n_records * anomaly_rate * 0.05),
        "unmatchable_bank": int(n_records * anomaly_rate * 0.05)
    }
    
    # Ensure at least 1 split payment and decoy are present if anomaly rate is non-zero
    if anomaly_rate > 0.0:
        counts["split_payment"] = max(1, counts["split_payment"])
        counts["duplicate_decoy"] = max(1, counts["duplicate_decoy"])
        
    # Adjust exact_match count to sum exactly to n_records
    total_scheduled = sum(counts.values())
    if total_scheduled < n_records:
        counts["exact_match"] += (n_records - total_scheduled)
    elif total_scheduled > n_records:
        counts["exact_match"] = max(0, counts["exact_match"] - (total_scheduled - n_records))

    # Helper function to introduce a typo in a string
    def introduce_typo(text):
        if not text or len(text) < 4:
            return text
        typo_type = random_state.choice(["transpose", "substitute", "omit"])
        chars = list(text)
        if typo_type == "transpose":
            idx = random_state.randint(0, len(chars) - 2)
            chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
        elif typo_type == "substitute":
            idx = random_state.randint(0, len(chars) - 1)
            chars[idx] = random_state.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        elif typo_type == "omit":
            idx = random_state.randint(0, len(chars) - 1)
            chars.pop(idx)
        return "".join(chars)

    def generate_vendor_name():
        prefix = random_state.choice(INDIAN_COMPANY_PREFIXES)
        suffix = random_state.choice(INDIAN_COMPANY_SUFFIXES)
        return f"{prefix} {suffix}"

    # Initialize sequential ID counters
    inv_counter = 10001
    led_counter = 20001
    bnk_counter = 30001
    ref_counter = 50001

    base_date = datetime(2026, 8, 1)

    for scenario, count in counts.items():
        for _ in range(count):
            vendor = generate_vendor_name()
            # Indian B2B scale: ₹15,000 to ₹8,00,000
            base_amount = round(random_state.uniform(15000.0, 800000.0), 2)
            
            # Currency selection: ~30% USD (foreign) when multi_currency enabled, else base INR
            if multi_currency and random_state.random() < 0.30:
                currency = "USD"
                local_amount = round(base_amount / FX_RATE_USD_INR, 2)
            else:
                currency = "INR"
                local_amount = base_amount

            # Standard reference format
            ref_id = f"REF{ref_counter}"
            ref_counter += 1
            
            # Due date for invoice
            due_date = (base_date + timedelta(days=random_state.randint(5, 20))).strftime("%Y-%m-%d")
            # Ledger date usually a few days before due date
            led_date = (datetime.strptime(due_date, "%Y-%m-%d") - timedelta(days=random_state.randint(1, 5))).strftime("%Y-%m-%d")
            # Bank statement date usually 1-3 days after ledger date
            bnk_date = (datetime.strptime(led_date, "%Y-%m-%d") + timedelta(days=random_state.randint(0, 3))).strftime("%Y-%m-%d")

            if scenario == "exact_match":
                inv_id = f"INV_{inv_counter}"
                led_id = f"LED_{led_counter}"
                bnk_id = f"BNK_{bnk_counter}"
                inv_counter += 1
                led_counter += 1
                bnk_counter += 1

                invoices.append({
                    "invoice_id": inv_id,
                    "amount": local_amount,
                    "due_date": due_date,
                    "vendor": vendor,
                    "currency": currency
                })
                ledger.append({
                    "ledger_id": led_id,
                    "date": led_date,
                    "amount": local_amount,
                    "vendor": vendor,
                    "reference_id": ref_id,
                    "currency": currency
                })
                bank_statement.append({
                    "bank_id": bnk_id,
                    "date": led_date,
                    "amount": local_amount,
                    "description": f"DEPOSIT {vendor.upper()} {ref_id}",
                    "reference_id": ref_id,
                    "currency": currency
                })

                ground_truth["matches"].append({
                    "invoice_id": inv_id,
                    "ledger_id": led_id,
                    "bank_ids": [bnk_id],
                    "match_type": "exact_match"
                })

            elif scenario == "date_shift":
                inv_id = f"INV_{inv_counter}"
                led_id = f"LED_{led_counter}"
                bnk_id = f"BNK_{bnk_counter}"
                inv_counter += 1
                led_counter += 1
                bnk_counter += 1

                # Shift bank date by 2-5 days
                shifted_bnk_date = (datetime.strptime(led_date, "%Y-%m-%d") + timedelta(days=random_state.randint(2, 5))).strftime("%Y-%m-%d")

                invoices.append({
                    "invoice_id": inv_id,
                    "amount": local_amount,
                    "due_date": due_date,
                    "vendor": vendor,
                    "currency": currency
                })
                ledger.append({
                    "ledger_id": led_id,
                    "date": led_date,
                    "amount": local_amount,
                    "vendor": vendor,
                    "reference_id": ref_id,
                    "currency": currency
                })
                bank_statement.append({
                    "bank_id": bnk_id,
                    "date": shifted_bnk_date,
                    "amount": local_amount,
                    "description": f"DEPOSIT {vendor.upper()} {ref_id}",
                    "reference_id": ref_id,
                    "currency": currency
                })

                ground_truth["matches"].append({
                    "invoice_id": inv_id,
                    "ledger_id": led_id,
                    "bank_ids": [bnk_id],
                    "match_type": "date_shift"
                })

            elif scenario == "amount_mismatch":
                inv_id = f"INV_{inv_counter}"
                led_id = f"LED_{led_counter}"
                bnk_id = f"BNK_{bnk_counter}"
                inv_counter += 1
                led_counter += 1
                bnk_counter += 1

                # Bank amount slightly lower due to wire fee or FX rounding (e.g. -₹450.00 wire fee)
                fee = round(random_state.uniform(100.0, 2500.0) if currency == "INR" else random_state.uniform(1.0, 25.0), 2)
                bank_amount = round(local_amount - fee, 2)

                invoices.append({
                    "invoice_id": inv_id,
                    "amount": local_amount,
                    "due_date": due_date,
                    "vendor": vendor,
                    "currency": currency
                })
                ledger.append({
                    "ledger_id": led_id,
                    "date": led_date,
                    "amount": local_amount,
                    "vendor": vendor,
                    "reference_id": ref_id,
                    "currency": currency
                })
                bank_statement.append({
                    "bank_id": bnk_id,
                    "date": bnk_date,
                    "amount": bank_amount,
                    "description": f"DEPOSIT {vendor.upper()} {ref_id} LESS FEE {fee}",
                    "reference_id": ref_id,
                    "currency": currency
                })

                ground_truth["matches"].append({
                    "invoice_id": inv_id,
                    "ledger_id": led_id,
                    "bank_ids": [bnk_id],
                    "match_type": "amount_mismatch"
                })

            elif scenario == "reference_typo":
                inv_id = f"INV_{inv_counter}"
                led_id = f"LED_{led_counter}"
                bnk_id = f"BNK_{bnk_counter}"
                inv_counter += 1
                led_counter += 1
                bnk_counter += 1

                # Typo injected into bank reference
                typo_ref_id = introduce_typo(ref_id)

                invoices.append({
                    "invoice_id": inv_id,
                    "amount": local_amount,
                    "due_date": due_date,
                    "vendor": vendor,
                    "currency": currency
                })
                ledger.append({
                    "ledger_id": led_id,
                    "date": led_date,
                    "amount": local_amount,
                    "vendor": vendor,
                    "reference_id": ref_id,
                    "currency": currency
                })
                bank_statement.append({
                    "bank_id": bnk_id,
                    "date": bnk_date,
                    "amount": local_amount,
                    "description": f"DEPOSIT {vendor.upper()} {typo_ref_id}",
                    "reference_id": typo_ref_id,
                    "currency": currency
                })

                ground_truth["matches"].append({
                    "invoice_id": inv_id,
                    "ledger_id": led_id,
                    "bank_ids": [bnk_id],
                    "match_type": "reference_typo"
                })

            elif scenario == "split_payment":
                inv_id = f"INV_{inv_counter}"
                led_id = f"LED_{led_counter}"
                bnk_id1 = f"BNK_{bnk_counter}"
                bnk_id2 = f"BNK_{bnk_counter + 1}"
                inv_counter += 1
                led_counter += 1
                bnk_counter += 2

                # Split payment: one invoice paid in two parts
                split1 = round(local_amount * random_state.uniform(0.3, 0.7), 2)
                split2 = round(local_amount - split1, 2)

                invoices.append({
                    "invoice_id": inv_id,
                    "amount": local_amount,
                    "due_date": due_date,
                    "vendor": vendor,
                    "currency": currency
                })
                ledger.append({
                    "ledger_id": led_id,
                    "date": led_date,
                    "amount": local_amount,
                    "vendor": vendor,
                    "reference_id": ref_id,
                    "currency": currency
                })
                bank_statement.append({
                    "bank_id": bnk_id1,
                    "date": bnk_date,
                    "amount": split1,
                    "description": f"DEPOSIT PART 1 {vendor.upper()} {ref_id}",
                    "reference_id": ref_id,
                    "currency": currency
                })
                bank_statement.append({
                    "bank_id": bnk_id2,
                    "date": bnk_date,
                    "amount": split2,
                    "description": f"DEPOSIT PART 2 {vendor.upper()} {ref_id}",
                    "reference_id": ref_id,
                    "currency": currency
                })

                ground_truth["matches"].append({
                    "invoice_id": inv_id,
                    "ledger_id": led_id,
                    "bank_ids": [bnk_id1, bnk_id2],
                    "match_type": "split_payment"
                })

            elif scenario == "duplicate_decoy":
                # Create base exact match
                inv_id = f"INV_{inv_counter}"
                led_id = f"LED_{led_counter}"
                bnk_id = f"BNK_{bnk_counter}"
                inv_counter += 1
                led_counter += 1
                bnk_counter += 1

                invoices.append({
                    "invoice_id": inv_id,
                    "amount": local_amount,
                    "due_date": due_date,
                    "vendor": vendor,
                    "currency": currency
                })
                ledger.append({
                    "ledger_id": led_id,
                    "date": led_date,
                    "amount": local_amount,
                    "vendor": vendor,
                    "reference_id": ref_id,
                    "currency": currency
                })
                bank_statement.append({
                    "bank_id": bnk_id,
                    "date": led_date,
                    "amount": local_amount,
                    "description": f"DEPOSIT {vendor.upper()} {ref_id}",
                    "reference_id": ref_id,
                    "currency": currency
                })

                ground_truth["matches"].append({
                    "invoice_id": inv_id,
                    "ledger_id": led_id,
                    "bank_ids": [bnk_id],
                    "match_type": "exact_match"
                })

                # Decide where to inject duplicate decoy (ledger or bank, or both)
                decoy_type = random_state.choice(["ledger", "bank"])
                if decoy_type == "ledger":
                    decoy_led_id = f"LED_{led_counter}"
                    led_counter += 1
                    ledger.append({
                        "ledger_id": decoy_led_id,
                        "date": led_date,
                        "amount": local_amount,
                        "vendor": vendor,
                        "reference_id": ref_id,
                        "currency": currency
                    })
                    ground_truth["decoys"]["ledger_ids"].append(decoy_led_id)
                else:
                    decoy_bnk_id = f"BNK_{bnk_counter}"
                    bnk_counter += 1
                    bank_statement.append({
                        "bank_id": decoy_bnk_id,
                        "date": bnk_date,
                        "amount": local_amount,
                        "description": f"DEPOSIT {vendor.upper()} {ref_id}",
                        "reference_id": ref_id,
                        "currency": currency
                    })
                    ground_truth["decoys"]["bank_ids"].append(decoy_bnk_id)

            elif scenario == "unmatchable_invoice":
                inv_id = f"INV_{inv_counter}"
                inv_counter += 1
                invoices.append({
                    "invoice_id": inv_id,
                    "amount": local_amount,
                    "due_date": due_date,
                    "vendor": vendor,
                    "currency": currency
                })
                ground_truth["unmatchable"]["invoice_ids"].append(inv_id)

            elif scenario == "unmatchable_ledger":
                led_id = f"LED_{led_counter}"
                led_counter += 1
                ledger.append({
                    "ledger_id": led_id,
                    "date": led_date,
                    "amount": local_amount,
                    "vendor": vendor,
                    "reference_id": ref_id,
                    "currency": currency
                })
                ground_truth["unmatchable"]["ledger_ids"].append(led_id)

            elif scenario == "unmatchable_bank":
                bnk_id = f"BNK_{bnk_counter}"
                bnk_counter += 1
                bank_statement.append({
                    "bank_id": bnk_id,
                    "date": bnk_date,
                    "amount": local_amount,
                    "description": f"BANK CHARGE OR UNMATCHABLE WIRE {ref_id}",
                    "reference_id": ref_id,
                    "currency": currency
                })
                ground_truth["unmatchable"]["bank_ids"].append(bnk_id)

    # Store FX rate metadata in ground truth
    ground_truth["fx_rate_usd_inr"] = FX_RATE_USD_INR
    ground_truth["multi_currency"] = multi_currency

    # Convert to pandas DataFrames
    invoices_df = pd.DataFrame(invoices)
    ledger_df = pd.DataFrame(ledger)
    bank_df = pd.DataFrame(bank_statement)

    # Shuffle to simulate real files (which won't be perfectly ordered by scenario)
    # Using random_state to ensure reproducibility
    if not invoices_df.empty:
        invoices_df = invoices_df.sample(frac=1, random_state=seed).reset_index(drop=True)
    if not ledger_df.empty:
        ledger_df = ledger_df.sample(frac=1, random_state=seed).reset_index(drop=True)
    if not bank_df.empty:
        bank_df = bank_df.sample(frac=1, random_state=seed).reset_index(drop=True)

    # Export to CSV files
    invoices_df.to_csv(os.path.join(output_dir, "invoices.csv"), index=False)
    ledger_df.to_csv(os.path.join(output_dir, "internal_ledger.csv"), index=False)
    bank_df.to_csv(os.path.join(output_dir, "bank_statement.csv"), index=False)

    # Write ground_truth.json
    with open(os.path.join(output_dir, "ground_truth.json"), "w") as f:
        json.dump(ground_truth, f, indent=4)

    return invoices_df, ledger_df, bank_df, ground_truth

if __name__ == "__main__":
    generate_reconciliation_data(100)
    print("Mock datasets generated inside data/")
