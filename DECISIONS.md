# Decisions, Definitions, and Methodological Limitations

This document records the architectural and clinical definitions, data handling decisions, human-review flags, and system boundaries adopted for the mera.health Diabetic Patient Follow-up Review Tool.

---

## 1. Terms Defined from the Hospital's Request

The hospital's request (*"Our doctors want to see which diabetic patients are overdue for follow-up so the front desk can call them"*) left key operational concepts undefined. The following definitions were established:

### A. "Diabetic" (Candidate Cohort Definition)
* **Problem:** The export does not contain an authoritative diagnosis table, ICD-10 code, or problem list.
* **Definition Adopted:** A candidate cohort formed by the **union of four independent evidence indicators**:
  1. Specialty encounter in Diabetology (54 patients).
  2. Clinical note keyword match for diabetes terms or clinical abbreviations (112 patients).
  3. Historical prescription matching audited antidiabetic drug classes (93 patients).
  4. Glycemic laboratory test matching blood sugar or glycated hemoglobin tests (111 patients).
* **Rationale:** A multi-signal union captures 122 candidate patients across the 300 registered patients without silently dropping individuals who receive diabetes care in General Medicine or through lab monitoring.
* **Distinction & Transparency:** The tool clearly distinguishes concordant cases (50 patients meeting all four signals) from single-indicator cases (e.g., 7 patients with only screening labs, 6 with only note mentions). Single-indicator cases are flagged for careful human verification rather than claimed as confirmed diagnoses.

### B. "Relevant Encounter" (Follow-up Anchor)
* **Problem:** 20 of 54 Diabetology patients had subsequent visits to other hospital departments (General Medicine, Orthopaedics, Dermatology, Emergency).
* **Definition Adopted:** A visit is classified as a relevant follow-up encounter only if it occurred in Diabetology, contained diabetes note keywords, or resulted in an antidiabetic prescription.
* **Rationale:** Unrelated acute specialty encounters (e.g., cast removal in Orthopaedics or skin rash treatment in Dermatology) do not address chronic glycemic management and must **never silently reset** the diabetes recall clock.

### C. "Overdue" (Follow-up Status Categories)
* **Problem:** 582 of 815 visits (71.4%) have no structured `next_appointment` date. Free-text notes frequently mention informal intervals (e.g., *"review in 3 months"*).
* **Definition Adopted:** Transparent, rule-based status assignment relative to a user-selectable reference date (`2026-09-29`, marked provisional):
  1. **"Due / potentially overdue — verify":** Recorded `next_appointment` is on or before the reference date (28 patients).
  2. **"Upcoming":** Recorded `next_appointment` is after the reference date (18 patients).
  3. **"Needs review — no reliable due date":** Latest relevant encounter lacks a structured appointment date, or the candidate has only lab results (76 patients).
* **Rationale:** The application strictly avoids guessing unrecorded dates or executing unverified natural-language date arithmetic. Front-desk staff are given a verifiable list of scheduled overdue patients, while unscheduled patients are surfaced for physician review.

---

## 2. Data Anomalies Identified and Actions Taken

| Anomaly Identified | Scope / Measure | Action Taken in Application |
| :--- | :--- | :--- |
| **Missing Appointment Dates** | 71.4% of visits lack `next_appointment` (including 52.2% in Diabetology). | Categorized explicitly as *"Needs review — no reliable due date"*. Prevents misleading "overdue" claims while preserving visibility. |
| **Non-Diabetic Drug Indications** | 10 Metformin prescriptions in OBG across 5 patients (PCOS and GDM). | Flagged with a specific **Clinical Context Alert** highlighting potential non-diabetic or gestational use. |
| **Normal Screening Labs** | 7 patients have glycemic tests without notes, drugs, or specialty visits. | Flagged with a **Screening Lab Only** alert indicating ordering tests does not prove diabetes. |
| **Pediatric Family History** | Note keyword match in Paediatrics regarding a diabetic parent. | Flagged with a **Pediatric Context Alert** indicating potential family history rather than patient disease. |
| **Duplicate Lab Records** | 4 exact duplicate rows across 4 record sets in `lab_results.csv`. | Deduplicated in memory for event counting without modifying the source CSV files. |
| **Missing Phone Numbers** | 8 patients in hospital denominator (3 in candidate cohort) have blank phone fields. | Flagged with high-visibility **"MISSING PHONE"** badge instructing staff to consult physical charts. |
| **Shared Phone Numbers** | 7 phone numbers shared across 17 patients (11 candidate patients). | Flagged with **"SHARED PHONE"** badge instructing staff to confirm patient name and DOB before speaking. |
| **Provisional Reference Date** | Visits/Rx terminate on `2026-09-29`; 2 lab records extend into late 2026 and 2027. | Default reference date set to `2026-09-29` and prominently labeled **PROVISIONAL — Requires Hospital Confirmation**. |
| **Chronology Discrepancies** | 1 visit precedes registration by 10 years; 9 distinct dataset rows predate recorded patient DOB (4 visit rows, 2 lab rows, and 3 prescription rows, affecting 2 distinct patients). In addition, 2 scheduled appointment dates within visit rows predate DOB. These anomalies heavily overlap across the same patient records. | Preserved transparently in source records; surfaced for hospital verification without automated data alteration. |

---

## 3. Human Review Flags vs. Automated Decisions

The application explicitly defers decisions to human staff wherever data cannot support certainty:
1. **Clinical Diagnosis:** Never automated. Every candidate card displays source indicators and explains why the patient was flagged.
2. **Unscheduled Recall Intervals:** Front-desk staff must consult physician notes or clinic scheduling guidelines before assigning recall intervals to the 76 unscheduled candidate patients.
3. **Telephone Outreach Protocols:** Front-desk staff are given explicit warnings for shared household phone numbers to avoid unauthorized disclosure of medical details.
4. **Subsequent Unrelated Visits:** When a patient visits another department after their last diabetes encounter, the system displays the visit in the patient deep-dive without resetting the follow-up clock.

---

## 4. What This Tool CANNOT Be Trusted For (System Boundaries)

* **Definitive Diagnostic Truth:** The tool does not confirm diabetes. It flags proxy signals. Patients with normal screening labs or PCOS may appear on the candidate list.
* **Autonomous Automated Outreach:** This tool is designed for front-desk staff decision-support and telephone triaging. It should not be connected directly to automated SMS/call robodialers without human verification.
* **Emergency or Inpatient Management:** The system reflects outpatient encounter exports and does not track acute inpatient admissions.
* **Authoritative Reference Date:** `2026-09-29` is an observed boundary of the export, not a verified hospital census date. All overdue calculations depend on hospital confirmation of the active working date.
