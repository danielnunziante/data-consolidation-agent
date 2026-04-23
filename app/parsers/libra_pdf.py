"""Parser de LIBRA SEGUROS - PDF texto estructurado.

El PDF tiene líneas del tipo:
  04/03/2026 1 4 1707326 0 CAMPIÑO, VERONICA VALERIA 02 $ Normal 4,516.59 1.00 18,819.12 28,369.57 4,516.59 0.00 4,516.59
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pdfplumber

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import safe_str
from .base_parser import log, make_record, reject

COMPANY = "LIBRA SEGUROS"


_HEAD_RE = re.compile(
    r"^\s*(?P<fecha>\d{2}/\d{2}/\d{4})\s+"
    r"\d+\s+"  # Suc
    r"(?P<ramo>\d+)\s+"
    r"(?P<poliza>\d+)\s+"
    r"\d+\s+"  # End
    r"(?P<tomador>.+?)\s+"
    r"(?P<pr>\d{2})\s+"
    r"\$\s+"
    r"(?P<tipo>\S+)\s+"
    r"(?P<rest>.+)$"
)
_NUM_RE = re.compile(r"[\-\d][\-\d\.,]*")


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="libra_pdf", source_file=file_path)
    fname = Path(file_path).name

    try:
        with pdfplumber.open(file_path) as pdf:
            all_text_lines: list[tuple[int, str]] = []
            for p_i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                for line in text.splitlines():
                    all_text_lines.append((p_i + 1, line))
    except Exception as exc:
        reject(result, fname, f"Error leyendo PDF: {exc}")
        return result

    # Los tomadores a veces se parten en dos líneas; si la línea siguiente es texto
    # sin números al final, lo concatenamos antes de intentar la regex.
    coalesced: list[tuple[int, str]] = []
    i = 0
    while i < len(all_text_lines):
        page_no, line = all_text_lines[i]
        stripped = line.strip()
        if re.match(r"^\d{2}/\d{2}/\d{4}\s", stripped):
            # Si queda línea siguiente tipo extensión del nombre, la pegamos
            if i + 1 < len(all_text_lines):
                nxt = all_text_lines[i + 1][1].strip()
                if nxt and not re.match(r"^\d{2}/\d{2}/\d{4}\s", nxt) and not re.search(r"\d+[\.,]\d{2}\s+\d+[\.,]\d{2}", nxt):
                    # nxt es un trozo de nombre
                    stripped = stripped + " " + nxt
                    coalesced.append((page_no, stripped))
                    i += 2
                    continue
        coalesced.append((page_no, stripped))
        i += 1

    for page_no, line in coalesced:
        m = _HEAD_RE.match(line)
        if not m:
            continue
        numbers = _NUM_RE.findall(m.group("rest"))
        # Asignamos desde la derecha: [... ComPR (ComME) Cambio Prima Premio ComMon Debe Haber]
        # Mínimo esperado: 7 números. Si no alcanza, es una línea de retención u otro tipo.
        if len(numbers) < 7:
            continue
        try:
            prima = to_float(numbers[-5])
            premio = to_float(numbers[-4])
            com_pr = to_float(numbers[0])  # primera columna siempre es la comisión
            rec = make_record(
                fecha=fecha,
                poliza=m.group("poliza"),
                asegurado=safe_str(m.group("tomador")),
                seccion=m.group("ramo"),
                compania=COMPANY,
                tipo="PR",
                comisiones=com_pr,
                prima=prima,
                premio=premio,
                source_file=fname,
                source_sheet=f"page{page_no}",
                source_row=None,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("LIBRA fila: %s", exc)
            reject(result, fname, f"Error línea: {exc}", source_sheet=f"page{page_no}", raw=line)
    return result
