"""Contact data quality and phone verification module.

Identifies missing phone numbers and shared contact numbers across household
clusters, generating operational safeguards for front-desk staff.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class ContactInfo:
    """Phone verification status and front-desk operational alerts for a patient."""

    mrn: str
    phone: Optional[str]
    is_missing: bool = False
    is_shared: bool = False
    shared_patient_count: int = 1
    shared_with_mrns: List[str] = field(default_factory=list)
    warning_flag: str = "Standard"
    warning_message: str = ""


def analyze_contact_data(patients_df: pd.DataFrame) -> Dict[str, ContactInfo]:
    """Analyze phone fields across the full patient export.

    Returns a dict mapping MRN -> ContactInfo.
    """
    # Count frequency of each non-blank phone number
    populated_phones = [
        p.strip() for p in patients_df["phone"] if p and p.strip()
    ]
    phone_counts = Counter(populated_phones)

    # Map phone -> list of MRNs sharing that phone
    phone_to_mrns: Dict[str, List[str]] = {}
    for _, row in patients_df.iterrows():
        p = (row.get("phone") or "").strip()
        if p:
            phone_to_mrns.setdefault(p, []).append(row["mrn"])

    contact_map: Dict[str, ContactInfo] = {}

    for _, row in patients_df.iterrows():
        mrn = row["mrn"]
        raw_phone = (row.get("phone") or "").strip()

        if not raw_phone:
            contact_map[mrn] = ContactInfo(
                mrn=mrn,
                phone=None,
                is_missing=True,
                is_shared=False,
                warning_flag="MISSING PHONE",
                warning_message=(
                    "Missing phone number. Front desk cannot reach this patient by phone; "
                    "requires alternative contact lookup in physical records or hospital master index."
                ),
            )
        elif phone_counts.get(raw_phone, 0) > 1:
            co_mrns = [m for m in phone_to_mrns.get(raw_phone, []) if m != mrn]
            count = phone_counts[raw_phone]
            contact_map[mrn] = ContactInfo(
                mrn=mrn,
                phone=raw_phone,
                is_missing=False,
                is_shared=True,
                shared_patient_count=count,
                shared_with_mrns=co_mrns,
                warning_flag="SHARED PHONE",
                warning_message=(
                    f"Shared contact number (shared by {count} patients in system). "
                    "Front desk must strictly verify patient identity (e.g. name, date of birth) "
                    "before disclosing clinical context or appointment reasons."
                ),
            )
        else:
            contact_map[mrn] = ContactInfo(
                mrn=mrn,
                phone=raw_phone,
                is_missing=False,
                is_shared=False,
                warning_flag="POPULATED",
                warning_message=(
                    "Populated 10-digit number present in export. "
                    "Note: Structural completeness does not guarantee that number is active, assigned, or reachable."
                ),
            )

    return contact_map
