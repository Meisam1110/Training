"""Line-manager batching and exact invoice arithmetic (Decimal only, no float drift)."""
from __future__ import annotations

from collections import OrderedDict
from decimal import ROUND_DOWN, Decimal
from typing import Callable, Hashable, Sequence, TypeVar

T = TypeVar("T")
MAX_PER_MANAGER = 9      # the legacy Line Manager Approval letter has 9 rows


def batch_by_manager(items: Sequence[T], manager_of: Callable[[T], Hashable],
                     max_per_batch: int = MAX_PER_MANAGER) -> list[tuple[Hashable, list[T]]]:
    """Group *items* by manager (first-seen order) and cut each group into chunks of <= max_per_batch.
    Items with an empty manager key raise ValueError (they cannot be addressed)."""
    if max_per_batch < 1:
        raise ValueError("max_per_batch must be >= 1")
    groups: "OrderedDict[Hashable, list[T]]" = OrderedDict()
    for it in items:
        key = manager_of(it)
        if key in (None, ""):
            raise ValueError("item without a line manager")
        groups.setdefault(key, []).append(it)
    out: list[tuple[Hashable, list[T]]] = []
    for key, lst in groups.items():
        for i in range(0, len(lst), max_per_batch):
            out.append((key, lst[i:i + max_per_batch]))
    return out


def _dec(v: "Decimal | int | str | float") -> Decimal:
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        return Decimal(str(v))
    return Decimal(str(v).replace(",", "").strip())


def invoice_total(unit_amount: "Decimal | int | str | float", motivations: int) -> Decimal:
    """Legacy rule: invoice total = Amount x number of motivations."""
    if motivations < 0:
        raise ValueError("motivations must be >= 0")
    return _dec(unit_amount) * motivations


def split_invoice(total: "Decimal | int | str | float", attendees: int, places: int = 0) -> list[Decimal]:
    """Per-attendee amounts (quantised to *places* decimals) that sum EXACTLY to *total*.
    The remainder is handed out one smallest unit at a time to the first attendees."""
    if attendees < 1:
        raise ValueError("attendees must be >= 1")
    t = _dec(total)
    if t < 0:
        raise ValueError("total must be >= 0")
    unit = Decimal(1).scaleb(-places)
    if t != t.quantize(unit):
        raise ValueError(f"total has more than {places} decimal places")
    units = int(t / unit)
    base, rem = divmod(units, attendees)
    return [((base + (1 if i < rem else 0)) * unit).quantize(unit, rounding=ROUND_DOWN) for i in range(attendees)]
