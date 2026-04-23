"""Parser de GALICIA SEGUROS."""
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

COMPANY = "GALICIA SEGUROS"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="galicia", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(df_raw, ["Poliza", "Detalle", "ComisionBruta", "PrimaTecnica"])
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_pol = find_col(columns, "Poliza")
    c_det = find_col(columns, "Detalle")
    c_sec = find_col(columns, "Sc")
    c_com = find_col(columns, "ComisionBruta")
    c_prima = find_col(columns, "PrimaTecnica")
    c_premio = find_col(columns, "Premio")

    if not all([c_pol, c_det, c_com, c_prima, c_premio]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        detalle = safe_str(row[c_det])
        poliza = safe_str(row[c_pol]).replace(",", "").strip()
        if not poliza or poliza == "0":
            continue
        if normalize(detalle).startswith("SALDO ANTERIOR"):
            continue
        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=detalle,
                seccion=safe_str(row[c_sec]) if c_sec else "",
                compania=COMPANY,
                tipo="PR",
                comisiones=row[c_com],
                prima=row[c_prima],
                premio=row[c_premio],
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("GALICIA fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
