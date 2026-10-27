# ContraBase

An AI-powered autonomous finance controller engine for corporate month-end reconciliation, built with policy-governed automation, deterministic safety controls, and human-in-the-loop oversight.

> **Core Principle:** *AI advises. Deterministic controls authorize. From raw transactions to close-ready books.*  
> 📹 **Demo Video:** [Watch System Walkthrough (Google Drive)](https://drive.google.com/file/d/157VqKgZKq5TNsw6G1ARJVE9Nk7OUPGlE/view?usp=sharing)

---

## 🎯 Problem Statement

Corporate month-end reconciliation requires matching thousands of transactions across bank feeds, internal general ledgers, and vendor invoices. 

Real-world variances—such as multi-part split payments, clearing date shifts, foreign exchange (FX) differences, and reference typos—cause massive backlogs and closing delays. Traditional automated matching uses rigid exact-equality scripts that fail on subtle edge cases, while unconstrained LLMs risk hallucinations and erroneous financial postings.

---

## 👥 Target Users

- **Financial Controllers:** Oversee month-end close readiness, set materiality limits, and enforce zero uninspected variances.
- **Internal Audit & Compliance Teams:** Inspect immutable audit logs, decision rationale, and policy compliance trails.
- **Accounting Operations (AP/AR):** Resolve high-volume transaction feeds with automated matching and an evidence-rich review queue.

---

## 💡 Solution

ContraBase combines the pattern-matching capabilities of LLMs with deterministic accounting controls through a **two-pass hybrid pipeline**:

```text
Incoming Invoices, Ledgers & Bank Statements
  ↓
[Pass 1: Deterministic Engine] ──(Exact Match >85%)──→ Auto-Reconciled
  ↓ (Unmatched / Ambiguous)
[Candidate Generation] Deterministic similarity & INR-normalized ranking
  ↓ (Top Plausible Candidates)
[Pass 2: Bounded Gemini 2.5 Flash] Structured JSON adjudication & rationale
  ↓
[Gate A: Materiality Engine] Flag high-value exposure (≥ ₹4,00,000) for review
  ↓
[Gate B: Journal Entry Validator] Verify Debits = Credits & variance cap (< ₹4,000)
  ↓
[HITL Review Queue] Human auditor approves, rejects, or escalates
  ↓
Close-Ready Reconciliation & Cryptographic Audit Trail
```

---

## ✨ Key Features

- **Two-Pass Reconciliation:** High-speed deterministic Pass 1 resolves >85% of standard records at 750+ recs/sec. Pass 2 uses Gemini 2.5 Flash strictly bounded to candidate sets for complex edge cases.
- **Gate A (Materiality Threshold):** Configurable threshold (default `₹4,00,000 INR`). Transactions at or above this threshold can never be auto-accepted without human sign-off (**0.0% auto-accept rate on high materiality**).
- **Gate B (Double-Entry Journal Validator):** Enforces strict accounting rules: mathematical balance ($\text{Debits} = \text{Credits}$), Chart of Accounts (COA) whitelist compliance, and an auto-post variance cap ($< \text{₹}4,000$).
- **7-Part Evidence Workbench:** Displays source record, candidates, evidence signals, policy routing, rejected candidates, AI reasoning, and validated journal entries.
- **Human-in-the-Loop Review Queue:** Interactive triage queue allowing auditors to Approve, Reject, or Escalate decisions with live Human Override Rate tracking.
- **Multi-Currency Normalization:** Handles INR and USD transactions with deterministic benchmark FX conversion ($1\text{ USD} = 83.50\text{ INR}$).
- **Calibrated Confidence Scoring:** Combines candidate evidence signals (60%) with model confidence (40%) achieving 99.0% accuracy in the high-confidence tier.
- **15-Scenario Safety Test Suite:** Built-in verification testing prompt injection resistance, JSON failure fallbacks, boundary conditions, and COA violations.
- **Multi-Seed Benchmark Suite:** Automated benchmark runner evaluating 5 seeds (`42, 101, 777, 1234, 2026`) demonstrating measurable lift over baseline matching.

---

## 🛠️ Tech Stack

- **Frontend:** Streamlit, Custom Dark Ledger CSS, Plotly
- **Backend & Data Processing:** Python 3.10+, Pandas, NumPy, Faker
- **AI & Reasoning:** Google Gemini 2.5 Flash via official `google-genai` SDK (structured JSON schemas with honest fallback)
- **Persistence & Auditing:** JSONL append-only audit trail, SHA-256 content-addressable run store
- **Testing:** Pytest (107 unit and integration tests across 20 modules)

---

## 🏛️ System Architecture

1. **Deterministic Matching (Pass 1):** Pandas-driven exact matching on amount, date, reference ID, and currency.
2. **Candidate Generation:** Deterministic ranking (`candidates.py`) surfaces top plausible candidates for unmatched records based on INR-normalized amounts, date proximity, and reference string similarity.
3. **Candidate-Bounded LLM Adjudication (Pass 2):** Evaluates ambiguous items against bounded candidate sets. If the API fails or is unavailable, an honest fallback routes records to review without fabricating decisions.
4. **Safety Policy Gates:** 
   - **Gate A:** Evaluates transaction exposure against the materiality threshold.
   - **Gate B:** Validates proposed corrective journal entries against double-entry balance and account whitelist rules.
5. **Auditor Queue & Audit Trails:** Items requiring review land in the HITL workbench. All actions are logged with SHA-256 fingerprinting to guarantee idempotency on batch re-runs.

---

## 🚀 Local Setup

### 1. Installation

```bash
git clone https://github.com/Dhinakarg/ContraBase.git
cd ContraBase
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and set your Gemini API key:

```bash
cp .env.example .env
```

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

*(Note: If no API key is provided, the application runs in deterministic fallback mode and safely routes ambiguous records to the human review queue).*

### 3. Launch Dashboard

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## 🔐 Environment Variables

| Variable | Description | Required | Default |
|---|---|:---:|---|
| `GEMINI_API_KEY` | Google Gemini API key for Pass 2 LLM adjudication | Recommended | None (Falls back to deterministic review routing) |
| `GOOGLE_API_KEY` | Alternative key alias for Gemini API | Optional | None |

---

## 🌐 Deployment (Streamlit Community Cloud)

1. Fork or push this repository to GitHub.
2. Log into [share.streamlit.io](https://share.streamlit.io) and create a **New app**.
3. Select your repository: `Dhinakarg/ContraBase`, branch: `main`, file: `app.py`.
4. In **Advanced Settings** -> **Secrets**, add:
   ```toml
   GEMINI_API_KEY = "your_actual_gemini_api_key_here"
   ```
5. Click **Deploy**.

---

## 🧪 Automated Testing & Benchmarks

Run the complete test suite (107 passing tests):

```bash
py -3 -m pytest tests/
```

Run the 5-seed benchmark evaluation:

```bash
py -c "from benchmark import BenchmarkRunner; results = BenchmarkRunner.run_five_seed_comparison(); print(results['lifts'])"
```

---

## 🎥 Demo Video

- **Video Walkthrough:** [Watch ContraBase Demo on Google Drive](https://drive.google.com/file/d/157VqKgZKq5TNsw6G1ARJVE9Nk7OUPGlE/view?usp=sharing)
- **Key Walkthrough Steps:**
  1. Executive Close Status banner & high-throughput Pass 1 matching
  2. Loading Demo Preset (Seed 42, 160 transactions)
  3. Gate A Materiality Cap blocking auto-acceptance of transactions $\ge$ ₹4,00,000
  4. Evidence-First HITL review queue with live override rate calculation
  5. Built-in 15-scenario Safety Verification suite
  6. Exporting tamper-proof JSONL audit trail
