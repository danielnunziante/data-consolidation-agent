"""Parser de BERKLEY ART - PDF.

Manual: "ES UN PDF así que son pocos movimientos y saco los datos a mano".
Implementamos un best-effort por tablas + regex; si el PDF viene escaneado o
los datos no matchean, las filas se mandan a rejected con razón clara.

Reglas:
    - POLIZA = "NRO CONTRATO"
    - ASEGURADO = "RAZON SOCIAL"
    - SECCION = "A.R.T."
    - TIPO = "PR" siempre
    - COMISION = "$ COMISION" / 1.21 (quitar IVA)
    - PRIMA = "RECAUDADO"
    - PREMIO = "RECAUDADO"
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pdfplumber

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import normalize, safe_str
from .base_parser import log, make_record, reject

COMPANY = "BERKLEY ART"
SECCION = "A.R.T."

_HEADER_TOKENS = ("NRO CONTRATO", "RAZON SOCIAL", "RECAUDADO", "COMISION")
_CUIT_RE = re.compile(r"\d{2}-?\d{8}-?\d")


def _find_header_idx(table: list[list[str]]) -> int | None:
    for i, row in enumerate(table):
        joined = normalize(" ".join(safe_str(c) for c in row))
        if all(tok in joined for tok in ("NRO CONTRATO", "RAZON")):
            return i
    return None


def _col_index(headers: list[str], *candidates: str) -> int | None:
    norm = [normalize(h) for h in headers]
    for cand in candidates:
        n = normalize(cand)
        for i, h in enumerate(norm):
            if n and (n == h or n in h):
                return i
    return None


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="berkley_art", source_file=file_path)
    fname = Path(file_path).name

    try:
        with pdfplumber.open(file_path) as pdf:
            tables_all: list[list[list[str]]] = []
            text_lines: list[str] = []
            for page in pdf.pages:
                for t in page.extract_tables() or []:
                    tables_all.append([[safe_str(c) for c in r] for r in t])
                txt = page.extract_text() or ""
                text_lines.extend(txt.splitlines())
    except Exception as exc:
        reject(result, fname, f"Error leyendo PDF: {exc}")
        return result

    found_any = False
    for table in tables_all:
        hdr = _find_header_idx(table)
        if hdr is None:
            continue
        headers = table[hdr]
        i_pol = _col_index(headers, "NRO CONTRATO", "CONTRATO")
        i_aseg = _col_index(headers, "RAZON SOCIAL", "RAZON")
        i_recaud = _col_index(headers, "RECAUDADO")
        i_com = _col_index(headers, "$ COMISION", "COMISION")
        if None in (i_pol, i_aseg, i_recaud, i_com):
            continue
        for r_i, row in enumerate(table[hdr + 1 :], start=hdr + 2):
            poliza = safe_str(row[i_pol]) if i_pol < len(row) else ""
            asegurado = safe_str(row[i_aseg]) if i_aseg < len(row) else ""
            if not poliza or normalize(poliza).startswith("TOTAL"):
                continue
            if not asegurado:
                continue
            recaudado = to_float(row[i_recaud]) if i_recaud < len(row) else None
            comision_bruta = to_float(row[i_com]) if i_com < len(row) else None
            if comision_bruta is None or recaudado is None:
                continue
            try:
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=asegurado,
                    seccion=SECCION,
                    compania=COMPANY,
                    tipo="PR",
                    comisiones=comision_bruta / 1.21,
                    prima=recaudado,
                    premio=recaudado,
                    source_file=fname,
                    source_row=r_i,
                )
                result.records.append(rec)
                found_any = True
            except Exception as exc:
                log.warning("BERKLEY ART fila %s: %s", r_i, exc)
                reject(result, fname, f"Error fila: {exc}", source_row=r_i, raw=row)

    if not found_any and not result.rejected:
        # TODO confirmar con cliente: si el PDF no tiene tablas extraíbles
        # (escaneado o layout libre), el manual sugiere cargar a mano.
        reject(
            result,
            fname,
            "No se encontraron filas válidas en el PDF (probablemente requiere carga manual)",
        )
    return result
