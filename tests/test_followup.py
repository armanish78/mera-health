"""Tests for follow-up status rules, date boundaries, and timeline integrity."""

from __future__ import annotations

import datetime
import pandas as pd
import pytest

from src.cohort import evaluate_cohort
from src.followup import DEFAULT_REFERENCE_DATE, evaluate_followup


def test_followup_status_rules():
    """Verify follow-up status assignment against reference date."""
    ref_date = DEFAULT_REFERENCE_DATE

    pts = pd.DataFrame([
        {"mrn": "P_OVERDUE", "name": "Overdue Patient", "dob": "1980-01-01", "sex": "M", "phone": "9000000001", "registered_on": "2024-01-01"},
        {"mrn": "P_UPCOMING", "name": "Upcoming Patient", "dob": "1980-01-01", "sex": "F", "phone": "9000000002", "registered_on": "2024-01-01"},
        {"mrn": "P_NO_APPT", "name": "Unscheduled Patient", "dob": "1980-01-01", "sex": "M", "phone": "9000000003", "registered_on": "2024-01-01"},
        {"mrn": "P_LAB_ONLY", "name": "Lab Only Patient", "dob": "1980-01-01", "sex": "F", "phone": "9000000004", "registered_on": "2024-01-01"},
    ])

    visits = pd.DataFrame([
        # P_OVERDUE: Next appt is on 2026-06-01 (before reference date 2026-09-29)
        {"visit_id": "V_O", "mrn": "P_OVERDUE", "visit_date": "2026-01-10", "department": "Diabetology", "doctor": "Dr. A", "notes": "", "next_appointment": "2026-06-01"},
        # P_UPCOMING: Next appt is on 2026-11-15 (after reference date 2026-09-29)
        {"visit_id": "V_U", "mrn": "P_UPCOMING", "visit_date": "2026-08-01", "department": "Diabetology", "doctor": "Dr. B", "notes": "", "next_appointment": "2026-11-15"},
        # P_NO_APPT: Blank next appointment
        {"visit_id": "V_N", "mrn": "P_NO_APPT", "visit_date": "2026-07-20", "department": "Diabetology", "doctor": "Dr. C", "notes": "Review in 3 months", "next_appointment": ""},
    ])

    labs = pd.DataFrame([
        {"mrn": "P_LAB_ONLY", "test_name": "HbA1c", "value": "7.9", "unit": "%", "reference_range": "<5.7", "collected_on": "2026-05-10"},
    ])

    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx)
    followups = evaluate_followup(candidates, visits, rx, reference_date=ref_date)

    # 1. Overdue case
    fu_o = followups["P_OVERDUE"]
    assert fu_o.status == "Due / potentially overdue — verify"
    assert fu_o.is_due_or_overdue
    assert fu_o.scheduled_next_appointment == datetime.date(2026, 6, 1)
    assert fu_o.days_difference == (ref_date - datetime.date(2026, 6, 1)).days

    # 2. Upcoming case
    fu_u = followups["P_UPCOMING"]
    assert fu_u.status == "Upcoming"
    assert fu_u.is_upcoming
    assert fu_u.scheduled_next_appointment == datetime.date(2026, 11, 15)
    assert fu_u.days_difference == (datetime.date(2026, 11, 15) - ref_date).days

    # 3. No structured appointment case
    fu_n = followups["P_NO_APPT"]
    assert fu_n.status == "Needs review — no reliable due date"
    assert fu_n.needs_review
    assert fu_n.scheduled_next_appointment is None

    # 4. Lab-only candidate case
    fu_l = followups["P_LAB_ONLY"]
    assert fu_l.status == "Needs review — no reliable due date"
    assert fu_l.needs_review
    assert "No relevant clinical encounter found" in fu_l.status_reason


