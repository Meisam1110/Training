"""Jalali (Solar Hijri) calendar: 33-year-cycle arithmetic algorithm (Borkowski), valid for
years -61..3177. Implements ``contracts.JalaliCalendar``. Pure stdlib.

The break table below is the one used by the widely verified ``jalaali`` reference
implementations; it reproduces the official calendar for 1178-1600 (e.g. leap years 1399,
1403, 1408, Nowruz 1403 = 2024-03-20, 1404 = 2025-03-21).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from .text import normalize_fa, to_latin_digits, to_persian_digits
from .words import number_to_words_fa, ordinal_words_fa

_BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097,
           2192, 2262, 2324, 2394, 2456, 3178]

MONTHS_FA = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
# Saturday-first: index 0 = Saturday (Python's weekday(): Monday=0, so Saturday=5)
WEEKDAYS_FA = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
WEEKDAYS_EN = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

MIN_JYEAR, MAX_JYEAR = 1, 3177


def _jal_cal(jy: int) -> tuple[int, int, int]:
    """Return (leap_remainder, gregorian_year, march_day_of_nowruz)."""
    if jy < _BREAKS[0] or jy >= _BREAKS[-1]:
        raise ValueError(f"Jalali year out of range: {jy}")
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for jm in _BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += (jump // 33) * 8 + (jump % 33) // 4
        jp = jm
    n = jy - jp
    leap_j += (n // 33) * 8 + ((n % 33) + 3) // 4
    if jump % 33 == 4 and jump - n == 4:
        leap_j += 1
    leap_g = gy // 4 - ((gy // 100 + 1) * 3) // 4 - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + ((jump + 4) // 33) * 33
    leap = ((n + 1) % 33 - 1) % 4
    if leap == -1:
        leap = 4
    return leap, gy, march


def is_leap_jalali(jy: int) -> bool:
    return _jal_cal(jy)[0] == 0


def days_in_jalali_month(jy: int, jm: int) -> int:
    if not 1 <= jm <= 12:
        raise ValueError("month must be 1..12")
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_leap_jalali(jy) else 29


def nowruz(jy: int) -> date:
    """Gregorian date of 1 Farvardin of Jalali year *jy*."""
    _, gy, march = _jal_cal(jy)
    return date(gy, 3, 1) + timedelta(days=march - 1)


def to_jalali(d: date) -> tuple[int, int, int]:
    jy = d.year - 621
    try:
        start = nowruz(jy)
    except ValueError:
        raise ValueError(f"date out of supported range: {d}") from None
    if d < start:
        jy -= 1
        start = nowruz(jy)
    k = (d - start).days
    if k <= 185:
        return jy, 1 + k // 31, k % 31 + 1
    k -= 186
    return jy, 7 + k // 30, k % 30 + 1


def to_gregorian(jy: int, jm: int, jd: int) -> date:
    if not 1 <= jm <= 12 or not 1 <= jd <= days_in_jalali_month(jy, jm):
        raise ValueError(f"invalid Jalali date {jy}/{jm}/{jd}")
    offset = (jm - 1) * 31 - (jm // 7) * (jm - 7) + jd - 1
    return nowruz(jy) + timedelta(days=offset)


def weekday_index(d: date) -> int:
    """0 = Saturday ... 6 = Friday."""
    return (d.weekday() + 2) % 7


class PersianCalendar:
    """Implements ``contracts.JalaliCalendar`` (plus a few helpers used by letters)."""

    months = MONTHS_FA

    def to_jalali(self, d: date) -> tuple[int, int, int]:
        return to_jalali(d)

    def to_gregorian(self, y: int, m: int, d: int) -> date:
        return to_gregorian(y, m, d)

    def is_leap(self, jy: int) -> bool:
        return is_leap_jalali(jy)

    def weekday_name(self, d: date) -> str:
        return WEEKDAYS_FA[weekday_index(d)]

    def month_name(self, m: int) -> str:
        return MONTHS_FA[m - 1]

    def format(self, d: date, style: Literal["short", "words", "weekday", "long"] = "short") -> str:
        y, m, dd = to_jalali(d)
        if style == "short":
            return f"{y:04d}/{m:02d}/{dd:02d}"
        if style == "words":
            return f"{ordinal_words_fa(dd)} {MONTHS_FA[m - 1]} {number_to_words_fa(y)}"
        if style == "weekday":
            return self.weekday_name(d)
        if style == "long":
            return f"{self.weekday_name(d)} {self.format(d, 'words')}"
        raise ValueError(f"unknown style: {style}")

    def add_days(self, d: date, n: int) -> date:
        return d + timedelta(days=int(n))

    def number_to_words_fa(self, n: int) -> str:
        return number_to_words_fa(n)

    def ordinal_words_fa(self, n: int) -> str:
        return ordinal_words_fa(n)

    def to_persian_digits(self, s: str) -> str:
        return to_persian_digits(s)

    def to_latin_digits(self, s: str) -> str:
        return to_latin_digits(s)

    def parse(self, s: str) -> date:
        """Parse 'YYYY/MM/DD' (Jalali, any digit script; '-' also accepted)."""
        parts = normalize_fa(to_latin_digits(s)).replace("-", "/").split("/")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("expected YYYY/MM/DD")
        return to_gregorian(*(int(p) for p in parts))
