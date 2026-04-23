"""Parser de VICTORIA ART - PDF.

El PDF viene rotado y en muchos casos sin texto extraíble (escaneado).
Si no se puede extraer texto con `pdfplumber`, el archivo se marca como
skipped y cada fila se reporta en rejected_rows.
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

COMPANY = "VICTORIA ART"
SECCION = "A.R.T."


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="victoria_art_pdf", source_file=file_path)
    fname = Path(file_path).name

    lines: list[str] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines.extend(text.splitlines())
                # intentamos también extraer palabras con distintas orientaciones
                if not text.strip():
                    words = page.extract_words(extra_attrs=["upright"]) or []
                    if words:
                        lines.append(" ".join(safe_str(w.get("text")) for w in words))
    except Exception as exc:
        reject(result, fname, f"Error leyendo PDF: {exc}")
        return result

    total_text = "\n".join(lines).strip()
    if not total_text:
        reject(
            result,
            fname,
            "PDF sin texto extraíble (probablemente escaneado). Requiere OCR.",
        )
        return result

    # Heurística: buscar líneas que contengan póliza + importes
    line_re = re.compile(
        r"^(?P<poliza>\d{4,})\s+(?P<resto>.+?)\s+(?P<prima>[\-\d\.,]+)\s+(?P<comis>[\-\d\.,]+)\s*$"
    )
    for line in lines:
        m = line_re.match(line.strip())
        if not m:
            continue
        try:
            rec = make_record(
                fecha=fecha,
                poliza=m.group("poliza"),
                asegurado=m.group("resto").strip(),
                seccion=SECCION,
                compania=COMPANY,
                tipo="PR",
                comisiones=to_float(m.group("comis")),
                prima=to_float(m.group("prima")),
                premio=to_float(m.group("prima")),
                source_file=fname,
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("VICTORIA fila: %s", exc)
            reject(result, fname, f"Error línea: {exc}", raw=line)
    return result
