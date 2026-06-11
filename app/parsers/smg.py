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
    # Algunos archivos cambian "Imp_comis_normal_eq" por "Imp_comis_normal".
    c_com = find_col(columns, "Imp_comis_normal_eq", "Imp_comis_normal")
    c_prima = find_col(columns, "Imp_prima")
    c_premio = find_col(columns, "Imp_premio")
    c_com_cob = find_col(columns, "Comision_cobranzas")
    c_moneda = find_col(columns, "Cod_moneda", "CodMoneda", "Moneda")
    c_endoso = find_col(columns, "Endoso", "Nro_endoso", "Cod_endoso")
    c_femision = find_col(columns, "F_emision", "Fecha_emision", "Fecha emision")

    if not all([c_pol, c_nom, c_ramo, c_com, c_prima, c_premio]):
        reject(result, Path(file_path).name, f"Columnas insuficientes: {columns}", source_sheet=sheet_name)
        return result

    # Dedup USD. Las pólizas en dólares vienen duplicadas:
    # a) Par USD/pesos con el MISMO recibo y la misma comisión, ambas filas
    #    con Cod_moneda == 1: una trae los importes en USD y la otra ya
    #    convertidos a pesos. Se conserva sólo la de pesos (mayor |prima|).
    # b) (histórico) fila USD duplicada de una fila en pesos (Cod_moneda != 1)
    #    de la misma póliza: se descartan las USD.
    drop_indices: set = set()
    c_recibo = find_col(columns, "Nro_recibo", "Recibo")
    if c_moneda is not None:
        def _pol_key(r) -> str:
            return safe_str(r[c_pol])

        # a) pares USD/pesos dentro del mismo recibo
        grupos: dict[tuple, list] = {}
        if c_recibo is not None:
            for idx, row in df.iterrows():
                if to_float(row[c_moneda]) != 1:
                    continue
                key = (
                    _pol_key(row),
                    safe_str(row[c_recibo]),
                    safe_str(row[c_com]),
                )
                grupos.setdefault(key, []).append(idx)
            for key, idxs in grupos.items():
                if len(idxs) < 2:
                    continue
                primas = {i: abs(to_float(df.loc[i, c_prima]) or 0.0) for i in idxs}
                keep = max(primas, key=primas.get)
                for i in idxs:
                    if i != keep:
                        drop_indices.add(i)

        # b) USD duplicadas de filas en pesos de la misma póliza
        polizas_con_pesos: set = set()
        for idx, row in df.iterrows():
            mon_v = to_float(row[c_moneda])
            if mon_v != 1:
                polizas_con_pesos.add(_pol_key(row))

        for idx, row in df.iterrows():
            if idx in drop_indices:
                continue
            mon_v = to_float(row[c_moneda])
            if mon_v == 1 and _pol_key(row) in polizas_con_pesos:
                # Si la fila sobrevivió al dedup por par (es la copia en pesos
                # de su recibo), no la tocamos.
                if c_recibo is not None:
                    key = (
                        _pol_key(row),
                        safe_str(row[c_recibo]),
                        safe_str(row[c_com]),
                    )
                    if len(grupos.get(key, [])) >= 2:
                        continue
                drop_indices.add(idx)

    fname = Path(file_path).name
    for idx, row in df.iterrows():
        if idx in drop_indices:
            continue
        poliza = safe_str(row[c_pol])
        if not poliza or poliza == "0":
            continue
        source_row = idx + header_row + 2
        com_v = to_float(row[c_com])
        prima_v = to_float(row[c_prima])
        premio_v = to_float(row[c_premio])
        try:
            rec_pr = make_record(
                fecha=fecha,
                poliza=poliza,
                asegurado=row[c_nom],
                seccion=row[c_ramo],
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
