from datetime import date, timedelta

import pytest

from app.contracts import JalaliCalendar  # noqa: F401
from app.persian import (
    PersianCalendar,
    is_leap_jalali,
    normalize_fa,
    nowruz,
    number_to_words_fa,
    ordinal_words_fa,
    to_gregorian,
    to_jalali,
    to_latin_digits,
    to_persian_digits,
    weekday_index,
)
from app.persian.jalali import days_in_jalali_month

cal = PersianCalendar()

KNOWN = [
    (date(2020, 3, 20), (1399, 1, 1)),
    (date(2021, 3, 20), (1399, 12, 30)),   # 1399 is leap
    (date(2021, 3, 21), (1400, 1, 1)),
    (date(2023, 5, 30), (1402, 3, 9)),
    (date(2024, 3, 19), (1402, 12, 29)),
    (date(2024, 3, 20), (1403, 1, 1)),
    (date(2025, 3, 19), (1403, 12, 29)),   # 1403 leap: 30 Esfand exists
    (date(2025, 3, 20), (1403, 12, 30)),
    (date(2025, 3, 21), (1404, 1, 1)),
    (date(2029, 3, 19), (1407, 12, 29)),
    (date(2029, 3, 20), (1408, 1, 1)),
    (date(2030, 3, 20), (1408, 12, 30)),   # 1408 leap
    (date(2030, 3, 21), (1409, 1, 1)),
    (date(2026, 9, 30), (1405, 7, 8)),
    (date(1979, 2, 11), (1357, 11, 22)),
]


@pytest.mark.parametrize("g,j", KNOWN)
def test_known_dates(g, j):
    assert to_jalali(g) == j
    assert to_gregorian(*j) == g


def test_leap_years_and_nowruz():
    leaps = [y for y in range(1395, 1420) if is_leap_jalali(y)]
    assert leaps == [1395, 1399, 1403, 1408, 1412, 1416]
    assert nowruz(1403) == date(2024, 3, 20)
    assert nowruz(1404) == date(2025, 3, 21)
    assert nowruz(1408) == date(2029, 3, 20)


def test_round_trip_all_days_1300_1500():
    d = to_gregorian(1300, 1, 1)
    end = to_gregorian(1500, 12, 29)
    prev = None
    n = 0
    while d <= end:
        j = to_jalali(d)
        assert to_gregorian(*j) == d
        if prev:  # strictly consecutive
            py, pm, pd = prev
            if j[2] == 1:
                assert pd == days_in_jalali_month(py, pm)
                assert j[:2] in ((py, pm + 1), (py + 1, 1))
            else:
                assert j == (py, pm, pd + 1)
        prev = j
        d += timedelta(days=1)
        n += 1
    assert n > 73000


def test_year_lengths():
    for y in range(1300, 1500):
        assert (nowruz(y + 1) - nowruz(y)).days in (365, 366)
        assert (nowruz(y + 1) - nowruz(y)).days == 366 if is_leap_jalali(y) else True


def test_invalid_dates():
    with pytest.raises(ValueError):
        to_gregorian(1404, 12, 30)  # 1404 not leap
    with pytest.raises(ValueError):
        to_gregorian(1404, 13, 1)
    with pytest.raises(ValueError):
        to_gregorian(1404, 7, 31)
    with pytest.raises(ValueError):
        days_in_jalali_month(1404, 0)
    with pytest.raises(ValueError):
        to_jalali(date(9000, 1, 1))


def test_weekdays_saturday_first():
    assert weekday_index(date(2023, 5, 27)) == 0  # Saturday
    assert cal.weekday_name(date(2023, 5, 27)) == "شنبه"
    assert cal.format(date(2023, 5, 28), "weekday") == "یکشنبه"
    assert cal.format(date(2023, 6, 2), "weekday") == "جمعه"
    assert cal.weekday_name(date(2023, 5, 31)) == "چهارشنبه"


def test_format_styles():
    d = date(2023, 5, 30)
    assert cal.format(d) == "1402/03/09"
    assert cal.format(d, "words") == "نهم خرداد یک هزار و چهارصد و دو"
    assert cal.format(d, "long") == "سه‌شنبه نهم خرداد یک هزار و چهارصد و دو"
    with pytest.raises(ValueError):
        cal.format(d, "bogus")  # type: ignore[arg-type]


def test_add_days_and_parse():
    assert cal.add_days(date(2024, 2, 28), 2) == date(2024, 3, 1)
    assert cal.add_days(date(2024, 3, 1), -1) == date(2024, 2, 29)
    assert cal.parse("۱۴۰۲/۰۳/۰۹") == date(2023, 5, 30)
    assert cal.parse("1402-3-9") == date(2023, 5, 30)
    with pytest.raises(ValueError):
        cal.parse("nonsense")
    assert cal.month_name(3) == "خرداد"
    assert cal.is_leap(1403)
    assert cal.to_jalali(date(2023, 5, 30)) == (1402, 3, 9)
    assert cal.to_gregorian(1402, 3, 9) == date(2023, 5, 30)


@pytest.mark.parametrize("n,w", [
    (0, "صفر"), (1, "یک"), (10, "ده"), (11, "یازده"), (19, "نوزده"), (20, "بیست"), (21, "بیست و یک"),
    (99, "نود و نه"), (100, "یکصد"), (101, "یکصد و یک"), (215, "دویست و پانزده"),
    (1000, "یک هزار"), (1402, "یک هزار و چهارصد و دو"), (2000, "دو هزار"),
    (12345, "دوازده هزار و سیصد و چهل و پنج"), (1000000, "یک میلیون"),
    (202500000, "دویست و دو میلیون و پانصد هزار"), (-5, "منفی پنج"),
])
def test_number_words(n, w):
    assert number_to_words_fa(n) == w
    assert cal.number_to_words_fa(n) == w


def test_number_words_too_large():
    with pytest.raises(ValueError):
        number_to_words_fa(10 ** 30)


@pytest.mark.parametrize("n,w", [(1, "اول"), (2, "دوم"), (3, "سوم"), (4, "چهارم"), (9, "نهم"), (10, "دهم"),
                                 (13, "سیزدهم"), (20, "بیستم"), (21, "بیست و یکم"), (22, "بیست و دوم"),
                                 (23, "بیست و سوم"), (30, "سی‌ام"), (31, "سی و یکم")])
def test_ordinals(n, w):
    assert ordinal_words_fa(n) == w
    assert cal.ordinal_words_fa(n) == w


def test_ordinal_invalid():
    with pytest.raises(ValueError):
        ordinal_words_fa(0)


def test_digits():
    assert to_persian_digits("Room 12/05") == "Room ۱۲/۰۵"
    assert to_persian_digits("١٢٣") == "۱۲۳"
    assert to_latin_digits("۱۴۰۲/٠٣/۰۹") == "1402/03/09"
    assert to_latin_digits("۱٫۵") == "1.5"
    assert cal.to_persian_digits("5") == "۵" and cal.to_latin_digits("۵") == "5"


def test_normalize():
    assert normalize_fa("علي  كريمي‏ ") == "علی کریمی"
    assert normalize_fa("a‌b", strip_zwnj=True) == "ab"