def test_latest_encounter_selection_and_specialty_continuity():
    """Verify that the latest relevant encounter is selected and that an unrelated visit does NOT reset follow-up."""
    ref_date = datetime.date(2026, 9, 29)

    pts = pd.DataFrame([
        {"mrn": "P_SPECIALTY", "name": "Specialty Test Patient", "dob": "1980-01-01", "sex": "M", "phone": "9000000001", "registered_on": "2024-01-01"},
    ])

    visits = pd.DataFrame([
        # Encounter 1: Earlier Diabetology visit
        {"visit_id": "V1", "mrn": "P_SPECIALTY", "visit_date": "2025-01-15", "department": "Diabetology", "doctor": "Dr. Rao", "notes": "DM2", "next_appointment": "2025-06-15"},
        # Encounter 2: Later Diabetology visit (must be selected as latest relevant)
        {"visit_id": "V2", "mrn": "P_SPECIALTY", "visit_date": "2026-02-10", "department": "Diabetology", "doctor": "Dr. Rao", "notes": "HbA1c test ordered", "next_appointment": "2026-05-10"},
        # Encounter 3: Later unrelated Orthopaedics visit (MUST NOT reset diabetes follow-up)
        {"visit_id": "V3", "mrn": "P_SPECIALTY", "visit_date": "2026-08-01", "department": "Orthopaedics", "doctor": "Dr. Kumar", "notes": "Cast removed, fracture healed", "next_appointment": "2026-08-15"},
    ])

    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx)
    followups = evaluate_followup(candidates, visits, rx, reference_date=ref_date)

    fu = followups["P_SPECIALTY"]
    # Latest relevant visit must be V2 (Diabetology on 2026-02-10), NOT V3 (Orthopaedics)
    assert fu.latest_relevant_visit_id == "V2"
    assert fu.latest_relevant_date == datetime.date(2026, 2, 10)
    assert fu.latest_relevant_dept == "Diabetology"
    assert fu.scheduled_next_appointment == datetime.date(2026, 5, 10)
    assert fu.status == "Due / potentially overdue — verify"

    # Subsequent unrelated encounter must be flagged in timeline notes
    assert len(fu.subsequent_unrelated_encounters) == 1
    assert fu.subsequent_unrelated_encounters[0]["department"] == "Orthopaedics"
    assert "Orthopaedics" in fu.timeline_explanation
    assert "did NOT reset" in fu.timeline_explanation


# ---------------------------------------------------------------------------
# Regression tests: as-of reference-date semantics (8 cases)
# ---------------------------------------------------------------------------

def _base_patient(mrn: str, name: str) -> dict:
    return {
        "mrn": mrn, "name": name,
        "dob": "1975-01-01", "sex": "M",
        "phone": "9000000099", "registered_on": "2024-01-01",
    }


def test_future_diabetology_visit_excluded_from_cohort():
    """Case 1: A Diabetology visit dated after reference_date must NOT make patient a candidate."""
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("FUTURE_VISIT", "Future Dept Patient")])
    visits = pd.DataFrame([{
        "visit_id": "VF1", "mrn": "FUTURE_VISIT",
        "visit_date": "2026-10-05",  # after ref
        "department": "Diabetology", "doctor": "Dr. X",
        "notes": "", "next_appointment": "2027-01-01",
    }])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    assert not candidates["FUTURE_VISIT"].is_candidate, (
        "Diabetology visit after reference_date must not qualify patient as candidate"
    )


def test_future_lab_result_excluded_from_cohort():
    """Case 2: A glycemic lab collected after reference_date must NOT contribute to cohort inclusion."""
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("FUTURE_LAB", "Future Lab Patient")])
    visits = pd.DataFrame(columns=["visit_id", "mrn", "visit_date", "department", "doctor", "notes", "next_appointment"])
    labs = pd.DataFrame([{
        "mrn": "FUTURE_LAB", "test_name": "HbA1c",
        "value": "8.5", "unit": "%",
        "reference_range": "<5.7", "collected_on": "2026-12-19",  # after ref
    }])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    assert not candidates["FUTURE_LAB"].is_candidate, (
        "Lab result collected after reference_date must not qualify patient as candidate"
    )


def test_future_prescription_excluded_from_cohort():
    """Case 3: An antidiabetic prescription dated after reference_date must NOT contribute to cohort."""
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("FUTURE_RX", "Future Rx Patient")])
    visits = pd.DataFrame([{
        "visit_id": "VRX1", "mrn": "FUTURE_RX",
        "visit_date": "2026-10-10",  # after ref — no dept match on its own
        "department": "General Medicine", "doctor": "Dr. Y",
        "notes": "", "next_appointment": "",
    }])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame([{
        "mrn": "FUTURE_RX", "visit_id": "VRX1",
        "drug": "Metformin 500mg", "dose": "1 tab OD",
        "prescribed_on": "2026-10-10",  # after ref
    }])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    assert not candidates["FUTURE_RX"].is_candidate, (
        "Prescription after reference_date must not qualify patient as candidate"
    )


