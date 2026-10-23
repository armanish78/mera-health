"""mera.health — Diabetic Patient Follow-up Review Interface.

A local Streamlit application designed for hospital front-desk staff to review
patients whose records suggest they may need diabetes follow-up.
"""

from __future__ import annotations

import datetime
import streamlit as st

from src.cohort import evaluate_cohort
from src.contact import analyze_contact_data
from src.data_loader import identify_duplicate_labs, load_raw_csvs, parse_date_safe
from src.config import DEFAULT_REFERENCE_DATE
from src.followup import evaluate_followup
from src.reporting import build_candidate_report_df, generate_export_csv


# Page configuration
st.set_page_config(
    page_title="mera.health | Follow-up Review",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def get_cached_raw_data():
    """Load and cache raw CSV datasets."""
    datasets = load_raw_csvs("data/raw")
    dedup_labs, num_dups = identify_duplicate_labs(datasets["lab_results.csv"])
    return datasets, dedup_labs, num_dups


def main():
    # -------------------------------------------------------------
    # 1. Header & Prominent Clinical Notice
    # -------------------------------------------------------------
    st.title("🏥 mera.health — Diabetes Follow-up Review Tool")
    st.caption("Decision-support system for hospital front-desk telephone outreach.")

    st.warning(
        "**CLINICAL NOTICE & SCOPE LIMITATION:** This application is an operational decision-support "
        "tool to assist front-desk staff with telephone scheduling. It flags patients exhibiting proxy "
        "evidence indicators (specialty encounters, note keywords, antidiabetic drugs, or glycemic labs). "
        "**It does NOT establish an authoritative clinical diagnosis, confirm active disease status, or "
        "replace physician review.** All candidate inclusions and overdue dates must be verified before "
        "clinical advice is given.",
        icon="⚠️",
    )

    # -------------------------------------------------------------
    # 2. Data Loading & Pipeline Execution
    # -------------------------------------------------------------
    try:
        datasets, dedup_labs, num_dup_labs = get_cached_raw_data()
    except Exception as e:
        st.error(f"Failed to load raw datasets from data/raw: {e}")
        st.stop()

    patients_df = datasets["patients.csv"]
    visits_df = datasets["visits.csv"]
    rx_df = datasets["prescriptions.csv"]

    # -------------------------------------------------------------
    # 3. Sidebar Controls & Reference Date
    # -------------------------------------------------------------
    st.sidebar.header("⚙️ Follow-up Settings")

    st.sidebar.markdown(
        "**Working Reference Date:**\n"
        "All encounter and prescription records in this export terminate on `2026-09-29`, "
        "while two lab results are dated later. `2026-09-29` serves as a *provisional* "
        "reference date for scheduling review and requires hospital operational confirmation."
    )

    selected_ref_date = st.sidebar.date_input(
        "Select Reference / As-of Date:",
        value=DEFAULT_REFERENCE_DATE,
        min_value=datetime.date(2023, 1, 1),
        max_value=datetime.date(2027, 12, 31),
        help="Dates on or before this date with a past next_appointment are marked 'Due / potentially overdue'.",
    )

    if selected_ref_date == DEFAULT_REFERENCE_DATE:
        st.sidebar.info("📌 Using default reference date: **2026-09-29 (PROVISIONAL)**")
    else:
        st.sidebar.warning(f"Custom reference date active: **{selected_ref_date}**")

    # Run cohort, follow-up, and contact evaluation
    candidates_map = evaluate_cohort(patients_df, visits_df, dedup_labs, rx_df, reference_date=selected_ref_date)
    followups_map = evaluate_followup(candidates_map, visits_df, rx_df, reference_date=selected_ref_date)
    contacts_map = analyze_contact_data(patients_df)
    report_df = build_candidate_report_df(candidates_map, followups_map, contacts_map)

    # -------------------------------------------------------------
    # 4. Sidebar Filtering Options
    # -------------------------------------------------------------
    st.sidebar.subheader("🔍 Filter Call List")

    # Status filter
    status_options = [
        "All Follow-up Statuses",
        "Due / potentially overdue — verify",
        "Upcoming",
        "Needs review — no reliable due date",
    ]
    selected_status = st.sidebar.selectbox("Follow-up Status:", status_options)

    # Indicator concordance filter
    concordance_options = [
        "All Candidate Patients",
        "Multiple indicators (2–4 sources)",
        "Single indicator only (1 source)",
    ]
    selected_concordance = st.sidebar.selectbox("Proxy Evidence Scope:", concordance_options)

    # Contact alert filter
    contact_options = [
        "All Contact Profiles",
        "Contact Warnings Only (Missing or Shared Phone)",
        "Missing Phone Number Only",
        "Shared Phone Number Only",
    ]
    selected_contact = st.sidebar.selectbox("Phone / Contact Filter:", contact_options)

    # Text search filter
    search_query = st.sidebar.text_input("Search Patient Name or MRN:", placeholder="e.g. SVH027... or Sharma").strip()

    # Apply filters
    filtered_df = report_df.copy()

    if selected_status != "All Follow-up Statuses":
        filtered_df = filtered_df[filtered_df["status"] == selected_status]

    if selected_concordance == "Multiple indicators (2–4 sources)":
        filtered_df = filtered_df[filtered_df["indicator_count"] >= 2]
    elif selected_concordance == "Single indicator only (1 source)":
        filtered_df = filtered_df[filtered_df["indicator_count"] == 1]

    if selected_contact == "Contact Warnings Only (Missing or Shared Phone)":
        filtered_df = filtered_df[filtered_df["contact_flag"] != "Populated"]
    elif selected_contact == "Missing Phone Number Only":
        filtered_df = filtered_df[filtered_df["contact_flag"] == "MISSING PHONE"]
    elif selected_contact == "Shared Phone Number Only":
        filtered_df = filtered_df[filtered_df["contact_flag"].str.startswith("SHARED")]

    if search_query:
        mask = (
            filtered_df["name"].str.contains(search_query, case=False, na=False, regex=False)
            | filtered_df["mrn"].str.contains(search_query, case=False, na=False, regex=False)
        )
        filtered_df = filtered_df[mask]

    # -------------------------------------------------------------
    # 5. Summary KPI Cards
    # -------------------------------------------------------------
    c1, c2, c3, c4, c5 = st.columns(5)
    total_pts = len(patients_df)
    total_cands = len(report_df)
    due_count = int((report_df["status"] == "Due / potentially overdue — verify").sum()) if "status" in report_df.columns else 0
    upcoming_count = int((report_df["status"] == "Upcoming").sum()) if "status" in report_df.columns else 0
    review_count = int((report_df["status"] == "Needs review — no reliable due date").sum()) if "status" in report_df.columns else 0

    candidate_pct_str = f"{(total_cands/total_pts)*100:.1f}% of hospital" if total_pts > 0 else "0.0% of hospital"

    c1.metric("Registered Denominator", f"{total_pts} pts")
    c2.metric("Candidate Cohort", f"{total_cands} pts", delta=candidate_pct_str)
    c3.metric("Due / Overdue", f"{due_count} pts", delta="Priority Outreach", delta_color="inverse")
    c4.metric("Upcoming Scheduled", f"{upcoming_count} pts", delta="Scheduled")
    c5.metric("Needs Review (Unscheduled)", f"{review_count} pts", delta="Missing Date", delta_color="off")

    st.markdown("---")

    # -------------------------------------------------------------
    # 6. Interactive Review Table & CSV Download
    # -------------------------------------------------------------
    t_col1, t_col2 = st.columns([3, 1])
    with t_col1:
        st.subheader(f"📋 Patient Review & Call List ({len(filtered_df)} patients shown)")
    with t_col2:
        export_csv_str = generate_export_csv(filtered_df)
        st.download_button(
            label="📥 Download Filtered Call List (CSV)",
            data=export_csv_str,
            file_name=f"mera_health_diabetes_call_list_{selected_ref_date}.csv",
            mime="text/csv",
            help="Download filtered list for front-desk staff telephone outreach.",
        )

    # Format table for display
    display_cols = [
        "mrn",
        "name",
        "status",
        "next_appointment",
        "days_relative",
        "latest_relevant_date",
        "latest_department",
        "phone",
        "contact_flag",
        "indicators",
    ]
    rename_map = {
        "mrn": "MRN",
        "name": "Patient Name",
        "status": "Follow-up Status",
        "next_appointment": "Next Appointment",
        "days_relative": "Overdue / In",
        "latest_relevant_date": "Latest Encounter",
        "latest_department": "Department",
        "phone": "Phone",
        "contact_flag": "Contact Flag",
        "indicators": "Matched Indicators",
    }
    if filtered_df.empty:
        if report_df.empty:
            st.info("ℹ️ No candidate patients identified as of the selected reference date. Select a later reference date to review candidate encounters.")
        else:
            st.info("ℹ️ No candidate patients match the selected filter criteria. Try adjusting your status, indicator, or search filters above.")
    else:
        table_to_show = filtered_df[display_cols].rename(columns=rename_map)

        # Colorize status column for immediate front-desk recognition
        def highlight_status(val):
            if "Due" in str(val):
                return "background-color: #ffdce0; color: #8a041a; font-weight: bold;"
            elif "Upcoming" in str(val):
                return "background-color: #d8f3e5; color: #0d6832; font-weight: bold;"
            elif "Needs review" in str(val):
                return "background-color: #fff3cd; color: #856404; font-weight: bold;"
            return ""

        def highlight_contact(val):
            if "MISSING" in str(val):
                return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
            elif "SHARED" in str(val):
                return "background-color: #e2e3e5; color: #383d41; font-weight: bold;"
            return ""

        styler = table_to_show.style
        # Support both pandas >= 2.1.0 (map) and older versions (applymap)
        styler_map = getattr(styler, "map", getattr(styler, "applymap", None))
        if styler_map:
            styled_table = styler_map(
                highlight_status, subset=["Follow-up Status"]
            )
            sub_map = getattr(styled_table, "map", getattr(styled_table, "applymap", None))
            if sub_map:
                styled_table = sub_map(highlight_contact, subset=["Contact Flag"])
        else:
            styled_table = styler

        st.dataframe(styled_table, use_container_width=True, height=360)

    st.markdown("---")

    # -------------------------------------------------------------
    # 7. Detailed Patient Inspector
    # -------------------------------------------------------------
    st.subheader("🔍 Patient Record Deep-Dive & Outreach Guide")
    st.caption("Select any candidate patient to view their complete evidence audit trail, clinical timeline, and contact warnings.")

    candidate_mrns = filtered_df["mrn"].tolist() if "mrn" in filtered_df.columns else []

    if not candidate_mrns:
        if report_df.empty:
            st.info("ℹ️ No candidate patients to inspect for the selected reference date.")
        else:
            st.info("ℹ️ No patients match these filters. Clear or adjust filters above to inspect patient details.")
    else:
        # Formatter for dropdown
        mrn_labels = {
            mrn: f"{mrn} — {candidates_map[mrn].name} [{followups_map[mrn].status}]"
            for mrn in candidate_mrns
        }

        selected_mrn = st.selectbox(
            "Choose Patient to Inspect:",
            options=candidate_mrns,
            format_func=lambda x: mrn_labels.get(x, x),
        )

        if selected_mrn:
            ev = candidates_map[selected_mrn]
            fu = followups_map[selected_mrn]
            ci = contacts_map[selected_mrn]

            p_col1, p_col2 = st.columns([2, 1])

            with p_col1:
                st.markdown(f"### **{ev.name}** (`{ev.mrn}`)")
                st.markdown(f"**Follow-up Determination:** `{fu.status}`")
                st.info(f"**Status Rationale:** {fu.status_reason}")

                if fu.timeline_explanation:
                    st.warning(f"**Specialty Timeline Caution:** {fu.timeline_explanation}")

                if ev.ambiguity_warnings:
                    for w in ev.ambiguity_warnings:
                        st.error(f"**Clinical Context Alert:** {w}")

            with p_col2:
                st.markdown("### **Contact Verification**")
                if ci.is_missing:
                    st.error("❌ **NO PHONE ON FILE**\n\nPatient cannot be reached by telephone. Front desk must check physical admission file or hospital master index.", icon="🚨")
                elif ci.is_shared:
                    st.warning(
                        f"⚠️ **SHARED PHONE NUMBER ({ci.phone})**\n\n"
                        f"This telephone number is shared across **{ci.shared_patient_count} patient records** in the hospital export.\n\n"
                        "**Identity Verification Protocol:** Staff must strictly verify the patient's full name and date of birth before mentioning diabetes or appointment details.",
                        icon="👥",
                    )
                else:
                    st.success(
                        f"📞 **Phone:** `{ci.phone}` (10 digits populated)\n\n"
                        "Reachability/active status unconfirmed. Standard verification protocol applies.",
                        icon="✅",
                    )

            # Tabbed Evidence Audit Trail
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📑 Evidence Breakdown",
                "📅 Visit Encounters",
                "💊 Prescriptions",
                "🧪 Lab Results",
                "ℹ️ Methodological Notes",
            ])

            with tab1:
                st.markdown("#### Matched Evidence Indicators")
                st.write(f"**Signal Corroboration:** {ev.signal_concordance} *(Proxy evidence only; not a diagnosis)*")
                for r in ev.reasons:
                    st.markdown(f"- ✅ **{r}**")

            with tab2:
                st.markdown("#### Clinical Encounters History")
                st.caption(f"Showing encounters with a recorded visit date on or before the selected reference date ({selected_ref_date}). Future-dated encounters are not shown.")
                p_visits = visits_df[visits_df["mrn"] == selected_mrn].copy()
                # Filter to visits on or before the selected reference date
                p_visits = p_visits[
                    p_visits["visit_date"].apply(
                        lambda d: (parse_date_safe(d) or datetime.date.max) <= selected_ref_date
                    )
                ]
                if not p_visits.empty:
                    st.dataframe(
                        p_visits[["visit_id", "visit_date", "department", "doctor", "next_appointment", "notes"]],
                        use_container_width=True,
                    )
                else:
                    st.info("No recorded visit encounters found for this patient on or before the reference date.")

            with tab3:
                st.markdown("#### Medication History")
                st.caption(f"Showing prescriptions with a recorded date on or before the selected reference date ({selected_ref_date}). Future-dated prescriptions are not shown.")
                p_rx = rx_df[rx_df["mrn"] == selected_mrn].copy()
                # Filter to prescriptions on or before the selected reference date
                p_rx = p_rx[
                    p_rx["prescribed_on"].apply(
                        lambda d: (parse_date_safe(d) or datetime.date.max) <= selected_ref_date
                    )
                ]
                if not p_rx.empty:
                    st.dataframe(
                        p_rx[["visit_id", "prescribed_on", "drug", "dose"]],
                        use_container_width=True,
                    )
                else:
                    st.info("No prescription records found for this patient on or before the reference date.")

            with tab4:
                st.markdown("#### Laboratory Results")
                st.caption(f"Showing lab results with a collection date on or before the selected reference date ({selected_ref_date}). Future-dated results are not shown.")
                p_labs = dedup_labs[dedup_labs["mrn"] == selected_mrn].copy()
                # Filter to labs on or before the selected reference date
                p_labs = p_labs[
                    p_labs["collected_on"].apply(
                        lambda d: (parse_date_safe(d) or datetime.date.max) <= selected_ref_date
                    )
                ]
                if not p_labs.empty:
                    st.dataframe(
                        p_labs[["test_name", "value", "unit", "reference_range", "collected_on"]],
                        use_container_width=True,
                    )
                else:
                    st.info("No laboratory records found for this patient on or before the reference date.")

            with tab5:
                st.markdown("""
                #### Operational Guidance & Hospital Uncertainties
                1. **Definition of 'Diabetic':** The hospital did not provide an authoritative diagnosis code or master problem list. Candidates reflect four proxy signals.
                2. **Unscheduled Recall:** 71.4% of hospital visits lack structured `next_appointment`. Front desk should check free-text review notes with the attending physician before assuming overdue intervals.
                3. **Specialty Continuity:** Encounters outside Diabetology (such as Orthopaedics or Dermatology) are not used to reset diabetes recall clocks.
                4. **Reference Date:** `2026-09-29` is provisional and subject to hospital confirmation.
                """)


if __name__ == "__main__":
    main()
