"""Helpers de normalización de cadenas."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        # pandas NaN
        import math
        if math.isnan(value):
            return ""
    return str(value).strip()


def squash_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize(value: Any) -> str:
    """Normaliza para comparaciones insensibles a acentos/case."""
    s = safe_str(value).upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return squash_spaces(s)


def normalize_file_key(filename: str) -> str:
    """Para detección de parser: saca extensión, fecha del mes y normaliza."""
    base = filename
    for ext in (".xlsx", ".xls", ".pdf", ".XLSX", ".XLS", ".PDF"):
        if base.endswith(ext):
            base = base[: -len(ext)]
            break
    s = normalize(base)
    # quita patrones de período "MARZO 2026", "2026-03", etc.
    s = re.sub(r"\b(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\b\s*\d{0,4}", "", s)
    s = re.sub(r"\b\d{4}[- /]?\d{1,2}\b", "", s)
    s = re.sub(r"\b\d{6,8}\b", "", s)
    s = squash_spaces(s)
    return s


def clean_policy(value: Any) -> str:
    """Limpia un número/código de póliza."""
    s = safe_str(value)
    s = s.replace("'", "").replace("`", "")
    s = s.replace(",", "")
    s = s.strip()
    # Caso cálculos como "12345.0" que vienen de pandas con ints promovidos a floats
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".")[0]
    return s


def strip_leading_zeros(value: str) -> str:
    if not value:
        return value
    sign = ""
    if value.startswith("-"):
        sign = "-"
        value = value[1:]
    stripped = value.lstrip("0")
    if not stripped:
        return "0"
    return sign + stripped


def first_nonempty(*values: Any) -> str:
    for v in values:
        s = safe_str(v)
        if s:
            return s
    return ""


def contains_any(haystack: str, needles: list[str]) -> bool:
    h = normalize(haystack)
    return any(normalize(n) in h for n in needles)
