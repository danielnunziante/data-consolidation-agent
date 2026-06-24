"""Normalización de la columna SECCION según equivalencias por compañía.

Cada aseguradora nombra sus ramos/secciones de forma distinta (códigos
numéricos, abreviaturas, textos con prefijos). Este módulo mapea esos valores
crudos a un vocabulario único de secciones, usando la tabla de equivalencias
que mantiene el cliente (`Ejemplos Data/EQUIVALENCIAS.xlsx`, convertida a
`seccion_equivalencias.py` por `scripts/build_equivalencias.py`).

Prioridad de la tabla de equivalencias:

1. Override editable `config/equivalencias_seccion.json` (opcional, permite al
   cliente agregar/corregir equivalencias sin recompilar). Formato:
   `{"COMPAÑÍA": {"codigo_crudo": "SECCION NORMALIZADA"}}`.
2. Tabla baked-in generada desde el Excel (`EQUIVALENCIAS_RAW`).

Si un par (compañía, código) no tiene equivalencia, se conserva el valor
crudo tal cual (no se pierde información) y se reporta como "sin equivalencia".

El match es tolerante: ignora mayúsculas/minúsculas, espacios sobrantes,
ceros a la izquierda en códigos numéricos, y cae a la compañía sin el sufijo
" USD" (ej.: `SAN CRISTOBAL USD` reutiliza la tabla de `SAN CRISTOBAL`).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from .logging_utils import get_logger
from .seccion_equivalencias import EQUIVALENCIAS_RAW

log = get_logger()

_WS_RE = re.compile(r"\s+")
_INT_RE = re.compile(r"\d+(\.0+)?")
_USD_SUFFIX_RE = re.compile(r"\s+USD$")


def _norm_company(value: object) -> str:
    return _WS_RE.sub(" ", str(value or "").strip()).upper()


def _strip_usd(company_key: str) -> str:
    return _USD_SUFFIX_RE.sub("", company_key).strip()


def _norm_code(value: object) -> str:
    """Clave canónica para un código de sección.

    - Colapsa espacios y pasa a mayúsculas.
    - Si es un entero (con o sin ceros a la izquierda, o como `14.0`), lo
      canonicaliza al entero (`'01'` y `1` -> `'1'`).
    """
    s = _WS_RE.sub(" ", str(value if value is not None else "").strip())
    if s and _INT_RE.fullmatch(s):
        s = str(int(float(s)))
    return s.upper()


def _config_path() -> Path:
    """Ruta canónica de config/equivalencias_seccion.json (junto al proyecto)."""
    return Path(__file__).resolve().parent.parent.parent / "config" / "equivalencias_seccion.json"


def _load_override() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    candidates = [Path("config") / "equivalencias_seccion.json", _config_path()]
    for path in candidates:
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("equivalencias_seccion.json inválido (%s): %s", path, exc)
            continue
        for compania, mapping in (data or {}).items():
            if not isinstance(mapping, dict):
                continue
            ckey = _norm_company(compania)
            for codigo, seccion in mapping.items():
                if seccion:
                    out[(ckey, _norm_code(codigo))] = str(seccion).strip()
        break
    return out


@lru_cache(maxsize=1)
def _lookup() -> dict[tuple[str, str], str]:
    table: dict[tuple[str, str], str] = {}
    for codigo, compania, seccion in EQUIVALENCIAS_RAW:
        if seccion:
            table[(_norm_company(compania), _norm_code(codigo))] = str(seccion).strip()
    # El override del cliente pisa la tabla baked-in.
    table.update(_load_override())
    return table


def normalize_seccion(compania: object, seccion_raw: object) -> Optional[str]:
    """Devuelve la SECCION normalizada para (compañía, valor crudo).

    Si no hay equivalencia, devuelve `None` para que el llamador decida
    (típicamente conservar el valor crudo).
    """
    table = _lookup()
    ckey = _norm_company(compania)
    code = _norm_code(seccion_raw)
    hit = table.get((ckey, code))
    if hit is not None:
        return hit
    base = _strip_usd(ckey)
    if base != ckey:
        return table.get((base, code))
    return None


def reset_cache() -> None:
    """Limpia el cache de la tabla (tras escribir el override)."""
    _lookup.cache_clear()


def normalize_records(records: Iterable) -> dict[tuple[str, str], int]:
    """Normaliza in-place el campo `seccion` de cada Record.

    Devuelve un dict {(compania, seccion_cruda): cantidad} con los pares que NO
    tuvieron equivalencia (para reportarlos en el log).
    """
    unmapped: dict[tuple[str, str], int] = {}
    for rec in records:
        raw = rec.seccion
        norm = normalize_seccion(rec.compania, raw)
        if norm is not None:
            rec.seccion = norm
        else:
            key = (str(rec.compania or ""), "" if raw is None else str(raw))
            unmapped[key] = unmapped.get(key, 0) + 1
    return unmapped
