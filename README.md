# ContraBase

An AI-powered finance controller engine for corporate month-end reconciliation, built with policy-governed automation, deterministic safety controls, and human oversight.

> **Product Concept:** *AI advises. Deterministic controls authorize. From reconciliation to close-ready decisions.*

---

## 🏛️ System Architecture

ContraBase executes a multi-layered reconciliation pipeline that reconciles internal ledgers, bank statements, and vendor invoices while enforcing enterprise financial safety, ground-truth isolation, evidence calibration, and human-in-the-loop governance:

1. **Pass 1 (Deterministic Matching Engine)**: High-speed pandas exact matching on amount, date, reference ID, and currency. Resolves **>85% of standard transaction volume** at throughputs up to **752.5 records/second** at zero LLM cost.
2. **Candidate Generation**: Deterministic candidate ranking (`candidates.py`) surfaces top plausible candidates for unmatched records using INR-normalized amounts (`amount_inr`), date proximity, and reference similarity.
3. **Pass 2 (Candidate-Bounded Gemini Adjudication)**: Gemini 2.5 Flash batch adjudication for unmatched records, evaluating bounded candidate sets and returning structured JSON decisions. Under API limits or empty responses, an **honest fallback mechanism** routes items to `status: exception` with `ai_confidence: 0.0` without fabricating decisions.
4. **Multi-Layer System Confidence**: Blends candidate evidence scores (60%) and AI self-reported confidence (40%). Empirical calibration demonstrates **99.0% ground-truth accuracy** in the 95–100% confidence band.
5. **Resolution Policy Engine (Gate A - Transaction Materiality)**: Enforces conservative enterprise policy rules with a **dynamically configurable materiality threshold** (default `materiality_threshold_inr = ₹4,00,000`). High-materiality transactions (or complex split payments / FX items above threshold) cannot be auto-accepted and require human sign-off (**0.0% auto-accept rate for high-materiality transactions**).
6. **Journal Entry Validator (Gate B - Corrective Journal Safety)**: Deterministic double-entry validator enforcing debits = credits, Chart of Accounts whitelist compliance, positive amounts, duplicate prevention, and auto-post safety caps (`journal_auto_post_variance_cap_inr = ₹4,000.00`). Corrective entries are eligible for auto-posting ONLY if variance $< ₹4,000$, transaction below materiality threshold, and all accounting rules pass.
7. **Human-in-the-Loop (HITL) Queue**: Interactive review queue for `needs_review` items allowing human auditors to `Approve`, `Reject`, or `Escalate` decisions, tracking original AI decision vs final decision and calculating a live `Human Override Rate`.
8. **Evidence-First UI**: 7-part workbench sequence exposing Source Record, Selected Candidates, Structured Evidence Signals, Decision & Policy Routing, Rejected Candidates, AI Rationale, and Validated Journal Entries.
9. **Idempotent Decision Handling**: Pipeline enforcement of stable identifiers (`run_id`, `decision_id`, `source_record_hash`, `journal_entry_id`) and in-place audit log updating to guarantee zero duplicate decisions or financial actions when re-running batches.
10. **Ground-Truth Isolation**: `ground_truth.json` is generated strictly isolated and accessed ONLY post-inference during evaluation by `scoring.py`, `benchmark.py`, and `failure_analysis.py`.
11. **Multi-Seed Benchmark Suite**: Standalone runner executing isolated pipeline runs across official independent seeds (`42, 101, 777, 1234, 2026`), calculating statistical aggregates (Mean, Median, Std Dev, Min, Max), and proving **deterministic benchmark reproducibility**.

---

## 💱 Currency & FX Disclosure

- **Primary Functional Currency:** **Indian Rupee (`INR` / `₹`)** with amounts in realistic Indian B2B scale (₹15,000 to ₹8,00,000).
- **Supported Foreign Currency:** **USD** (simulating export/import transactions). Foreign currency transactions preserve their original transaction currency (`$10,000.00 USD`) while being evaluated for materiality using their **INR-normalized exposure** (`₹8,35,000.00`).
- **Benchmark FX Rate:** **Deterministic synthetic benchmark rate (1 USD = 83.50 INR)** for strict benchmark reproducibility (no live FX APIs used).

---

## 🚀 Getting Started

### Prerequisites

You need **Python 3.10+** (verified with Python 3.13) installed on your system.

### 1. Installation

Clone or copy the project files to your local workspace, navigate to the directory, and install dependencies:

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the root directory (or copy `.env.example` to `.env`) and add your Gemini API Key:

```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

### 3. Running the Dashboard

Launch the application using Streamlit:

```bash
streamlit run app.py
```

Streamlit will boot the server and open the web dashboard in your browser (typically at `http://localhost:8501`).

---

## 🧪 Running Automated Tests & Benchmarks

To run the complete automated unit test suite (107 passing tests):

```bash
py -3 -m pytest tests/
```

To run the official 5-seed benchmark evaluation:

```bash
py -c "from benchmark import BenchmarkRunner; results = BenchmarkRunner.run_five_seed_comparison(); print(results['lifts'])"
```

---

## 🎭 Narration & Live Demo Guide

1. **Initial Dashboard State**: Point out the Executive Month-End Close banner showing Operational Close Status, record breakdown, and Pass 1 deterministic throughput (752.5 records/second).
2. **Load Demo Preset**: Click **🎭 Load Demo Preset** in the sidebar. This loads Seed 42 (160 records, 15% noise) showcasing exact matches, date shifts, reference typos, split payments, duplicate decoys, and exceptions.
3. **Toggle Multi-Currency**: Toggle **🌐 Multi-Currency (INR/USD)** to generate foreign USD transactions and observe FX-aware candidate ranking with dual currency display (`$10,000 USD (₹8,35,000 INR equiv)`).
4. **Governance Safety Gates**: Explain Gate A (Transaction Materiality cap) and Gate B (Corrective Journal Auto-Post cap $< ₹4,000$).
5. **Auditor Action**: Review pending `needs_review` items in the HITL queue, view the 7-part Evidence Workbench, and click **Approve**, **Reject**, or **Escalate** to observe live Human Override Rate tracking.
6. **Export Audit Log**: Click **📥 Export Audit Log** to export complete cryptographic audit trails with execution timing metadata.

---

## ♿ Accessibility & Compliance Disclosure

- **Browser Zoom:** Verified across 67%–150% browser zoom levels for responsive text legibility, non-overlapping controls, and unclipped financial values.
- **Multi-Modal Indicators:** All operational states use structured text labels alongside color cues and symbols (e.g. `🟢 CLOSE READY`, `🟡 CONTROLLER REVIEW REQUIRED`, `🔴 EXCEPTIONS BLOCK CLOSE`).


