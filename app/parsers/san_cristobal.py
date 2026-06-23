"""Parser de SAN CRISTOBAL - hojas Comisiones PAS (PR) y Comisiones ORG (AY/IND)."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.fx import get_fx
from ..utils.numbers import to_float
from ..utils.strings import contains_any, safe_str
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)


def _clean_poliza(raw: str) -> str:
    """De "01-05-01-32106279" conservamos la parte numérica útil.

    Mantenemos los últimos dígitos largos (número de póliza real).
    """
    s = safe_str(raw).replace(" ", "")
    if not s:
        return ""
    parts = re.split(r"[-/]", s)
    # Nos quedamos con la última porción numérica más larga
    parts_num = [p for p in parts if p.isdigit()]
    if not parts_num:
        return s
    return max(parts_num, key=len)


def _parse_sheet(
    df_raw,
    sheet_name: str,
    fecha,
    fname: str,
    sheet_tipo: str,
    result: ParseResult,
    default_usd: bool,
) -> None:
    header_row = detect_header_row(df_raw, ["CLIENTE", "RAMO", "N° DE PÓLIZA", "COMISIÓN", "PREMIO"])
    if header_row is None:
        reject(result, fname, "No se detectó cabecera", source_sheet=sheet_name)
        return
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_cli = find_col(columns, "CLIENTE")
    c_ramo = find_col(columns, "RAMO")
    c_pol = find_col(columns, "N° DE PÓLIZA", "N° DE POLIZA", "N DE POLIZA", "N DE PÓLIZA")
    c_com = find_col(columns, "COMISIÓN", "COMISION")
    c_prima = find_col(columns, "PRIMA")
    c_prem = find_col(columns, "PREMIO")
    c_pas_name = find_col(columns, "NOMBRE PAS")
    c_moneda = find_col(columns, "MONEDA")

    if not all([c_cli, c_ramo, c_pol, c_com]):
        reject(result, fname, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return

    for idx, row in df.iterrows():
        poliza_raw = safe_str(row[c_pol])
        if not poliza_raw:
            continue
        poliza = _clean_poliza(poliza_raw)
        if not poliza:
            continue

        # Las filas en dólares (columna MONEDA "Dólares (USD)") van a la
        # compañía SAN CRISTOBAL USD convertidas con el TC configurado.
        moneda_val = safe_str(row[c_moneda]) if c_moneda else ""
        es_usd = default_usd or contains_any(moneda_val, ["DOLAR", "USD", "U$S"])

        if sheet_tipo == "PAS":
            tipo = "PR"
        else:
            name_val = safe_str(row[c_pas_name]) if c_pas_name else ""
            if contains_any(name_val, ["COBERTURAS", "COBERSER"]):
                tipo = "AY"
            else:
                tipo = "IND"

        if tipo == "PR":
            prima = row[c_prima] if c_prima else None
            premio = row[c_prem] if c_prem else None
        else:
            prima = None
            premio = None

        company_name = "SAN CRISTOBAL USD" if es_usd else "SAN CRISTOBAL"
        tc = None
        if es_usd:
            tc = get_fx("SAN CRISTOBAL")
            if tc is None:
                reject(
                    result,
                    fname,
                    "USD sin TC configurado (definir SAN_CRISTOBAL_USD_TC o config/fx.json)",
                    source_sheet=sheet_name,
                    source_row=idx + header_row + 2,
                    compania=company_name,
                    raw=row.to_dict(),
                )
                continue

        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_cli],
                seccion=row[c_ramo],
                compania=company_name,
                tipo=tipo,
                comisiones=row[c_com],
                prima=prima,
                premio=premio,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=idx + header_row + 2,
            )
            if tc is not None:
                if rec.comisiones is not None:
                    rec.comisiones = round(rec.comisiones * tc, 2)
                if rec.prima is not None:
                    rec.prima = round(rec.prima * tc, 2)
                if rec.premio is not None:
                    rec.premio = round(rec.premio * tc, 2)
            # Cuando la prima es negativa (devolución), el premio debe serlo también
            if rec.prima is not None and rec.premio is not None and rec.prima < 0 and rec.premio > 0:
                rec.premio = -rec.premio
            result.records.append(rec)
        except Exception as exc:
            log.warning("SAN CRISTOBAL %s fila %s: %s", sheet_name, idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())


_HEADER_TOKENS = ["CLIENTE", "RAMO", "N° DE PÓLIZA", "COMISIÓN", "PREMIO"]


def _classify_sheet(sheet_name: str, df_raw) -> str | None:
    """Decide si una hoja es de productores ("PAS") u organizadores ("ORG").

    Primero por el nombre (comportamiento histórico) y, si el nombre no lo
    aclara, por el contenido: la hoja de organizadores trae una columna "ORG".
    Devuelve None si la hoja no parece tener datos de San Cristóbal.
    """
    low = sheet_name.lower()
    if "pas" in low:
        return "PAS"
    if "org" in low:
        return "ORG"

    # Nombre no reconocido: clasificamos por contenido para no saltear una hoja
    # en silencio (causa típica de "no veo las filas de la pestaña ORG").
    header_row = detect_header_row(df_raw, _HEADER_TOKENS)
    if header_row is None:
        log.info("SAN CRISTOBAL: hoja %r ignorada (sin cabecera reconocible)", sheet_name)
        return None
    columns = [safe_str(v) for v in df_raw.iloc[header_row].tolist()]
    tipo = "ORG" if find_col(columns, "ORG") else "PAS"
    log.warning(
        "SAN CRISTOBAL: hoja %r sin 'PAS'/'ORG' en el nombre; clasificada como %s por contenido",
        sheet_name,
        tipo,
    )
    return tipo


def _parse(file_path: str, fecha: date, default_usd: bool) -> ParseResult:
    result = ParseResult(parser_name="san_cristobal", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    fname = Path(file_path).name

    for sheet_name, df_raw in sheets.items():
        sheet_tipo = _classify_sheet(sheet_name, df_raw)
        if sheet_tipo is None:
            continue
        _parse_sheet(df_raw, sheet_name, fecha, fname, sheet_tipo, result, default_usd)
    return result


def parse_pesos(file_path: str, fecha: date) -> ParseResult:
    res = _parse(file_path, fecha, default_usd=False)
    res.parser_name = "san_cristobal"
    return res


def parse_usd(file_path: str, fecha: date) -> ParseResult:
    # Archivo dedicado de cuenta USD: todas las filas se convierten.
    res = _parse(file_path, fecha, default_usd=True)
    res.parser_name = "san_cristobal_usd"
    return res
