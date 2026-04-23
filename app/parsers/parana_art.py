"""Parser de PARANA ART - PDF."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pdfplumber

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import safe_str
from .base_parser import log, make_record, reject

COMPANY = "PARANA ART"
SECCION = "A.R.T."


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="parana_art", source_file=file_path)
    fname = Path(file_path).name
    try:
        with pdfplumber.open(file_path) as pdf:
            tables_all = []
            for page in pdf.pages:
                for t in page.extract_tables() or []:
                    tables_all.append(t)
    except Exception as exc:
        reject(result, fname, f"Error leyendo PDF: {exc}")
        return result

    # Buscamos la tabla de liquidación: sus filas tienen CUIT (11 dígitos) + varias columnas numéricas
    for table in tables_all:
        for row in table:
            cells = [safe_str(c) for c in row if safe_str(c)]
            if len(cells) < 6:
                continue
            cuit = cells[0]
            if not re.fullmatch(r"\d{11}", cuit):
                continue
            # Intentamos mapear posiciones conocidas (según exploración):
            # [0]=CUIT, [1]=Razon Social, [2]=Fecha, [3]=Periodo,
            # [4]=Importe Cobrado Vep, [5]=PD, [6]=Vigencia, [7]=PAS,
            # [8]=Tasa, [9]=ORG%, [10]=Super, [11]=Osseg, [12]=FFEP,
            # [13]=Prima Cobrada, [14]=Comision PAS, [15]=Comision ORG
            try:
                asegurado = cells[1]
                poliza = cells[5] if len(cells) > 5 else ""
                prima = to_float(cells[13]) if len(cells) > 13 else None
                comis_pas = to_float(cells[14]) if len(cells) > 14 else None
                if not poliza or not prima or not comis_pas:
                    continue
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=asegurado,
                    seccion=SECCION,
                    compania=COMPANY,
                    tipo="PR",
                    comisiones=comis_pas,
                    prima=prima,
                    premio=prima,
                    source_file=fname,
                )
                result.records.append(rec)
            except Exception as exc:
                log.warning("PARANA fila: %s", exc)
                reject(result, fname, f"Error fila: {exc}", raw=row)
    if not result.records and not result.rejected:
        reject(result, fname, "No se encontraron filas válidas en el PDF de PARANA")
    return result
