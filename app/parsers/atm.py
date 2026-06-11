"""Parser de ATM.

Manual:
    - COMISION TOTAL = MONTO COMISION S/PREMIO + MONTO COMISION S/PRIMA
    - POLIZA = "PÓLIZA"
    - ASEGURADO = "NOMBRE TOMADOR"
    - SECCION = "RAMA"
    - TIPO = "PR" salvo cuando "TIPO DE LIQUIDACION" == "ONE SHOT" -> "AY"
    - COMISIONES = COMISION TOTAL (también para AY)
    - PRIMA = "PRIMA COBRADA" (None para AY)
    - PREMIO = "PREMIO COBRADO" (None para AY)
"""
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

COMPANY = "ATM"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="atm", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw,
        [
            "PÓLIZA",
            "NOMBRE TOMADOR",
            "RAMA",
            "MONTO COMISION",
            "PRIMA COBRADA",
            "PREMIO COBRADO",
            "TIPO DE LIQUIDACION",
        ],
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_pol = find_col(columns, "PÓLIZA", "POLIZA")
    c_aseg = find_col(columns, "NOMBRE TOMADOR", "TOMADOR")
    c_rama = find_col(columns, "RAMA")
    c_com_premio = find_col(columns, "MONTO COMISION S/PREMIO", "COMISION S/PREMIO")
    c_com_prima = find_col(columns, "MONTO COMISION S/PRIMA", "COMISION S/PRIMA")
    c_prima = find_col(columns, "PRIMA COBRADA")
    c_premio = find_col(columns, "PREMIO COBRADO")
    c_tipo_liq = find_col(columns, "TIPO DE LIQUIDACION", "TIPO LIQUIDACION")

    if not all([c_pol, c_aseg, c_rama, c_prima, c_premio]):
        reject(
            result,
            Path(file_path).name,
            f"Columnas insuficientes: {columns}",
            source_sheet=sheet_name,
        )
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza = safe_str(row[c_pol])
        if not poliza or poliza == "0":
            continue
        source_row = idx + header_row + 2

        com_premio_v = to_float(row[c_com_premio]) if c_com_premio else 0.0
        com_prima_v = to_float(row[c_com_prima]) if c_com_prima else 0.0
        comision_total = (com_premio_v or 0.0) + (com_prima_v or 0.0)
        if not comision_total:
            comision_total = None

        tipo_liq = normalize(row[c_tipo_liq]) if c_tipo_liq else ""
        if "ONESHOT" in tipo_liq.replace(" ", ""):
            tipo = "AY"
            prima = None
            premio = None
        else:
            tipo = "PR"
            prima = to_float(row[c_prima])
            premio = to_float(row[c_premio])

        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=row[c_rama],
                compania=COMPANY,
                tipo=tipo,
                comisiones=comision_total,
                prima=prima,
                premio=premio,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=source_row,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("ATM fila %s: %s", idx, exc)
            reject(
                result,
                fname,
                f"Error: {exc}",
                source_sheet=sheet_name,
                source_row=source_row,
                raw=row.to_dict(),
            )
    return result
