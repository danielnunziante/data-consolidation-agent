"""Parser de FEDERACION PATRONAL - expande 2 filas por fila origen (PR y AY)."""
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

COMPANY = "FEDERACION PATRONAL"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="fedpat", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = None
    for name in sheets:
        if name.strip().lower() == "libro1":
            sheet_name = name
            break
    if sheet_name is None:
        sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(df_raw, ["Poliza", "Asegurado", "Ramo", "Prima", "Premio", "Comisión normal"])
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_pol = find_col(columns, "Póliza", "Poliza")
    c_aseg = find_col(columns, "Asegurado")
    c_ramo = find_col(columns, "Ramo")
    c_prima = find_col(columns, "Prima")
    c_premio = find_col(columns, "Premio")
    c_com_norm = find_col(columns, "Comisión normal", "Comision normal")
    c_com_cob = find_col(columns, "Comisión cobranza", "Comision cobranza")
    c_com_fom = find_col(columns, "Comisión fomento", "Comision fomento")

    if not all([c_pol, c_aseg, c_ramo, c_prima, c_premio, c_com_norm]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza = safe_str(row[c_pol])
        if not poliza or poliza.lower() == "nan":
            continue
        source_row = idx + header_row + 2
        # Fila PR. Anulaciones: si la comisión es negativa, prima y premio
        # se vuelcan negativos (así lo hace la consolidación manual).
        com_v = to_float(row[c_com_norm])
        prima_v = to_float(row[c_prima])
        premio_v = to_float(row[c_premio])
        if com_v is not None and com_v < 0:
            if prima_v is not None and prima_v > 0:
                prima_v = -prima_v
            if premio_v is not None and premio_v > 0:
                premio_v = -premio_v
        try:
            rec_pr = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=row[c_ramo],
                compania=COMPANY,
                tipo="PR",
                comisiones=com_v,
                prima=prima_v,
                premio=premio_v,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=source_row,
            )
            result.records.append(rec_pr)
        except Exception as exc:
            log.warning("FEDPAT PR fila %s: %s", idx, exc)
            reject(result, fname, f"Error PR: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())

        # Fila AY: cobranza + fomento
        com_cob = to_float(row[c_com_cob]) if c_com_cob else 0.0
        com_fom = to_float(row[c_com_fom]) if c_com_fom else 0.0
        total_ay = (com_cob or 0.0) + (com_fom or 0.0)
        try:
            rec_ay = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=row[c_ramo],
                compania=COMPANY,
                tipo="AY",
                comisiones=total_ay,
                prima=None,
                premio=None,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=source_row,
            )
            result.records.append(rec_ay)
        except Exception as exc:
            log.warning("FEDPAT AY fila %s: %s", idx, exc)
            reject(result, fname, f"Error AY: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())
    return result
