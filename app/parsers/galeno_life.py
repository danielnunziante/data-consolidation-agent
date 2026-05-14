"""Parser de GALENO LIFE."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import safe_str, strip_leading_zeros
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)

COMPANY = "GALENO LIFE"


def _clean_poliza(value) -> str:
    s = safe_str(value)
    # Contrato/Póliza viene con rama separada por '-' o formato 170XXXXXX
    # Conservamos la porción numérica principal quitando ceros a la izquierda.
    s = s.replace(",", "").strip()
    m = re.search(r"\d+", s)
    if m:
        return strip_leading_zeros(m.group(0))
    return s


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="galeno_life", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(
        df_raw,
        ["Contrato/Póliza", "Cliente", "Importe Cobranzas", "Comisión Legajo"],
    )
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    c_pol = find_col(list(df.columns), "Contrato/Póliza", "Contrato/Poliza", "Póliza", "Poliza")
    c_prod = find_col(list(df.columns), "Producto")
    c_aseg = find_col(list(df.columns), "Cliente/Razón Social", "Cliente")
    c_imp = find_col(list(df.columns), "Importe Cobranzas")
    c_com = find_col(list(df.columns), "Comisión Legajo", "Comision Legajo")
    c_com_org = find_col(list(df.columns), "Comis Organizador", "Comision Organizador", "Comisión Organizador")

    if not all([c_pol, c_aseg, c_imp, c_com]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {list(df.columns)}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza = _clean_poliza(row[c_pol])
        if not poliza:
            continue
        source_row = idx + header_row + 2
        prima = to_float(row[c_imp])
        premio = prima * 1.40 if prima is not None else None
        com_pr = to_float(row[c_com])
        com_org = to_float(row[c_com_org]) if c_com_org else None

        # Manual: si están las dos columnas -> PR + AY. Si solo Comis Organizador -> IND.
        # TODO confirmar con cliente: criterio cuando ambas comisiones aparecen pero alguna es 0.
        try:
            if com_pr is not None and com_pr != 0:
                rec_pr = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=row[c_aseg],
                    seccion=row[c_prod] if c_prod else "",
                    compania=COMPANY,
                    tipo="PR",
                    comisiones=com_pr,
                    prima=prima,
                    premio=premio,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=source_row,
                )
                result.records.append(rec_pr)
                if com_org is not None and com_org != 0:
                    rec_ay = make_record(
                        fecha=fecha,
                        poliza=poliza,
                        asegurado=row[c_aseg],
                        seccion=row[c_prod] if c_prod else "",
                        compania=COMPANY,
                        tipo="AY",
                        comisiones=com_org,
                        prima=None,
                        premio=None,
                        source_file=fname,
                        source_sheet=sheet_name,
                        source_row=source_row,
                    )
                    result.records.append(rec_ay)
            elif com_org is not None and com_org != 0:
                rec_ind = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=row[c_aseg],
                    seccion=row[c_prod] if c_prod else "",
                    compania=COMPANY,
                    tipo="IND",
                    comisiones=com_org,
                    prima=None,
                    premio=None,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=source_row,
                )
                result.records.append(rec_ind)
            else:
                # ninguna columna trae comisión, dejamos el comportamiento
                # original (PR con comisión vacía) para no perder la fila.
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=row[c_aseg],
                    seccion=row[c_prod] if c_prod else "",
                    compania=COMPANY,
                    tipo="PR",
                    comisiones=com_pr,
                    prima=prima,
                    premio=premio,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=source_row,
                )
                result.records.append(rec)
        except Exception as exc:
            log.warning("GALENO LIFE fila %s: %s", idx, exc)
            reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())
    return result
