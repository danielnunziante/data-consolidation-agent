"""Parser de QBE-ZURICH.

Reglas de extracción de póliza (orden de evaluación importa):

1. Si POLIZA empieza con "AMM"  -> la póliza real está en CERTIF.
   Tomar los últimos 5 dígitos. Si el 5to por derecha (es decir, el primer
   carácter de esa porción) es '0', quedarse con 4.
2. Si POLIZA empieza con "AUS"  -> CERTIF, últimos 6 dígitos de derecha.
3. Si POLIZA empieza con "AMT" / "AUT1" / "CON" / "HOC" / "ICQ"
   -> la póliza está en POLIZA, después del prefijo de letras. Tomar el
   número resultante stripeando todos los ceros a la izquierda
   ("después del último 0 de izquierda a derecha").
4. Regla general extra: si la póliza resultante queda con 7 dígitos, recortar
   a los 6 de la derecha (regla del manual: "SOLO LAS DE 7 DIGITOS, VAN LOS 6
   DE DERECHA").

Tipo de comisión:
    - Si la columna del productor dice "OR" -> el cliente marca AY para sus
      pólizas propias e IND para las de otros. No hay forma confiable de
      identificarlo desde el Excel: por defecto marcamos IND y exponemos la
      constante editable POLIZAS_PROPIAS_AY para override manual.
    - Resto -> PR.

Reglas adicionales del manual:
    - Si la comisión es negativa, prima y premio también deben ser negativos.
    - SECCION = columna SECCION / RAMO / RAMA del archivo.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import clean_policy, normalize, safe_str
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)

COMPANY = "QBE-ZURICH"

# Override manual: pólizas que el cliente sabe que son propias (cuando aparece "OR"
# se marcan AY en vez de IND). Editable acá hasta que el cliente nos pase un
# mapa concreto.
# TODO confirmar con cliente: criterios para distinguir póliza propia vs ajena.
POLIZAS_PROPIAS_AY: set[str] = set()

_PREFIX_AMM = ("AMM",)
_PREFIX_AUS = ("AUS",)
_PREFIX_LETTERS = ("AMT", "AUT1", "CON", "HOC", "ICQ")
_DIGIT_RE = re.compile(r"\d")


def _digits_only(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def _starts_with(value: str, prefixes: tuple[str, ...]) -> Optional[str]:
    up = normalize(value)
    for p in prefixes:
        if up.startswith(p):
            return p
    return None


def _apply_general_truncate(poliza: str) -> str:
    """Si la póliza resultante tiene 7 dígitos, queda con los 6 de derecha."""
    if poliza.isdigit() and len(poliza) == 7:
        return poliza[-6:]
    return poliza


def _extract_poliza(poliza_raw: str, certif_raw: str) -> str:
    poliza_str = clean_policy(poliza_raw)
    certif_str = clean_policy(certif_raw)

    # 1) AMM -> CERTIF, últimos 5; si el 5to por derecha == '0' -> 4
    if _starts_with(poliza_str, _PREFIX_AMM):
        digits = _digits_only(certif_str)
        if len(digits) >= 5:
            last5 = digits[-5:]
            if last5[0] == "0":
                return _apply_general_truncate(last5[1:])
            return _apply_general_truncate(last5)
        return _apply_general_truncate(digits)

    # 2) AUS -> CERTIF, últimos 6 de derecha
    if _starts_with(poliza_str, _PREFIX_AUS):
        digits = _digits_only(certif_str)
        if len(digits) >= 6:
            return _apply_general_truncate(digits[-6:])
        return _apply_general_truncate(digits)

    # 3) AMT / AUT1 / CON / HOC / ICQ -> POLIZA, después del prefijo,
    #    strippear ceros a la izquierda.
    prefix = _starts_with(poliza_str, _PREFIX_LETTERS)
    if prefix:
        rest = poliza_str[len(prefix):]
        m = _DIGIT_RE.search(rest)
        if m:
            digits_part = rest[m.start():]
            digits_only = _digits_only(digits_part)
            stripped = digits_only.lstrip("0") or "0"
            return _apply_general_truncate(stripped)
        return _apply_general_truncate(poliza_str)

    # 4) Cualquier otro caso: la dejamos como viene (con clean_policy).
    return _apply_general_truncate(poliza_str)


def _normalize_productor(value) -> str:
    return normalize(value)


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="qbe_zurich", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw,
        ["POLIZA", "CERTIF", "ASEGURADO", "COMISION", "PRIMA"],
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    log.debug("QBE-ZURICH columnas: %s", columns)

    c_pol = find_col(columns, "POLIZA")
    c_cert = find_col(columns, "CERTIF", "CERTIFICADO")
    c_aseg = find_col(columns, "ASEGURADO", "RAZON SOCIAL", "CLIENTE")
    c_sec = find_col(columns, "SECCION", "RAMO", "RAMA")
    c_com = find_col(columns, "COMISION", "COMISIONES")
    c_prima = find_col(columns, "PRIMA")
    c_premio = find_col(columns, "PREMIO")
    c_prod = find_col(columns, "PRODUCTOR", "TIPO PROD", "TIPO PARTICIPACION", "PARTICIPACION")

    if not all([c_pol, c_aseg, c_com, c_prima]):
        reject(
            result,
            Path(file_path).name,
            f"Columnas insuficientes: {columns}",
            source_sheet=sheet_name,
        )
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza_raw = safe_str(row[c_pol])
        certif_raw = safe_str(row[c_cert]) if c_cert else ""
        if not poliza_raw or normalize(poliza_raw) == "0":
            continue
        poliza = _extract_poliza(poliza_raw, certif_raw)
        if not poliza:
            continue

        source_row = idx + header_row + 2

        com_v = to_float(row[c_com])
        prima_v = to_float(row[c_prima]) if c_prima else None
        premio_v = to_float(row[c_premio]) if c_premio else None

        # Si la comisión es negativa, prima y premio negativas (regla general manual).
        if com_v is not None and com_v < 0:
            if prima_v is not None and prima_v > 0:
                prima_v = -prima_v
            if premio_v is not None and premio_v > 0:
                premio_v = -premio_v

        prod_norm = _normalize_productor(row[c_prod]) if c_prod else ""
        if prod_norm == "OR":
            # Default IND salvo override por POLIZAS_PROPIAS_AY.
            tipo = "AY" if poliza in POLIZAS_PROPIAS_AY else "IND"
        else:
            tipo = "PR"

        if tipo == "PR":
            prima_out = prima_v
            premio_out = premio_v
        else:
            prima_out = None
            premio_out = None

        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=row[c_sec] if c_sec else "",
                compania=COMPANY,
                tipo=tipo,
                comisiones=com_v,
                prima=prima_out,
                premio=premio_out,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=source_row,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("QBE-ZURICH fila %s: %s", idx, exc)
            reject(
                result,
                fname,
                f"Error: {exc}",
                source_sheet=sheet_name,
                source_row=source_row,
                raw=row.to_dict(),
            )
    return result
