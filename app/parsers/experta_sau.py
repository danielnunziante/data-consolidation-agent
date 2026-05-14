"""Parser de EXPERTA SAU - PROD/ORG con lógica PR/AY/IND."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import clean_policy, contains_any, normalize, safe_str
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)

COMPANY = "EXPERTA SAU"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="experta_sau", source_file=file_path)
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
        [
            "N° de Póliza",
            "Razon Social",
            "Ramo",
            "Productor",
            "Tipo de Participacion",
            "Prima",
            "Premio",
        ],
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_pol = find_col(columns, "N° de Póliza", "Nro de Poliza", "Póliza")
    c_aseg = find_col(columns, "Razon Social")
    c_ramo = find_col(columns, "Ramo")
    c_prod = find_col(columns, "Productor")
    c_tipo_part = find_col(columns, "Tipo de Participacion", "Tipo de Participación")
    c_prima = find_col(columns, "Prima")
    c_premio = find_col(columns, "Premio")
    c_importe = find_col(columns, "Importe (AR$)", "Importe")
    c_comision_col = find_col(columns, "% de comision", "% de comisión")

    if not all([c_pol, c_aseg, c_ramo, c_prod, c_tipo_part]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    # Muchos reportes Experta traen cabeceras desplazadas +1 respecto a la columna
    # real (por celdas combinadas). Si la columna está vacía en todas las filas
    # iniciales, tomamos la columna inmediatamente a la izquierda por posición.
    def _pos_series(idx: int):
        return df.iloc[:20, idx]

    def _col_idx(col_name: str) -> int:
        for i, c in enumerate(df.columns):
            if c == col_name:
                return i
        return -1

    def _shift_if_all_nan(col_name: str | None) -> str | int | None:
        """Devuelve un índice entero si la columna por nombre está vacía; si no, el nombre original."""
        if col_name is None:
            return None
        pos = _col_idx(col_name)
        if pos < 0:
            return col_name
        if _pos_series(pos).dropna().empty and pos - 1 >= 0:
            return pos - 1  # devolvemos índice posicional
        return col_name

    c_tipo_part = _shift_if_all_nan(c_tipo_part)
    c_importe = _shift_if_all_nan(c_importe)

    def _get(row, col_ref):
        if isinstance(col_ref, int):
            return row.iloc[col_ref]
        return row[col_ref]

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza_raw = safe_str(row[c_pol])
        if not poliza_raw:
            continue
        tipo_part = normalize(_get(row, c_tipo_part))
        productor_val = safe_str(row[c_prod])
        ramo = safe_str(row[c_ramo])

        if tipo_part == "PROD":
            tipo_final = "PR"
        elif tipo_part == "ORG":
            if contains_any(productor_val, ["COBERTURAS"]):
                tipo_final = "AY"
            else:
                tipo_final = "IND"
        else:
            continue  # tipos no esperados se ignoran

        # Manual: pólizas de 8 dígitos (salvo Ramo "FLOTA") -> primeros 6 por
        # izquierda + sufijo literal "01" (no "1"). El "01" sobrevive a
        # clean_policy porque no contiene comas, comillas ni sufijo ".0".
        poliza = clean_policy(poliza_raw)
        if normalize(ramo) != "FLOTA" and len(poliza) >= 8 and poliza.isdigit():
            poliza = poliza[:6] + "01"

        # Comisión - Importe (AR$) según spec. Si no está, calcular prima * %
        comisiones = None
        if c_importe is not None:
            comisiones = to_float(_get(row, c_importe))
        if comisiones is None and c_prima and c_comision_col:
            prima_v = to_float(row[c_prima])
            pct = to_float(row[c_comision_col])
            if prima_v is not None and pct is not None:
                comisiones = prima_v * pct

        prima = None
        premio = None
        if tipo_final == "PR":
            prima = row[c_prima] if c_prima else None
            premio = row[c_premio] if c_premio else None

        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=ramo,
                compania=COMPANY,
                tipo=tipo_final,
                comisiones=comisiones,
                prima=prima,
                premio=premio,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("EXPERTA SAU fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
