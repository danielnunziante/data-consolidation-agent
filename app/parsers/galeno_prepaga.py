"""Parser de GALENO PREPAGA ORG - ADICIONAL -> compañía "GALENO ARGENTINA".

Archivo "Detalle de comisiones..." con cabecera en la fila ~4:
Año RRHH | Mes RRHH | ... | Numero Asociado | Nombre Asociado | ... |
Monto Facturado | % Comision | Monto Comision

Mapeo (validado contra la consolidación manual MAYO 2026):
- POLIZA = Numero Asociado, ASEGURADO = Nombre Asociado.
- SECCION = "PREPAGA MEDICA", TIPO = AY (comisión de organizador/adicional).
- COMISIONES = Monto Comision; sin PRIMA ni PREMIO.
- La fila "Total comisiones" se descarta.
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

COMPANY = "GALENO ARGENTINA"
SECCION = "PREPAGA MEDICA"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="galeno_prepaga", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    fname = Path(file_path).name

    for sheet_name, df_raw in sheets.items():
        if df_raw.empty:
            continue
        header_row = detect_header_row(
            df_raw, ["Numero Asociado", "Nombre Asociado", "Monto Comision"]
        )
        if header_row is None:
            continue
        df = slice_as_dataframe(df_raw, header_row)
        cols = list(df.columns)
        c_num = find_col(cols, "Numero Asociado")
        c_nom = find_col(cols, "Nombre Asociado")
        c_com = find_col(cols, "Monto Comision")
        if not all([c_num, c_nom, c_com]):
            continue
        for idx, row in df.iterrows():
            asociado = safe_str(row[c_num])
            if not asociado or asociado.lower() == "nan":
                continue
            if normalize(asociado).startswith("TOTAL"):
                continue
            com_v = to_float(row[c_com])
            if com_v is None:
                continue
            try:
                rec = make_record(
                    fecha=fecha,
                    poliza=asociado,
                    asegurado=row[c_nom],
                    seccion=SECCION,
                    compania=COMPANY,
                    tipo="AY",
                    comisiones=com_v,
                    prima=None,
                    premio=None,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=idx + header_row + 2,
                )
                result.records.append(rec)
            except Exception as exc:
                log.warning("GALENO PREPAGA fila %s: %s", idx, exc)
                reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    if not result.records and not result.rejected:
        reject(result, fname, "No se encontraron filas válidas")
    return result
