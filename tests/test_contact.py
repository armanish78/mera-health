"""Tests for contact data quality and phone verification rules."""

from __future__ import annotations

import pandas as pd
import pytest

from src.contact import analyze_contact_data


def test_analyze_contact_data():
    """Verify classification of missing, shared, and populated phone numbers."""
    patients = pd.DataFrame([
        # Missing phone
        {"mrn": "P_MISS1", "phone": ""},
        {"mrn": "P_MISS2", "phone": "   "},
        # Shared phone: 9000000099 shared by P_SHARE1 and P_SHARE2
        {"mrn": "P_SHARE1", "phone": "9000000099"},
        {"mrn": "P_SHARE2", "phone": "9000000099"},
        # Unique populated phone
        {"mrn": "P_UNIQUE", "phone": "9000000001"},
    ])

    contacts = analyze_contact_data(patients)

    # Missing cases
    assert contacts["P_MISS1"].is_missing
    assert contacts["P_MISS1"].phone is None
    assert "Missing phone number" in contacts["P_MISS1"].warning_message

    assert contacts["P_MISS2"].is_missing
    assert contacts["P_MISS2"].phone is None

    # Shared cases
    c_s1 = contacts["P_SHARE1"]
    assert c_s1.is_shared
    assert not c_s1.is_missing
    assert c_s1.shared_patient_count == 2
    assert "P_SHARE2" in c_s1.shared_with_mrns
    assert "Shared contact number" in c_s1.warning_message
    assert "verify patient identity" in c_s1.warning_message

    c_s2 = contacts["P_SHARE2"]
    assert c_s2.is_shared
    assert "P_SHARE1" in c_s2.shared_with_mrns

    # Unique populated case
    c_u = contacts["P_UNIQUE"]
    assert not c_u.is_missing
    assert not c_u.is_shared
    assert c_u.phone == "9000000001"
    assert "active, assigned, or reachable" in c_u.warning_message.lower()
