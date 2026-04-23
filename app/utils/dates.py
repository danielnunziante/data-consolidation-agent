"""Helpers de fechas."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional


def first_day_of_period(period: str) -> date:
    """`YYYY-MM` -> date(YYYY, MM, 1). Acepta también YYYYMM."""
    s = period.strip()
    m = re.fullmatch(r"(\d{4})[- /]?(\d{1,2})", s)
    if not m:
        raise ValueError(f"Período inválido: {period!r} (esperado YYYY-MM)")
    year = int(m.group(1))
    month = int(m.group(2))
    if not (1 <= month <= 12):
        raise ValueError(f"Mes inválido en período {period!r}")
    return date(year, month, 1)


def is_valid_period(period: Optional[str]) -> bool:
    if not period:
        return False
    try:
        first_day_of_period(period)
        return True
    except ValueError:
        return False
