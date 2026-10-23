# Implementation Plan: Diabetic Patient Follow-up

## 1. Objective
Build a local tool that helps hospital front-desk staff identify
patients whose records suggest they may be overdue for diabetes
follow-up. Show the reasons for inclusion and flag uncertain cases
for human review. No login or deployment is required.

## 2. Initial Investigation
Audit the four CSV files for identifier consistency, missing contact
details, duplicates, date inconsistencies, and available evidence of
diabetes and follow-up dates. Preserve the original data.

## 3. Key Uncertainties
The export has no single authoritative diabetes diagnosis field.
The meaning of "overdue" is also unclear, particularly when follow-up
dates are missing or later visits may affect a patient's status.
Do not silently infer diagnoses or invent due dates.

## 4. Approach and Validation
Provisionally use Python, pandas, Streamlit and pytest. Implement
transparent classification rules, explain each result, flag ambiguous
records for review, and validate representative cases against the
source data.

## 5. Deliverables and Open Questions
Deliver the tool, run instructions, DECISIONS.md and reply.txt
(under 200 words). Clarify the reference date, acceptable diagnosis
evidence, missing follow-up dates, relevant visit types and contact
exceptions. If clarification is unavailable, document assumptions
and limitations. Preserve meaningful Git history and the agent
transcript where available.