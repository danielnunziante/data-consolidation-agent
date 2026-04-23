"""Parser de LA SEGUNDA GENERALES."""
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

COMPANY = "LA SEGUNDA GENERALES"


def parse(file_path: str, fecha: date, company_name: str = COMPANY) -> ParseResult:
    result = ParseResult(parser_name="la_segunda_grales", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw, ["Ref", "Asegurado", "Seccion", "Prima", "Premio", "Com.Prima", "Com.s/premio"]
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_ref = find_col(columns, "Ref")
    c_aseg = find_col(columns, "Asegurado")
    c_sec = find_col(columns, "Seccion")
    c_prima = find_col(columns, "Prima")
    c_premio = find_col(columns, "Premio")
    c_com_pr = find_col(columns, "Com.Prima")
    c_com_prem = find_col(columns, "Com.s/premio")

    if not all([c_ref, c_aseg, c_sec, c_prima, c_premio, c_com_pr]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza = safe_str(row[c_ref])
        if not poliza or poliza == "0":
            continue
        source_row = idx + header_row + 2
        try:
            rec_pr = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=row[c_sec],
                compania=company_name,
                tipo="PR",
                comisiones=row[c_com_pr],
                prima=row[c_prima],
                premio=row[c_premio],
                source_file=fname,
                source_sheet=sheet_name,
                source_row=source_row,
            )
            result.records.append(rec_pr)
        except Exception as exc:
            log.warning("LS GENERALES PR fila %s: %s", idx, exc)
            reject(result, fname, f"Error PR: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())
            continue

        com_prem = to_float(row[c_com_prem]) if c_com_prem else 0.0
        if com_prem and com_prem != 0:
            try:
                rec_ay = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=row[c_aseg],
                    seccion=row[c_sec],
                    compania=company_name,
                    tipo="AY",
                    comisiones=com_prem,
                    prima=None,
                    premio=None,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=source_row,
                )
                result.records.append(rec_ay)
            except Exception as exc:
                log.warning("LS GENERALES AY fila %s: %s", idx, exc)
                reject(result, fname, f"Error AY: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())
    return result