def test_historical_evidence_still_qualifies_despite_future_events():
    """Case 4: Patient with historical evidence MUST still be a candidate even if they also have future events."""
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("HIST_AND_FUTURE", "Both Evidence Patient")])
    visits = pd.DataFrame([
        {
            "visit_id": "VHIST", "mrn": "HIST_AND_FUTURE",
            "visit_date": "2026-05-01",  # before ref — qualifies
            "department": "Diabetology", "doctor": "Dr. A",
            "notes": "", "next_appointment": "2026-11-01",
        },
        {
            "visit_id": "VFUT", "mrn": "HIST_AND_FUTURE",
            "visit_date": "2026-10-15",  # after ref — should be ignored
            "department": "Diabetology", "doctor": "Dr. A",
            "notes": "", "next_appointment": "2027-04-15",
        },
    ])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    followups = evaluate_followup(candidates, visits, rx, reference_date=ref)

    assert candidates["HIST_AND_FUTURE"].is_candidate, "Historical Diabetology visit must qualify patient"
    fu = followups["HIST_AND_FUTURE"]
    # Latest RELEVANT encounter must be the historical one (VHIST), not the future one
    assert fu.latest_relevant_visit_id == "VHIST"
    assert fu.latest_relevant_date == datetime.date(2026, 5, 1)
    # next_appointment from VHIST (2026-11-01) is after ref so it's Upcoming
    assert fu.status == "Upcoming"


def test_unparseable_date_event_excluded_safely():
    """Case 5: Events with unparseable/missing dates must be excluded without crashing."""
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("BAD_DATE", "Bad Date Patient")])
    visits = pd.DataFrame([
        {
            "visit_id": "VBAD", "mrn": "BAD_DATE",
            "visit_date": "not-a-date",  # unparseable
            "department": "Diabetology", "doctor": "Dr. Z",
            "notes": "", "next_appointment": "",
        },
        {
            "visit_id": "VGOOD", "mrn": "BAD_DATE",
            "visit_date": "2026-03-10",  # valid historical
            "department": "Diabetology", "doctor": "Dr. Z",
            "notes": "", "next_appointment": "2026-09-10",
        },
    ])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    followups = evaluate_followup(candidates, visits, rx, reference_date=ref)

    assert candidates["BAD_DATE"].is_candidate, "Valid historical visit must still qualify"
    fu = followups["BAD_DATE"]
    assert fu.latest_relevant_visit_id == "VGOOD"


def test_reference_date_boundary_on_the_day_included():
    """Case 6: Events dated exactly on reference_date must be included (boundary = inclusive)."""
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("ON_DATE", "On Date Patient")])
    visits = pd.DataFrame([{
        "visit_id": "VON", "mrn": "ON_DATE",
        "visit_date": "2026-09-29",  # exactly on ref — must be included
        "department": "Diabetology", "doctor": "Dr. A",
        "notes": "", "next_appointment": "2027-03-29",
    }])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    followups = evaluate_followup(candidates, visits, rx, reference_date=ref)

    assert candidates["ON_DATE"].is_candidate, "Visit on reference_date itself must be included"
    fu = followups["ON_DATE"]
    assert fu.latest_relevant_visit_id == "VON"
    assert fu.status == "Upcoming"


def test_one_day_after_reference_excluded():
    """Case 7: Event dated exactly one day after reference_date must be excluded."""
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("DAY_AFTER", "Day After Patient")])
    visits = pd.DataFrame([{
        "visit_id": "VAFTER", "mrn": "DAY_AFTER",
        "visit_date": "2026-09-30",  # one day after ref — must be excluded
        "department": "Diabetology", "doctor": "Dr. A",
        "notes": "", "next_appointment": "2027-03-30",
    }])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    assert not candidates["DAY_AFTER"].is_candidate, (
        "Visit dated one day after reference_date must not qualify patient"
    )


def test_note_keyword_in_future_visit_does_not_qualify():
    """Case 8: A future visit whose notes match diabetes keywords must NOT qualify the patient."""
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("FUTURE_NOTE", "Future Note Patient")])
    visits = pd.DataFrame([{
        "visit_id": "VFNOTE", "mrn": "FUTURE_NOTE",
        "visit_date": "2026-10-01",  # after ref
        "department": "General Medicine", "doctor": "Dr. B",
        "notes": "T2DM review planned", "next_appointment": "",
    }])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    assert not candidates["FUTURE_NOTE"].is_candidate, (
        "Diabetes keyword in a future-dated note must not qualify patient as of reference_date"
    )


# ---------------------------------------------------------------------------
# Regression tests: subsequent_unrelated_encounters windowing (5 cases)
# ---------------------------------------------------------------------------

