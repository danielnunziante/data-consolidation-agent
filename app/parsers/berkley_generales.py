"""Parser de BERKLEY GENERALES - PDF (archivo "BERKLEY INT ...").

Liquidación de comisiones en texto plano. Cada movimiento es una línea:

    17 37480 8 DEHEZA 2071, CONS DE PROP CA 1,000000 1.072,17 1.065,78 CBU 234,14 0,00
    ^rgo ^póliza ^sup ^asegurado          ^pv ^cotiz  ^premio  ^prima   ^fpago ^com.venta ^com.cobranza

Mapeo (validado contra la consolidación manual ABRIL 2026):
    - POLIZA = póliza, ASEGURADO = texto intermedio.
    - SECCION = ramo mapeado (17 -> VIDA); fallback: nro de ramo.
    - TIPO = "PR", COMISION = comisión por venta,
      PRIMA = prima proporcional, PREMIO = premio cobrado.

Se mantiene el camino por tablas para layouts viejos.
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

COMPANY = "BERKLEY GENERALES"
DEFAULT_SECCION = "CAUCION"

# Ramos conocidos (de la consolidación manual del cliente).
RAMO_SECCION = {
    "17": "VIDA",
}

_LINE_RE = re.compile(
    r"^(?P<rgo>\d{1,3})\s+(?P<poliza>\d{3,})\s+(?P<sup>\d+)\s+(?P<aseg>.+?)\s+"
    r"(?P<pv>[A-Z]{1,3})\s+(?P<cotiz>[\d\.,]+)\s+(?P<premio>-?[\d\.,]+)\s+"
    r"(?P<prima>-?[\d\.,]+)\s+(?P<fpago>\S+)\s+(?P<com_vta>-?[\d\.,]+)\s+(?P<com_cob>-?[\d\.,]+)\s*$"
)


def _parse_text_lines(result: ParseResult, text_lines: list[str], fecha: date, fname: str) -> bool:
    found = False
    for n, line in enumerate(text_lines, start=1):
        s = line.strip()
        if not s or normalize(s).startswith("TOTAL"):
            continue
        m = _LINE_RE.match(s)
        if not m:
            continue
        try:
            rec = make_record(
                fecha=fecha,
                poliza=m.group("poliza"),
                asegurado=m.group("aseg"),
                seccion=RAMO_SECCION.get(m.group("rgo"), m.group("rgo")),
                compania=COMPANY,
                tipo="PR",
                comisiones=to_float(m.group("com_vta")),
                prima=to_float(m.group("prima")),
                premio=to_float(m.group("premio")),
                source_file=fname,
                source_row=n,
            )
            result.records.append(rec)
            found = True
        except Exception as exc:
            log.warning("BERKLEY GRALES línea %s: %s", n, exc)
            reject(result, fname, f"Error línea: {exc}", source_row=n, raw=s)
    return found


def _find_header_idx(table: list[list[str]]) -> int | None:
    for i, row in enumerate(table):
        joined = normalize(" ".join(safe_str(c) for c in row))
        if "POLIZA" in joined and "ASEGURADO" in joined:
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
    result = ParseResult(parser_name="berkley_generales", source_file=file_path)
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

    found_any = _parse_text_lines(result, text_lines, fecha, fname)
    if found_any:
        return result
    for table in tables_all:
        hdr = _find_header_idx(table)
        if hdr is None:
            continue
        headers = table[hdr]
        i_pol = _col_index(headers, "POLIZA")
        i_aseg = _col_index(headers, "ASEGURADO")
        i_sec = _col_index(headers, "SECCION", "RAMO", "RAMA")
        i_com = _col_index(headers, "COMISION POR VTA", "COMISION")
        i_prima = _col_index(headers, "PRIMA PROPORC", "PRIMA PROPORCIONAL", "PRIMA")
        i_premio = _col_index(headers, "PREMIO COBRADO", "PREMIO")
        if None in (i_pol, i_aseg, i_com, i_prima, i_premio):
            continue

        for r_i, row in enumerate(table[hdr + 1 :], start=hdr + 2):
            poliza = safe_str(row[i_pol]) if i_pol < len(row) else ""
            asegurado = safe_str(row[i_aseg]) if i_aseg < len(row) else ""
            if not poliza or normalize(poliza).startswith("TOTAL"):
                continue
            if not asegurado:
                continue
            seccion = safe_str(row[i_sec]) if (i_sec is not None and i_sec < len(row)) else ""
            if not seccion:
                seccion = DEFAULT_SECCION
            com_v = to_float(row[i_com]) if i_com < len(row) else None
            prima_v = to_float(row[i_prima]) if i_prima < len(row) else None
            premio_v = to_float(row[i_premio]) if i_premio < len(row) else None
            if com_v is None or prima_v is None:
                continue
            try:
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=asegurado,
                    seccion=seccion,
                    compania=COMPANY,
                    tipo="PR",
                    comisiones=com_v,
                    prima=prima_v,
                    premio=premio_v if premio_v is not None else prima_v,
                    source_file=fname,
                    source_row=r_i,
                )
                result.records.append(rec)
                found_any = True
            except Exception as exc:
                log.warning("BERKLEY GRALES fila %s: %s", r_i, exc)
                reject(result, fname, f"Error fila: {exc}", source_row=r_i, raw=row)

    if not found_any and not result.rejected:
        # TODO confirmar con cliente: revisar layout real cuando llegue el primer PDF.
        reject(
            result,
            fname,
            "No se encontraron filas válidas en el PDF (probablemente requiere carga manual)",
        )
    return result
