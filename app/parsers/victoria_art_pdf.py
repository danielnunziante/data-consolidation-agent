"""Parser de VICTORIA ART - PDF.

El PDF de VICTORIA llega ESCANEADO: cada página es una imagen (CCITT G4, sin
capa de texto). Por eso:

1. Primero intentamos extraer texto con `pdfplumber` (por si algún mes llega
   un PDF con texto real).
2. Si no hay texto, caemos a OCR por visión de OpenAI (ver `utils/ocr.py`).
   El OCR es OPCIONAL: si no hay API key configurada, la fila se rechaza con
   un motivo claro (comportamiento previo).

Mapeo de columnas del "RESUMEN CUENTA CORRIENTE PRODUCTORES" (calibrado contra
la base manual ABRIL/MAYO 2026):
    - poliza      <- "Póliza" (sin ceros a la izquierda)
    - asegurado   <- "Asegurado s/o Detalle"
    - comisiones  <- "Imp. Bruto Comisiones"
    - prima       <- "Prima Cobrada"
    - premio      <- "Premio Cobrado"
    - seccion     = "A.R.T.", tipo = "PR"
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pdfplumber

from ..models import ParseResult, Record
from ..utils.numbers import to_float
from ..utils.ocr import ocr_available, render_pdf_pages, vision_extract_json
from ..utils.strings import safe_str
from .base_parser import log, make_record, reject

COMPANY = "VICTORIA ART"
SECCION = "A.R.T."


# --------------------------------------------------------------------------- #
# OCR (visión)
# --------------------------------------------------------------------------- #
_OCR_SYSTEM = (
    "Sos un asistente experto en extraer datos tabulares de imágenes de "
    "reportes contables de seguros con máxima precisión numérica. Respondés "
    "únicamente con JSON válido, sin texto adicional."
)

_OCR_USER = (
    'Las imágenes son las páginas de un "RESUMEN CUENTA CORRIENTE PRODUCTORES" '
    "de VICTORIA A.R.T. La tabla tiene estas columnas, de izquierda a derecha: "
    "Dia, Sc, Póliza, Endoso, \"Asegurado s/o Detalle\", \"Premio Cobrado\", "
    '"Prima Cobrada", "Imp. Bruto Comisiones", un código de retención, '
    'las retenciones (Jub/I.Brutos y Serv.Soc), "Neto debitado" y "Neto acreditado".\n\n'
    "Extraé SOLO las filas de detalle que corresponden a una póliza real "
    "(tienen número de Póliza Y nombre de asegurado). IGNORÁ por completo las "
    'filas de "Saldo ...", "Sub-totales ...", "Totales ..." y los encabezados.\n\n'
    "Para cada fila de póliza devolvé un objeto con exactamente estas claves:\n"
    '  - "poliza": número de la columna Póliza, como string y sin ceros a la izquierda.\n'
    '  - "asegurado": texto de "Asegurado s/o Detalle".\n'
    '  - "comisiones": valor de "Imp. Bruto Comisiones".\n'
    '  - "prima": valor de "Prima Cobrada".\n'
    '  - "premio": valor de "Premio Cobrado".\n\n'
    "Los importes están en formato argentino (el punto separa miles y la coma "
    'los decimales), por ejemplo "16.346.119,45". Devolvé cada importe como '
    "número con punto decimal (16346119.45) y respetá el signo negativo si lo hay. "
    "No inventes filas ni valores: si un dato no es legible, poné null.\n\n"
    'Respondé con este JSON: {"rows": [ {"poliza": ..., "asegurado": ..., '
    '"comisiones": ..., "prima": ..., "premio": ...}, ... ]}'
)


def _norm_poliza(raw) -> str:
    digits = re.sub(r"\D", "", safe_str(raw))
    return digits.lstrip("0") or digits


def build_records_from_ocr(rows: list[dict], fecha: date, fname: str) -> list[Record]:
    """Convierte las filas devueltas por el modelo de visión en Records.

    Separado del I/O para poder testearlo sin red.
    """
    records: list[Record] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        poliza = _norm_poliza(row.get("poliza"))
        if not poliza:
            continue
        rec = make_record(
            fecha=fecha,
            poliza=poliza,
            asegurado=row.get("asegurado"),
            seccion=SECCION,
            compania=COMPANY,
            tipo="PR",
            comisiones=to_float(row.get("comisiones")),
            prima=to_float(row.get("prima")),
            premio=to_float(row.get("premio")),
            source_file=fname,
        )
        records.append(rec)
    return records


def _parse_via_ocr(file_path: str, fecha: date, fname: str, result: ParseResult) -> None:
    available, reason = ocr_available()
    if not available:
        reject(
            result,
            fname,
            f"PDF escaneado sin texto. OCR no disponible: {reason}. "
            "Configurá la API key de OpenAI o cargá las filas a mano.",
        )
        return
    try:
        images = render_pdf_pages(file_path)
        data = vision_extract_json(images, _OCR_SYSTEM, _OCR_USER)
    except Exception as exc:
        log.warning("VICTORIA OCR falló: %s", exc)
        reject(result, fname, f"OCR falló: {exc}")
        return

    rows = data.get("rows") if isinstance(data, dict) else None
    records = build_records_from_ocr(rows or [], fecha, fname)
    if not records:
        reject(result, fname, "OCR no devolvió filas de pólizas reconocibles.")
        return
    result.records.extend(records)
    log.info("VICTORIA: %d filas extraídas por OCR", len(records))


# --------------------------------------------------------------------------- #
# Texto (PDF con capa de texto, poco frecuente)
# --------------------------------------------------------------------------- #
_LINE_RE = re.compile(
    r"^(?P<poliza>\d{4,})\s+(?P<resto>.+?)\s+(?P<prima>[\-\d\.,]+)\s+(?P<comis>[\-\d\.,]+)\s*$"
)


def _parse_via_text(lines: list[str], fecha: date, fname: str, result: ParseResult) -> None:
    for line in lines:
        m = _LINE_RE.match(line.strip())
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


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="victoria_art_pdf", source_file=file_path)
    fname = Path(file_path).name

    lines: list[str] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines.extend(text.splitlines())
                if not text.strip():
                    words = page.extract_words(extra_attrs=["upright"]) or []
                    if words:
                        lines.append(" ".join(safe_str(w.get("text")) for w in words))
    except Exception as exc:
        reject(result, fname, f"Error leyendo PDF: {exc}")
        return result

    if "\n".join(lines).strip():
        _parse_via_text(lines, fecha, fname, result)
        if result.records:
            return result

    # PDF escaneado (sin texto) o el texto no produjo filas -> OCR por visión.
    _parse_via_ocr(file_path, fecha, fname, result)
    return result