def test_future_diabetology_visit_not_in_subsequent_unrelated():
    """A future Diabetology visit must not appear as a subsequent_unrelated_encounter.

    VHIST is the latest relevant encounter.  VFUT_DIAB is a Diabetology visit
    dated after the reference date.  It is a future event and must be invisible
    in the historical as-of timeline — neither as a relevant encounter nor as
    a subsequent unrelated encounter.
    """
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("FUT_DIAB_UNREL", "Future Diab Patient")])
    visits = pd.DataFrame([
        {
            "visit_id": "VHIST",
            "mrn": "FUT_DIAB_UNREL",
            "visit_date": "2026-04-01",
            "department": "Diabetology",
            "doctor": "Dr. A",
            "notes": "",
            "next_appointment": "2026-10-01",
        },
        {
            "visit_id": "VFUT_DIAB",
            "mrn": "FUT_DIAB_UNREL",
            "visit_date": "2026-11-05",  # after ref — future Diabetology visit
            "department": "Diabetology",
            "doctor": "Dr. A",
            "notes": "DM follow-up",
            "next_appointment": "2027-05-05",
        },
    ])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    followups = evaluate_followup(candidates, visits, rx, reference_date=ref)

    fu = followups["FUT_DIAB_UNREL"]
    assert fu.latest_relevant_visit_id == "VHIST", "Latest relevant encounter must be VHIST (historical)"
    # The future Diabetology visit must not appear in subsequent_unrelated_encounters
    unrel_ids = [v["visit_id"] for v in fu.subsequent_unrelated_encounters]
    assert "VFUT_DIAB" not in unrel_ids, (
        "Future Diabetology visit must not appear in subsequent_unrelated_encounters"
    )
    assert len(fu.subsequent_unrelated_encounters) == 0


def test_future_unrelated_visit_not_in_historical_timeline():
    """A future unrelated (non-diabetes) visit after reference_date must not appear in
    subsequent_unrelated_encounters for the historical as-of timeline.
    """
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("FUT_UNREL", "Future Unrelated Patient")])
    visits = pd.DataFrame([
        {
            "visit_id": "VHIST2",
            "mrn": "FUT_UNREL",
            "visit_date": "2026-03-10",
            "department": "Diabetology",
            "doctor": "Dr. B",
            "notes": "",
            "next_appointment": "2026-09-10",
        },
        {
            "visit_id": "VFUT_ORTHO",
            "mrn": "FUT_UNREL",
            "visit_date": "2026-10-20",  # after ref — future unrelated visit
            "department": "Orthopaedics",
            "doctor": "Dr. C",
            "notes": "Fracture review",
            "next_appointment": "",
        },
    ])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    followups = evaluate_followup(candidates, visits, rx, reference_date=ref)

    fu = followups["FUT_UNREL"]
    assert fu.latest_relevant_visit_id == "VHIST2"
    # The future unrelated visit must not appear in the as-of timeline
    unrel_ids = [v["visit_id"] for v in fu.subsequent_unrelated_encounters]
    assert "VFUT_ORTHO" not in unrel_ids, (
        "Future unrelated visit must not appear in subsequent_unrelated_encounters"
    )
    assert len(fu.subsequent_unrelated_encounters) == 0


def test_historical_unrelated_visit_still_listed_and_does_not_reset_clock():
    """A genuinely historical unrelated visit (after latest relevant but within reference_date)
    must be listed in subsequent_unrelated_encounters and must NOT reset the follow-up clock.
    """
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("HIST_UNREL", "Historical Unrelated Patient")])
    visits = pd.DataFrame([
        {
            "visit_id": "VDIAB",
            "mrn": "HIST_UNREL",
            "visit_date": "2026-02-15",
            "department": "Diabetology",
            "doctor": "Dr. D",
            "notes": "",
            "next_appointment": "2026-08-15",  # before ref → overdue
        },
        {
            "visit_id": "VORTHO",
            "mrn": "HIST_UNREL",
            "visit_date": "2026-07-01",  # after VDIAB, still before ref
            "department": "Orthopaedics",
            "doctor": "Dr. E",
            "notes": "Cast removed",
            "next_appointment": "",
        },
    ])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    followups = evaluate_followup(candidates, visits, rx, reference_date=ref)

    fu = followups["HIST_UNREL"]
    # Latest relevant encounter is the Diabetology visit — not the Orthopaedics one
    assert fu.latest_relevant_visit_id == "VDIAB"
    assert fu.latest_relevant_dept == "Diabetology"
    # The Orthopaedics visit IS listed (historical, after VDIAB, before ref)
    assert len(fu.subsequent_unrelated_encounters) == 1
    assert fu.subsequent_unrelated_encounters[0]["visit_id"] == "VORTHO"
    assert fu.subsequent_unrelated_encounters[0]["department"] == "Orthopaedics"
    # The Orthopaedics visit did NOT reset the follow-up clock
    assert fu.status == "Due / potentially overdue — verify", (
        "Unrelated historical visit must not reset follow-up status"
    )
    assert fu.scheduled_next_appointment == datetime.date(2026, 8, 15)
    assert "did NOT reset" in fu.timeline_explanation


