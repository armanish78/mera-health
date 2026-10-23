"""Data loader and schema validator for mera.health records.

Reads CSV exports read-only from the project directory, validates schemas,
parses dates across known hospital formats, and detects duplicate records
in memory without modifying source data.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# Required columns per specification
REQUIRED_SCHEMAS: Dict[str, List[str]] = {
    "patients.csv": ["mrn", "name", "dob", "sex", "phone", "registered_on"],
    "visits.csv": [
        "visit_id",
        "mrn",
        "visit_date",
        "department",
        "doctor",
        "notes",
        "next_appointment",
    ],
    "lab_results.csv": [
        "mrn",
        "test_name",
        "value",
        "unit",
        "reference_range",
        "collected_on",
    ],
    "prescriptions.csv": [
        "mrn",
        "visit_id",
        "drug",
        "dose",
        "prescribed_on",
    ],
}


class DataValidationError(Exception):
    """Raised when raw CSV data fails schema validation or cannot be read."""
    pass


def parse_date_safe(val: Any) -> Optional[datetime.date]:
    """Safely parse a date string across observed hospital date formats.

    Supported formats:
      - YYYY-MM-DD (e.g. '2024-06-25')
      - DD/MM/YYYY (e.g. '15/08/2024')
      - DD Mon YY  (e.g. '12 Oct 23')

    Returns None if value is null, blank, or unparseable.
    Never raises an uncaught exception on malformed input.
    """
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "nat"):
        return None

    # Format 1: ISO YYYY-MM-DD
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.date.fromisoformat(s)
        except ValueError:
            pass

    # Format 2: DD/MM/YYYY
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        try:
            return datetime.datetime.strptime(s, "%d/%m/%Y").date()
        except ValueError:
            pass

    # Format 3: DD Mon YY (e.g. '12 Oct 23')
    for fmt in ("%d %b %y", "%d %B %y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass

    # Fallback to dateutil/pandas parser if standard formats fail
    try:
        ts = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if pd.notna(ts):
            return ts.date()
    except Exception:
        pass

    return None


def validate_schema(df: pd.DataFrame, filename: str) -> None:
    """Validate that required columns exist in the DataFrame."""
    required = REQUIRED_SCHEMAS.get(filename)
    if not required:
        return
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataValidationError(
            f"Schema validation failed for {filename}: missing required columns {missing}."
        )


def load_raw_csvs(data_dir: str | Path = "data/raw") -> Dict[str, pd.DataFrame]:
    """Load the four hospital CSVs into pandas DataFrames with schema validation.

    Ensures read-only access relative to project root without modifying source files.
    Reads all columns with dtype=str, preserving raw field values as strings while
    stripping surrounding whitespace from column names and cell values, and applies
    schema validation.

    Returns:
        Dict mapping filename (e.g. 'patients.csv') to validated pd.DataFrame.
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        raise DataValidationError(f"Data directory '{data_dir}' does not exist.")

    datasets: Dict[str, pd.DataFrame] = {}

    for filename, required_cols in REQUIRED_SCHEMAS.items():
        file_path = data_path / filename
        if not file_path.exists():
            raise DataValidationError(f"Required file '{filename}' not found in '{data_dir}'.")

        try:
            # Read all columns as string by default to prevent silent type coercion / float conversion of phone/MRN
            df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
        except Exception as e:
            raise DataValidationError(f"Failed to read CSV '{filename}': {e}") from e

        # Strip whitespace from column names and string cells
        df.columns = df.columns.str.strip()
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()

        validate_schema(df, filename)
        datasets[filename] = df

    return datasets


def identify_duplicate_labs(labs_df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Detect and deduplicate exact duplicate laboratory records in memory.

    Does NOT modify the source CSV file.
    Returns:
        (deduplicated_labs_df, count_of_redundant_duplicates)
    """
    exact_dup_mask = labs_df.duplicated(keep="first")
    num_duplicates = int(exact_dup_mask.sum())
    dedup_df = labs_df.loc[~exact_dup_mask].copy()
    return dedup_df, num_duplicates
