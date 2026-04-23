"""Parser de PROVINCIA ART."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.strings import normalize, safe_str
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)

COMPANY = "PROVINCIA ART"
SECCION = "A.R.T."


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="provincia_art", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = None
    for name in sheets:
        if name.strip().lower() == "movimientos":
            sheet_name = name
            break
    if sheet_name is None:
        sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(df_raw, ["CONTRATO", "RAZÓN SOCIAL", "COBRADO NETO", "MONTO LIQUIDADO", "CONCEPTO"])
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_pol = find_col(columns, "CONTRATO")
    c_aseg = find_col(columns, "RAZÓN SOCIAL", "RAZON SOCIAL")
    c_concepto = find_col(columns, "CONCEPTO")
    c_prima = find_col(columns, "COBRADO NETO IMPUESTOS", "COBRADO NETO")
    c_com = find_col(columns, "MONTO LIQUIDADO")

    if not all([c_pol, c_aseg, c_concepto, c_prima, c_com]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        if normalize(row[c_concepto]) != "COMISIONES":
            continue
        poliza = safe_str(row[c_pol])
        if not poliza or poliza.lower() == "nan":
            continue
        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=SECCION,
                compania=COMPANY,
                tipo="PR",
                comisiones=row[c_com],
                prima=row[c_prima],
                premio=row[c_prima],
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("PROVINCIA ART fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
