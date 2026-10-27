# ContraBase

An AI-powered autonomous finance controller engine for corporate month-end reconciliation, built with policy-governed automation, deterministic safety controls, and human oversight.

> **Core Philosophy:** *AI advises. Deterministic controls authorize. From reconciliation to close-ready decisions.*  
> 🎥 **Demo Video:** [Watch ContraBase Walkthrough](https://drive.google.com/file/d/157VqKgZKq5TNsw6G1ARJVE9Nk7OUPGlE/view?usp=sharing)

---

## 🎯 Problem Statement

Corporate month-end financial reconciliation is one of the most critical yet labor-intensive operations in enterprise accounting. Finance and audit teams must reconcile millions in transaction volume across disparate sources: internal general ledgers, commercial bank statements, and vendor invoices. 

Manual reconciliation suffers from severe friction:
- **Discrepancy Fatigue:** Complex real-world variances—such as multi-invoice split payments, clearing date shifts, foreign exchange (FX) currency fluctuations, and reference invoice typos—create massive backlogs of unresolved items.
- **Month-End Closing Delays:** A single unallocated transaction blocks books from closing, slowing executive financial reporting.
- **The AI Dilemma:** Traditional automated matching relies on rigid exact-equality scripts that fail on subtle variances. Conversely, naively applying unconstrained Large Language Models (LLMs) risks hallucinations, unauthorized ledger writes, and catastrophic financial loss.

There is a critical need for software that combines the pattern-matching intelligence of LLMs with deterministic, verifiable accounting safeguards.

---

## 👥 Target Users

ContraBase is engineered for corporate finance and compliance departments:

1. **Corporate Financial Controllers:** Responsible for month-end close sign-offs, materiality exposure management, and ensuring zero unauthorized journal postings.
2. **Internal Audit & Compliance Officers:** Requiring immutable cryptographic audit trails, evidence lineage, and full explainability for every automated or human reconciliation decision.
3. **Accounts Payable (AP) & Accounts Receivable (AR) Specialists:** Operators handling high-volume transaction feeds who require fast candidate resolution and an evidence-first workbench to quickly triage ambiguous exceptions.

---

## 💡 Solution

ContraBase bridges the gap between speed and governance through a **policy-governed, two-pass hybrid reconciliation pipeline**:

```text
Incoming Invoices, Ledgers & Bank Feeds
  ↓
[Pass 1] Deterministic Exact Engine (>85% volume resolved @ >750 recs/sec)
  ↓ (Unmatched Records)
[Candidate Generation] Deterministic similarity & INR-normalized ranking
  ↓ (Top Bounded Candidates)
[Pass 2] Candidate-Bounded Gemini 2.5 Flash Adjudication
  ↓
[Multi-Layer Confidence] 60% Evidence Signals + 40% AI Self-Confidence
  ↓
[Gate A: Materiality Policy Engine] High-value exposure (≥ ₹4,00,000) requires human sign-off
  ↓
[Gate B: Double-Entry Journal Validator] Balance checks (Debits = Credits) & auto-post cap (< ₹4,000)
  ↓
[HITL Review Queue] Human controller approves, rejects, or escalates ambiguous items
  ↓
Close-Ready Financial Statements & Cryptographic Audit Trail
```

By ensuring that **AI advises, but deterministic safety gates authorize**, ContraBase achieves complete operational reliability with zero uninspected financial leakage.

---

## ✨ Key Features

- ⚡ **Two-Pass Reconciliation Engine:** Sub-millisecond deterministic matching for exact records combined with candidate-bounded Gemini 2.5 Flash adjudication for complex edge cases.
- 🛡️ **Dual Governance Safety Gates:**
  - **Gate A (Materiality Threshold):** Configurable threshold (default `₹4,00,000 INR`). Transactions equal to or above this cap can **never** be auto-accepted without human controller review (**0.0% auto-accept rate for high-materiality transactions**).
  - **Gate B (Double-Entry Journal Validator):** Validates all proposed corrective entries against a Chart of Accounts (COA) whitelist, verifies mathematical balance ($\text{Debits} = \text{Credits}$), and enforces an auto-post variance cap ($< \text{₹}4,000.00$).
- 🔍 **7-Part Evidence-First Workbench:** Every flagged transaction reveals its Source Record, Selected Candidates, Structured Evidence Signals, Decision & Policy Routing, Rejected Candidates, AI Rationale, and Validated Journal Entries.
- 👤 **Interactive Human-in-the-Loop (HITL) Queue:** Allows auditors to `Approve`, `Reject`, or `Escalate` ambiguous items, logging auditor identity, timestamp, and computing a live `Human Override Rate`.
- 💱 **Multi-Currency Normalization:** Native dual-currency processing (INR and USD) with deterministic benchmark FX normalization ($1\text{ USD} = 83.50\text{ INR}$) to prevent false mismatches.
- 📊 **Calibrated Confidence Scoring:** Combines heuristic evidence signals (60%) with model confidence (40%) to yield **99.0% ground-truth accuracy** in the 95–100% confidence tier.
- 🔒 **Idempotent Audit Persistence:** SHA-256 fingerprinting across dataset configs, records, and candidate sets guarantees zero duplicate postings or redundant API calls on re-runs.
- 🧪 **15-Scenario Safety Verification Suite:** Built-in verification engine verifying resilience against prompt injections, malformed AI outputs, COA violations, boundary conditions, and API outages.
- 📈 **Multi-Seed Benchmark Evaluation:** Reproducible statistical suite across 5 independent seeds (`42, 101, 777, 1234, 2026`) providing mathematical proof of lift over naive baseline matching.

---

## 🛠️ Tech Stack

- **Dashboard & User Interface:** [Streamlit](https://streamlit.io/) (with custom high-contrast digital ledger styling)
- **Data Processing & Analytics:** [Pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/), [Plotly](https://plotly.com/python/)
- **Artificial Intelligence:** Google Gemini 2.5 Flash via official [`google-genai`](https://pypi.org/project/google-genai/) SDK with structured JSON schemas
- **Synthetic Data Generation:** [Faker](https://faker.readthedocs.io/) (realistic enterprise vendors, reference numbers, and invoices)
- **Configuration & Secrets:** [`python-dotenv`](https://pypi.org/project/python-dotenv/) and Streamlit Cloud `st.secrets`
- **Automated Testing Suite:** [Pytest](https://docs.pytest.org/) (107 unit and integration tests across 20 test modules)

---

## 🏛️ System Architecture

ContraBase executes a multi-layered reconciliation pipeline that reconciles internal ledgers, bank statements, and vendor invoices while enforcing enterprise financial safety, ground-truth isolation, evidence calibration, and human-in-the-loop governance:

1. **Pass 1 (Deterministic Matching Engine):** High-speed pandas exact matching on amount, date, reference ID, and currency. Resolves **>85% of standard transaction volume** at throughputs exceeding **750+ records/second** (with full end-to-end pipeline execution including Gemini LLM network adjudication averaging ~125–150 records/second on standard demo batches).
2. **Candidate Generation:** Deterministic candidate ranking (`candidates.py`) surfaces top plausible candidates for unmatched records using INR-normalized amounts (`amount_inr`), date proximity, and reference similarity.
3. **Pass 2 (Candidate-Bounded Gemini Adjudication):** Gemini 2.5 Flash batch adjudication for unmatched records, evaluating bounded candidate sets and returning structured JSON decisions. Under API limits or empty responses, an **honest fallback mechanism** routes items to `status: exception` with `ai_confidence: 0.0` without fabricating decisions.
4. **Multi-Layer System Confidence:** Blends candidate evidence scores (60%) and AI self-reported confidence (40%). Empirical calibration demonstrates **99.0% ground-truth accuracy** in the 95–100% confidence band.
5. **Resolution Policy Engine (Gate A - Transaction Materiality):** Enforces conservative enterprise policy rules with a **dynamically configurable materiality threshold** (default `materiality_threshold_inr = ₹4,00,000`). High-materiality transactions (or complex split payments / FX items above threshold) cannot be auto-accepted and require human sign-off (**0.0% auto-accept rate for high-materiality transactions**).
6. **Journal Entry Validator (Gate B - Corrective Journal Safety):** Deterministic double-entry validator enforcing debits = credits, Chart of Accounts whitelist compliance, positive amounts, duplicate prevention, and auto-post safety caps (`journal_auto_post_variance_cap_inr = ₹4,000.00`). Corrective entries are eligible for auto-posting ONLY if variance $< ₹4,000$, transaction below materiality threshold, and all accounting rules pass.
7. **Human-in-the-Loop (HITL) Queue:** Interactive review queue for `needs_review` items allowing human auditors to `Approve`, `Reject`, or `Escalate` decisions, tracking original AI decision vs final decision and calculating a live `Human Override Rate`.
8. **Evidence-First UI:** 7-part workbench sequence exposing Source Record, Selected Candidates, Structured Evidence Signals, Decision & Policy Routing, Rejected Candidates, AI Rationale, and Validated Journal Entries.
9. **Idempotent Decision Handling:** Pipeline enforcement of stable identifiers (`run_id`, `decision_id`, `source_record_hash`, `journal_entry_id`) and in-place audit log updating to guarantee zero duplicate decisions or financial actions when re-running batches.
10. **Ground-Truth Isolation:** `ground_truth.json` is generated strictly isolated and accessed ONLY post-inference during evaluation by `scoring.py`, `benchmark.py`, and `failure_analysis.py`.
11. **Multi-Seed Benchmark Suite:** Standalone runner executing isolated pipeline runs across official independent seeds (`42, 101, 777, 1234, 2026`), calculating statistical aggregates (Mean, Median, Std Dev, Min, Max), and proving **deterministic benchmark reproducibility**.

---

## 💱 Currency & FX Disclosure

- **Primary Functional Currency:** **Indian Rupee (`INR` / `₹`)** with amounts in realistic Indian B2B scale (₹15,000 to ₹8,00,000).
- **Supported Foreign Currency:** **USD** (simulating export/import transactions). Foreign currency transactions preserve their original transaction currency (`$10,000.00 USD`) while being evaluated for materiality using their **INR-normalized exposure** (`₹8,35,000.00`).
- **Benchmark FX Rate:** **Deterministic synthetic benchmark rate (1 USD = 83.50 INR)** for strict benchmark reproducibility (no live FX APIs used).

---

## 🚀 Local Setup

### Prerequisites

You need **Python 3.10+** (verified through Python 3.13) installed on your system.

### 1. Installation

Clone the repository and install required dependencies:

```bash
git clone https://github.com/Dhinakarg/Contra_Base.git
cd Contra_Base
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the root directory (or copy from `.env.example`):

```bash
cp .env.example .env
```

Open `.env` and add your Google Gemini API key:

```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

*(Note: If no API key is provided, ContraBase automatically activates its deterministic fallback mode and routes all ambiguous transactions to the human review queue safely).*

### 3. Launching the Dashboard

Run the Streamlit application:

```bash
streamlit run app.py
```

Streamlit will boot the local server and open the web dashboard in your browser (typically at `http://localhost:8501`).

---

## 🔐 Environment Variables

The project uses the following environment variables:

| Variable | Description | Required | Default |
|---|---|:---:|---|
| `GEMINI_API_KEY` | Google Gemini API Key for Pass 2 LLM adjudication | Recommended | None (Falls back to deterministic review routing) |
| `GOOGLE_API_KEY` | Alternative environment key alias for Gemini API | Optional | None |

> **Security Note:** Real API keys are never stored in source code. `.env` is listed in `.gitignore` to prevent credential leaks.

---

## 🌐 Deployment (Streamlit Community Cloud)

ContraBase is cloud-ready and configured for one-click deployment on **Streamlit Community Cloud**:

1. Fork or push this repository to your GitHub account.
2. Log into [share.streamlit.io](https://share.streamlit.io) and click **"New app"**.
3. Select your repository, branch (`main`), and set the main file path to:
   ```text
   app.py
   ```
4. Click **Advanced Settings** -> **Secrets**, and enter your Gemini API key:
   ```toml
   GEMINI_API_KEY = "your_actual_gemini_api_key_here"
   ```
5. Click **Deploy!** The cloud deployment will install dependencies from `requirements.txt` and launch automatically.

---

## 🧪 Running Automated Tests & Benchmarks

### Running the Pytest Suite (107 Tests)

The repository includes a comprehensive automated test suite verifying policy rules, idempotency, journal validation, state persistence, and UI navigation:

```bash
py -3 -m pytest tests/
```

*(Expected output: `107 passed, 1 skipped in ~10s`)*

### Running Multi-Seed Benchmarks

To execute the isolated 5-seed benchmark evaluation comparing ContraBase against naive exact matching:

```bash
py -c "from benchmark import BenchmarkRunner; results = BenchmarkRunner.run_five_seed_comparison(); print(results['lifts'])"
```

---

## 🎥 Demo Video & Narration Walkthrough

> 📹 **Live Demonstration:** [Watch ContraBase Walkthrough on Google Drive](https://drive.google.com/file/d/157VqKgZKq5TNsw6G1ARJVE9Nk7OUPGlE/view?usp=sharing)

When demonstrating the application (e.g., in a 3–5 minute video):

1. **Executive Dashboard (0:00 - 0:45):** Highlight the Month-End Close banner showing Operational Close Status (`🟢 CLOSE READY` or `🟡 CONTROLLER REVIEW REQUIRED`), pipeline throughput (>750 recs/sec Pass 1; ~130 recs/sec end-to-end), and total closed volume.
2. **Demo Preset Execution (0:45 - 1:30):** Click **🎭 Load Demo Preset** in the sidebar. This loads Seed 42 with 160 transactions, showcasing date shifts, typos, and split payments.
3. **Multi-Currency Normalization (1:30 - 2:15):** Toggle **🌐 Multi-Currency (INR/USD)** to generate foreign USD transactions and display INR-normalized materiality calculations (`$10,000 USD (₹8,35,000 INR equiv)`).
4. **Governance Safety Gates (2:15 - 3:00):** Show Gate A (Materiality Threshold blocking auto-accept on transactions $\ge$ ₹4,00,000) and Gate B (blocking debits $\ne$ credits in proposed journals).
5. **Auditor Action in HITL Queue (3:00 - 4:00):** Open the Review Queue, inspect the 7-part Evidence Workbench, and click **Approve** or **Reject** to demonstrate real-time Human Override Rate calculation.
6. **Safety Verification Suite (4:00 - 4:45):** Navigate to the **🛡️ Safety Verification** tab and demonstrate the 15 live automated safety tests verifying prompt injection blocks, malformed AI JSON fallbacks, and boundary conditions.
7. **Audit Log Export (4:45 - 5:00):** Download the tamper-proof JSONL cryptographic audit trail.

---

## 🛡️ Enterprise Architecture & Single-Tenant Workstation Model

- **Single-Tenant Controller Model:** ContraBase is architected as an internal Financial Controller Workstation. To ensure regulatory privacy and compliance with banking bank-feed secrecy laws, transaction ledgers and ground-truth records remain strictly isolated on the host machine or enterprise virtual private cloud (VPC).
- **Ground-Truth Isolation:** `ground_truth.json` is generated strictly isolated in `data/` and is never exposed to the LLM or matching pipeline during inference. It is referenced solely post-inference by `scoring.py` and `benchmark.py` for mathematical accuracy reporting.
- **API Failure Resilience:** If the Gemini API experiences network timeouts or rate limits, ContraBase's honest fallback catches the exception, assigns `ai_confidence: 0.0`, and routes the record to `needs_review` with a clear explanation rather than fabricating false financial matches.

---

## ♿ Accessibility & Compliance Disclosure

- **Browser Zoom:** Fully responsive and verified across 67%–150% browser zoom levels with non-overlapping controls and unclipped financial figures.
- **Multi-Modal Indicators:** All operational states use structured text labels alongside color cues and symbols (e.g. `🟢 CLOSE READY`, `🟡 CONTROLLER REVIEW REQUIRED`, `🔴 EXCEPTIONS BLOCK CLOSE`) to guarantee full accessibility for color-blind controllers.
