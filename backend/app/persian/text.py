"""Persian text helpers: digit conversion and character normalisation (no dependencies)."""
from __future__ import annotations

_FA = "۰۱۲۳۴۵۶۷۸۹"
_AR = "٠١٢٣٤٥٦٧٨٩"
_LAT = "0123456789"

_TO_PERSIAN = str.maketrans(_LAT + _AR, _FA + _FA)
_TO_LATIN = str.maketrans(_FA + _AR, _LAT + _LAT)

# Arabic variants that show up in exports typed on Arabic keyboards.
_NORMALIZE = str.maketrans({
    "ي": "ی", "ى": "ی", "ئ": "ئ", "ك": "ک", "ۀ": "ه", "ة": "ه",
    "‏": "", "‎": "", "‪": "", "‫": "", "‬": "",
    " ": " ", "﻿": "",
})


def to_persian_digits(s: str) -> str:
    """Latin and Arabic-Indic digits -> Persian digits (۰-۹)."""
    return str(s).translate(_TO_PERSIAN)


def to_latin_digits(s: str) -> str:
    """Persian and Arabic-Indic digits -> Latin digits. Also maps the Arabic decimal/thousand separators."""
    return str(s).translate(_TO_LATIN).replace("٫", ".").replace("٬", ",")


def normalize_fa(s: str, *, strip_zwnj: bool = False) -> str:
    """Unify yeh/kaf variants, remove bidi marks, collapse whitespace."""
    out = str(s).translate(_NORMALIZE)
    if strip_zwnj:
        out = out.replace("‌", "")
    return " ".join(out.split())
