"""Parser de AGC (Aseguradora de Créditos y Garantías) -> compañía "ACG".

PDF de liquidación de comisiones en texto plano. Cada movimiento:

    CUZZUOL S.R.L. 14/05/2026 0004-02235560 1630746 3 Prod 133.664,05 1,00 $ 33.416,01 33.416,01
    ^asegurado     ^feccobro  ^factura      ^póliza ^end ^rol ^primaprop ^tc ^mon ^importeMO ^importeMN

Mapeo (validado contra la consolidación manual MAYO 2026):
- POLIZA = póliza, ASEGURADO = descripción, SECCION = "CAUCION", TIPO = PR.
- COMISIONES = ImporteMN (pesos), PRIMA = PrimaProp * T.C., PREMIO = PRIMA * 1.40.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pdfplumber

from ..models import ParseResult
from ..utils.numbers import round2, to_float
from ..utils.strings import normalize
from .base_parser import log, make_record, reject

COMPANY = "ACG"
SECCION = "CAUCION"

_LINE_RE = re.compile(
    r"^(?P<aseg>.+?)\s+(?P<fec>\d{1,2}/\d{1,2}/\d{4})\s+(?P<fact>\S+)\s+"
    r"(?P<pol>\d+)\s+(?P<endoso>\d+)\s+(?P<rol>\S+)\s+(?P<prima>-?[\d\.,]+)\s+"
    r"(?P<tc>[\d\.,]+)\s+(?P<mon>\S+)\s+(?P<impmo>-?[\d\.,]+)\s+(?P<impmn>-?[\d\.,]+)\s*$"
)


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="agc_pdf", source_file=file_path)
    fname = Path(file_path).name

    try:
        with pdfplumber.open(file_path) as pdf:
            lines: list[str] = []
            for page in pdf.pages:
                txt = page.extract_text() or ""
                lines.extend(txt.splitlines())
    except Exception as exc:
        reject(result, fname, f"Error leyendo PDF: {exc}")
        return result

    for n, line in enumerate(lines, start=1):
        s = line.strip()
        if not s or normalize(s).startswith("TOTAL"):
            continue
        m = _LINE_RE.match(s)
        if not m:
            continue
        prima = to_float(m.group("prima"))
        tc = to_float(m.group("tc")) or 1.0
        if prima is not None and tc and tc != 1.0:
            prima = prima * tc
        premio = round2(prima * 1.40) if prima is not None else None
        try:
            rec = make_record(
                fecha=fecha,
                poliza=m.group("pol"),
                asegurado=m.group("aseg"),
                seccion=SECCION,
                compania=COMPANY,
                tipo="PR",
                comisiones=to_float(m.group("impmn")),
                prima=round2(prima),
                premio=premio,
                source_file=fname,
                source_row=n,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("ACG línea %s: %s", n, exc)
            reject(result, fname, f"Error línea: {exc}", source_row=n, raw=s)

    if not result.records and not result.rejected:
        reject(result, fname, "No se encontraron filas válidas en el PDF")
    return result
