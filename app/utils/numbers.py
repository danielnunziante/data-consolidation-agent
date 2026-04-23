"""Parseo flexible de números presentes en los archivos de las aseguradoras."""
from __future__ import annotations

import math
import re
from typing import Any, Optional

_CURRENCY_CHARS = re.compile(r"[\s\$u\$U\$USDARS]")
_NON_NUMERIC_TAIL = re.compile(r"[^\d,\.\-]+")


def to_float(value: Any) -> Optional[float]:
    """Convierte celdas/cadenas potencialmente sucias a float.

    Soporta:
        - None / NaN / vacío -> None
        - "$ 12.345,67" (AR: puntos de miles, coma decimal)
        - "1,234.56" (US)
        - "1234.56"
        - paréntesis para negativo "(123,45)"
        - signo al final "12,34-"
        - porcentajes "%5" o "5%" -> 5.0 (sin dividir)
        - números ya float/int
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)

    s = str(value).strip()
    if not s:
        return None
    low = s.lower()
    if low in {"nan", "none", "null", "-", "--"}:
        return None

    # paréntesis -> negativo
    negative_paren = s.startswith("(") and s.endswith(")")
    if negative_paren:
        s = s[1:-1]

    # signo al final
    trailing_minus = s.endswith("-") and not s.startswith("-")
    if trailing_minus:
        s = "-" + s[:-1]

    # quitar símbolos de moneda y espacios
    s = s.replace("$", "").replace("ARS", "").replace("USD", "").replace("U$S", "").replace("u$s", "")
    s = s.replace("%", "")
    s = s.strip()

    if not s:
        return None

    # separar signo
    sign = 1
    if s.startswith("-"):
        sign = -1
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()

    # eliminar caracteres finales no numéricos
    s = _NON_NUMERIC_TAIL.sub("", s)
    if not s:
        return None

    # Heurística coma vs punto: si ambos aparecen, el último es el decimal
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")
    if last_comma > -1 and last_dot > -1:
        if last_comma > last_dot:
            # formato AR: 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif last_comma > -1:
        # sólo coma
        int_part, _, frac = s.rpartition(",")
        if len(frac) == 3 and int_part and "," not in int_part and int_part.replace("-", "").isdigit():
            # puede ser miles: 1,234 -> entero. Pero muchas aseguradoras usan coma decimal,
            # por lo que si hay >1 coma tratamos las anteriores como miles y la última como decimal.
            if s.count(",") >= 2:
                s = s.replace(",", "")
            else:
                # Ambiguo. En este proyecto AR la coma es decimal.
                s = s.replace(",", ".")
        else:
            s = s.replace(",", ".")
    # si sólo hay puntos dejamos como está; python float(.)

    try:
        result = float(s)
    except ValueError:
        return None

    if negative_paren:
        sign = -sign
    result = sign * result
    if math.isnan(result):
        return None
    return result


def round2(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 2)