def test_sliding_reference_date_exposes_newly_eligible_encounters():
    """Moving the reference date forward must make newly eligible historical encounters available.

    At ref=2026-05-01: only VEARLY is within window → patient is candidate, overdue.
    At ref=2026-09-29: VLATER is also within window → it becomes the latest relevant encounter.
    """
    early_ref = datetime.date(2026, 5, 1)
    late_ref = datetime.date(2026, 9, 29)

    pts = pd.DataFrame([_base_patient("SLIDE_REF", "Sliding Ref Patient")])
    visits = pd.DataFrame([
        {
            "visit_id": "VEARLY",
            "mrn": "SLIDE_REF",
            "visit_date": "2026-01-10",  # before both refs
            "department": "Diabetology",
            "doctor": "Dr. F",
            "notes": "",
            "next_appointment": "2026-07-10",
        },
        {
            "visit_id": "VLATER",
            "mrn": "SLIDE_REF",
            "visit_date": "2026-08-20",  # only within late_ref
            "department": "Diabetology",
            "doctor": "Dr. F",
            "notes": "",
            "next_appointment": "2027-02-20",
        },
    ])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])

    # Early reference: only VEARLY is eligible
    cands_early = evaluate_cohort(pts, visits, labs, rx, reference_date=early_ref)
    fus_early = evaluate_followup(cands_early, visits, rx, reference_date=early_ref)
    fu_e = fus_early["SLIDE_REF"]
    assert fu_e.latest_relevant_visit_id == "VEARLY", "Early ref: only VEARLY eligible"
    # next_appointment 2026-07-10 is after early_ref (2026-05-01) → Upcoming
    assert fu_e.status == "Upcoming"

    # Late reference: VLATER is now also eligible and becomes the latest
    cands_late = evaluate_cohort(pts, visits, labs, rx, reference_date=late_ref)
    fus_late = evaluate_followup(cands_late, visits, rx, reference_date=late_ref)
    fu_l = fus_late["SLIDE_REF"]
    assert fu_l.latest_relevant_visit_id == "VLATER", "Late ref: VLATER must now be the latest"
    # next_appointment 2027-02-20 is after late_ref → Upcoming
    assert fu_l.status == "Upcoming"


def test_evaluate_followup_does_not_mutate_input_dataframes():
    """evaluate_followup must not mutate the caller's visits_df or rx_df."""
    ref = datetime.date(2026, 9, 29)
    pts = pd.DataFrame([_base_patient("MUTATE_CHECK", "Mutation Check Patient")])
    visits = pd.DataFrame([{
        "visit_id": "VM1",
        "mrn": "MUTATE_CHECK",
        "visit_date": "2026-06-01",
        "department": "Diabetology",
        "doctor": "Dr. G",
        "notes": "",
        "next_appointment": "2026-12-01",
    }])
    rx = pd.DataFrame(columns=["mrn", "visit_id", "drug", "dose", "prescribed_on"])
    labs = pd.DataFrame(columns=["mrn", "test_name", "value", "unit", "reference_range", "collected_on"])

    # Capture deep copies, shape, and columns before call
    visits_expected = visits.copy(deep=True)
    rx_expected = rx.copy(deep=True)
    visits_shape_before = visits.shape
    rx_shape_before = rx.shape
    visits_cols_before = list(visits.columns)
    rx_cols_before = list(rx.columns)

    candidates = evaluate_cohort(pts, visits, labs, rx, reference_date=ref)
    evaluate_followup(candidates, visits, rx, reference_date=ref)

    # Shape and columns must be unchanged after the call
    assert visits.shape == visits_shape_before, "visits_df was mutated by evaluate_followup"
    assert rx.shape == rx_shape_before, "rx_df was mutated by evaluate_followup"
    assert list(visits.columns) == visits_cols_before
    assert list(rx.columns) == rx_cols_before

    # Complete DataFrame equality check: values, columns, index, and dtypes
    pd.testing.assert_frame_equal(visits, visits_expected)
    pd.testing.assert_frame_equal(rx, rx_expected)
