"""Parser de PREVENCION ART - hoja 152526 (AY) y 213871 (PR)."""
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

COMPANY = "PREVENCION ART"
SECCION = "A.R.T."

SHEET_TIPO = {"152526": "AY", "213871": "PR"}


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="prevencion_art", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    fname = Path(file_path).name

    for sheet_name, df_raw in sheets.items():
        tipo = SHEET_TIPO.get(sheet_name.strip())
        if tipo is None:
            continue

        header_row = detect_header_row(
            df_raw,
            ["Contrato", "DenominaciónCliente", "Denominacion Cliente", "ImporteBase", "ImporteComisión"],
        )
        if header_row is None:
            reject(result, fname, "No se detectó cabecera", source_sheet=sheet_name)
            continue
        df = slice_as_dataframe(df_raw, header_row)

        columns = list(df.columns)
        c_contr = find_col(columns, "Contrato")
        c_aseg = find_col(columns, "DenominaciónCliente", "Denominación Cliente", "Denominacion Cliente")
        c_imp_com = find_col(columns, "ImporteComisión", "Importe Comision", "Importe Comisión")
        c_imp_base = find_col(columns, "ImporteBase", "Importe Base")

        if not all([c_contr, c_aseg, c_imp_com]):
            reject(result, fname, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
            continue

        for idx, row in df.iterrows():
            poliza = safe_str(row[c_contr])
            if not poliza or poliza.lower() == "nan":
                continue
            com_bruto = to_float(row[c_imp_com])
            comisiones = com_bruto / 1.21 if com_bruto is not None else None

            if tipo == "PR":
                prima = row[c_imp_base] if c_imp_base else None
                premio = row[c_imp_base] if c_imp_base else None
            else:
                prima = None
                premio = None

            try:
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=row[c_aseg],
                    seccion=SECCION,
                    compania=COMPANY,
                    tipo=tipo,
                    comisiones=comisiones,
                    prima=prima,
                    premio=premio,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=idx + header_row + 2,
                )
                result.records.append(rec)
            except Exception as exc:
                log.warning("PREVENCION ART fila %s: %s", idx, exc)
                reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())

    return result
