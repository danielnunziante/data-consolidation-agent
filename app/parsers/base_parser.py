"""Utilitarios comunes a todos los parsers."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

from ..models import ParseResult, RejectedRow, Record
from ..utils.logging_utils import get_logger
from ..utils.numbers import round2, to_float
from ..utils.strings import clean_policy, normalize, safe_str, squash_spaces

log = get_logger()


def make_record(
    *,
    fecha: date,
    poliza: Any,
    asegurado: Any,
    seccion: Any,
    compania: str,
    tipo: str,
    comisiones: Any,
    prima: Any,
    premio: Any,
    source_file: str,
    source_sheet: Optional[str] = None,
    source_row: Optional[int] = None,
    observacion: Optional[str] = None,
) -> Record:
    return Record(
        fecha=fecha,
        poliza=clean_policy(poliza),
        asegurado=squash_spaces(safe_str(asegurado)),
        seccion=squash_spaces(safe_str(seccion)),
        compania=compania,
        tipo=tipo,
        comisiones=round2(to_float(comisiones)),
        prima=round2(to_float(prima)),
        premio=round2(to_float(premio)),
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=source_row,
        observacion=observacion,
    )


def read_excel_sheets(path: str, engine: Optional[str] = None) -> dict[str, pd.DataFrame]:
    """Lee todas las hojas sin asumir header (lo resolvemos por parser)."""
    p = Path(path)
    if engine is None:
        engine = "openpyxl" if p.suffix.lower() in {".xlsx", ".xlsm"} else None
    return pd.read_excel(p, sheet_name=None, header=None, engine=engine, dtype=object)


def detect_header_row(df: pd.DataFrame, header_tokens: Iterable[str], max_rows: int = 30) -> Optional[int]:
    """Busca la fila que contiene la mayor cantidad de tokens esperados."""
    needed = [normalize(t) for t in header_tokens]
    best_row: Optional[int] = None
    best_score = 0
    for i in range(min(max_rows, len(df))):
        row_values = [normalize(v) for v in df.iloc[i].tolist()]
        score = sum(1 for tok in needed if any(tok and tok in v for v in row_values))
        if score > best_score:
            best_score = score
            best_row = i
    if best_row is None or best_score < max(1, len(needed) // 2):
        return None
    return best_row


def slice_as_dataframe(df: pd.DataFrame, header_row: int) -> pd.DataFrame:
    """Convierte un DataFrame crudo (sin header) en uno con header=header_row."""
    headers = [safe_str(v) for v in df.iloc[header_row].tolist()]
    data = df.iloc[header_row + 1 :].copy()
    data.columns = headers
    data = data.reset_index(drop=True)
    return data


def find_col(columns: list[str], *candidates: str) -> Optional[str]:
    """Busca una columna cuyo nombre normalizado contenga cualquiera de `candidates`."""
    norm_map = {c: normalize(c) for c in columns}
    for cand in candidates:
        n = normalize(cand)
        for col, norm_col in norm_map.items():
            if n and norm_col == n:
                return col
        for col, norm_col in norm_map.items():
            if n and n in norm_col:
                return col
    return None


def reject(
    result: ParseResult,
    source_file: str,
    reason: str,
    *,
    source_sheet: Optional[str] = None,
    source_row: Optional[int] = None,
    compania: Optional[str] = None,
    raw: Any = "",
) -> None:
    result.rejected.append(
        RejectedRow(
            source_file=source_file,
            source_sheet=source_sheet,
            source_row=source_row,
            compania=compania,
            reason=reason,
            raw=safe_str(raw)[:500],
        )
    )
