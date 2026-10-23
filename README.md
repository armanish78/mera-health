# mera.health — Diabetic Patient Follow-up Review Tool

A decision-support web application designed for hospital front-desk staff to review, prioritize, and conduct follow-up telephone outreach for patients whose clinical records suggest they may need diabetes care.

---

## 1. Quick Start (Windows / PowerShell)

### Prerequisites
- Python 3.10+ installed and available on PATH (`python --version`).

### Step 1: Install Dependencies
Open PowerShell in the project root directory and run:
```powershell
pip install -r requirements.txt
```

### Step 2: Launch Application
Run the Streamlit application:
```powershell
streamlit run app.py
```
The interface will automatically launch in your default browser at `http://localhost:8501`.

---

## 2. Running Automated Tests

To run the complete automated test suite:
```powershell
pytest -v
```
Unit tests use isolated synthetic fixtures to verify date boundaries, schema validation, indicator classification, and phone safety checks without exposing real patient identifiers. An end-to-end integration smoke test additionally validates data pipeline invariants on the supplied CSV export files.

---

## 3. Key Operational Features

* **Candidate Cohort Identification:** Flags 122 candidate patients across four audited evidence indicators (Diabetology visits, clinical note keywords, antidiabetic prescriptions, and glycemic labs).
* **Transparent Follow-up Status:** Evaluates scheduled `next_appointment` against a user-configurable reference date (`2026-09-29`, marked provisional):
  * **Due / potentially overdue — verify** (28 patients): Next appointment is on or before the reference date.
  * **Upcoming** (18 patients): Next appointment is scheduled in the future.
  * **Needs review — no reliable due date** (76 patients): No return date recorded in structured data. Surfaced for clinical chart review rather than assuming due dates.
* **Specialty Care Continuity:** Encounters outside Diabetology (such as Orthopaedics or Dermatology) are displayed in the patient timeline but do not reset the diabetes recall clock.
* **Patient Safety & Privacy Alerts:**
  * **Missing Phone:** Clearly flagged to prompt physical chart review.
  * **Shared Phone Numbers:** Explicit warning to verify patient name and date of birth before disclosing clinical context.
  * **Non-Diabetic Context:** Highlights Metformin prescribed in OBG (potential PCOS/GDM) and normal screening lab results.
* **Downloadable Call List:** Generates an immediate, filtered CSV of patients for front-desk outreach.

---

## 4. Project Structure

```text
mera-health-followup/
├── data/
│   └── raw/                   # Four read-only hospital CSV exports
├── scripts/
│   └── audit_data.py          # Reproducible exploratory data audit script
├── src/
│   ├── __init__.py
│   ├── cohort.py              # Candidate cohort & evidence indicator evaluation
│   ├── config.py              # Shared configuration & provisional reference date
│   ├── contact.py             # Phone data quality & household cluster alerts
│   ├── data_loader.py         # CSV loading, schema validation & safe date parsing
│   ├── followup.py            # Follow-up status determination & timeline rules
│   └── reporting.py           # Front-desk review table & CSV export builder
├── tests/
│   ├── test_cohort.py         # Cohort indicator & false-positive tests
│   ├── test_contact.py        # Phone number verification tests
│   ├── test_data_loader.py    # Schema & parser unit tests
│   ├── test_followup.py       # Due date boundary & continuity tests
│   └── test_reporting_and_integration.py # End-to-end integration smoke tests
├── app.py                     # Streamlit front-desk web interface
├── audit_output.txt           # Machine-readable output of reproducible audit
├── brief.md                   # Assessment briefing
├── DECISIONS.md               # Definitions, data handling decisions & limitations
├── email.txt                  # Original hospital request
├── PLAN.md                    # Initial pre-implementation plan (protected)
├── reply.txt                  # Reply email to hospital operations manager (<200 words)
├── requirements.txt           # Minimal runtime dependencies
└── WORKLOG.md                 # Complete exploratory audit worklog
```

---

## 5. Important Clinical & System Disclaimers

1. **Decision Support Only:** This application supports front-desk telephone outreach triaging and does **not** establish clinical diagnoses.
2. **Provisional Snapshot Date:** The default reference date of `2026-09-29` is an observed boundary of the export dataset and requires hospital confirmation.
3. **No External Dependencies:** Runs 100% locally with zero external network calls, cloud dependencies, or database configurations.
