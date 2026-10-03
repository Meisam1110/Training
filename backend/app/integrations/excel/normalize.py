"""Cell/header normalisation for the iCare / IFS / legacy workbooks. No PII is ever put in messages."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from app.persian import normalize_fa, to_gregorian, to_latin_digits

_SUFFIX_RE = re.compile(r"\s*\[\s*MTNIrancell\s*-\s*([^\]]*?)\s*\]\s*$", re.IGNORECASE)
_TICKET_RE = re.compile(r"\b([A-Za-z]{2,10})\s*-?\s*(\d{3,9})\b")
_MTC_RE = re.compile(r"MTC\s*-?\s*(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})")
_DASHES = {"", "-", "--", "—", "–", "n/a", "na", "none", "null", "0"}


def norm_header(h: Any) -> str:
    s = normalize_fa(to_latin_digits(str(h if h is not None else ""))).lower()
    s = re.sub(r"[:_\-./]+", " ", s)
    return " ".join(s.split())


def build_column_map(header_row: Sequence[Any], aliases: Mapping[str, Sequence[str]]) -> dict[str, int]:
    """key -> column index, matching normalised header text against *aliases* (first hit wins)."""
    normed = [norm_header(h) for h in header_row]
    result: dict[str, int] = {}
    for key, names in aliases.items():
        for alias in names:
            a = norm_header(alias)
            if a in normed:
                result[key] = normed.index(a)
                break
    return result


def score_header(row: Sequence[Any], aliases: Mapping[str, Sequence[str]]) -> int:
    return len(build_column_map(row, aliases))


def cell(row: Sequence[Any], cmap: Mapping[str, int], key: str) -> Any:
    i = cmap.get(key)
    if i is None or i >= len(row):
        return None
    return row[i]


def to_text(v: Any) -> str:
    """Trimmed text of a cell; integral floats lose '.0'; None -> ''."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return normalize_fa(str(v), strip_zwnj=False)


def fa_text(v: Any) -> str:
    return to_text(v)


def is_blank(v: Any) -> bool:
    return to_text(v) == ""


def parse_date(v: Any) -> tuple[date | None, bool]:
    """Return (date|None, ok). Blank / '-' -> (None, True); unparsable -> (None, False).
    Accepts datetimes, Excel serials, ISO / slash strings in any digit script, Jalali years
    (< 1700 are converted) and the legacy 'Sunday-28-May-2023' form."""
    if v is None:
        return None, True
    if isinstance(v, datetime):
        return v.date(), True
    if isinstance(v, date):
        return v, True
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 < v < 80000:
            from openpyxl.utils.datetime import from_excel
            try:
                return from_excel(v).date(), True
            except Exception:  # noqa: BLE001
                return None, False
        return None, False
    s = to_latin_digits(to_text(v)).strip()
    if s.lower() in _DASHES:
        return None, True
    m = _DATE_RE.search(s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            if y < 1700:
                return to_gregorian(y, mo, d), True
            return date(y, mo, d), True
        except ValueError:
            return None, False
    for fmt in ("%A-%d-%b-%Y", "%d-%b-%Y", "%d-%B-%Y", "%A-%d-%B-%Y"):
        try:
            return datetime.strptime(s, fmt).date(), True
        except ValueError:
            continue
    return None, False


def split_reporter(name: Any) -> tuple[str, str]:
    """'Name [ MTNIrancell - CR ]' -> ('Name', 'CR'). Suffix missing -> (name, '')."""
    s = to_text(name)
    m = _SUFFIX_RE.search(s)
    if not m:
        return s, ""
    return s[: m.start()].strip(), m.group(1).strip()


def clean_ticket(v: Any) -> str:
    """'lms 900002' / 'LMS-900002 ' / Persian digits -> 'LMS-900002'; unknown shapes are returned trimmed."""
    s = to_latin_digits(to_text(v))
    m = _TICKET_RE.search(s)
    if m:
        return f"{m.group(1).upper()}-{m.group(2)}"
    return s.strip()


def clean_section_b(v: Any) -> str:
    """Section B cleanup as the VBA did: 'MTC-123' stays; blanks/'0'/dashes -> '-'."""
    s = to_latin_digits(to_text(v))
    m = _MTC_RE.search(s)
    if m:
        return f"MTC-{m.group(1)}"
    return "-" if s.strip().lower() in _DASHES else s.strip()


def clean_emp_no(v: Any) -> str:
    s = to_latin_digits(to_text(v)).replace(" ", "").upper()
    return s


def fix_national_code(v: Any) -> str:
    """Excel stores national codes as numbers: restore dropped leading zeros (10 digits)."""
    s = re.sub(r"\D", "", to_latin_digits(to_text(v)))
    if not s:
        return ""
    return s.zfill(10) if len(s) < 10 else s


def fix_mobile(v: Any) -> str:
    s = re.sub(r"[^\d+]", "", to_latin_digits(to_text(v)))
    if len(s) == 10 and s.startswith("9"):
        return "0" + s
    if s.startswith("+98") or s.startswith("0098"):
        s = "0" + s.replace("+98", "", 1).replace("0098", "", 1)
    return s


def clean_email(v: Any) -> str:
    s = to_text(v).strip().lower()
    return s if "@" in s else ""


def gender(v: Any) -> str:
    s = to_text(v).lower()
    if s in ("male", "m", "مرد"):
        return "male"
    if s in ("female", "f", "زن"):
        return "female"
    return ""


def to_float(v: Any) -> tuple[float | None, bool]:
    if v is None or to_text(v) in ("", "-"):
        return None, True
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v), True
    try:
        return float(to_latin_digits(to_text(v)).replace(",", "")), True
    except ValueError:
        return None, False


def to_int(v: Any, default: int = 0) -> int:
    f, ok = to_float(v)
    return int(f) if ok and f is not None else default
