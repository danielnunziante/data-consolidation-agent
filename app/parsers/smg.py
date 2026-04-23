"""Parser de SMG (CuentaCorriente)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import to_float
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

COMPANY = "SMG"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="smg", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    sheet_name = next(iter(sheets))
    df_raw = sheets[sheet_name]

    header_row = detect_header_row(df_raw, ["Nro_pol", "Txt_nombre", "Imp_prima", "Imp_premio", "Cod_ramo"])
    if header_row is None:
        reject(result, Path(file_path).name, "No se detectó cabecera", source_sheet=sheet_name)
        return result
    df = slice_as_dataframe(df_raw, header_row)

    columns = list(df.columns)
    c_pol = find_col(columns, "Nro_pol")
    c_nom = find_col(columns, "Txt_nombre")
    c_ramo = find_col(columns, "Cod_ramo")
    c_com = find_col(columns, "Imp_comis_normal_eq")
    c_prima = find_col(columns, "Imp_prima")
    c_premio = find_col(columns, "Imp_premio")
    c_com_cob = find_col(columns, "Comision_cobranzas")

    if not all([c_pol, c_nom, c_ramo, c_com, c_prima, c_premio]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        poliza = safe_str(row[c_pol])
        if not poliza or poliza == "0":
            continue
        source_row = idx + header_row + 2
        try:
            rec_pr = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_nom],
                seccion=row[c_ramo],
                compania=COMPANY,
                tipo="PR",
                comisiones=row[c_com],
                prima=row[c_prima],
                premio=row[c_premio],
                source_file=fname,
                source_sheet=sheet_name,
                source_row=source_row,
            )
            result.records.append(rec_pr)
        except Exception as exc:
            log.warning("SMG PR fila %s: %s", idx, exc)
            reject(result, fname, f"Error PR: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())
            continue

        cob = to_float(row[c_com_cob]) if c_com_cob else 0.0
        if cob and cob != 0:
            try:
                rec_ay = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=row[c_nom],
                    seccion=row[c_ramo],
                    compania=COMPANY,
                    tipo="AY",
                    comisiones=cob,
                    prima=None,
                    premio=None,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=source_row,
                )
                result.records.append(rec_ay)
            except Exception as exc:
                log.warning("SMG AY fila %s: %s", idx, exc)
                reject(result, fname, f"Error AY: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())
    return result
