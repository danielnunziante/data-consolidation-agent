"""Parser de SANCOR - hojas 152526 (IND) y 213871 (PR + AY)."""
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

COMPANY = "SANCOR"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="sancor", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    fname = Path(file_path).name

    known_sheets = {"152526", "213871"}
    for sheet_name, df_raw in sheets.items():
        clean = sheet_name.strip()
        if clean not in known_sheets:
            # TODO confirmar con cliente: aparecieron hojas nuevas en SANCOR
            # ("ME APARECIO UNA SOLAPA MAS"). Intentamos procesarla como
            # 213871 (PR+AY) si la estructura coincide; si no, rechazamos.
            log.info(
                "SANCOR hoja desconocida: %s — intentando procesar como 213871",
                sheet_name,
            )

        header_row = detect_header_row(
            df_raw, ["Nro Oficial Poliza", "Denominacion Cliente", "Ramo", "Comision", "Prima Unif"]
        )
        if header_row is None:
            if clean in known_sheets:
                reject(result, fname, "No se detectó cabecera", source_sheet=sheet_name)
            else:
                reject(
                    result,
                    fname,
                    "Hoja desconocida sin estructura reconocida",
                    source_sheet=sheet_name,
                )
            continue
        df = slice_as_dataframe(df_raw, header_row)

        columns = list(df.columns)
        c_pol = find_col(columns, "Nro Oficial Poliza")
        c_aseg = find_col(columns, "Denominacion Cliente")
        c_ramo = find_col(columns, "Ramo")
        c_com = find_col(columns, "Comision")
        c_adic_extra = find_col(columns, "Adic Extra Red")
        c_adic_cob = find_col(columns, "Adic Cobranza")
        c_prima_unif = find_col(columns, "Prima Unif")
        c_premio_cap = find_col(columns, "Premio Cap")

        if not all([c_pol, c_aseg, c_ramo, c_com]):
            reject(result, fname, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
            continue

        # Para hojas desconocidas que sí matchearon la estructura, las tratamos
        # como 213871 (PR + AY) que es el formato general.
        sheet_kind = clean if clean in known_sheets else "213871"
        for idx, row in df.iterrows():
            poliza = safe_str(row[c_pol])
            if poliza.lower() in {"nan", ""}:
                continue
            ramo = row[c_ramo]
            aseg = row[c_aseg]
            source_row = idx + header_row + 2

            if sheet_kind == "152526":
                comision = to_float(row[c_com])
                if (comision is None or comision == 0) and c_adic_extra:
                    comision = to_float(row[c_adic_extra])
                if comision is None:
                    continue
                if comision == 0:
                    continue
                try:
                    rec = make_record(
                        fecha=fecha,
                        poliza=poliza,
                        asegurado=aseg,
                        seccion=ramo,
                        compania=COMPANY,
                        tipo="IND",
                        comisiones=comision,
                        prima=None,
                        premio=None,
                        source_file=fname,
                        source_sheet=sheet_name,
                        source_row=source_row,
                    )
                    result.records.append(rec)
                except Exception as exc:
                    log.warning("SANCOR 152526 fila %s: %s", idx, exc)
                    reject(result, fname, f"Error IND: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())
            elif sheet_kind == "213871":
                com_v = to_float(row[c_com])
                prima_v = to_float(row[c_prima_unif]) if c_prima_unif else None
                premio_v = to_float(row[c_premio_cap]) if c_premio_cap else None
                # fila PR siempre
                try:
                    rec_pr = make_record(
                        fecha=fecha,
                        poliza=poliza,
                        asegurado=aseg,
                        seccion=ramo,
                        compania=COMPANY,
                        tipo="PR",
                        comisiones=com_v,
                        prima=prima_v,
                        premio=premio_v,
                        source_file=fname,
                        source_sheet=sheet_name,
                        source_row=source_row,
                    )
                    result.records.append(rec_pr)
                except Exception as exc:
                    log.warning("SANCOR 213871 PR fila %s: %s", idx, exc)
                    reject(result, fname, f"Error PR: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())
                # fila AY si Adic Cobranza != 0
                adic_cob = to_float(row[c_adic_cob]) if c_adic_cob else 0.0
                if adic_cob and adic_cob != 0:
                    try:
                        rec_ay = make_record(
                            fecha=fecha,
                            poliza=poliza,
                            asegurado=aseg,
                            seccion=ramo,
                            compania=COMPANY,
                            tipo="AY",
                            comisiones=adic_cob,
                            prima=None,
                            premio=None,
                            source_file=fname,
                            source_sheet=sheet_name,
                            source_row=source_row,
                        )
                        result.records.append(rec_ay)
                    except Exception as exc:
                        log.warning("SANCOR 213871 AY fila %s: %s", idx, exc)
                        reject(result, fname, f"Error AY: {exc}", source_sheet=sheet_name, source_row=source_row, raw=row.to_dict())
    return result
