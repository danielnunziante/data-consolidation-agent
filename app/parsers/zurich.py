"""Parser de ZURICH."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import safe_str
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)

COMPANY = "ZURICH"


def _extract_poliza_zurich(value) -> str:
    s = safe_str(value)
    digits = "".join(c for c in s if c.isdigit())
    return digits if digits else s


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="zurich", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw,
        ["POLIZA", "Apellido y Nombre", "Sección", "Prima Técnica", "Comisión Pesos"],
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_pol = find_col(columns, "POLIZA")
    c_aseg = find_col(columns, "Apellido y Nombre del Cliente", "Apellido")
    c_sec = find_col(columns, "Sección", "Seccion")
    c_prima = find_col(columns, "Prima Técnica", "Prima Tecnica")
    c_com = find_col(columns, "Comisión Pesos", "Comision Pesos")

    if not all([c_pol, c_aseg, c_sec, c_prima, c_com]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza_raw = safe_str(row[c_pol])
        if not poliza_raw or poliza_raw == "0":
            continue
        poliza = _extract_poliza_zurich(poliza_raw)
        com_v = to_float(row[c_com])
        prima_v = to_float(row[c_prima])
        comisiones = abs(com_v) if com_v is not None else None
        prima_abs = abs(prima_v) if prima_v is not None else None
        premio = prima_abs * 1.40 if prima_abs is not None else None
        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=row[c_sec],
                compania=COMPANY,
                tipo="PR",
                comisiones=comisiones,
                prima=prima_abs,
                premio=premio,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("ZURICH fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
