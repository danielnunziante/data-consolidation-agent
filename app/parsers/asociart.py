"""Parser de ASOCIART SA."""
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

COMPANY = "ASOCIART SA"
SECCION = "A.R.T."


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="asociart", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = None
    for name in sheets:
        if name.strip().lower() == "listado":
            sheet_name = name
            break
    if sheet_name is None:
        reject(result, Path(file_path).name, "Hoja 'Listado' no encontrada")
        return result

    df_raw = sheets[sheet_name]
    header_row = detect_header_row(df_raw, ["Contrato", "Razon social", "Prima Recaudada"])
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    c_pol = find_col(list(df.columns), "Contrato")
    c_aseg = find_col(list(df.columns), "Razon social", "Razon Social")
    c_prima = find_col(list(df.columns), "Prima Recaudada")
    c_com = find_col(list(df.columns), "Productor/AI", "Productor / AI", "Productor")

    if not all([c_pol, c_aseg, c_prima, c_com]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {list(df.columns)}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza = safe_str(row[c_pol])
        if not poliza or poliza.lower() == "nan":
            continue
        com_bruto = to_float(row[c_com])
        comisiones = com_bruto / 1.21 if com_bruto is not None else None
        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=SECCION,
                compania=COMPANY,
                tipo="PR",
                comisiones=comisiones,
                prima=row[c_prima],
                premio=row[c_prima],
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("ASOCIART fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
