"""Parser de SMG LIFE."""
from __future__ import annotations

import re
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

COMPANY = "SMG LIFE"


def _split_poliza(raw: str) -> tuple[str, str]:
    """Devuelve (seccion, poliza) desde una póliza tipo `CVO9-0-41695-99-0-45132-0`.

    Manual: "SEPARAR LA COLUMNA POLIZA POR `-` Y ES EL NRO QUE QUEDA EN LA
    TERCER COLUMNA". La sección es el primer bloque (índice 0).
    """
    s = safe_str(raw)
    if not s:
        return ("", "")
    parts = [p.strip() for p in re.split(r"[-/]", s)]
    seccion = parts[0] if parts else ""
    poliza = parts[2] if len(parts) >= 3 else ""
    if not poliza:
        for p in parts[1:]:
            if p.isdigit():
                poliza = p
                break
    return (seccion, poliza or s)


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="smg_life", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw, ["Póliza", "Asegurado", "Base cálculo", "Comisión", "Grupo Movimiento"]
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_pol = find_col(columns, "Póliza", "Poliza")
    c_aseg = find_col(columns, "Asegurado")
    c_base = find_col(columns, "Base cálculo", "Base calculo")
    c_com = find_col(columns, "Comisión", "Comision")
    c_grupo = find_col(columns, "Grupo Movimiento")
    c_moneda = find_col(columns, "Moneda", "Cod Moneda", "CodMoneda")
    c_cotiz = find_col(columns, "Cotizacion", "Cotización", "Tipo de cambio", "TC")

    if not all([c_pol, c_aseg, c_com, c_base]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        grupo = normalize(row[c_grupo]) if c_grupo else ""
        # excluir comisiones adicionales (no PR "básicas" o "colectivo")
        if grupo and "ADICIONAL" in grupo:
            continue

        seccion, poliza = _split_poliza(row[c_pol])
        if not poliza:
            continue

        com_bruto = to_float(row[c_com])
        comisiones = com_bruto / 1.21 if com_bruto is not None else None
        prima = to_float(row[c_base])

        # Manual: las primas en USD se llevan a pesos usando la columna Cotizacion.
        is_usd = False
        if c_moneda is not None:
            mon_norm = normalize(row[c_moneda])
            if mon_norm and any(tok in mon_norm for tok in ("USD", "U$S", "DOLAR", "DOL")):
                is_usd = True
        if is_usd and prima is not None and c_cotiz is not None:
            tc = to_float(row[c_cotiz])
            if tc and tc > 0:
                prima = prima * tc
            else:
                log.warning(
                    "SMG LIFE fila %s: USD sin Cotizacion válida (%r)",
                    idx,
                    row[c_cotiz] if c_cotiz else None,
                )

        premio = prima * 1.40 if prima is not None else None

        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=seccion,
                compania=COMPANY,
                tipo="PR",
                comisiones=comisiones,
                prima=prima,
                premio=premio,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("SMG LIFE fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
