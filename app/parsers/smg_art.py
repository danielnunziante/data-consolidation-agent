"""Parser de SMG ART - múltiples bloques "Productor: ..." en una misma hoja.

- Bloques de COBERTURAS (S.A y SA/B) -> PR (cartera propia).
- Bloques de productores terceros -> IND sólo cuando hay comisión de
  organizador (Com.Org != 0); el resto se descarta.
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
    # Manual: PRIMA = PREMIO = Importe(3). Si no aparece el subíndice, buscamos
    # la 3ra columna cuyo encabezado contenga la palabra "Importe" (sin caer en
    # el primer "Importe" suelto, que suele ser otro concepto).
    c_importe = col_for("Importe (3)", "Importe(3)")
    if c_importe is None:
        importe_positions = [
            i for i, h in enumerate(header_cells) if "IMPORTE" in normalize(h)
        ]
        if len(importe_positions) >= 3:
            c_importe = importe_positions[2]
    c_com_org = col_for("Com. Org. (5)", "Com. Org.")
    c_com_prod = col_for("Com. Prod. (5)", "Com. Prod.")

    if None in (c_cliente, c_contrato, c_importe):
        reject(result, fname, f"Columnas insuficientes: {header_cells}", source_sheet=sheet_name)
        return result

    # 2) Escanear filas detectando bloques por líneas "Productor: ...".
    # Reglas (validadas contra la consolidación manual de ABRIL 2026):
    #   - Bloques cuyo productor es COBERTURAS (S.A o SA/B) -> TIPO=PR.
    #     COMISIONES = Com.Org si es != 0, si no Com.Prod (en el bloque del
    #     organizador la comisión viene en Com.Org; en el SA/B en Com.Prod).
    #     PRIMA = PREMIO = Importe(3). Se conservan filas con comisión 0.
    #   - Bloques de otros productores (terceros) -> el bróker sólo cobra la
    #     comisión de organizador: si Com.Org != 0 la fila va como IND (sólo
    #     comisiones); si Com.Org == 0 la fila se descarta.
    bloque_coberturas = False
    bloque_activo = False

    for i in range(header_row + 1, n_rows):
        row = df.iloc[i].tolist()
        raw_str = " ".join(safe_str(v) for v in row)
        norm = normalize(raw_str)
        if "PRODUCTOR:" in norm:
            bloque_activo = True
            bloque_coberturas = "COBERTURAS" in norm
            log.debug("SMG ART bloque: %r (coberturas=%s)", raw_str.strip()[:80], bloque_coberturas)
            continue

        if not bloque_activo:
            continue

        cliente = safe_str(row[c_cliente]) if c_cliente < len(row) else ""
        contrato = safe_str(row[c_contrato]) if c_contrato < len(row) else ""
        importe_v = to_float(row[c_importe]) if c_importe < len(row) else None

        if not cliente and not contrato:
            continue
        if not contrato or importe_v is None:
            continue
        if normalize(cliente).startswith(("CLIENTE", "TOTALES")):
            continue

        org_v = to_float(row[c_com_org]) if c_com_org is not None and c_com_org < len(row) else None
        prod_v = to_float(row[c_com_prod]) if c_com_prod is not None and c_com_prod < len(row) else None

        if bloque_coberturas:
            tipo = "PR"
            comis = org_v if org_v not in (None, 0) else prod_v
            prima_out = importe_v
            premio_out = importe_v
        else:
            if org_v in (None, 0):
                continue
            tipo = "IND"
            comis = org_v
            prima_out = None
            premio_out = None

        try:
            rec = make_record(
                fecha=fecha,
                poliza=contrato,
                asegurado=cliente,
                seccion=SECCION,
                compania=COMPANY,
                tipo=tipo,
                comisiones=comis,
                prima=prima_out,
                premio=premio_out,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=i + 1,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("SMG ART fila %s: %s", i, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=i + 1, raw=row)
    return result
