# Data Audit Worklog: Raw Data Exploration & Findings

**Audit Scope:** `data/raw/patients.csv`, `data/raw/visits.csv`, `data/raw/lab_results.csv`, `data/raw/prescriptions.csv`
**Purpose:** Establish baseline data quality, verifiable counts, schema anomalies, and structural ambiguities before designing classification logic or follow-up rules.

**Methodology & Reproducibility:**
- **Automated Audit Script (`scripts/audit_data.py`):** Directly calculates and reproduces all core numerical aggregates: dataset row/column dimensions, column-by-column missing values, duplicate counts, key uniqueness, referential integrity metrics, date format distributions, chronological bounds, anomaly totals, phone formatting metrics, exploratory diabetes indicator counts, and cohort overlap sets.
- **Manual Data Inspection:** Complements the automated script with qualitative contextual findings: specific clinical note contents (e.g., pediatric family history context, doctors' free-text recall phrasing), department distributions across visits, detailed sub-categorization of lab tests, unit scaling discrepancies on missing-unit records, and non-diabetic indications for medications (e.g., Metformin for PCOS and GDM in OBG).

---

## 1. File Dimensions & Column Schemas *(Reproduced by audit script)*

| File | Rows | Columns | Column List |
| :--- | :--- | :--- | :--- |
| `patients.csv` | 300 | 6 | `mrn`, `name`, `dob`, `sex`, `phone`, `registered_on` |
| `visits.csv` | 815 | 7 | `visit_id`, `mrn`, `visit_date`, `department`, `doctor`, `notes`, `next_appointment` |
| `lab_results.csv` | 425 | 6 | `mrn`, `test_name`, `value`, `unit`, `reference_range`, `collected_on` |
| `prescriptions.csv` | 540 | 5 | `mrn`, `visit_id`, `drug`, `dose`, `prescribed_on` |

**Total Records Across Export:** 2,080 rows.

---

## 2. Missing Values and Duplicate Records

### Missing Values by Table and Column *(Reproduced by audit script)*
- **`patients.csv`**:
  - `phone`: 8 missing values (2.67%).
  - All other fields (`mrn`, `name`, `dob`, `sex`, `registered_on`): 0 missing (100% complete).
- **`visits.csv`**:
  - `next_appointment`: 582 missing values (71.41%). Only 233 visits have a recorded next appointment.
  - All other fields (`visit_id`, `mrn`, `visit_date`, `department`, `doctor`, `notes`): 0 missing (100% complete).
- **`lab_results.csv`**:
  - `unit`: 12 missing values (2.82%).
  - `reference_range`: 8 missing values (1.88%).
  - All other fields (`mrn`, `test_name`, `value`, `collected_on`): 0 missing (100% complete).
- **`prescriptions.csv`**:
  - 0 missing values across all columns (100% complete).

### Duplicate Records & Key Uniqueness
- **Key Uniqueness *(Reproduced by audit script)*:**
  - `patients.csv`: 0 duplicate rows; 300 unique MRNs (1 row per patient).
  - `visits.csv`: 0 duplicate rows; 815 unique `visit_id` values.
  - `prescriptions.csv`: 0 duplicate rows; 540 unique `(visit_id, drug)` combinations.
- **Duplicate Records *(Counts reproduced by audit script; contents identified via manual inspection)*:**
  - `lab_results.csv`: **4 duplicate rows across 4 distinct record sets** (8 rows total):
    - Total Cholesterol `232.0 mg/dL` on `08/11/2024` (2 identical rows).
    - Creatinine `1.0 mg/dL` on `14/09/2025` (2 identical rows).
    - HbA1c `6.8 %` on `11/12/2025` (2 identical rows).
    - PPBS `244.0 mg/dL` on `10/08/2026` (2 identical rows).

---

## 3. Cross-File Referential Integrity & ID Consistency *(Reproduced by audit script)*

- **Patient MRN Integrity:**
  - 100% referential integrity across all files.
  - Every MRN present in `visits.csv` (300 unique MRNs), `lab_results.csv` (143 unique MRNs), and `prescriptions.csv` (193 unique MRNs) exists in `patients.csv`.
  - Zero orphan records exist in secondary tables.
  - All 300 registered patients in `patients.csv` have at least one encounter recorded in `visits.csv`.
- **Visit ID & Prescription Linkage:**
  - Every `visit_id` in `prescriptions.csv` (540 records, 321 unique visit IDs) matches a valid `visit_id` in `visits.csv`.
  - Prescriptions date vs. visit date mismatches: 0.
  - Prescription MRN vs. referenced visit MRN mismatches: 0.
- **Lab Linkage:**
  - `lab_results.csv` records carry `mrn` and `collected_on`, but no `visit_id`. They must be correlated with clinical encounters by patient and date.

---

## 4. Date Formats, Temporal Bounds & Chronological Anomalies

### Date Formats and Parseability *(Reproduced by audit script)*
- `patients.dob`: 300 valid, 0 missing, 0 unparseable (`YYYY-MM-DD`: 300).
- `patients.registered_on`: 300 valid, 0 missing, 0 unparseable (`YYYY-MM-DD`: 300).
- `visits.visit_date`: 815 valid, 0 missing, 0 unparseable (`YYYY-MM-DD`: 815).
- `visits.next_appointment`: 233 valid, 582 missing, 0 unparseable (`YYYY-MM-DD`: 233).
- `lab_results.collected_on`: 425 valid, 0 missing, 0 unparseable (`DD Mon YY`: 35, `DD/MM/YYYY`: 390).
- `prescriptions.prescribed_on`: 540 valid, 0 missing, 0 unparseable (`YYYY-MM-DD`: 540).

### Observed Chronological Bounds *(Reproduced by audit script)*
- `patients.registered_on`: `2016-04-05` to `2026-09-29`.
- `visits.visit_date`: `2015-03-28` to `2026-09-29`.
- `prescriptions.prescribed_on`: `2023-10-02` to `2026-09-29`.
- `lab_results.collected_on`: `2023-10-02` to `2027-02-27`.
- `visits.next_appointment`: `2023-11-07` to `2027-03-09`.

**Provisional Reference Date:** All recorded visit encounters and prescriptions terminate on **`2026-09-29`**, though two laboratory records carry later dates in late 2026 and 2027. Consequently, `2026-09-29` serves as a provisional working reference date for overdue calculations, but requires hospital confirmation rather than being treated as a proven universal export cutoff.

### Chronological Anomalies Requiring Verification
- **Counts reproduced by audit script; specific dates noted via manual inspection:**
  1. **Visit Preceding Registration (1 case in audit script):**
     - One Paediatrics visit is dated `2015-03-28`, while the patient's registration date is recorded as `2025-03-28`. This ten-year disparity is an anomaly requiring verification against hospital records.
  2. **Future-Dated Lab Records (2 cases in audit script):**
     - Two lab entries are dated beyond the provisional reference date of `2026-09-29` (`19/12/2026` and `27/02/2027`). Both appear in the dataset alongside records from late 2025 and early 2026, representing date anomalies requiring hospital confirmation.
  3. **Scheduled Follow-up Distribution *(Reproduced by audit script)*:**
     - 206 scheduled `next_appointment` dates are on or before the provisional reference date of `2026-09-29`.
     - 27 scheduled `next_appointment` dates extend beyond the provisional reference date (through `2027-03-09`).
  4. **DOB-Relative Anomalies *(Counts reproduced by audit script)*:**
     - 1 patient has a recorded DOB after their registration date (same-day registration on date of birth is not flagged). This chronological inconsistency requires hospital verification rather than assuming patient age or clinical status.
     - 4 visit records are dated before the corresponding patient's recorded DOB (affecting 2 patients).
     - 2 laboratory records are dated before the corresponding patient's recorded DOB (affecting 1 patient).
     - 3 prescription records are dated before the corresponding patient's recorded DOB (affecting 1 patient).
     - 2 scheduled `next_appointment` dates fall before the corresponding patient's recorded DOB (affecting 1 patient).
     - No scheduled `next_appointment` date precedes its own visit date.
     - *Note:* These anomaly counts overlap — multiple records from the same patient account for most of the above. They must not be summed as distinct affected patients. All DOB-relative records require verification and must not be silently corrected.

---

## 5. Contact Data Quality & Reachability *(Reproduced by audit script)*

- **Missing Phone Numbers:** 8 patients in `patients.csv` have blank phone fields and cannot be telephoned without an alternative administrative lookup.
- **10-Digit-Formatted Numbers:** 292 patients have populated 10-digit phone strings (all using the `9000` prefix). The presence of a formatted phone string in the export indicates structural completeness, but does not confirm whether a number is active, assigned, or currently reachable.
- **Shared Phone Numbers (Household / Family Clusters):**
  - **7 phone numbers are shared across multiple patients**, representing **17 patient records**:
    - 3 numbers are each shared by 3 patients (9 patients total).
    - 4 numbers are each shared by 2 patients (8 patients total).
- **Operational Consideration:** When front-desk staff dial a shared number, they must confirm the specific patient's identity (e.g., name, date of birth) before disclosing clinical context.

---

## 6. Exploratory Diabetes-Related Evidence Indicators

*Note: The following indicators represent exploratory pattern searches across the raw data. They demonstrate where diabetes-related signals appear, but do not constitute confirmed clinical diagnoses.*

### A. Visits Data (`visits.csv`)
- **Department Breakdown (815 visits total; identified via manual inspection):**
  - General Medicine: 333
  - Diabetology: 115 (54 unique patients) *(reproduced by audit script)*
  - Orthopaedics: 71
  - Dermatology: 62
  - ENT: 45
  - Paediatrics: 44
  - Emergency: 36
  - OBG: 32
  - Dental: 28
  - Ophthalmology: 27
  - Cardiology: 22
- **Clinical Note Keyword Matches *(Reproduced by audit script)*:**
  - Case-insensitive regex matching diabetes-related terms and word extensions (`diabet\w*` capturing `"diabetes"` and `"diabetic"`, along with `dm`, `dm2`, `t2dm`, `type 2`, `niddm`, `hba1c`, `a1c`, `fbs`, `ppbs`, `grbs`, `sugars`, `oha`) identifies **283 visits across 112 unique patients**.
- **Unstructured Recall Instructions vs. Blank Scheduling Field *(Manual inspection)*:**
  - 60 of 115 Diabetology visits (52.17%) have a blank `next_appointment` field.
  - In many of these encounters, the physician wrote natural-language follow-up intervals into the clinical note (e.g., review in 1 month, 6 weeks, 3 months, or 6 months).
- **Family History Keyword Match *(Manual inspection)*:**
  - In Paediatrics, a visit note mentions a parent's concern regarding a diabetic father on insulin. Naive keyword search matches this note, highlighting why text matching alone cannot establish a patient diagnosis.

### B. Prescriptions Data (`prescriptions.csv`)
- **Medication Pattern Matches *(Reproduced by audit script)*:**
  - **280 prescription records match the configured antidiabetic medication-name patterns** across 31 distinct drug strings and **93 unique patients**.
  - Matched drug classes include Biguanides (Metformin), Sulfonylureas (Glimepiride, Gliclazide), DPP-4 inhibitors (Sitagliptin, Vildagliptin), SGLT-2 inhibitors (Dapagliflozin), and Insulins (Glargine, Degludec, Lispro, Aspart, Mixtard).
  - *Methodological note:* Matching medication name patterns indicates historical prescription entries in the export; it does not independently verify active therapy, patient adherence, or a confirmed diabetes diagnosis.
- **Specialty Context & Non-Diabetic Indications *(Counts reproduced by audit script; clinical context from manual inspection)*:**
  - 128 total Metformin prescriptions exist across the dataset.
  - While 118 are prescribed in General Medicine and Diabetology, **10 prescriptions appear in Obstetrics & Gynecology (OBG) across 5 patients**.
  - Within OBG, manual review reveals that 4 patients were treated for polycystic ovary syndrome (PCOS/PCOD), and 1 patient was managed for Gestational Diabetes Mellitus (GDM) during pregnancy.

### C. Laboratory Results (`lab_results.csv`)
- **Glycemic Biomarkers *(Total reproduced by audit script; sub-breakdown from manual inspection)*:**
  - **300 lab tests across 111 unique patients** match glycemic test names:
    - HbA1c variants: `HbA1c` (130), `A1C` (21), `Glycated Hb` (17). Total: 168.
    - Fasting glucose variants: `FBS` (76), `Fasting Glucose` (8), `Glucose (F)` (3). Total: 87.
    - Post-prandial variants: `PPBS` (41), `Glucose (PP)` (2), `Post Prandial Glucose` (2). Total: 45.
- **Unit Heterogeneity & Measurement Standards *(Manual inspection)*:**
  - `A1C` is recorded in `%` (21 tests).
  - `Glycated Hb` is recorded in `mmol/mol` (17 tests, IFCC standard).
  - `HbA1c` is recorded in `%` (127 tests); 3 `HbA1c` records have no unit recorded (see below).
  - Glucose variants in `mmol/L` (10 tests): `Fasting Glucose` (8) and `Post Prandial Glucose` (2).
  - Glucose variants in `mg/dL` (122 tests): `FBS` (76), `PPBS` (41), `Glucose (F)` (3), and `Glucose (PP)` (2).
- **Missing Units & Scaling Discrepancies *(Manual inspection)*:**
  - 3 `HbA1c` records have missing units and values of `65.0`, `65.0`, and `68.0`. These numeric values align with the IFCC standard (`mmol/mol`, corresponding to ~8.1%–8.4% NGSP), rather than percentage values. Units remain unconfirmed and should not be assigned automatically.
- **Screening Results *(Counts reproduced by audit script; interpretation from manual inspection)*:**
  - 7 patients have glycemic lab records with no diabetes visit notes, no antidiabetic prescriptions, and no Diabetology encounters. Manual inspection of their results shows mostly normal blood glucose or HbA1c values, demonstrating that lab test ordering does not equate to a diabetes diagnosis.

---

## 7. Cohort Overlap Analysis *(Reproduced by audit script)*

The four exploratory indicators intersect across the 300 registered patients as follows:

| Criteria / Evidence Source | Patient Count | Description |
| :--- | :--- | :--- |
| **Total Registered Patients** | **300** | Full patient denominator |
| Diabetology Department Visits | 54 | Patients seen in specialty Diabetology |
| Clinical Note Keyword Matches | 112 | Patients with diabetes-related tokens in notes |
| Antidiabetic Prescriptions | 93 | Patients with records matching antidiabetic medication-name patterns |
| Glycemic Lab Tests | 111 | Patients with blood sugar or HbA1c lab tests |
| **Union of All 4 Indicators** | **122** | Patients meeting at least one exploratory indicator (not confirmed diabetic) |
| Concordant on all 4 indicators | 50 | Patients meeting all four signals |
| Concordant on Notes, Rx, and Labs | 85 | Patients meeting notes, drug, and lab signals |
| ONLY Glycemic Labs | 7 | Screening tests without diagnostic notes or drugs |
| ONLY Clinical Notes Matches | 6 | Keyword matches without drugs, labs, or Diabetology |
| ONLY Prescriptions | 0 | No patient has prescriptions without other indicators |

*Note on counts:* Keyword matching that includes word extensions for `"diabetes"` and `"diabetic"` identifies 112 patients with notes-based signals, resulting in a candidate union of 122 patients who have at least one exploratory indicator.

---

## 8. Material Findings Impacting Call List Accuracy *(Synthesis)*

1. **Missing Follow-up Dates (71.41% unpopulated):**
   - Evaluating "overdue" solely by comparing `next_appointment` against a reference date excludes the majority of encounters, including 52.17% of Diabetology visits where recall instructions were written into clinical notes.
2. **Specialty Care Continuity & Encounter Patterns:**
   - 20 of 54 Diabetology patients had a subsequent visit to another department (16 in General Medicine, 2 in Orthopaedics, 1 in Dermatology, and 1 in Emergency).
   - In clinical notes, General Medicine encounters frequently document diabetes management, whereas visits in acute or procedure-focused specialties (such as Dermatology or Orthopaedics) rarely address diabetes. However, the policy question of whether encounters outside Diabetology count toward follow-up or reset the recall clock remains unresolved and requires hospital guidance.
3. **Exploratory Signals vs. Confirmed Diagnoses:**
   - Meeting one or more exploratory indicators does not confirm a diagnosis: 122 patients exhibit at least one exploratory signal, but this includes non-diabetic indications (e.g., PCOS in OBG), non-diagnostic mentions (e.g., family history in Paediatrics), and routine screening tests with normal lab values.
4. **Data Handling Considerations:**
   - 4 duplicate lab rows should not be counted as separate clinical events.
   - Lab units in `mmol/L` and `mmol/mol` must be standardized before evaluating against clinical thresholds.
   - Future-dated records and pre-registration visit dates require verification rather than automatic correction.
   - Additional DOB-relative anomalies (visits, labs, prescriptions, and scheduled appointments predating the patient's recorded DOB) were identified in the audit and require hospital verification. These anomalies overlap across the same patient records and must not be silently corrected or summed as distinct cases.
5. **Call Delivery Considerations:**
   - 8 patients cannot be phoned due to missing numbers.
   - 17 patients share contact numbers across 7 phone numbers, requiring verification at call time.

---

## 9. Measured Facts vs. Working Assumptions and Unanswered Questions

| Dimension | Measured Fact (Verified in Data) | Working Assumption / Unanswered Question (Requires Hospital Alignment) |
| :--- | :--- | :--- |
| **Snapshot Date** | Visit and prescription records end on `2026-09-29`, while two lab records are dated later. | `2026-09-29` serves as a provisional reference date, but the exact "as-of" snapshot date requires hospital confirmation. |
| **Cohort Criteria** | 122 patients exhibit at least one exploratory indicator, but this includes non-diabetic PCOS and family history cases. | Which specific clinical definition (physician diagnosis, active therapy, or lab threshold) determines patient eligibility for outreach? |
| **Overdue Criteria** | 233 visits have explicit `next_appointment` dates; 582 do not. Doctors frequently wrote review intervals in notes. | When `next_appointment` is absent, what recall interval or policy determines that a patient is overdue? |
| **Relevant Encounters** | Observed records show diabetes care documented primarily in Diabetology and General Medicine encounters, with other specialties focusing on unrelated complaints. | Which encounter types or clinical departments count as valid diabetes follow-up for resetting the recall timeline? |
| **Contact Exceptions** | 8 patients have no phone numbers; 17 share phone numbers across 7 distinct numbers. | How should front-desk staff triage overdue patients who lack valid telephone contact info? |
