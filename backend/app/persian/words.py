"""Number -> Persian words (port of the VBA ``TbH``/``AbH`` helpers)."""
from __future__ import annotations

_ONES = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
_TEENS = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
_TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
_HUNDREDS = ["", "یکصد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]
_SCALES = ["", "هزار", "میلیون", "میلیارد", "تریلیون", "کوادریلیون"]

# Ordinals below 20 are irregular (3 -> سوم); everything else is cardinal + «م».
_ORD_SPECIAL = {1: "اول", 3: "سوم"}


def _below_1000(n: int) -> str:
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if r >= 20:
        t, o = divmod(r, 10)
        parts.append(_TENS[t])
        if o:
            parts.append(_ONES[o])
    elif r >= 10:
        parts.append(_TEENS[r - 10])
    elif r:
        parts.append(_ONES[r])
    return " و ".join(parts)


def number_to_words_fa(n: int) -> str:
    """1402 -> «یک هزار و چهارصد و دو». Zero -> «صفر»; negatives get «منفی»."""
    n = int(n)
    if n == 0:
        return "صفر"
    if n < 0:
        return "منفی " + number_to_words_fa(-n)
    groups = []
    i = 0
    while n:
        n, g = divmod(n, 1000)
        if g:
            groups.append((g, i))
        i += 1
    if groups[0][1] >= len(_SCALES) or i > len(_SCALES):
        raise ValueError("number too large")
    parts = []
    for g, idx in reversed(groups):
        w = _below_1000(g)
        parts.append(f"{w} {_SCALES[idx]}".strip())
    return " و ".join(parts)


def ordinal_words_fa(n: int) -> str:
    """9 -> «نهم», 21 -> «بیست و یکم», 30 -> «سی‌ام»."""
    n = int(n)
    if n < 1:
        raise ValueError("ordinal must be >= 1")
    if n in _ORD_SPECIAL:
        return _ORD_SPECIAL[n]
    if n % 10 == 3 and n > 3 and n % 100 != 13:
        base = number_to_words_fa(n)[: -len("سه")] + "سوم"
        return base
    if n % 10 == 1 and n > 1:
        return number_to_words_fa(n) + "م"  # ... و یکم
    w = number_to_words_fa(n)
    if w.endswith("ی"):        # سی -> سی‌ام
        return w + "‌ام"
    return w + "م"
