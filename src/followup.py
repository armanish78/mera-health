"""Follow-up status evaluation module based on structured appointment dates.

Transparently determines the most recent relevant clinical encounter for each
candidate patient, compares its recorded next_appointment against a user-selectable
reference date, and assigns a verifiable follow-up status.

Status categories:
  - 'Due / potentially overdue — verify': next_appointment <= reference_date
  - 'Upcoming': next_appointment > reference_date
  - 'Needs review — no reliable due date': missing next_appointment or no relevant encounter

Strict clinical rules:
  - Does NOT invent follow-up intervals or infer due dates from free-text notes.
  - Does NOT allow unrelated specialty visits (e.g. Orthopaedics, Dermatology) to reset
    the diabetes follow-up timeline.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import pandas as pd

from src.cohort import ANTIDIABETIC_DRUG_PATTERN, NOTE_DIABETES_PATTERN, CandidateEvidence
from src.config import DEFAULT_REFERENCE_DATE
from src.data_loader import parse_date_safe


@dataclass
class FollowUpStatus:
    """Follow-up status determination and encounter timeline for a patient."""

    mrn: str
    status: str
    reference_date: datetime.date

    # Latest relevant encounter details
    latest_relevant_visit_id: Optional[str] = None
    latest_relevant_date: Optional[datetime.date] = None
    latest_relevant_dept: Optional[str] = None
    latest_relevant_doctor: Optional[str] = None
    latest_relevant_notes: Optional[str] = None

    # Next appointment details
    scheduled_next_appointment: Optional[datetime.date] = None
    days_difference: Optional[int] = None  # Non-negative day count: days overdue for due/overdue status, or days until appointment for upcoming status; None if missing

    # Explanations and caveats
    status_reason: str = ""
    timeline_explanation: str = ""
    subsequent_unrelated_encounters: List[Dict[str, str]] = field(default_factory=list)

    @property
    def is_due_or_overdue(self) -> bool:
        return self.status == "Due / potentially overdue — verify"

    @property
    def is_upcoming(self) -> bool:
        return self.status == "Upcoming"

    @property
    def needs_review(self) -> bool:
        return self.status == "Needs review — no reliable due date"


def identify_relevant_visits(
    visits_df: pd.DataFrame,
    rx_df: pd.DataFrame,
) -> Set[str]:
    """Identify visit_ids that document diabetes care using transparent proxy criteria:
      1. Visit was in Diabetology department, OR
      2. Visit clinical notes matched diabetes-related keywords, OR
      3. Visit resulted in a prescription for an antidiabetic medication.

    Returns a set of relevant visit_id strings.
    """
    relevant_vids: Set[str] = set()

    # 1 & 2: Diabetology or Note keywords
    for _, row in visits_df.iterrows():
        vid = row["visit_id"]
        dept = (row.get("department", "") or "").strip().lower()
        notes = row.get("notes", "") or ""

        if dept == "diabetology" or NOTE_DIABETES_PATTERN.search(notes):
            relevant_vids.add(vid)

    # 3: Linked antidiabetic prescriptions
    for _, row in rx_df.iterrows():
        vid = row.get("visit_id", "")
        drug = row.get("drug", "") or ""
        if ANTIDIABETIC_DRUG_PATTERN.search(drug):
            relevant_vids.add(vid)

    return relevant_vids


def evaluate_followup(
    candidate_evidences: Dict[str, CandidateEvidence],
    visits_df: pd.DataFrame,
    rx_df: pd.DataFrame,
    reference_date: datetime.date = DEFAULT_REFERENCE_DATE,
) -> Dict[str, FollowUpStatus]:
    """Evaluate follow-up status for each candidate patient as of reference_date.

    Only visits and prescriptions that occurred on or before reference_date are
    considered when identifying relevant encounters and building timelines.
    Future-dated events (after reference_date) are excluded from both relevance
    identification and timeline ordering.  Upcoming scheduled appointments
    (the next_appointment field on a historical encounter) remain visible.

    Returns a dict mapping MRN -> FollowUpStatus.
    """
    # ----------------------------------------------------------------
    # Filter DataFrames to historical evidence on or before reference_date
    # ----------------------------------------------------------------
    def _within_ref(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
        """Return rows whose date_col parses to a date <= reference_date."""
        mask = []
        for val in df[date_col]:
            d = parse_date_safe(val)
            mask.append(d is not None and d <= reference_date)
        return df[mask].reset_index(drop=True)

    hist_visits = _within_ref(visits_df, "visit_date")
    hist_rx = _within_ref(rx_df, "prescribed_on")

    # Identify relevant visit_ids using only historical encounters
    relevant_vids = identify_relevant_visits(hist_visits, hist_rx)
    results: Dict[str, FollowUpStatus] = {}

    # Group historical visits by MRN for timeline analysis
    visits_by_mrn: Dict[str, List[Dict[str, str]]] = {}
    for _, row in hist_visits.iterrows():
        mrn = row["mrn"]
        visits_by_mrn.setdefault(mrn, []).append(dict(row))

    for mrn, ev in candidate_evidences.items():
        if not ev.is_candidate:
            continue

        # Historical visits for this patient (on or before reference_date)
        patient_visits = visits_by_mrn.get(mrn, [])

        # Filter to relevant encounters (already restricted to historical)
        relevant_encounters = [
            v for v in patient_visits if v["visit_id"] in relevant_vids
        ]

        if not relevant_encounters:
            # Candidate has no relevant clinical encounter recorded (e.g. lab results only)
            results[mrn] = FollowUpStatus(
                mrn=mrn,
                status="Needs review — no reliable due date",
                reference_date=reference_date,
                status_reason=(
                    "No relevant clinical encounter found in records. Patient flagged via "
                    "laboratory results or screening tests without a documented visit. "
                    "Front desk cannot determine an overdue date without clinical chart review."
                ),
                timeline_explanation="No clinical visits associated with diabetes care.",
            )
            continue

        # Sort relevant encounters chronologically by visit_date
        # In case of tie on date, prefer encounter with populated next_appointment
        def sort_key(v: Dict[str, str]):
            d = parse_date_safe(v.get("visit_date")) or datetime.date.min
            has_appt = 1 if (v.get("next_appointment") or "").strip() else 0
            return (d, has_appt)

        sorted_relevant = sorted(relevant_encounters, key=sort_key)
        latest_rel = sorted_relevant[-1]

        latest_rel_date = parse_date_safe(latest_rel.get("visit_date"))
        latest_rel_dept = latest_rel.get("department", "Unknown")
        latest_rel_doctor = latest_rel.get("doctor", "Unknown")
        latest_rel_notes = latest_rel.get("notes", "")
        latest_rel_vid = latest_rel.get("visit_id")

        # Check for subsequent visits in unrelated departments (e.g. Orthopaedics, Dermatology)
        # Only include visits within the historical window (on or before reference_date) that
        # are strictly later than the latest relevant encounter.  Future visits must not appear
        # in the as-of timeline regardless of their department or content.
        subsequent_unrelated = []
        if latest_rel_date:
            for v in patient_visits:  # already filtered to <= reference_date
                v_date = parse_date_safe(v.get("visit_date"))
                if v_date and v_date > latest_rel_date and v["visit_id"] not in relevant_vids:
                    subsequent_unrelated.append({
                        "visit_id": v.get("visit_id", ""),
                        "visit_date": v.get("visit_date", ""),
                        "department": v.get("department", ""),
                        "doctor": v.get("doctor", ""),
                    })

        raw_next_appt = (latest_rel.get("next_appointment") or "").strip()
        parsed_next_appt = parse_date_safe(raw_next_appt)

        # Build timeline explanation
        timeline_notes = []
        if subsequent_unrelated:
            depts = {v["department"] for v in subsequent_unrelated}
            timeline_notes.append(
                f"Note: Patient had {len(subsequent_unrelated)} subsequent visit(s) to unrelated "
                f"departments ({', '.join(sorted(depts))}) after the latest diabetes encounter on "
                f"{latest_rel_date}. These encounters did not document diabetes care and did NOT "
                "reset the diabetes follow-up clock."
            )

        if not parsed_next_appt:
            # Case 1: Missing next appointment date
            status = "Needs review — no reliable due date"
            days_diff = None
            reason = (
                f"Latest relevant encounter on {latest_rel_date} ({latest_rel_dept}) has no "
                "structured next_appointment date. (Doctors frequently wrote informal recall notes "
                "such as 'review in 3 months', but front desk must verify clinical policy before calling)."
            )
        elif parsed_next_appt <= reference_date:
            # Case 2: Due or overdue relative to reference date
            status = "Due / potentially overdue — verify"
            days_diff = (reference_date - parsed_next_appt).days
            reason = (
                f"Scheduled next appointment was on {parsed_next_appt} "
                f"({days_diff} day(s) overdue relative to provisional reference date {reference_date}). "
                f"Originating encounter: {latest_rel_dept} on {latest_rel_date}."
            )
        else:
            # Case 3: Upcoming appointment
            status = "Upcoming"
            days_diff = (parsed_next_appt - reference_date).days
            reason = (
                f"Scheduled next appointment is in the future on {parsed_next_appt} "
                f"({days_diff} day(s) from reference date {reference_date}). "
                f"Originating encounter: {latest_rel_dept} on {latest_rel_date}."
            )

        results[mrn] = FollowUpStatus(
            mrn=mrn,
            status=status,
            reference_date=reference_date,
            latest_relevant_visit_id=latest_rel_vid,
            latest_relevant_date=latest_rel_date,
            latest_relevant_dept=latest_rel_dept,
            latest_relevant_doctor=latest_rel_doctor,
            latest_relevant_notes=latest_rel_notes,
            scheduled_next_appointment=parsed_next_appt,
            days_difference=days_diff,
            status_reason=reason,
            timeline_explanation=" ".join(timeline_notes),
            subsequent_unrelated_encounters=subsequent_unrelated,
        )

    return results
