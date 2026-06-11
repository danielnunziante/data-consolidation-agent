"""Parser de HDI.

Manual:
    - PRIMERO QUE TODO VER SI HAY EN LA COLUMNA MONEDA USD. Si la fila es USD,
      la PRIMA y el PREMIO inicialmente figuran en USD y hay que pasarlos a
      pesos.
    - El tipo de cambio efectivo se calcula con la comisión: viene en dos
      columnas, COMISION (MONEDA CTE) en pesos y COMISION (MONEDA EMISION) en
      USD. TC_fila = pesos / usd.
    - POLIZA = "POLIZA" (NO "Sup. Poliza")
    - ASEGURADO = "ASEGURADO"
    - SECCION = "NOMBRE RAMA"
    - TIPO = "PR" siempre
    - COMISION = "COMISION EN MONEDA CTE" (ya en pesos, no convertir)
    - PRIMA = "PRIMA PROPORCIONAL" * TC si USD, sino tal cual
    - PREMIO = "PREMIO" * TC si USD, sino tal cual
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

COMPANY = "HDI"


def _is_usd(moneda_value) -> bool:
    n = normalize(moneda_value)
    if not n:
        return False
    return any(tok in n for tok in ("USD", "U$S", "U$D", "DOLAR", "DOL", "U$"))


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="hdi", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw,
        [
            "POLIZA",
            "ASEGURADO",
            "NOMBRE RAMA",
            "MONEDA",
            "PRIMA PROPORCIONAL",
            "PREMIO",
            "COMISION",
        ],
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    log.debug("HDI columnas: %s", columns)

    # OJO con "Sup. Poliza" — el manual remarca que NO es la póliza.
    poliza_candidates = [c for c in columns if normalize(c) == "POLIZA"]
    if poliza_candidates:
        c_pol = poliza_candidates[0]
    else:
        # find_col() podría matchear "Sup. Poliza"; lo evitamos explícitamente
        c_pol = None
        for c in columns:
            nc = normalize(c)
            if "POLIZA" in nc and not nc.startswith("SUP"):
                c_pol = c
                break

    c_aseg = find_col(columns, "ASEGURADO")
    c_rama = find_col(columns, "NOMBRE RAMA", "RAMA")
    c_moneda = find_col(columns, "MONEDA")
    c_prima = find_col(columns, "PRIMA PROPORCIONAL", "PRIMA PROPORC", "PRIMA")
    c_premio = find_col(columns, "PREMIO")
    c_com_cte = find_col(
        columns,
        "COMISION EN MONEDA CTE",
        "COMISION MONEDA CTE",
        "COMISION CTE",
        "COM MONEDA CTE",
        "EN MONEDA CTE",
    )
    c_com_emi = find_col(
        columns,
        "COMISION EN MONEDA EMISION",
        "COMISION MONEDA EMISION",
        "COMISION EMISION",
        "COM MONEDA EMISION",
        "EN MONEDA EMISION",
    )

    if not all([c_pol, c_aseg, c_rama, c_prima, c_premio, c_com_cte]):
        reject(
            result,
            Path(file_path).name,
            f"Columnas insuficientes: {columns}",
            source_sheet=sheet_name,
        )
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza = safe_str(row[c_pol])
        if not poliza or poliza == "0":
            continue
        source_row = idx + header_row + 2

        com_cte = to_float(row[c_com_cte])
        prima_v = to_float(row[c_prima])
        premio_v = to_float(row[c_premio])

        moneda_val = row[c_moneda] if c_moneda is not None else ""
        if _is_usd(moneda_val):
            # TC fila = comision_pesos / comision_usd
            com_emi = to_float(row[c_com_emi]) if c_com_emi is not None else None
            tc = None
            if com_cte is not None and com_emi not in (None, 0):
                tc = com_cte / com_emi
            if tc is None or tc <= 0:
                # TODO confirmar con cliente: cómo manejar USD sin pareja de
                # comisión para deducir el TC. Por ahora rechazamos.
                reject(
                    result,
                    fname,
                    "USD sin par de comisión (MONEDA CTE / EMISION) para deducir TC",
                    source_sheet=sheet_name,
                    source_row=source_row,
                    compania=COMPANY,
                    raw=row.to_dict(),
                )
                continue
            if prima_v is not None:
                prima_v = prima_v * tc
            if premio_v is not None:
                premio_v = premio_v * tc

        try:
            rec = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_aseg],
                seccion=row[c_rama],
                compania=COMPANY,
                tipo="PR",
                comisiones=com_cte,
                prima=prima_v,
                premio=premio_v,
                source_file=fname,
                source_sheet=sheet_name,
                source_row=source_row,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("HDI fila %s: %s", idx, exc)
            reject(
                result,
                fname,
                f"Error: {exc}",
                source_sheet=sheet_name,
                source_row=source_row,
                raw=row.to_dict(),
            )
    return result
