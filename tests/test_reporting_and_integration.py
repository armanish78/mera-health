"""Integration and end-to-end reporting tests."""

from __future__ import annotations

import datetime
from pathlib import Path
import pandas as pd
import pytest

from src.cohort import evaluate_cohort
from src.contact import analyze_contact_data
from src.data_loader import identify_duplicate_labs, load_raw_csvs
from src.followup import evaluate_followup
from src.reporting import (
    EXPORT_COLUMNS,
    REPORT_COLUMNS,
    build_candidate_report_df,
    generate_export_csv,
)


def test_build_candidate_report_df_structure():
    """Verify DataFrame structure, required front-desk columns, and CSV export."""
    ref_date = datetime.date(2026, 9, 29)

    pts = pd.DataFrame([
        {"mrn": "M1", "name": "Patient One", "dob": "1980-01-01", "sex": "M", "phone": "9000000001", "registered_on": "2024-01-01"},
        {"mrn": "M2", "name": "Patient Two", "dob": "1985-02-02", "sex": "F", "phone": "", "registered_on": "2024-01-01"},
    ])

    visits = pd.DataFrame([
        {"visit_id": "V1", "mrn": "M1", "visit_date": "2026-01-01", "department": "Diabetology", "doctor": "Dr. Smith", "notes": "DM2 review", "next_appointment": "2026-06-01"},
    ])

    labs = pd.DataFrame([
        {"mrn": "M2", "test_name": "HbA1c", "value": "8.1", "unit": "%", "reference_range": "<5.7", "collected_on": "2026-02-01"},
    ])

    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx)
    followups = evaluate_followup(candidates, visits, rx, reference_date=ref_date)
    contacts = analyze_contact_data(pts)

    df = build_candidate_report_df(candidates, followups, contacts)

    assert len(df) == 2
    required_cols = [
        "mrn", "name", "status", "next_appointment", "days_relative",
        "latest_relevant_date", "latest_department", "phone", "contact_flag", "indicators"
    ]
    for col in required_cols:
        assert col in df.columns

    csv_text = generate_export_csv(df)
    assert "Patient One" in csv_text
    assert "Due / potentially overdue — verify" in csv_text
    assert "MISSING PHONE" in csv_text


def test_empty_candidate_report():
    """Verify build_candidate_report_df handles empty candidate input without errors,
    preserves stable column schema, and generate_export_csv exports header without data rows.
    """
    df = build_candidate_report_df({}, {}, {})
    assert df.empty
    assert len(df) == 0

    # Verify stable column schema
    assert list(df.columns) == REPORT_COLUMNS

    # Verify empty CSV export contains header row and no data rows
    csv_text = generate_export_csv(df)
    csv_lines = [line.strip() for line in csv_text.strip().splitlines() if line.strip()]
    assert len(csv_lines) == 1, f"Expected header row only, got {len(csv_lines)} lines: {csv_lines}"
    header_cols = csv_lines[0].split(",")
    assert header_cols == EXPORT_COLUMNS

    # Verify fallback behavior on a DataFrame with no columns
    df_no_cols = pd.DataFrame()
    csv_fallback = generate_export_csv(df_no_cols)
    fallback_lines = [line.strip() for line in csv_fallback.strip().splitlines() if line.strip()]
    assert len(fallback_lines) == 1
    assert fallback_lines[0].split(",") == EXPORT_COLUMNS


def test_early_reference_date_zero_candidates():
    """Verify that an early reference date with zero qualifying candidates produces a valid schema."""
    pts = pd.DataFrame([
        {"mrn": "M1", "name": "Patient One", "dob": "1980-01-01", "sex": "M", "phone": "9000000001", "registered_on": "2024-01-01"},
    ])
    visits = pd.DataFrame([
        {"visit_id": "V1", "mrn": "M1", "visit_date": "2026-01-01", "department": "Diabetology", "doctor": "Dr. A", "notes": "", "next_appointment": "2026-06-01"},
    ])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    early_ref = datetime.date(2023, 1, 1)
    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=early_ref)
    followups = evaluate_followup(candidates, visits, rx, reference_date=early_ref)
    contacts = analyze_contact_data(pts)

    df = build_candidate_report_df(candidates, followups, contacts)
    assert df.empty
    assert list(df.columns) == REPORT_COLUMNS
    csv_text = generate_export_csv(df)
    assert csv_text.strip().split(",") == EXPORT_COLUMNS


def test_real_dataset_smoke_check():
    """Smoke test asserting core invariant reproduction on actual data/raw CSVs."""
    raw_dir = Path("data/raw")
    if not (raw_dir / "patients.csv").exists():
        pytest.skip("data/raw directory not present in environment")

    datasets = load_raw_csvs(raw_dir)
    patients = datasets["patients.csv"]
    visits = datasets["visits.csv"]
    labs = datasets["lab_results.csv"]
    rx = datasets["prescriptions.csv"]

    assert len(patients) == 300
    assert len(visits) == 815
    assert len(labs) == 425
    assert len(rx) == 540

    dedup_labs, num_dups = identify_duplicate_labs(labs)
    assert num_dups == 4
    assert len(dedup_labs) == 421

    candidates = evaluate_cohort(patients, visits, dedup_labs, rx)
    cand_mrns = [mrn for mrn, ev in candidates.items() if ev.is_candidate]
    # Invariant from verified audit: exactly 122 candidate patients
    assert len(cand_mrns) == 122

    followups = evaluate_followup(candidates, visits, rx)
    contacts = analyze_contact_data(patients)

    df = build_candidate_report_df(candidates, followups, contacts)
    assert len(df) == 122

    status_counts = df["status"].value_counts().to_dict()
    assert status_counts["Needs review — no reliable due date"] == 76
    assert status_counts["Due / potentially overdue — verify"] == 28
    assert status_counts["Upcoming"] == 18
    assert sum(status_counts.values()) == 122
