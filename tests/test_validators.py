"""Tests for app/validators.py."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app import validators as v

# ---- past_month_utc ---------------------------------------------------------


def test_past_month_utc_accepts_clearly_past():
    v.get("past_month_utc")("2020-01")
    v.get("past_month_utc")("2024-12")


def test_past_month_utc_rejects_current_month():
    now = datetime.now(UTC)
    current = f"{now.year:04d}-{now.month:02d}"
    with pytest.raises(ValueError, match="past month"):
        v.get("past_month_utc")(current)


def test_past_month_utc_rejects_future_month():
    with pytest.raises(ValueError, match="past month"):
        v.get("past_month_utc")("2099-12")


def test_past_month_utc_rejects_invalid_format():
    with pytest.raises(ValueError):
        v.get("past_month_utc")("not-a-date")


def test_past_month_utc_rejects_invalid_month_value():
    # YYYY-MM with month=13 should not parse
    with pytest.raises(ValueError):
        v.get("past_month_utc")("2025-13")


def test_past_month_utc_rejects_non_string():
    with pytest.raises(ValueError):
        v.get("past_month_utc")(202506)


# ---- registry ---------------------------------------------------------------


def test_get_unknown_validator_raises():
    with pytest.raises(ValueError, match="unknown"):
        v.get("definitely-not-a-validator")
