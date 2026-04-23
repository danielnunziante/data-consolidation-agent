"""Parser de EXPERTA ART - hoja ReporteComisiones, filtro PROD."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import to_float
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

COMPANY = "EXPERTA ART"
SECCION = "A.R.T."


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="experta_art", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = None
    for name in sheets:
        if "reporte" in name.lower() and "comis" in name.lower():
            sheet_name = name
            break
    if sheet_name is None:
        sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw,
        ["N° de Póliza", "Razon Social", "Base Calculo", "Importe", "Tipo de Participacion"],
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    c_pol = find_col(list(df.columns), "N° de Póliza", "N° de Poliza", "Nro de Poliza", "Póliza")
    c_aseg = find_col(list(df.columns), "Razon Social")
    c_base = find_col(list(df.columns), "Base Calculo", "Base Cálculo")
    c_imp = find_col(list(df.columns), "Importe")
    c_tipo = find_col(list(df.columns), "Tipo de Participacion", "Tipo de Participación")

    if not all([c_pol, c_aseg, c_base, c_imp, c_tipo]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {list(df.columns)}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        if normalize(row[c_tipo]) != "PROD":
            continue
        poliza = safe_str(row[c_pol])
        if not poliza:
            continue
        imp = to_float(row[c_imp])
        comisiones = imp / 1.21 if imp is not None else None
        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=SECCION,
                compania=COMPANY,
                tipo="PR",
                comisiones=comisiones,
                prima=row[c_base],
                premio=row[c_base],
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("EXPERTA ART fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
