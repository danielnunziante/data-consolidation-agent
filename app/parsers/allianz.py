"""Parser de ALLIANZ.

Soporta dos layouts:
1. xlsx tabular clásico (hoja Sheet1 con columnas).
2. xlsx "CSV embebido" (ABRIL 2026+): una sola columna donde cada celda es
   una línea CSV completa con campos entrecomillados:
   Organizador,"Productor","Tipo","Fecha","Seccion","Nro Poliza","Endoso",
   "Asegurado","Mda","Tipo Cambio","Premio","Prima","Comisiones Devengadas",
   "Comisiones Devengadas $",...

Mapeo (consolidación manual del cliente):
- POLIZA=Nro Poliza completo, SECCION=Seccion, ASEGURADO=Asegurado.
- TIPO: "Productor" -> PR; otro valor (organizador) -> IND.
- COMISIONES="Comisiones Devengadas $" (ya en pesos), PRIMA=Prima,
  PREMIO=Premio multiplicados por "Tipo Cambio" si la moneda no es $.
- Se conservan filas en cero o negativas (anulaciones).
"""
from __future__ import annotations

import csv
import io
from datetime import date
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

COMPANY = "ALLIANZ"


def _parse_embedded_csv(result: ParseResult, df_raw, sheet_name: str, fecha: date, fname: str) -> None:
    lines = [safe_str(df_raw.iloc[i, 0]) for i in range(len(df_raw))]
    lines = [l for l in lines if l]
    if not lines:
        reject(result, fname, "Archivo vacío", source_sheet=sheet_name)
        return
    rows = []
    for l in lines:
        try:
            rows.append(next(csv.reader(io.StringIO(l))))
        except StopIteration:
            rows.append([])
    header = [normalize(h) for h in rows[0]]

    def col(name: str) -> int:
        n = normalize(name)
        for i, h in enumerate(header):
            if h == n:
                return i
        for i, h in enumerate(header):
            if n in h:
                return i
        return -1

    i_tipo = col("Tipo")
    i_sec = col("Seccion")
    i_pol = col("Nro Poliza")
    i_aseg = col("Asegurado")
    i_tc = col("Tipo Cambio")
    i_premio = col("Premio")
    i_prima = col("Prima")
    i_com_pes = col("Comisiones Devengadas $")
    if i_com_pes == -1:
        i_com_pes = col("Comisiones Devengadas")

    if min(i_pol, i_aseg, i_sec, i_com_pes) < 0:
        reject(result, fname, f"Cabecera CSV embebida insuficiente: {rows[0]}", source_sheet=sheet_name)
        return

    for n, r in enumerate(rows[1:], start=2):
        if len(r) <= max(i_pol, i_aseg, i_sec, i_com_pes):
            continue
        poliza = safe_str(r[i_pol])
        if not poliza or poliza == "0":
            continue
        tc = to_float(r[i_tc]) if i_tc >= 0 else None
        if not tc or tc <= 0:
            tc = 1.0
        prima = to_float(r[i_prima]) if i_prima >= 0 else None
        premio = to_float(r[i_premio]) if i_premio >= 0 else None
        com = to_float(r[i_com_pes])
        tipo_raw = normalize(r[i_tipo]) if i_tipo >= 0 else "PRODUCTOR"
        tipo = "PR" if tipo_raw.startswith("PRODUCTOR") else "IND"
        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=r[i_aseg],
                seccion=r[i_sec],
                compania=COMPANY,
                tipo=tipo,
                comisiones=com,
                prima=round2(prima * tc) if prima is not None else None,
                premio=round2(premio * tc) if premio is not None else None,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=n,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("ALLIANZ fila %s: %s", n, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=n, raw="|".join(r))


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="allianz", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = "Sheet1" if "Sheet1" in sheets else next(iter(sheets))
    df_raw = sheets[sheet_name]
    fname = Path(file_path).name

    # Layout "CSV embebido": una sola columna con líneas CSV.
    first_cell = safe_str(df_raw.iloc[0, 0]) if len(df_raw) else ""
    if df_raw.shape[1] == 1 and '","' in first_cell:
        _parse_embedded_csv(result, df_raw, sheet_name, fecha, fname)
        return result

    header_row = detect_header_row(df_raw, ["Nro Poliza", "Asegurado", "Seccion", "Comisiones Devengadas"])
    if header_row is None:
        reject(result, fname, "No se detectó cabecera", source_sheet=sheet_name)
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
        reject(result, fname, f"Faltan columnas: {missing}", source_sheet=sheet_name)
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
                source_file=fname,
                source_sheet=sheet_name,
                source_row=header_row + 1 + idx + 1,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("ALLIANZ fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
