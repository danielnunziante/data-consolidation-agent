"""Parser de LA SEGUNDA ART - hoja 73059 con cabecera desplazada."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import safe_str
from .base_parser import (
    detect_header_row,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)

COMPANY = "LA SEGUNDA ART"
SECCION = "A.R.T."


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="la_segunda_art", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = None
    for name in sheets:
        if re.fullmatch(r"\d+", name.strip()):
            sheet_name = name
            break
    if sheet_name is None:
        sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(df_raw, ["Cont/Sin Razon Social", "Comisiones", "Prima", "F. dep"])
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)
    fname = Path(file_path).name

    # "Cont/Sin Razon Social" sale partido en dos columnas: la primera tiene el contrato/póliza,
    # la segunda la razón social. Identificamos las columnas por su orden dentro del DataFrame.
    columns = list(df.columns)
    # buscamos la columna cuya cabecera contiene "Cont/Sin" o está vacía antes de "Razon Social"
    try:
        idx_cont = next(i for i, c in enumerate(columns) if "Cont" in safe_str(c))
    except StopIteration:
        reject(result, fname, f"Sin columna Cont/Sin Razon Social: {columns}", source_sheet=sheet_name)
        return result
    idx_razon = idx_cont + 1 if idx_cont + 1 < len(columns) else None
    try:
        idx_com = next(i for i, c in enumerate(columns) if "Comisiones" in safe_str(c))
        idx_prima = next(i for i, c in enumerate(columns) if safe_str(c).strip().lower() == "prima")
    except StopIteration:
        reject(result, fname, f"Sin Comisiones/Prima: {columns}", source_sheet=sheet_name)
        return result

    for idx, row in df.iterrows():
        values = row.tolist()
        if len(values) <= max(idx_com, idx_prima):
            continue
        poliza = safe_str(values[idx_cont])
        if not poliza or not re.search(r"\d", poliza):
            continue
        # Si viene mezclado "123 RAZON SOCIAL", separamos
        asegurado = safe_str(values[idx_razon]) if idx_razon is not None else ""
        m = re.match(r"^\s*(\d+)\s+(.+)$", poliza)
        if m and not asegurado:
            poliza, asegurado = m.group(1), m.group(2)

        com_v = to_float(values[idx_com])
        prima_v = to_float(values[idx_prima])
        if com_v is None and prima_v is None:
            continue

        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=asegurado,
                seccion=SECCION,
                compania=COMPANY,
                tipo="PR",
                comisiones=com_v,
                prima=prima_v,
                premio=prima_v,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("LA SEGUNDA ART fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=values)
    return result
