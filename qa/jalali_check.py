"""Independent verification of app.persian.jalali against jdatetime and convertdate for every day 1300..1500; boundaries; words; VBA 1499 hack."""
import sys; sys.path.insert(0, "/home/user/training/backend")
from datetime import date, timedelta
import jdatetime
from convertdate import persian
from app.persian import PersianCalendar
from app.persian.jalali import is_leap_jalali, to_jalali, to_gregorian, nowruz
cal = PersianCalendar()
d0 = date(1921, 3, 21); d1 = date(2121, 3, 21)
d = d0; bad_jd = []; bad_cd = []; n = 0
while d < d1:
    a = to_jalali(d)
    j = jdatetime.date.fromgregorian(date=d); b = (j.year, j.month, j.day)
    c = persian.from_gregorian(d.year, d.month, d.day)
    if a != b and len(bad_jd) < 10: bad_jd.append((d.isoformat(), a, b))
    if a != tuple(c) and len(bad_cd) < 10: bad_cd.append((d.isoformat(), a, tuple(c)))
    assert to_gregorian(*a) == d
    d += timedelta(days=1); n += 1
print(f"days checked: {n}; mismatches vs jdatetime: {len(bad_jd)} {bad_jd[:3]}; vs convertdate (astronomical): {len(bad_cd)} {bad_cd[:3]}")
print("leap years 1395..1420:", [y for y in range(1395, 1421) if is_leap_jalali(y)])
print("jdatetime leap 1395..1420:", [y for y in range(1395, 1421) if jdatetime.date(y, 1, 1).isleap()])
print("convertdate leap 1395..1420:", [y for y in range(1395, 1421) if persian.leap(y)])
for label, dd in [("Esfand 30 1399", date(2021, 3, 20)), ("Farvardin 1 1400", date(2021, 3, 21)), ("Esfand 30 1403", date(2025, 3, 20)), ("Esfand 29 1404", date(2026, 3, 20)), ("Nowruz 1405", date(2026, 3, 21)),
                  ("year rollover 2026-12-31", date(2026, 12, 31)), ("2027-01-01", date(2027, 1, 1)), ("Dey 11 1404 (Jan 1 2026)", date(2026, 1, 1))]:
    print(f"{label:28s} {dd} -> {cal.format(dd,'short')} | {cal.format(dd,'long')}")
try: to_gregorian(1404, 12, 30); print("invalid 1404/12/30 accepted (BAD)")
except ValueError: print("1404/12/30 rejected (correct: not leap)")
print("1403/12/30 ->", to_gregorian(1403, 12, 30))
# legacy hack: SUBSTITUTE(...,1499,1399) must be gone
print("date in 2120 (jalali 1499):", cal.format(date(2120, 6, 1), "short"), "| 1499 parse:", cal.parse("1499/01/01"))
import re, pathlib
hits = [str(p) for p in pathlib.Path("/home/user/training/backend/app").rglob("*.py") if re.search(r"1499|1399\b", p.read_text())]
print("files mentioning 1499/1399 literal in app/:", hits)
# words
for dd in (date(2026, 3, 21), date(2025, 3, 20), date(2026, 10, 31)):
    print(dd, cal.format(dd, "words"))
