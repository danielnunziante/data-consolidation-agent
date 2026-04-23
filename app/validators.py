"""Validadores aplicados sobre los registros finales."""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from .config import ALLOWED_TIPOS, EXPECTED_COUNTS
from .models import Record


def validate_records(records: Iterable[Record]) -> list[str]:
    """Valida invariantes sobre los registros generados.

    Devuelve lista de warnings; no interrumpe la ejecución.
    """
    warnings: list[str] = []
    for r in records:
        if not r.poliza:
            warnings.append(f"Fila sin POLIZA ({r.source_file} row {r.source_row})")
        if not r.asegurado:
            warnings.append(f"Fila sin ASEGURADO ({r.source_file} row {r.source_row})")
        if not r.compania:
            warnings.append(f"Fila sin COMPAÑÍA ({r.source_file} row {r.source_row})")
        if r.tipo not in ALLOWED_TIPOS:
            warnings.append(f"TIPO inválido {r.tipo!r} ({r.source_file} row {r.source_row})")
        if r.comisiones is None:
            warnings.append(f"COMISIONES vacías ({r.compania} {r.source_file} row {r.source_row})")
        if r.tipo in {"AY", "IND"}:
            if r.prima not in (None, 0, 0.0):
                warnings.append(
                    f"TIPO {r.tipo} pero PRIMA no vacía ({r.compania} {r.poliza})"
                )
            if r.premio not in (None, 0, 0.0):
                warnings.append(
                    f"TIPO {r.tipo} pero PREMIO no vacío ({r.compania} {r.poliza})"
                )
    return warnings


def expected_counts_warnings(
    rows_by_company: dict[str, int],
    present_companies: set[str],
) -> list[str]:
    """Avisa si el conteo real difiere del esperado para este lote de prueba."""
    warnings: list[str] = []
    for comp, expected in EXPECTED_COUNTS.items():
        if comp not in present_companies:
            continue
        actual = rows_by_company.get(comp, 0)
        if actual != expected:
            warnings.append(
                f"[conteo] {comp}: generados={actual} esperados={expected} (diff={actual - expected:+d})"
            )
    return warnings


def summarize_by_company(records: Iterable[Record]) -> dict[str, int]:
    c = Counter(r.compania for r in records)
    return dict(c)
