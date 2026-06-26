"""Parser de LA HOLANDO - ART vs GENERALES."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import normalize, safe_str, strip_leading_zeros
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)


def _extract_poliza(nro_op: str) -> str:
    """NroOperacion vienen como 'R.T.- 0000217202- 2602006' u otros formatos."""
    s = safe_str(nro_op)
    if not s:
        return ""
    tokens = re.findall(r"\d+", s)
    if not tokens:
        return s
    # El primer bloque numérico suele ser el número de operación/póliza útil
    return strip_leading_zeros(tokens[0]) or tokens[0]


def _extract_seccion_code(nro_op: str) -> str:
    """El prefijo de NroOperacion identifica el ramo/sección, no el asegurado.

    Ej.: 'Aut.- 0014015393- 0000020' -> 'Aut.';
         'Com.- 0004580919- 0000000' -> 'Com.';
         'R.C.- 0000113177- 0000000' -> 'R.C.'.

    La tabla de equivalencias (LA HOLANDO GENERALES) mapea estos códigos al
    vocabulario único de secciones.
    """
    s = safe_str(nro_op)
    if not s:
        return ""
    return s.split("-")[0].strip()


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="la_holando", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw,
        ["Rama", "NroOperacion", "Detalle Operacion", "Com.Bruta", "PremioComisionable"],
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    log.debug("LA HOLANDO columnas: %s", columns)
    c_rama = find_col(columns, "Rama")
    c_tipo_op = find_col(
        columns,
        "Tipo de Operacion",
        "Tipo de Operación",
        "TipoOperacion",
        "Tipo Operacion",
        "TipoOp",
        "Tipo Op",
    )
    c_nro_op = find_col(columns, "NroOperacion")
    c_det = find_col(columns, "Detalle Operacion")
    c_com = find_col(columns, "Com.Bruta")
    c_prima = find_col(columns, "PrimaComisionable")
    c_premio = find_col(columns, "PremioComisionable")

    if not all([c_rama, c_nro_op, c_det, c_com, c_prima, c_premio]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        # Sólo procesamos filas con PrimaComisionable o PremioComisionable reales; filas Deb/Cre o sin póliza se ignoran
        nro_op = safe_str(row[c_nro_op])
        poliza = _extract_poliza(nro_op)
        if not poliza or poliza == "0":
            continue
        prima_v = to_float(row[c_prima])
        premio_v = to_float(row[c_premio])
        com_v = to_float(row[c_com])
        if (prima_v is None or prima_v == 0) and (premio_v is None or premio_v == 0):
            # movimientos administrativos sin póliza real
            continue

        rama = normalize(row[c_rama])
        if rama == "ART":
            compania = "LA HOLANDO ART"
            seccion = "A.R.T."
        else:
            compania = "LA HOLANDO GENERALES"
            # El asegurado va en Detalle Operacion; la SECCION es el prefijo de
            # NroOperacion (Aut./Com./Col./Obl./R.C.), no el nombre del asegurado.
            seccion = _extract_seccion_code(nro_op)

        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_det],
                seccion=seccion,
                compania=compania,
                tipo="PR",
                comisiones=com_v,
                prima=prima_v,
                premio=premio_v,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("LA HOLANDO fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
