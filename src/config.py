"""Shared configuration constants for mera.health follow-up application."""

from __future__ import annotations

import datetime

# Default provisional working reference date established during data audit
# (Prescriptions and visits end on this date; requires hospital confirmation)
DEFAULT_REFERENCE_DATE: datetime.date = datetime.date(2026, 9, 29)
