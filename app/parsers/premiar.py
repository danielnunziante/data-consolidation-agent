"""Parser de PREMIAR."""
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

COMPANY = "PREMIAR"
SECCION = "CAUCION"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="premiar", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw, ["Poliza / Endoso", "Tomador", "Prima $", "Comisión pagada $"]
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_pol = find_col(columns, "Poliza / Endoso", "Poliza/Endoso", "Poliza")
    c_tom = find_col(columns, "Tomador")
    c_prima = find_col(columns, "Prima $")
    c_com = find_col(columns, "Comisión pagada $", "Comision pagada $")

    if not all([c_pol, c_tom, c_prima, c_com]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        raw_pol = safe_str(row[c_pol])
        if not raw_pol:
            continue
        poliza = raw_pol.split("/")[0].strip() if "/" in raw_pol else raw_pol
        prima = to_float(row[c_prima])
        premio = prima * 1.40 if prima is not None else None
        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_tom],
                seccion=SECCION,
                compania=COMPANY,
                tipo="PR",
                comisiones=row[c_com],
                prima=prima,
                premio=premio,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("PREMIAR fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
