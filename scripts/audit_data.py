#!/usr/bin/env python3
"""
scripts/audit_data.py

Reproducible Data Audit for mera.health Engineering Assessment.
Audits the four raw CSV exports in data/raw/ using only the Python standard library.

Computes:
- Dataset dimensions and column schemas
- Missing values and duplicate records
- Referential integrity across files (including prescription MRN vs visit MRN consistency)
- Date formats, chronological bounds, and unparseable date tracking
- Phone completeness and shared contact numbers
- Four exploratory diabetes indicators and their cohort overlaps
- Methodological notes and identified ambiguities

Privacy constraint: Prints aggregate counts and metadata only.
Does not print patient names, MRNs, phone numbers, or full clinical notes.
"""

import csv
import re
from datetime import datetime
from collections import Counter
from pathlib import Path

# Paths to raw data:
# BASE_DIR finds the project root (parent directory of 'scripts/')
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"

# Dictionary mapping friendly table names to their actual file paths on disk
FILES = {
    "patients": DATA_DIR / "patients.csv",
    "visits": DATA_DIR / "visits.csv",
    "lab_results": DATA_DIR / "lab_results.csv",
    "prescriptions": DATA_DIR / "prescriptions.csv",
}


def load_csv(path):
    """
    Load a CSV file into memory using Python's standard csv module.

    csv.DictReader reads each row as an OrderedDict/dict where keys are column headers.
    'utf-8-sig' transparently strips any UTF-8 Byte Order Mark (BOM) if present.
    Returns:
      rows: list of row dictionaries
      fieldnames: list of column header strings in order
    """
    rows = []
    with open(path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for r in reader:
            rows.append(r)
    return rows, fieldnames


def parse_date(date_str):
    """
    Safely parse a date string across three expected date formats:
      1. '%Y-%m-%d' : ISO standard (e.g., '2024-03-28') used in patients, visits, rx
      2. '%d/%m/%Y' : Day/Month/Year (e.g., '03/04/2024') used in most lab results
      3. '%d %b %y' : Day Abbreviated-Month 2-digit Year (e.g., '2 Oct 23') in older labs

    Returns a datetime.date object on success.
    Returns None if the string is empty, invalid, or cannot be parsed.
    Using try/except ensures an unparseable date will never crash the script.
    """
    if not date_str or not date_str.strip():
        return None
    cleaned = date_str.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %b %y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass  # Try the next format in the tuple
    return None


def detect_date_format(date_str):
    """
    Classify the textual structure of a date string using regular expressions:
    - '^\\d{4}-\\d{2}-\\d{2}$'       : 4 digits, dash, 2 digits, dash, 2 digits (YYYY-MM-DD)
    - '^\\d{1,2}/\\d{1,2}/\\d{4}$'   : 1-2 digits, slash, 1-2 digits, slash, 4 digits (DD/MM/YYYY)
    - '^\\d{1,2}\\s+[A-Za-z]{3}\\s+\\d{2}$' : 1-2 digits, space, 3-letter month, space, 2-digit year (DD Mon YY)
    Returns 'empty' if blank, or 'other' if non-empty but unrecognized.
    """
    if not date_str or not date_str.strip():
        return "empty"
    s = date_str.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return "YYYY-MM-DD"
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", s):
        return "DD/MM/YYYY"
    if re.match(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{2}$", s):
        return "DD Mon YY"
    return "other"


def main():
    print("=" * 75)
    print("MERA.HEALTH DATA AUDIT - REPRODUCIBLE EXPLORATORY REPORT")
    print("Data directory: data/raw")
    print("=" * 75)

    # Pre-flight check: Ensure all 4 CSV files exist before attempting to process
    for name, path in FILES.items():
        if not path.is_file():
            print(f"ERROR: Missing expected file at {path}")
            return

    # Load all four tables into memory as lists of dictionaries
    patients, p_cols = load_csv(FILES["patients"])
    visits, v_cols = load_csv(FILES["visits"])
    labs, l_cols = load_csv(FILES["lab_results"])
    rx, r_cols = load_csv(FILES["prescriptions"])

    # ---------------------------------------------------------
    # 1. Dataset Dimensions & Column Schemas
    # ---------------------------------------------------------
    # Purpose: Verifies record volume and expected column headers across the export.
    # Why it matters: Confirms that the hospital export matches expected file sizes
    # (~2,000 rows total) and has all necessary fields before analyzing contents.
    print("\n1. DATASET DIMENSIONS & COLUMN SCHEMAS")
    print("-" * 55)
    total_records = len(patients) + len(visits) + len(labs) + len(rx)
    datasets = [
        ("patients.csv", patients, p_cols),
        ("visits.csv", visits, v_cols),
        ("lab_results.csv", labs, l_cols),
        ("prescriptions.csv", rx, r_cols),
    ]
    for filename, data, cols in datasets:
        print(f"  {filename:<18}: {len(data):>5} rows | {len(cols)} columns: {cols}")
    print(f"  {'Total records':<18}: {total_records:>5} rows across all files")

    # ---------------------------------------------------------
    # 2. Missing Values & Duplicate Records
    # ---------------------------------------------------------
    # Purpose: Detects missing fields, duplicate entries, and primary key uniqueness.
    # Why it matters: Identifies data gaps (e.g., missing next_appointment dates or phone numbers)
    # and prevents duplicate lab or visit records from distorting patient history.
    print("\n2. MISSING VALUES & DUPLICATES")
    print("-" * 55)
    print("Missing Values by Table and Column:")
    for filename, data, cols in datasets:
        # Dictionary comprehension: counts how many rows have None or empty/whitespace strings
        # sum(1 for r in data if ...) is a Python idiom: yields 1 for each matching row and sums them
        null_counts = {
            c: sum(1 for r in data if r[c] is None or r[c].strip() == "")
            for c in cols
        }
        # Filter down to only columns that actually have missing values (> 0)
        active_nulls = {k: v for k, v in null_counts.items() if v > 0}
        if active_nulls:
            for col, count in active_nulls.items():
                pct = (count / len(data)) * 100
                print(f"  {filename:<18} [{col}]: {count} missing ({pct:.2f}%)")
        else:
            print(f"  {filename:<18} : 0 missing values across all columns")

    print("\nDuplicate Records Check:")
    for filename, data, cols in datasets:
        # Convert each row dict into a tuple of values: e.g. ('SVH001', 'John', '1980-01-01', ...)
        # Tuples are immutable and hashable, allowing Counter to count exact row occurrences
        tuples = [tuple(r[c] for c in cols) for r in data]
        counts = Counter(tuples)
        # If a row appears 3 times, there is 1 original and (3 - 1) = 2 redundant duplicates
        exact_dups = sum(cnt - 1 for cnt in counts.values() if cnt > 1)
        duplicate_sets = sum(1 for cnt in counts.values() if cnt > 1)
        print(f"  {filename:<18}: {exact_dups} duplicate rows (across {duplicate_sets} distinct record sets)")

    # Key Uniqueness Checks:
    # Converting a list to a set (e.g., set(p_mrns)) automatically removes duplicates.
    # Comparing len(set(keys)) with len(keys) verifies if keys are 100% unique.
    p_mrns = [r["mrn"] for r in patients]
    v_ids = [r["visit_id"] for r in visits]
    rx_keys = [(r["visit_id"], r["drug"]) for r in rx]
    print(f"  Unique patients MRN : {len(set(p_mrns))} / {len(patients)}")
    print(f"  Unique visit IDs    : {len(set(v_ids))} / {len(visits)}")
    print(f"  Unique (visit_id, drug) in rx: {len(set(rx_keys))} / {len(rx)}")

    # ---------------------------------------------------------
    # 3. Referential Integrity Across Files
    # ---------------------------------------------------------
    # Purpose: Verifies foreign-key linkages between patients, visits, labs, and prescriptions.
    # Why it matters: Ensures there are no "orphaned" records (e.g. lab results or visits for
    # an MRN not in patients.csv) and confirms every prescription links to the right patient & visit.
    print("\n3. REFERENTIAL INTEGRITY & ID CONSISTENCY")
    print("-" * 55)
    # Build unique sets of identifiers for fast set-difference operations:
    p_mrn_set = set(p_mrns)                     # All registered patient MRNs
    v_mrn_set = set(r["mrn"] for r in visits)   # All MRNs appearing in visits
    l_mrn_set = set(r["mrn"] for r in labs)     # All MRNs appearing in labs
    r_mrn_set = set(r["mrn"] for r in rx)       # All MRNs appearing in prescriptions
    v_id_set = set(v_ids)                       # All valid visit IDs

    rx_vid_set = set(r["visit_id"] for r in rx)
    orphaned_v_mrns = v_mrn_set - p_mrn_set
    orphaned_l_mrns = l_mrn_set - p_mrn_set
    orphaned_r_mrns = r_mrn_set - p_mrn_set
    orphaned_rx_vids = rx_vid_set - v_id_set

    print(f"  Visits MRNs not in patients        : {len(orphaned_v_mrns)}")
    print(f"  Labs MRNs not in patients          : {len(orphaned_l_mrns)}")
    print(f"  Prescriptions MRNs not in patients : {len(orphaned_r_mrns)}")
    print(f"  Prescriptions visit_ids not in visits: {len(orphaned_rx_vids)}")
    print(f"  Patients with 0 visits             : {len(p_mrn_set - v_mrn_set)}")
    print(f"  Patients with 0 visits/labs/rx     : {len(p_mrn_set - (v_mrn_set | l_mrn_set | r_mrn_set))}")
    print(f"  Unique patient MRNs in visits.csv         : {len(v_mrn_set)}")
    print(f"  Unique patient MRNs in lab_results.csv    : {len(l_mrn_set)}")
    print(f"  Unique patient MRNs in prescriptions.csv  : {len(r_mrn_set)}")
    print(f"  Unique visit_id in prescriptions.csv      : {len(rx_vid_set)}")

    # Check that prescriptions.prescribed_on matches visits.visit_date for the same visit_id.
    # v_date_map provides an O(1) hash table lookup: visit_id -> visit_date string
    v_date_map = {r["visit_id"]: r["visit_date"] for r in visits}
    rx_date_mismatches = sum(
        1 for r in rx if v_date_map.get(r["visit_id"]) != r["prescribed_on"]
    )
    print(f"  Prescription date vs Visit date mismatches: {rx_date_mismatches}")

    # Check that the MRN on a prescription row matches the MRN on the corresponding visit row.
    # v_mrn_map provides an O(1) lookup: visit_id -> mrn
    v_mrn_map = {r["visit_id"]: r["mrn"] for r in visits}
    rx_mrn_mismatches = sum(
        1 for r in rx if r.get("visit_id") in v_mrn_map and r["mrn"] != v_mrn_map[r["visit_id"]]
    )
    print(f"  Prescription MRN vs Visit MRN mismatches   : {rx_mrn_mismatches}")

    # ---------------------------------------------------------
    # 4. Date Formats, Chronology & Anomalies
    # ---------------------------------------------------------
    # Purpose: Validates date parsing, measures data spans, and detects date entry errors.
    # Why it matters: Mixed date formats (e.g. DD/MM/YYYY vs DD Mon YY in labs) cause silent
    # errors if parsed naively. Year typos (e.g. 2015 vs 2025, or 2027) distort chronological order.
    print("\n4. DATE FORMATS, BOUNDS & ANOMALIES")
    print("-" * 55)
    date_cols = [
        ("patients", patients, "dob"),
        ("patients", patients, "registered_on"),
        ("visits", visits, "visit_date"),
        ("visits", visits, "next_appointment"),
        ("lab_results", labs, "collected_on"),
        ("prescriptions", rx, "prescribed_on"),
    ]

    # Audit each date field:
    # Tracks valid parsed dates, missing dates, and unparseable dates independently.
    # parsed_date_store stores valid datetime.date objects for computing min and max bounds safely.
    parsed_date_store = {}
    for tablename, data, col in date_cols:
        key = f"{tablename}.{col}"
        fmt_counts = Counter()
        missing_count = 0
        unparseable_count = 0
        parsed_dates = []

        for r in data:
            raw_val = r[col]
            if not raw_val or not raw_val.strip():
                missing_count += 1
            else:
                fmt = detect_date_format(raw_val)
                fmt_counts[fmt] += 1
                dt = parse_date(raw_val)
                if dt is None:
                    unparseable_count += 1
                else:
                    parsed_dates.append(dt)

        parsed_date_store[key] = parsed_dates
        valid_count = len(parsed_dates)
        print(f"  {key:<27}: {valid_count:>3} valid, {missing_count:>3} missing, {unparseable_count:>3} unparseable | formats: {dict(fmt_counts)}")

    # Helper function: returns min to max string, or fallback if the list is empty
    def safe_date_bounds(date_list):
        if not date_list:
            return "N/A (no valid dates)"
        return f"{min(date_list)} to {max(date_list)}"

    p_reg_dates = parsed_date_store.get("patients.registered_on", [])
    v_dates = parsed_date_store.get("visits.visit_date", [])
    v_next = parsed_date_store.get("visits.next_appointment", [])
    l_dates = parsed_date_store.get("lab_results.collected_on", [])
    r_dates = parsed_date_store.get("prescriptions.prescribed_on", [])

    print("\nObserved Chronological Bounds (Valid Dates Only):")
    print(f"  patients.registered_on  : {safe_date_bounds(p_reg_dates)}")
    print(f"  visits.visit_date       : {safe_date_bounds(v_dates)}")
    print(f"  visits.next_appointment : {safe_date_bounds(v_next)}")
    print(f"  lab_results.collected_on: {safe_date_bounds(l_dates)}")
    print(f"  prescriptions.prescribed: {safe_date_bounds(r_dates)}")

    # Chronological Integrity:
    # A patient cannot have a visit before they were registered. If visit_date < registered_on,
    # it indicates a chronological anomaly requiring verification (e.g. 2015 vs 2025).
    p_reg_map = {r["mrn"]: parse_date(r["registered_on"]) for r in patients}
    visits_before_reg = 0
    for r in visits:
        vd = parse_date(r["visit_date"])
        rd = p_reg_map.get(r["mrn"])
        if vd and rd and vd < rd:
            visits_before_reg += 1

    print(f"\nChronological Integrity Checks:")
    print(f"  Visits with visit_date < registered_on: {visits_before_reg}")

    # Provisional reference date check:
    # Visit and prescription encounters end on 2026-09-29, while two lab records carry later dates.
    # 2026-09-29 serves as a provisional reference date requiring hospital confirmation,
    # rather than a confirmed universal export cutoff. Later lab records require verification.
    ref_date = datetime.strptime("2026-09-29", "%Y-%m-%d").date()
    future_labs_count = sum(1 for d in l_dates if d > ref_date)
    print(f"  Labs with collected_on > provisional reference date (2026-09-29): {future_labs_count}")

    # Breakdown of scheduled next appointments relative to the provisional reference date:
    # appts_past_ref: next_appointment is on or before reference date
    # appts_future_ref: next_appointment is after reference date (scheduled for future follow-up)
    appts_past_ref = sum(1 for d in v_next if d <= ref_date)
    appts_future_ref = sum(1 for d in v_next if d > ref_date)
    print(f"  Scheduled next_appointment <= provisional reference date : {appts_past_ref}")
    print(f"  Scheduled next_appointment > provisional reference date  : {appts_future_ref}")

    # DOB-relative integrity checks:
    # A patient's DOB should precede every recorded encounter. Records predating the patient's
    # own DOB indicate a systematic date-entry error (e.g. a swapped or mistyped year) and
    # must be verified against hospital records before any date arithmetic is applied.
    # Note: these anomalies may overlap — the same patient record can appear in multiple counts.

    # Build a DOB lookup: mrn -> parsed date-of-birth
    dob_map = {r["mrn"]: parse_date(r["dob"]) for r in patients}

    # Patients whose recorded DOB is strictly after their registration date
    # (Same-day DOB and registration date, such as newborn registration, is not automatically flagged;
    # DOB > reg_on represents a chronological inconsistency requiring hospital verification)
    pts_dob_gt_reg = sum(
        1 for r in patients
        if dob_map.get(r["mrn"]) and p_reg_map.get(r["mrn"])
        and dob_map[r["mrn"]] > p_reg_map[r["mrn"]]
    )
    # Visits whose visit_date falls before the patient's DOB (patient not yet born)
    visits_before_dob_count = sum(
        1 for r in visits
        if parse_date(r["visit_date"]) and dob_map.get(r["mrn"])
        and parse_date(r["visit_date"]) < dob_map[r["mrn"]]
    )
    visits_before_dob_mrns = len({
        r["mrn"] for r in visits
        if parse_date(r["visit_date"]) and dob_map.get(r["mrn"])
        and parse_date(r["visit_date"]) < dob_map[r["mrn"]]
    })
    # Lab records collected before the patient's DOB
    labs_before_dob_count = sum(
        1 for r in labs
        if parse_date(r["collected_on"]) and dob_map.get(r["mrn"])
        and parse_date(r["collected_on"]) < dob_map[r["mrn"]]
    )
    labs_before_dob_mrns = len({
        r["mrn"] for r in labs
        if parse_date(r["collected_on"]) and dob_map.get(r["mrn"])
        and parse_date(r["collected_on"]) < dob_map[r["mrn"]]
    })
    # Prescriptions dated before the patient's DOB
    rx_before_dob_count = sum(
        1 for r in rx
        if parse_date(r["prescribed_on"]) and dob_map.get(r["mrn"])
        and parse_date(r["prescribed_on"]) < dob_map[r["mrn"]]
    )
    rx_before_dob_mrns = len({
        r["mrn"] for r in rx
        if parse_date(r["prescribed_on"]) and dob_map.get(r["mrn"])
        and parse_date(r["prescribed_on"]) < dob_map[r["mrn"]]
    })
    # Scheduled next_appointments falling before the patient's DOB
    appts_before_dob_count = sum(
        1 for r in visits
        if parse_date(r.get("next_appointment", "")) and dob_map.get(r["mrn"])
        and parse_date(r["next_appointment"]) < dob_map[r["mrn"]]
    )
    appts_before_dob_mrns = len({
        r["mrn"] for r in visits
        if parse_date(r.get("next_appointment", "")) and dob_map.get(r["mrn"])
        and parse_date(r["next_appointment"]) < dob_map[r["mrn"]]
    })
    # Sanity check: next_appointment should never precede the visit itself
    appts_before_visit = sum(
        1 for r in visits
        if parse_date(r.get("next_appointment", "")) and parse_date(r["visit_date"])
        and parse_date(r["next_appointment"]) < parse_date(r["visit_date"])
    )

    print(f"  Patients with DOB after registration date          : {pts_dob_gt_reg}")
    print(f"  Visits predating patient DOB                       : {visits_before_dob_count} records, {visits_before_dob_mrns} {'patient' if visits_before_dob_mrns == 1 else 'patients'}")
    print(f"  Lab records predating patient DOB                  : {labs_before_dob_count} records, {labs_before_dob_mrns} {'patient' if labs_before_dob_mrns == 1 else 'patients'}")
    print(f"  Prescriptions predating patient DOB                : {rx_before_dob_count} records, {rx_before_dob_mrns} {'patient' if rx_before_dob_mrns == 1 else 'patients'}")
    print(f"  Scheduled appts predating patient DOB              : {appts_before_dob_count} records, {appts_before_dob_mrns} {'patient' if appts_before_dob_mrns == 1 else 'patients'}")
    print(f"  Scheduled next_appointment before its visit date   : {appts_before_visit}")

    # ---------------------------------------------------------
    # 5. Contact Data Quality & Reachability
    # ---------------------------------------------------------
    # Purpose: Assesses patient reachability for front-desk phone calls.
    # Why it matters: The front desk cannot call patients with missing phone numbers, and shared
    # phone numbers (household/family members) require caller verification to avoid privacy issues.
    print("\n5. CONTACT DATA QUALITY & REACHABILITY")
    print("-" * 55)
    phones = [r["phone"].strip() for r in patients if r["phone"] and r["phone"].strip()]
    phone_counts = Counter(phones)
    # shared_phones filters to phone numbers that appear more than once (> 1) in patients.csv
    shared_phones = {ph: cnt for ph, cnt in phone_counts.items() if cnt > 1}
    total_shared_patients = sum(shared_phones.values())

    print(f"  Total registered patients             : {len(patients)}")
    print(f"  Patients with missing phone number     : {len(patients) - len(phones)}")
    print(f"  Patients with populated phone number   : {len(phones)}")
    print(f"  Distinct phone numbers                : {len(phone_counts)}")
    print(f"  Phone numbers shared by multiple pts  : {len(shared_phones)}")
    print(f"  Total patient records sharing a phone : {total_shared_patients}")
    phone_lengths = Counter(len(ph) for ph in phones)
    print(f"  Phone string lengths distribution     : {dict(phone_lengths)}")

    # ---------------------------------------------------------
    # 6. Four Diabetes-Related Evidence Indicators
    # ---------------------------------------------------------
    # Purpose: Explores where diabetes signals appear across departments, notes, drugs, and labs.
    # IMPORTANT: These are exploratory keyword and string indicators to understand data patterns,
    # NOT confirmed clinical diagnoses. Each indicator alone has limitations and false positives.
    print("\n6. FOUR DIABETES-RELATED EVIDENCE INDICATORS")
    print("-" * 55)

    # Indicator 1: Diabetology Department Visits
    # Method: Simple filter on visits table where department == 'Diabetology'
    # Specificity: High for diabetic care, but misses diabetics managed in General Medicine.
    diab_dept_visits = [r for r in visits if r["department"] == "Diabetology"]
    mrn_dept_diab = set(r["mrn"] for r in diab_dept_visits)
    print(f"  Indicator 1: Diabetology Department Visits")
    print(f"    Method   : visits[department == 'Diabetology']")
    print(f"    Count    : {len(diab_dept_visits)} visits across {len(mrn_dept_diab)} unique patients")

    # Indicator 2: Clinical Note Keyword Matches (Exploratory Indicator)
    # Method: Regular expression token search across free-text visit notes
    # Pattern explanation:
    #   \b          : word boundary anchor (ensures we don't match inside words like 'epidm')
    #   diabet\w*   : matches 'diabet' + letters (matches 'diabetes', 'diabetic', 'diabetology')
    #   dm|dm2|t2dm : matches standard clinical abbreviations for diabetes mellitus
    #   type\s*2    : matches 'type 2' or 'type2'
    #   hba1c|a1c   : matches glycated hemoglobin references in notes
    #   fbs|ppbs|grbs: fasting, post-prandial, or general random blood sugar
    #   sugars?     : matches 'sugar' or 'sugars'
    #   oha         : matches oral hypoglycemic agents
    #   re.IGNORECASE: case-insensitive matching
    # Caveat: Matches family history mentions (e.g. 'Father diabetic') or screening notes.
    note_pattern = re.compile(
        r"\b(diabet\w*|dm|dm2|t2dm|type\s*2|niddm|hba1c|a1c|fbs|ppbs|grbs|sugars?|oha)\b",
        re.IGNORECASE,
    )
    dm_note_visits = [r for r in visits if note_pattern.search(r["notes"] or "")]
    mrn_notes_dm = set(r["mrn"] for r in dm_note_visits)
    print(f"\n  Indicator 2: Clinical Note Keyword Matches (Exploratory)")
    print(f"    Method   : Regex token search on visits.notes (exploratory, not clinical diagnosis)")
    print(f"    Tokens   : diabet*, diabetes, diabetic, dm, dm2, t2dm, type 2, niddm, hba1c, a1c, fbs, ppbs, grbs, sugars, oha")
    print(f"    Count    : {len(dm_note_visits)} visits across {len(mrn_notes_dm)} unique patients")

    # Indicator 3: Antidiabetic Prescriptions
    # Method: Case-insensitive substring search for selected medication-name patterns
    # in historical prescription records exported in prescriptions.csv.
    # A match means the drug name string contains a configured pattern; it does NOT
    # establish that the patient is currently on active therapy or confirm a diagnosis.
    # Classes included: Biguanides (metformin), Sulfonylureas (glimepiride, gliclazide),
    # DPP-4 inhibitors (sitagliptin, vildagliptin), SGLT-2 inhibitors (dapagliflozin), and Insulins.
    # Caveat: Metformin is also prescribed for PCOS (polycystic ovary syndrome) in non-diabetics.
    antidiabetic_classes = [
        "metformin", "glimepiride", "gliclazide", "sitagliptin", "vildagliptin",
        "dapagliflozin", "empagliflozin", "insulin", "mixtard", "glargine",
        "degludec", "lispro", "aspart"
    ]
    rx_pattern = re.compile("|".join(antidiabetic_classes), re.IGNORECASE)
    dm_rx_rows = [r for r in rx if rx_pattern.search(r["drug"] or "")]
    mrn_rx_dm = set(r["mrn"] for r in dm_rx_rows)
    unique_dm_drugs = set(r["drug"] for r in dm_rx_rows)
    print(f"\n  Indicator 3: Antidiabetic Prescriptions")
    print(f"    Method   : Substring match on antidiabetic drug classes in prescriptions.drug")
    print(f"    Classes  : Biguanides, Sulfonylureas, DPP-4i, SGLT-2i, Insulins")
    print(f"    Count    : {len(dm_rx_rows)} prescriptions ({len(unique_dm_drugs)} distinct drug strings) across {len(mrn_rx_dm)} unique patients")

    # Indicator 4: Glycemic Lab Tests
    # Method: Matches test_name against known blood glucose / glycated hemoglobin tests.
    # Tests include: HbA1c, A1C, Glycated Hb, Fasting Blood Sugar (FBS), Post-Prandial Blood Sugar (PPBS).
    # Caveat: Ordering a screening test does not mean the patient has diabetes (test may be normal).
    glycemic_test_names = {
        "hba1c", "a1c", "glycated hb", "fbs", "glucose (f)",
        "fasting glucose", "ppbs", "glucose (pp)", "post prandial glucose"
    }
    dm_lab_rows = [r for r in labs if (r["test_name"] or "").strip().lower() in glycemic_test_names]
    mrn_labs_dm = set(r["mrn"] for r in dm_lab_rows)
    print(f"\n  Indicator 4: Glycemic Lab Tests")
    print(f"    Method   : Matching test_name against glycemic biomarkers in lab_results.csv")
    print(f"    Tests    : HbA1c/A1C/Glycated Hb, Fasting Glucose/FBS, Post-Prandial/PPBS")
    print(f"    Count    : {len(dm_lab_rows)} lab tests across {len(mrn_labs_dm)} unique patients")

    # ---------------------------------------------------------
    # 7. Cohort Overlap Analysis
    # ---------------------------------------------------------
    # Purpose: Analyzes how the four indicators intersect using mathematical set theory.
    # Set Operations Explained:
    #   | (Union)       : items in ANY of the sets (A or B or C or D)
    #   & (Intersection): items in ALL of the sets simultaneously (A and B and C and D)
    #   - (Difference)  : items in the first set that are NOT in the other sets
    print("\n7. COHORT OVERLAP ANALYSIS")
    print("-" * 55)
    union_all = mrn_dept_diab | mrn_notes_dm | mrn_rx_dm | mrn_labs_dm
    all_four = mrn_dept_diab & mrn_notes_dm & mrn_rx_dm & mrn_labs_dm
    notes_rx_labs = mrn_notes_dm & mrn_rx_dm & mrn_labs_dm
    only_labs = mrn_labs_dm - (mrn_dept_diab | mrn_notes_dm | mrn_rx_dm)
    only_notes = mrn_notes_dm - (mrn_dept_diab | mrn_rx_dm | mrn_labs_dm)
    only_rx = mrn_rx_dm - (mrn_dept_diab | mrn_notes_dm | mrn_labs_dm)

    print(f"  Total registered patient denominator  : {len(p_mrn_set)}")
    print(f"  Patients with ANY diabetes indicator   : {len(union_all)}")
    print(f"  Patients with ALL 4 indicators         : {len(all_four)}")
    print(f"  Patients with Notes, Rx, AND Labs      : {len(notes_rx_labs)}")
    print(f"  Patients with ONLY Glycemic Labs       : {len(only_labs)}")
    print(f"  Patients with ONLY Notes Matches       : {len(only_notes)}")
    print(f"  Patients with ONLY Prescriptions       : {len(only_rx)}")

    # Specific Edge Cases: Metformin in OBG / PCOS
    # Maps each prescription visit_id to the visit department via v_dept_map
    # Shows that Metformin in Obstetrics & Gynecology (OBG) is often for PCOS, not diabetes.
    v_dept_map = {r["visit_id"]: r["department"] for r in visits}
    metformin_rx = [r for r in rx if "metformin" in (r["drug"] or "").lower()]
    met_obg_rx = [r for r in metformin_rx if v_dept_map.get(r["visit_id"]) == "OBG"]
    met_obg_mrns = set(r["mrn"] for r in met_obg_rx)
    print(f"\n  Specialty Context - Metformin in OBG:")
    print(f"    Total Metformin prescriptions        : {len(metformin_rx)}")
    print(f"    Metformin prescribed in OBG dept     : {len(met_obg_rx)} prescriptions across {len(met_obg_mrns)} patients")

    # ---------------------------------------------------------
    # 8. Unresolved Ambiguities & Methodological Limitations
    # ---------------------------------------------------------
    # Purpose: Clearly distinguishes exploratory data findings from hospital policy decisions.
    # Why it matters: Prevents an engineering tool from guessing or making up clinical rules.
    print("\n8. IDENTIFIED AMBIGUITIES & METHODOLOGICAL LIMITATIONS")
    print("-" * 55)
    print("  [!] The following points CANNOT be resolved by data exploration alone:")
    print("      1. Authoritative 'Diabetic' Definition: Clinical team must decide whether")
    print("         to require physician diagnosis, active pharmacotherapy, lab cutoffs,")
    print("         or a consensus combination. Simple keyword or drug matches capture")
    print("         non-diabetic entities (e.g., Metformin for PCOS, pediatric family history).")
    print("      2. Provisional Reference Date: Visit and prescription records end on 2026-09-29,")
    print("         while two lab records carry later dates. The reference date requires hospital")
    print("         confirmation rather than assuming a universal export cutoff.")
    print("      3. Overdue Cadence for Blank Dates: 582 of 815 visits lack next_appointment.")
    print("         Whether to parse natural language review text, apply clinical defaults")
    print("         (e.g., 90/180 days), or flag as unscheduled requires operational policy.")
    print("      4. Specialty Continuity: Whether a visit to an acute/unrelated department")
    print("         (e.g., Orthopaedics, Dermatology) resets the chronic diabetes recall clock.")
    print("=" * 75)
    print("Audit script completed successfully.")
    print("=" * 75)


if __name__ == "__main__":
    main()
