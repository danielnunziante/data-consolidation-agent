"""Parser de QBE-ZURICH (archivo "ZURICH EX QBE ..." / "QBE ...").

Formato real (validado con ABRIL 2026): columnas
CODIGO | POLIZA | CERTIF | ENDOSO | RECIBO | MONEDA | COMISION | BASE |
PORC. | PREMIO | ... | ASEGURADO | ...

Reglas (consolidación manual del cliente):
- Póliza: si CERTIF tiene dígitos significativos, se toman los últimos 6
  dígitos sin ceros a la izquierda; si no, se hace lo mismo con la parte
  numérica de la columna POLIZA.
- TIPO: filas con CODIGO "OR..." son comisión de organizador: AY si la
  póliza también tiene una fila de productor (CODIGO "PR.../P...") en el
  archivo, IND si no. El resto es PR.
- PR lleva PRIMA=BASE y PREMIO=PREMIO; si la comisión es negativa
  (anulación) prima y premio se vuelcan negativos.
- SECCION: según el prefijo alfabético de POLIZA (AMM/AMT=MOTOVEHICULOS,
  AUS/AUT=AUTOMOTORES, HOC=COMBINADO FAMILIAR, ICQ=INTEGRAL DE COMERCIO,
  CON=INTEGRAL DE CONSORCIO).
- La última fila es un total (POLIZA vacía) y se descarta.
"""
from __future__ import annotations

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

COMPANY = "QBE-ZURICH"

_SECCION_BY_PREFIX = {
    "AMM": "MOTOVEHICULOS",
    "AMT": "MOTOVEHICULOS",
    "AUS": "AUTOMOTORES",
    "AUT": "AUTOMOTORES",
    "HOC": "COMBINADO FAMILIAR",
    "ICQ": "INTEGRAL DE COMERCIO",
    "CON": "INTEGRAL DE CONSORCIO",
}


def _digits_only(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def _extract_poliza(poliza_raw: str, certif_raw: str) -> str:
    cert_digits = _digits_only(certif_raw)
    if cert_digits and cert_digits.strip("0"):
        return cert_digits[-6:].lstrip("0") or "0"
    pol_digits = _digits_only(poliza_raw)
    if pol_digits:
        return pol_digits[-6:].lstrip("0") or "0"
    return ""


def _seccion_for(poliza_raw: str) -> str:
    up = normalize(poliza_raw)
    for prefix, seccion in _SECCION_BY_PREFIX.items():
        if up.startswith(prefix):
            return seccion
    return ""


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="qbe_zurich", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw,
        ["CODIGO", "POLIZA", "CERTIF", "COMISION", "BASE", "PREMIO", "ASEGURADO"],
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    log.debug("QBE-ZURICH columnas: %s", columns)

    c_cod = find_col(columns, "CODIGO")
    c_pol = find_col(columns, "POLIZA")
    c_cert = find_col(columns, "CERTIF", "CERTIFICADO")
    c_aseg = find_col(columns, "ASEGURADO", "RAZON SOCIAL", "CLIENTE")
    c_com = find_col(columns, "COMISION", "COMISIONES")
    c_base = find_col(columns, "BASE", "PRIMA")
    c_premio = find_col(columns, "PREMIO")

    if not all([c_pol, c_aseg, c_com, c_base]):
        reject(
            result,
            Path(file_path).name,
            f"Columnas insuficientes: {columns}",
            source_sheet=sheet_name,
        )
        return result

    fname = Path(file_path).name

    # Primera pasada: pólizas que tienen fila de productor (no-OR), para
    # clasificar las filas OR como AY (propias) o IND (de terceros).
    polizas_con_pr: set[str] = set()
    parsed_rows: list[dict] = []
    for idx, row in df.iterrows():
        poliza_raw = safe_str(row[c_pol])
        if not poliza_raw or normalize(poliza_raw) == "0":
            continue
        poliza = _extract_poliza(poliza_raw, safe_str(row[c_cert]) if c_cert else "")
        if not poliza:
            continue
        codigo = normalize(row[c_cod]) if c_cod else ""
        es_or = codigo.startswith("OR")
        if not es_or:
            polizas_con_pr.add(poliza)
        parsed_rows.append(
            {
                "source_row": idx + header_row + 2,
                "poliza": poliza,
                "poliza_raw": poliza_raw,
                "asegurado": safe_str(row[c_aseg]),
                "es_or": es_or,
                "com": to_float(row[c_com]),
                "base": to_float(row[c_base]),
                "premio": to_float(row[c_premio]) if c_premio else None,
            }
        )

    for r in parsed_rows:
        com_v = r["com"]
        if com_v is None:
            continue
        if r["es_or"]:
            tipo = "AY" if r["poliza"] in polizas_con_pr else "IND"
            prima_out = None
            premio_out = None
        else:
            tipo = "PR"
            prima_out = r["base"]
            premio_out = r["premio"]
            # Anulaciones: si la comisión es negativa, prima y premio negativos.
            if com_v < 0:
                if prima_out is not None and prima_out > 0:
                    prima_out = -prima_out
                if premio_out is not None and premio_out > 0:
                    premio_out = -premio_out
        try:
            rec = make_record(
                fecha=fecha,
                poliza=r["poliza"],
                asegurado=r["asegurado"],
                seccion=_seccion_for(r["poliza_raw"]),
                compania=COMPANY,
                tipo=tipo,
                comisiones=com_v,
                prima=prima_out,
                premio=premio_out,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=r["source_row"],
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("QBE-ZURICH fila %s: %s", r["source_row"], exc)
            reject(
                result,
                fname,
                f"Error: {exc}",
                source_sheet=sheet_name,
                source_row=r["source_row"],
                raw=str(r),
            )
    return result
