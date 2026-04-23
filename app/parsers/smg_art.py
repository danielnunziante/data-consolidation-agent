"""Parser de SMG ART - múltiples bloques en una misma hoja.

Sólo procesamos los dos primeros bloques encabezados por:
  - Productor: COBERTURAS y SERVICIOS S.A [xxxxx]
  - Productor: COBERTURAS y SERVICIOS S.A/B [xxxxx]
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import normalize, safe_str
from .base_parser import (
    log,
    make_record,
    read_excel_sheets,
    reject,
)

COMPANY = "SMG ART"
SECCION = "A.R.T."


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="smg_art", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df = sheets[sheet_name]
    fname = Path(file_path).name

    n_rows = len(df)

    # 1) Localizar fila de cabecera tipo "Cliente ... CUIT Contrato ... Importe(3) ... Com. Org. ... Com. Prod."
    header_row = None
    for i in range(min(30, n_rows)):
        row_values = [normalize(v) for v in df.iloc[i].tolist()]
        score = 0
        for tok in ["CLIENTE", "CUIT", "CONTRATO", "PERIODO ART", "FECHA", "IMPORTE", "PRIMA COMIS", "COM. ORG", "COM. PROD"]:
            if any(tok in v for v in row_values):
                score += 1
        if score >= 6:
            header_row = i
            break
    if header_row is None:
        reject(result, fname, "No se detectó cabecera", source_sheet=sheet_name)
        return result

    # Identificamos las columnas de interés por posición en la cabecera
    header_cells = [safe_str(v) for v in df.iloc[header_row].tolist()]

    def col_for(*tokens: str) -> int | None:
        for t in tokens:
            n = normalize(t)
            for i, h in enumerate(header_cells):
                nh = normalize(h)
                if n == nh or n in nh:
                    return i
        return None

    c_cliente = col_for("Cliente")
    c_contrato = col_for("Contrato")
    c_importe = col_for("Importe (3)", "Importe(3)", "Importe")
    c_com_org = col_for("Com. Org. (5)", "Com. Org.")
    c_com_prod = col_for("Com. Prod. (5)", "Com. Prod.")

    if None in (c_cliente, c_contrato, c_importe):
        reject(result, fname, f"Columnas insuficientes: {header_cells}", source_sheet=sheet_name)
        return result

    # 2) Escanear filas detectando bloques por líneas "Productor: COBERTURAS..."
    # Aceptamos los dos primeros bloques. Dentro de cada bloque hay filas de datos
    # (Cliente, CUIT, Contrato, Fechas, Importe, ...) y filas vacías entre bloques.
    bloques_aceptados = 0
    bloque_activo = False
    usar_org = False  # True si estamos en bloque /B (sub-bloque ORG)

    for i in range(header_row + 1, n_rows):
        row = df.iloc[i].tolist()
        raw_str = " ".join(safe_str(v) for v in row)
        norm = normalize(raw_str)
        if "PRODUCTOR:" in norm and "COBERTURAS" in norm:
            bloques_aceptados += 1
            if bloques_aceptados > 2:
                break
            bloque_activo = True
            # "/B" indica el segundo bloque (sub-organizador)
            usar_org = "/B" in raw_str.upper() or bloques_aceptados == 2
            continue

        if not bloque_activo:
            continue

        cliente = safe_str(row[c_cliente]) if c_cliente < len(row) else ""
        contrato = safe_str(row[c_contrato]) if c_contrato < len(row) else ""
        importe_v = to_float(row[c_importe]) if c_importe < len(row) else None

        if not cliente and not contrato:
            continue
        if not contrato or not importe_v:
            continue
        # saltear filas que son encabezados repetidos dentro del bloque
        if normalize(cliente).startswith("CLIENTE"):
            continue

        if usar_org:
            comis = to_float(row[c_com_org]) if c_com_org is not None and c_com_org < len(row) else None
        else:
            comis = to_float(row[c_com_prod]) if c_com_prod is not None and c_com_prod < len(row) else None
            # Algunos archivos invierten las columnas (Prod vacío, Org real). Si comis es None probamos la otra.
            if comis is None and c_com_org is not None and c_com_org < len(row):
                comis = to_float(row[c_com_org])

        try:
            rec = make_record(
                fecha=fecha,
                poliza=contrato,
                asegurado=cliente,
                seccion=SECCION,
                compania=COMPANY,
                tipo="PR",
                comisiones=comis,
                prima=importe_v,
                premio=importe_v,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=i + 1,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("SMG ART fila %s: %s", i, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=i + 1, raw=row)
    return result
