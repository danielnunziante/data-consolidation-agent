"""Parser de LA MERCANTIL ANDINA (ARS y USD).

La hoja viene como un "listado contable". Cada movimiento real está representado
por una fila con POLIZA != 0 y una DESCRIPCION del tipo:

    ``516367856 0002 Cta 01 Po  152377,03-CB``
    ``516367856 0002 Cta 01 Pa   83479,63-AY``
    ``516367856 0002 Cta 01 Pa   83479,63-PR``

- Las filas con sufijo ``-PR`` generan TIPO=PR.
- Las filas con sufijo ``-AY`` y ``-CB`` se consolidan como TIPO=AY (se suman las
  comisiones si están en el mismo movimiento de póliza/cuota).

El importe numérico embebido en la descripción representa la PRIMA base sobre
la que se calculó la comisión. El HABER de la fila es la comisión.

Para PR: PRIMA = importe base, PREMIO = importe base + cualquier CB asociado
al mismo documento (fila complementaria con prefijo ``Po``). Si no hay CB,
PREMIO = PRIMA.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.fx import get_fx
from ..utils.numbers import round2, to_float
from ..utils.strings import safe_str
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)


# Manual: regla de truncado de póliza por prefijo numérico.
# Prefijos que toman 7 dígitos por derecha:
_PREFIX_7 = {"4", "6", "9", "13", "14", "16", "17", "18", "19", "30"}
# Prefijo que toma 6 dígitos:
_PREFIX_6 = {"35"}
# Prefijo que toma 8 dígitos:
_PREFIX_8 = {"51"}


def _truncate_mercantil(poliza_original: str) -> tuple[str, str]:
    """Devuelve (poliza_truncada, seccion) según las reglas del manual.

    La sección es el prefijo (1 o 2 dígitos) según la tabla.
    Para prefijos no listados, fallback al comportamiento histórico:
    `seccion = poliza[:2]`, `poliza = poliza[1:]`.
    """
    digits = "".join(c for c in safe_str(poliza_original) if c.isdigit())
    if not digits:
        return (poliza_original, "")
    # Probamos primero los prefijos de 2 dígitos (mayor longitud) y después los de 1.
    for plen in (2, 1):
        if len(digits) <= plen:
            continue
        prefix = digits[:plen]
        if prefix in _PREFIX_8:
            return (digits[-8:], prefix)
        if prefix in _PREFIX_7:
            return (digits[-7:], prefix)
        if prefix in _PREFIX_6:
            return (digits[-6:], prefix)
    # Fallback: comportamiento histórico
    return (digits[1:] if len(digits) > 1 else digits, digits[:2])


_DESC_RE = re.compile(
    r"^\s*(?P<poliza_desc>\d+)\s+(?P<cert>\d+)\s+Cta\s+(?P<cta>\d+)\s+(?P<cbp>\S+)\s+(?P<importe>[\-\d\.\,]+)\s*-\s*(?P<sufijo>PR|AY|CB)\b",
    re.IGNORECASE,
)


def _parse_desc(descripcion: str) -> dict | None:
    m = _DESC_RE.match(safe_str(descripcion))
    if not m:
        return None
    return {
        "poliza_desc": m.group("poliza_desc"),
        "certificado": m.group("cert"),
        "cuenta": m.group("cta"),
        "cbp": m.group("cbp").upper(),  # 'Po' (premio/CB) o 'Pa' (prima -> AY/PR)
        "importe_base": to_float(m.group("importe")),
        "sufijo": m.group("sufijo").upper(),
    }


def _parse(file_path: str, fecha: date, company_name: str) -> ParseResult:
    result = ParseResult(parser_name="mercantil_andina", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(df_raw, ["FECHA", "DESCRIPCION", "POLIZA", "ASEGURADO", "HABER"])
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_desc = find_col(columns, "DESCRIPCION")
    c_pol = find_col(columns, "POLIZA")
    c_aseg = find_col(columns, "ASEGURADO")
    c_haber = find_col(columns, "HABER")

    if not all([c_desc, c_pol, c_aseg, c_haber]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name

    # Recolectamos los CB asociados para poder reconstruir PREMIO al emitir PR.
    # Clave: (poliza_original, certificado, cuenta)
    cb_by_key: dict[tuple[str, str, str], float] = {}
    rows_buffer: list[dict] = []

    for idx, row in df.iterrows():
        poliza_original = safe_str(row[c_pol]).strip()
        if not poliza_original or poliza_original == "0":
            continue
        parsed = _parse_desc(row[c_desc])
        if not parsed:
            continue
        importe_com = to_float(row[c_haber])
        if importe_com is None:
            continue

        certificado = parsed["certificado"]
        cuenta = parsed["cuenta"]
        key = (poliza_original, certificado, cuenta)
        if parsed["sufijo"] == "CB":
            cb_by_key[key] = cb_by_key.get(key, 0.0) + (parsed["importe_base"] or 0.0)

        rows_buffer.append(
            {
                "idx": idx,
                "source_row": idx + header_row + 2,
                "poliza": poliza_original,
                "asegurado": safe_str(row[c_aseg]),
                "sufijo": parsed["sufijo"],
                "cbp": parsed["cbp"],
                "importe_base": parsed["importe_base"],
                "comision": importe_com,
                "cert": certificado,
                "cta": cuenta,
            }
        )

    # Emitimos un registro por cada fila. Regla:
    #   - sufijo PR -> TIPO=PR con prima/premio
    #   - sufijo AY -> TIPO=AY, sin prima/premio
    #   - sufijo CB -> TIPO=AY, sin prima/premio (se consolida como AY en la salida)
    for r in rows_buffer:
        sufijo = r["sufijo"]
        poliza_original = r["poliza"]
        poliza_cut, seccion = _truncate_mercantil(poliza_original)
        key = (poliza_original, r["cert"], r["cta"])
        try:
            if sufijo == "PR":
                prima_base = r["importe_base"]
                cb_extra = cb_by_key.get(key, 0.0) or 0.0
                if prima_base is None:
                    premio = None
                else:
                    premio = round2(prima_base + (cb_extra or 0.0))
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza_cut,
                    asegurado=r["asegurado"],
                    seccion=seccion,
                    compania=company_name,
                    tipo="PR",
                    comisiones=r["comision"],
                    prima=prima_base,
                    premio=premio,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=r["source_row"],
                )
            else:
                # AY o CB -> TIPO=AY
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza_cut,
                    asegurado=r["asegurado"],
                    seccion=seccion,
                    compania=company_name,
                    tipo="AY",
                    comisiones=r["comision"],
                    prima=None,
                    premio=None,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=r["source_row"],
                )
            result.records.append(rec)
        except Exception as exc:
            log.warning("MERCANTIL fila %s: %s", r["idx"], exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=r["source_row"], raw=str(r))
    return result


def parse_pesos(file_path: str, fecha: date) -> ParseResult:
    res = _parse(file_path, fecha, "MERCANTIL ANDINA")
    res.parser_name = "mercantil_andina"
    return res


def parse_usd(file_path: str, fecha: date) -> ParseResult:
    res = _parse(file_path, fecha, "MERCANTIL ANDINA USD")
    res.parser_name = "mercantil_andina_usd"

    # Manual: la cuenta USD se lleva a pesos.
    tc = get_fx("MERCANTIL ANDINA")
    fname = Path(file_path).name
    if tc is None:
        original = list(res.records)
        res.records = []
        for rec in original:
            reject(
                res,
                fname,
                "USD sin TC configurado (definir MERCANTIL_ANDINA_USD_TC o config/fx.json)",
                source_sheet=rec.source_sheet,
                source_row=rec.source_row,
                compania=rec.compania,
                raw=rec.to_dict(),
            )
        return res

    log.info("MERCANTIL ANDINA USD TC aplicado: %s", tc)
    for rec in res.records:
        if rec.comisiones is not None:
            rec.comisiones = round2(rec.comisiones * tc)
        if rec.prima is not None:
            rec.prima = round2(rec.prima * tc)
        if rec.premio is not None:
            rec.premio = round2(rec.premio * tc)
    return res
