"""Parser de INTEGRITY - BASICA=PR, EXTRA=AY."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.fx import get_fx
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

COMPANY = "INTEGRITY"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="integrity", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw, ["TipoComision", "Poliza", "NombreAsegurado", "Seccion", "Comision"]
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_tipo_com = find_col(columns, "TipoComision")
    c_pol = find_col(columns, "Poliza")
    c_aseg = find_col(columns, "NombreAsegurado")
    c_sec = find_col(columns, "Seccion")
    c_com = find_col(columns, "Comision")
    c_prima = find_col(columns, "Prima")
    c_importe = find_col(columns, "Importe")
    c_moneda = find_col(columns, "Moneda", "Cod Moneda", "CodMoneda")

    if not all([c_tipo_com, c_pol, c_aseg, c_com]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    tc_cache: float | None = None
    tc_logged = False
    for idx, row in df.iterrows():
        tipo_com_val = normalize(row[c_tipo_com])
        if tipo_com_val == "BASICA":
            tipo = "PR"
        elif tipo_com_val == "EXTRA":
            tipo = "AY"
        else:
            continue

        poliza = safe_str(row[c_pol])
        if not poliza or poliza == "0":
            continue

        source_row = idx + header_row + 2
        # Detección USD: la columna Moneda puede traer "USD", "U$S", "DOLAR", etc.
        is_usd = False
        if c_moneda is not None:
            mon_norm = normalize(row[c_moneda])
            if mon_norm and mon_norm not in {"PESOS", "ARS", "PESO", "$"}:
                if any(tok in mon_norm for tok in ("USD", "U$S", "DOLAR", "DOL")):
                    is_usd = True

        com_v = to_float(row[c_com])
        prima_v = to_float(row[c_prima]) if c_prima else None
        premio_v = to_float(row[c_importe]) if c_importe else None

        if is_usd:
            if tc_cache is None:
                tc_cache = get_fx("INTEGRITY")
            if tc_cache is None:
                reject(
                    result,
                    fname,
                    "USD sin TC configurado (definir INTEGRITY_USD_TC o config/fx.json)",
                    source_sheet=sheet_name,
                    source_row=source_row,
                    compania=COMPANY,
                    raw=row.to_dict(),
                )
                continue
            if not tc_logged:
                log.info("INTEGRITY USD TC aplicado: %s", tc_cache)
                tc_logged = True
            if com_v is not None:
                com_v *= tc_cache
            if prima_v is not None:
                prima_v *= tc_cache
            if premio_v is not None:
                premio_v *= tc_cache

        if tipo == "PR":
            prima = prima_v
            premio = premio_v
        else:
            prima = None
            premio = None

        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=safe_str(row[c_sec]) if c_sec else "",
                compania=COMPANY,
                tipo=tipo,
                comisiones=com_v,
                prima=prima,
                premio=premio,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=source_row,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("INTEGRITY fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    return result
