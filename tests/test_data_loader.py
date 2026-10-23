"""Tests for data_loader module: schemas, parsing, deduplication, error handling."""

from __future__ import annotations

import datetime
from pathlib import Path

import pandas as pd
import pytest

from src.data_loader import (
    DataValidationError,
    identify_duplicate_labs,
    load_raw_csvs,
    parse_date_safe,
    validate_schema,
)


def test_parse_date_safe_formats():
    """Verify safe date parsing across all observed formats."""
    # ISO YYYY-MM-DD
    assert parse_date_safe("2024-06-25") == datetime.date(2024, 6, 25)
    # DD/MM/YYYY
    assert parse_date_safe("15/08/2024") == datetime.date(2024, 8, 15)
    # DD Mon YY
    assert parse_date_safe("12 Oct 23") == datetime.date(2023, 10, 12)
    assert parse_date_safe("05 Nov 24") == datetime.date(2024, 11, 5)

    # Empty, null, whitespace, and malformed inputs
    assert parse_date_safe("") is None
    assert parse_date_safe("   ") is None
    assert parse_date_safe(None) is None
    assert parse_date_safe("invalid-date") is None
    assert parse_date_safe("2024/99/99") is None
    assert parse_date_safe("NaN") is None


def test_validate_schema_success():
    """Verify schema validator accepts valid DataFrames."""
    df = pd.DataFrame(columns=["mrn", "name", "dob", "sex", "phone", "registered_on"])
    validate_schema(df, "patients.csv")  # Should not raise


def test_validate_schema_missing_column():
    """Verify schema validator raises DataValidationError on missing required columns."""
    df = pd.DataFrame(columns=["mrn", "name", "dob"])
    with pytest.raises(DataValidationError) as exc:
        validate_schema(df, "patients.csv")
    assert "missing required columns" in str(exc.value)


def test_load_raw_csvs_nonexistent_dir(tmp_path: Path):
    """Verify error handling when data directory does not exist."""
    with pytest.raises(DataValidationError):
        load_raw_csvs(tmp_path / "nonexistent")


def test_load_raw_csvs_missing_file(tmp_path: Path):
    """Verify error handling when a required CSV is missing from the directory."""
    # Create only patients.csv
    (tmp_path / "patients.csv").write_text("mrn,name,dob,sex,phone,registered_on\nP1,Test,2000-01-01,M,9000000001,2024-01-01\n")
    with pytest.raises(DataValidationError) as exc:
        load_raw_csvs(tmp_path)
    assert "visits.csv" in str(exc.value) or "Required file" in str(exc.value)


def test_identify_duplicate_labs():
    """Verify exact duplicate laboratory records are detected and deduplicated in memory."""
    synthetic_labs = pd.DataFrame([
        {"mrn": "M001", "test_name": "HbA1c", "value": "7.5", "unit": "%", "reference_range": "<5.7", "collected_on": "2024-01-01"},
        {"mrn": "M001", "test_name": "HbA1c", "value": "7.5", "unit": "%", "reference_range": "<5.7", "collected_on": "2024-01-01"},  # duplicate
        {"mrn": "M002", "test_name": "FBS", "value": "110", "unit": "mg/dL", "reference_range": "70-99", "collected_on": "2024-01-02"},
    ])

    dedup_df, dup_count = identify_duplicate_labs(synthetic_labs)
    assert dup_count == 1
    assert len(dedup_df) == 2
    assert len(synthetic_labs) == 3  # Original DataFrame untouched
