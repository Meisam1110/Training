"""Masking of personal data for list/detail responses."""
from __future__ import annotations


def mask_tail(value: str | None, keep: int = 2) -> str:
    """Return ``******34``: same length as the value would leak, so use a fixed width."""
    if not value:
        return ""
    return "*" * 8 + value[-keep:] if len(value) > keep else "*" * 8


def mask_national_code(v: str | None) -> str:
    return mask_tail(v, 2)


def mask_mobile(v: str | None) -> str:
    return mask_tail(v, 2)


def mask_date(v: str | None) -> str:
    return "****-**-**" if v else ""
