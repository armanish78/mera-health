"""Candidate cohort identification and evidence explanation module.

Evaluates four independent, audited diabetes-related evidence indicators:
  1. Diabetology department visit
  2. Diabetes-related note keyword matches
  3. Antidiabetic prescription matches
  4. Glycemic laboratory test matches

Provides structured explanations and highlights known ambiguity caveats
(e.g., Metformin for PCOS/GDM in OBG, screening lab ordering, family history in notes).
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

import pandas as pd

from src.config import DEFAULT_REFERENCE_DATE
from src.data_loader import parse_date_safe


# Audited token patterns matching WORKLOG.md & scripts/audit_data.py
NOTE_DIABETES_PATTERN = re.compile(
    r"\b(diabet\w*|dm|dm2|t2dm|type\s*2|niddm|hba1c|a1c|fbs|ppbs|grbs|sugars?|oha)\b",
    re.IGNORECASE,
)

ANTIDIABETIC_DRUG_PATTERN = re.compile(
    r"(metformin|glimepiride|gliclazide|sitagliptin|vildagliptin|"
    r"dapagliflozin|empagliflozin|insulin|mixtard|glargine|"
    r"degludec|lispro|aspart)",
    re.IGNORECASE,
)

GLYCEMIC_TEST_NAMES: Set[str] = {
    "hba1c",
    "a1c",
    "glycated hb",
    "fbs",
    "glucose (f)",
    "fasting glucose",
    "ppbs",
    "glucose (pp)",
    "post prandial glucose",
}


@dataclass
class CandidateEvidence:
    """Detailed evidence indicators and explanations for a patient."""

    mrn: str
    name: str
    has_dept: bool = False
    has_notes: bool = False
    has_rx: bool = False
    has_labs: bool = False

    indicator_count: int = 0
    indicator_names: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    ambiguity_warnings: List[str] = field(default_factory=list)

    # Specific evidence items for UI inspector
    dept_visits: List[Dict[str, str]] = field(default_factory=list)
    note_matches: List[Dict[str, str]] = field(default_factory=list)
    rx_matches: List[Dict[str, str]] = field(default_factory=list)
    lab_matches: List[Dict[str, str]] = field(default_factory=list)

    @property
    def is_candidate(self) -> bool:
        """True if patient exhibits at least one diabetes evidence indicator."""
        return self.indicator_count > 0

    @property
    def signal_concordance(self) -> str:
        """Categorizes candidate into multiple vs single proxy indicators."""
        if self.indicator_count >= 3:
            return "Multiple indicators (3-4 sources) — Broad proxy evidence"
        elif self.indicator_count == 2:
            return "Multiple indicators (2 sources) — Corroborated proxy evidence"
        elif self.indicator_count == 1:
            return "Single indicator (1 source) — Isolated proxy evidence (verify carefully)"
        return "No indicators"

    @property
    def confidence_level(self) -> str:
        """Backwards-compatible alias for signal_concordance."""
        return self.signal_concordance


def evaluate_cohort(
    patients_df: pd.DataFrame,
    visits_df: pd.DataFrame,
    labs_df: pd.DataFrame,
    rx_df: pd.DataFrame,
    reference_date: datetime.date = DEFAULT_REFERENCE_DATE,
) -> Dict[str, CandidateEvidence]:
    """Evaluate evidence indicators for every patient as of the reference_date.

    Only clinical events (encounters, notes, prescriptions, lab collections)
    that occurred on or before reference_date are considered eligible historical evidence.

    Returns a dict mapping MRN -> CandidateEvidence.
    """
    evidence_map: Dict[str, CandidateEvidence] = {}

    for _, p_row in patients_df.iterrows():
        mrn = p_row["mrn"]
        evidence_map[mrn] = CandidateEvidence(
            mrn=mrn,
            name=p_row.get("name", "Unknown"),
        )

    # 1. Evaluate Diabetology Visits
    for _, v_row in visits_df.iterrows():
        mrn = v_row.get("mrn", "")
        if mrn not in evidence_map:
            continue
        v_date = parse_date_safe(v_row.get("visit_date"))
        if not v_date or v_date > reference_date:
            continue
        dept = v_row.get("department", "").strip()
        if dept.lower() == "diabetology":
            ev = evidence_map[mrn]
            ev.has_dept = True
            ev.dept_visits.append({
                "visit_id": v_row.get("visit_id", ""),
                "date": v_row.get("visit_date", ""),
                "doctor": v_row.get("doctor", ""),
                "next_appointment": v_row.get("next_appointment", ""),
                "notes": v_row.get("notes", ""),
            })

    # 2. Evaluate Clinical Note Keyword Matches
    for _, v_row in visits_df.iterrows():
        mrn = v_row.get("mrn", "")
        if mrn not in evidence_map:
            continue
        v_date = parse_date_safe(v_row.get("visit_date"))
        if not v_date or v_date > reference_date:
            continue
        note_text = v_row.get("notes", "")
        match = NOTE_DIABETES_PATTERN.search(note_text)
        if match:
            ev = evidence_map[mrn]
            ev.has_notes = True
            matched_token = match.group(0)
            ev.note_matches.append({
                "visit_id": v_row.get("visit_id", ""),
                "date": v_row.get("visit_date", ""),
                "department": v_row.get("department", ""),
                "doctor": v_row.get("doctor", ""),
                "matched_token": matched_token,
                "notes": note_text,
            })

    # 3. Evaluate Antidiabetic Prescriptions
    # Map visit_id -> department for context (e.g. OBG)
    v_dept_map = dict(zip(visits_df["visit_id"], visits_df["department"]))
    for _, r_row in rx_df.iterrows():
        mrn = r_row.get("mrn", "")
        if mrn not in evidence_map:
            continue
        rx_date = parse_date_safe(r_row.get("prescribed_on"))
        if not rx_date or rx_date > reference_date:
            continue
        drug_name = r_row.get("drug", "")
        match = ANTIDIABETIC_DRUG_PATTERN.search(drug_name)
        if match:
            ev = evidence_map[mrn]
            ev.has_rx = True
            vid = r_row.get("visit_id", "")
            dept = v_dept_map.get(vid, "Unknown")
            ev.rx_matches.append({
                "visit_id": vid,
                "drug": drug_name,
                "dose": r_row.get("dose", ""),
                "date": r_row.get("prescribed_on", ""),
                "department": dept,
                "matched_class": match.group(0),
            })

    # 4. Evaluate Glycemic Lab Tests
    for _, l_row in labs_df.iterrows():
        mrn = l_row.get("mrn", "")
        if mrn not in evidence_map:
            continue
        l_date = parse_date_safe(l_row.get("collected_on"))
        if not l_date or l_date > reference_date:
            continue
        test_name = (l_row.get("test_name", "") or "").strip().lower()
        if test_name in GLYCEMIC_TEST_NAMES:
            ev = evidence_map[mrn]
            ev.has_labs = True
            ev.lab_matches.append({
                "test_name": l_row.get("test_name", ""),
                "value": l_row.get("value", ""),
                "unit": l_row.get("unit", ""),
                "reference_range": l_row.get("reference_range", ""),
                "collected_on": l_row.get("collected_on", ""),
            })

    # Synthesize counts, reasons, and ambiguity warnings
    for mrn, ev in evidence_map.items():
        reasons = []
        names = []

        if ev.has_dept:
            names.append("Diabetology Department")
            reasons.append(f"Seen in specialty Diabetology ({len(ev.dept_visits)} visit(s))")

        if ev.has_notes:
            names.append("Clinical Notes Match")
            tokens = {m["matched_token"].lower() for m in ev.note_matches}
            reasons.append(f"Notes contain diabetes keywords: {', '.join(sorted(tokens))}")

        if ev.has_rx:
            names.append("Antidiabetic Prescriptions")
            drugs = {m["drug"] for m in ev.rx_matches}
            reasons.append(f"Prescribed antidiabetic medication(s): {', '.join(sorted(drugs))}")

        if ev.has_labs:
            names.append("Glycemic Lab Tests")
            tests = {m["test_name"] for m in ev.lab_matches}
            reasons.append(f"Glycemic laboratory tests recorded: {', '.join(sorted(tests))}")

        ev.indicator_names = names
        ev.indicator_count = len(names)
        ev.reasons = reasons

        # Ambiguity / False Positive Warnings:
        warnings = []
        # Case A: Metformin in OBG (potential PCOS or GDM)
        obg_metformin_rx = [
            m for m in ev.rx_matches
            if m["department"].upper() == "OBG" and "metformin" in m["drug"].lower()
        ]
        if obg_metformin_rx and not ev.has_dept:
            warnings.append(
                "Non-diabetic medication context: Metformin prescribed in Obstetrics & Gynecology (OBG). "
                "Frequently prescribed for PCOS or Gestational Diabetes; requires chart verification."
            )

        # Case B: Only Glycemic Labs (possible screening with normal results)
        if ev.has_labs and ev.indicator_count == 1:
            warnings.append(
                "Screening lab only: Patient has glycemic lab tests without Diabetology visits, notes, or prescriptions. "
                "Ordering a test does not prove a diabetes diagnosis; check if results were normal."
            )

        # Case C: Only Clinical Notes (potential family history or non-diagnostic mention)
        if ev.has_notes and ev.indicator_count == 1:
            paed_notes = [m for m in ev.note_matches if m["department"].lower() == "paediatrics"]
            if paed_notes:
                warnings.append(
                    "Pediatric note context: Diabetes keyword appeared in Paediatrics notes; "
                    "may represent family medical history rather than patient diagnosis."
                )
            else:
                warnings.append(
                    "Note mention only: Keyword matched in free text without specialty visits, drugs, or lab tests; "
                    "requires physician review to confirm diagnosis."
                )

        ev.ambiguity_warnings = warnings

    return evidence_map
