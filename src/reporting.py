"""Reporting and review table aggregation module for front-desk staff.

Assembles candidate cohort evidence, follow-up status, and contact flags
into a clean, structured DataFrame ready for interactive filtering and CSV export.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from src.cohort import CandidateEvidence
from src.contact import ContactInfo
from src.followup import FollowUpStatus


# Stable schema for candidate report DataFrame
REPORT_COLUMNS: List[str] = [
    "mrn",
    "name",
    "status",
    "next_appointment",
    "days_relative",
    "days_difference_numeric",
    "latest_relevant_date",
    "latest_department",
    "latest_doctor",
    "indicator_count",
    "indicators",
    "confidence_level",
    "phone",
    "contact_flag",
    "contact_warning",
    "inclusion_reasons",
    "ambiguity_caveats",
    "status_explanation",
    "timeline_notes",
]

EXPORT_COLUMNS: List[str] = [
    "mrn",
    "name",
    "status",
    "next_appointment",
    "days_relative",
    "latest_relevant_date",
    "latest_department",
    "latest_doctor",
    "phone",
    "contact_flag",
    "contact_warning",
    "indicators",
    "inclusion_reasons",
    "ambiguity_caveats",
    "status_explanation",
]


def build_candidate_report_df(
    candidates: Dict[str, CandidateEvidence],
    followups: Dict[str, FollowUpStatus],
    contacts: Dict[str, ContactInfo],
) -> pd.DataFrame:
    """Combine evidence, follow-up status, and contact data into a unified DataFrame.

    Only includes candidate patients (patients with at least one indicator).
    Guarantees a stable column schema defined by REPORT_COLUMNS even when zero candidates match.
    """
    rows: List[Dict[str, str | int | None]] = []

    for mrn, ev in candidates.items():
        if not ev.is_candidate:
            continue

        fu = followups.get(mrn)
        ci = contacts.get(mrn)

        # Format days difference string
        days_str = "N/A"
        if fu and fu.days_difference is not None:
            if fu.is_due_or_overdue:
                days_str = f"{fu.days_difference} days overdue"
            elif fu.is_upcoming:
                days_str = f"In {fu.days_difference} days"

        # Format phone status tag
        phone_tag = "Populated"
        if ci:
            if ci.is_missing:
                phone_tag = "MISSING PHONE"
            elif ci.is_shared:
                phone_tag = f"SHARED ({ci.shared_patient_count} pts)"

        rows.append({
            "mrn": mrn,
            "name": ev.name,
            "status": fu.status if fu else "Unknown",
            "next_appointment": (
                fu.scheduled_next_appointment.isoformat()
                if (fu and fu.scheduled_next_appointment)
                else "Unscheduled / None"
            ),
            "days_relative": days_str,
            "days_difference_numeric": fu.days_difference if fu else None,
            "latest_relevant_date": (
                fu.latest_relevant_date.isoformat()
                if (fu and fu.latest_relevant_date)
                else "None"
            ),
            "latest_department": fu.latest_relevant_dept if fu else "None",
            "latest_doctor": fu.latest_relevant_doctor if fu else "None",
            "indicator_count": ev.indicator_count,
            "indicators": ", ".join(ev.indicator_names),
            "confidence_level": ev.confidence_level,
            "phone": ci.phone if (ci and ci.phone) else "Missing",
            "contact_flag": phone_tag,
            "contact_warning": ci.warning_message if ci else "",
            "inclusion_reasons": " | ".join(ev.reasons),
            "ambiguity_caveats": " | ".join(ev.ambiguity_warnings) if ev.ambiguity_warnings else "None noted",
            "status_explanation": fu.status_reason if fu else "",
            "timeline_notes": fu.timeline_explanation if fu else "",
        })

    df = pd.DataFrame(rows, columns=REPORT_COLUMNS)

    if not df.empty:
        # Default sort: Due/overdue first (highest days overdue), then Upcoming, then Needs review
        status_priority = {
            "Due / potentially overdue — verify": 0,
            "Upcoming": 1,
            "Needs review — no reliable due date": 2,
        }
        df["_priority"] = df["status"].map(status_priority).fillna(99)
        # Sort by priority, then descending overdue days
        df = df.sort_values(
            by=["_priority", "days_difference_numeric"],
            ascending=[True, False],
        ).drop(columns=["_priority"])

    return df


def generate_export_csv(report_df: pd.DataFrame) -> str:
    """Generate CSV string formatted for front-desk outreach and supervisory audit.

    Exports column headers predictably even when there are zero candidate rows.
    """
    available_cols = [c for c in EXPORT_COLUMNS if c in report_df.columns]
    if not available_cols:
        available_cols = EXPORT_COLUMNS
    return report_df.reindex(columns=available_cols).to_csv(index=False)
