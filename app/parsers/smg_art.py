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

    # 2) Escanear filas detectando bloques por líneas "Productor: COBERTURAS..."
    # Aceptamos los dos primeros bloques. Para cada bloque determinamos si la
    # comisión efectiva está en Com.Org o Com.Prod mirando qué columna tiene
    # valores no-cero en las primeras filas del bloque (no por orden de bloque).
    BLOCK_PEEK = 10  # filas a inspeccionar antes de decidir la columna

    def _decide_usar_org(start: int) -> bool:
        org_hits = prod_hits = 0
        seen = 0
        for j in range(start, min(start + 60, n_rows)):
            row_j = df.iloc[j].tolist()
            raw_j = normalize(" ".join(safe_str(v) for v in row_j))
            if "PRODUCTOR:" in raw_j and "COBERTURAS" in raw_j:
                break
            cli = safe_str(row_j[c_cliente]) if c_cliente < len(row_j) else ""
            con = safe_str(row_j[c_contrato]) if c_contrato < len(row_j) else ""
            if not con or normalize(cli).startswith("CLIENTE"):
                continue
            org_v = to_float(row_j[c_com_org]) if c_com_org is not None and c_com_org < len(row_j) else None
            prod_v = to_float(row_j[c_com_prod]) if c_com_prod is not None and c_com_prod < len(row_j) else None
            if org_v not in (None, 0):
                org_hits += 1
            if prod_v not in (None, 0):
                prod_hits += 1
            seen += 1
            if seen >= BLOCK_PEEK:
                break
        # Si ninguna tiene datos asumimos Prod (default histórico)
        return org_hits > prod_hits

    # bloque 1 → PR; bloque 2 → IND (sólo pólizas no vistas en bloque 1)
    bloques_aceptados = 0
    bloque_activo = False
    usar_org = False
    polizas_pr: set = set()

    for i in range(header_row + 1, n_rows):
        row = df.iloc[i].tolist()
        raw_str = " ".join(safe_str(v) for v in row)
        norm = normalize(raw_str)
        if "PRODUCTOR:" in norm and "COBERTURAS" in norm:
            bloques_aceptados += 1
            if bloques_aceptados > 2:
                break
            bloque_activo = True
            usar_org = _decide_usar_org(i + 1)
            log.debug(
                "SMG ART bloque %s: usar_org=%s (header=%r)",
                bloques_aceptados,
                usar_org,
                raw_str.strip()[:80],
            )
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
        if normalize(cliente).startswith("CLIENTE"):
            continue

        if usar_org:
            comis = to_float(row[c_com_org]) if c_com_org is not None and c_com_org < len(row) else None
        else:
            comis = to_float(row[c_com_prod]) if c_com_prod is not None and c_com_prod < len(row) else None

        if bloques_aceptados == 1:
            tipo = "PR"
            polizas_pr.add(contrato)
        else:
            # Bloque 2 es el productor organizador (IND). Excluir pólizas que
            # ya aparecieron en el bloque PR para evitar duplicados.
            if contrato in polizas_pr:
                continue
            tipo = "IND"

        try:
            rec = make_record(
                fecha=fecha,
                poliza=contrato,
                asegurado=cliente,
                seccion=SECCION,
                compania=COMPANY,
                tipo=tipo,
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
