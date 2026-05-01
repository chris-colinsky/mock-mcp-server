"""
Built-in custom validators for x-mock-validate, used to express request rules
that standard OAS schema keywords can't (regex/range/etc. ARE expressible
via OAS, so prefer those — this file is for the rest).

x-mock-validate:
  - field: report_month        # query param name
    type: past_month_utc       # validator id
    message: "..."             # optional override

Validators receive the resolved value and raise ValueError on failure.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


def _past_month_utc(value: Any) -> None:
    """Value must parse as YYYY-MM and be strictly before the current UTC month."""
    if not isinstance(value, str):
        raise ValueError("expected YYYY-MM string")
    try:
        d = datetime.strptime(value + "-01", "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("must be a valid YYYY-MM date") from exc
    now = datetime.now(UTC)
    if (d.year, d.month) >= (now.year, now.month):
        raise ValueError("must be a past month (current month and future are not allowed)")


VALIDATORS: dict[str, Callable[[Any], None]] = {
    "past_month_utc": _past_month_utc,
}


def get(name: str) -> Callable[[Any], None]:
    if name not in VALIDATORS:
        raise ValueError(f"unknown x-mock-validate type: {name!r}")
    return VALIDATORS[name]
