"""Parser de ALLIANZ - xlsx simple con hoja Sheet1."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import ParseResult
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)

COMPANY = "ALLIANZ"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="allianz", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = "Sheet1" if "Sheet1" in sheets else next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(df_raw, ["Nro Poliza", "Asegurado", "Seccion", "Comisiones Devengadas"])
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    c_pol = find_col(list(df.columns), "Nro Poliza", "Poliza")
    c_aseg = find_col(list(df.columns), "Asegurado")
    c_sec = find_col(list(df.columns), "Seccion")
    c_com = find_col(list(df.columns), "Comisiones Devengadas")
    c_prima = find_col(list(df.columns), "Prima")
    c_prem = find_col(list(df.columns), "Premio")

    required = {"poliza": c_pol, "asegurado": c_aseg, "seccion": c_sec, "com": c_com}
    missing = [k for k, v in required.items() if v is None]
    if missing:
        reject(result, Path(file_path).name, f"Faltan columnas: {missing}", source_sheet=sheet_name)
        return result

    for idx, row in df.iterrows():
        poliza = row[c_pol]
        if not str(poliza).strip() or str(poliza).strip() in {"nan", "0"}:
            continue
        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=row[c_sec],
                compania=COMPANY,
                tipo="PR",
                comisiones=row[c_com],
                prima=row[c_prima] if c_prima else None,
                premio=row[c_prem] if c_prem else None,
                source_file=Path(file_path).name,
                source_sheet=sheet_name,
                source_row=header_row + 1 + idx + 1,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("ALLIANZ fila %s: %s", idx, exc)
            reject(result, Path(file_path).name, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
