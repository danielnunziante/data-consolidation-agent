"""Parser de LUGO (organizador "LUGO DANTE") -> compañía según columna.

Archivo chico: Asegurado | Poliza | Compañía | Comision, seguido de un bloque
de totales (SUBPAS / IVA). La compañía real es la de la columna (p.ej. RUS).

Mapeo (validado contra las consolidaciones manuales ABRIL/MAYO 2026):
- COMISIONES = Comision * 0.70 (la parte del sub-PAS, neta del organizador;
  coincide con la línea "SUBPAS" del archivo).
- PRIMA = COMISIONES * 5 (la comisión es el 20% de la prima).
- PREMIO = PRIMA * 1.40.
- SECCION = "AUTOMOTORES", TIPO = PR.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import round2, to_float
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

SECCION = "AUTOMOTORES"
SUBPAS_SHARE = 0.70


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="lugo", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    fname = Path(file_path).name

    for sheet_name, df_raw in sheets.items():
        if df_raw.empty:
            continue
        header_row = detect_header_row(df_raw, ["Asegurado", "Poliza", "Compañía", "Comision"])
        if header_row is None:
            continue
        df = slice_as_dataframe(df_raw, header_row)
        cols = list(df.columns)
        c_aseg = find_col(cols, "Asegurado")
        c_pol = find_col(cols, "Poliza")
        c_cia = find_col(cols, "Compañía", "Compania")
        c_com = find_col(cols, "Comision")
        if not all([c_aseg, c_pol, c_com]):
            continue
        for idx, row in df.iterrows():
            poliza = safe_str(row[c_pol])
            if not poliza or poliza.lower() == "nan":
                continue
            com_total = to_float(row[c_com])
            if com_total is None:
                continue
            compania = normalize(row[c_cia]) if c_cia else ""
            if not compania:
                compania = "RUS"
            # Redondeo "de planilla" (half-up), igual que el cliente en Excel:
            # 13995.15 * 0.7 = 9796.605 -> 9796.61
            comis_d = (Decimal(str(com_total)) * Decimal("0.7")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            comis = float(comis_d)
            prima = float((comis_d * 5).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            premio = float(
                (comis_d * 5 * Decimal("1.4")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            try:
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=row[c_aseg],
                    seccion=SECCION,
                    compania=compania,
                    tipo="PR",
                    comisiones=comis,
                    prima=prima,
                    premio=premio,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=idx + header_row + 2,
                )
                result.records.append(rec)
            except Exception as exc:
                log.warning("LUGO fila %s: %s", idx, exc)
                reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    if not result.records and not result.rejected:
        reject(result, fname, "No se encontraron filas válidas")
    return result
