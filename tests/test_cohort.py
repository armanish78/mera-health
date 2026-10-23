"""Tests for cohort identification, indicators, and ambiguity warnings."""

from __future__ import annotations

import pandas as pd
import pytest

from src.cohort import evaluate_cohort


@pytest.fixture
def synthetic_data():
    """Create a minimal synthetic dataset testing various indicator combinations."""
    patients = pd.DataFrame([
        {"mrn": "SYNTH01", "name": "Diabetology Patient", "dob": "1975-04-10", "sex": "M", "phone": "9000000001", "registered_on": "2024-01-01"},
        {"mrn": "SYNTH02", "name": "Note Only Patient", "dob": "1980-05-15", "sex": "F", "phone": "9000000002", "registered_on": "2024-01-01"},
        {"mrn": "SYNTH03", "name": "OBG Metformin Patient", "dob": "1992-08-20", "sex": "F", "phone": "9000000003", "registered_on": "2024-01-01"},
        {"mrn": "SYNTH04", "name": "Screening Lab Only", "dob": "1960-12-01", "sex": "M", "phone": "9000000004", "registered_on": "2024-01-01"},
        {"mrn": "SYNTH05", "name": "Non Diabetic Patient", "dob": "1985-02-14", "sex": "M", "phone": "9000000005", "registered_on": "2024-01-01"},
        {"mrn": "SYNTH06", "name": "Full Concordance Patient", "dob": "1970-07-22", "sex": "F", "phone": "9000000006", "registered_on": "2024-01-01"},
    ])

    visits = pd.DataFrame([
        {"visit_id": "V1", "mrn": "SYNTH01", "visit_date": "2024-02-01", "department": "Diabetology", "doctor": "Dr. Rao", "notes": "Followup review", "next_appointment": "2024-08-01"},
        {"visit_id": "V2", "mrn": "SYNTH02", "visit_date": "2024-02-05", "department": "General Medicine", "doctor": "Dr. Nair", "notes": "T2DM review, diet advice", "next_appointment": "2024-05-05"},
        {"visit_id": "V3", "mrn": "SYNTH03", "visit_date": "2024-02-10", "department": "OBG", "doctor": "Dr. Gupta", "notes": "PCOS management", "next_appointment": "2024-06-10"},
        {"visit_id": "V4", "mrn": "SYNTH05", "visit_date": "2024-03-01", "department": "Orthopaedics", "doctor": "Dr. Kumar", "notes": "Knee fracture review", "next_appointment": "2024-04-01"},
        {"visit_id": "V5", "mrn": "SYNTH06", "visit_date": "2024-03-15", "department": "Diabetology", "doctor": "Dr. Rao", "notes": "HbA1c elevated, adjust insulin", "next_appointment": "2024-09-15"},
    ])

    labs = pd.DataFrame([
        {"mrn": "SYNTH04", "test_name": "FBS", "value": "92", "unit": "mg/dL", "reference_range": "70-99", "collected_on": "2024-02-15"},
        {"mrn": "SYNTH05", "test_name": "Uric Acid", "value": "5.2", "unit": "mg/dL", "reference_range": "3.5-7.2", "collected_on": "2024-03-02"},
        {"mrn": "SYNTH06", "test_name": "HbA1c", "value": "8.5", "unit": "%", "reference_range": "<5.7", "collected_on": "2024-03-15"},
    ])

    rx = pd.DataFrame([
        {"mrn": "SYNTH03", "visit_id": "V3", "drug": "Metformin 500mg", "dose": "1 tab BD", "prescribed_on": "2024-02-10"},
        {"mrn": "SYNTH05", "visit_id": "V4", "drug": "Paracetamol 650mg", "dose": "SOS", "prescribed_on": "2024-03-01"},
        {"mrn": "SYNTH06", "visit_id": "V5", "drug": "Insulin Glargine 10U", "dose": "At bedtime", "prescribed_on": "2024-03-15"},
    ])

    return patients, visits, labs, rx


def test_evaluate_cohort_all_indicators(synthetic_data):
    """Verify evaluation of candidate cohort across different evidence combinations."""
    pts, visits, labs, rx = synthetic_data
    candidates = evaluate_cohort(pts, visits, labs, rx)

    # SYNTH01: Diabetology department only
    c1 = candidates["SYNTH01"]
    assert c1.is_candidate
    assert c1.has_dept
    assert not c1.has_notes
    assert not c1.has_rx
    assert not c1.has_labs
    assert c1.indicator_count == 1
    assert "Diabetology Department" in c1.indicator_names

    # SYNTH02: Notes only
    c2 = candidates["SYNTH02"]
    assert c2.is_candidate
    assert c2.has_notes
    assert c2.indicator_count == 1
    assert any("Note mention only" in w for w in c2.ambiguity_warnings)

    # SYNTH03: Metformin in OBG (PCOS context)
    c3 = candidates["SYNTH03"]
    assert c3.is_candidate
    assert c3.has_rx
    assert c3.indicator_count == 1
    # Check that OBG Metformin warning is present
    assert any("OBG" in w and "PCOS" in w for w in c3.ambiguity_warnings)

    # SYNTH04: Screening lab only
    c4 = candidates["SYNTH04"]
    assert c4.is_candidate
    assert c4.has_labs
    assert c4.indicator_count == 1
    assert any("Screening lab only" in w for w in c4.ambiguity_warnings)

    # SYNTH05: Non-diabetic patient (Orthopaedics, Paracetamol, Uric Acid)
    c5 = candidates["SYNTH05"]
    assert not c5.is_candidate
    assert c5.indicator_count == 0

    # SYNTH06: All 4 indicators
    c6 = candidates["SYNTH06"]
    assert c6.is_candidate
    assert c6.has_dept and c6.has_notes and c6.has_rx and c6.has_labs
    assert c6.indicator_count == 4
    assert "Broad proxy evidence" in c6.signal_concordance
    assert "Broad proxy evidence" in c6.confidence_level


def test_obg_non_metformin_drug_does_not_trigger_pcos_warning():
    """Verify that an antidiabetic prescription other than Metformin in OBG does NOT trigger the PCOS/Metformin warning."""
    pts = pd.DataFrame([
        {"mrn": "P_OBG_INSULIN", "name": "Insulin in OBG", "dob": "1990-01-01", "sex": "F", "phone": "9000000001", "registered_on": "2024-01-01"},
    ])
    visits = pd.DataFrame([
        {"visit_id": "V_OBG", "mrn": "P_OBG_INSULIN", "visit_date": "2024-05-01", "department": "OBG", "doctor": "Dr. G", "notes": "Antenatal check", "next_appointment": "2024-06-01"},
    ])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame([
        {"mrn": "P_OBG_INSULIN", "visit_id": "V_OBG", "drug": "Insulin Glargine 10U", "dose": "10U SC", "prescribed_on": "2024-05-01"},
    ])

    candidates = evaluate_cohort(pts, visits, labs, rx)
    c = candidates["P_OBG_INSULIN"]
    assert c.is_candidate
    assert c.has_rx
    # Should NOT contain Metformin/PCOS warning
    assert not any("PCOS" in w or "Metformin" in w for w in c.ambiguity_warnings)
