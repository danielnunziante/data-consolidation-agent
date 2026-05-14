"""Parser de ANDINA ART - archivo .xls pero HTML real."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from ..models import ParseResult
from ..utils.numbers import to_float
from ..utils.strings import normalize, safe_str
from .base_parser import log, make_record, reject

COMPANY = "ANDINA ART"
SECCION = "A.R.T."


HEADER_TOKENS = [
    "F. PAGO PRIMA",
    "POLIZA",
    "CUIT",
    "RAZON SOCIAL",
    "PERIODO DDJJ",
    "PRIMA COBRADA",
    "COMISION %",
    "COMISION $",
    "IMPUESTOS",
    "TOTAL A FACTURAR",
]


def _read_html(path: str) -> BeautifulSoup:
    # El archivo viene en latin-1 pero con cabecera HTML; usamos un encoding tolerante.
    try:
        data = Path(path).read_text(encoding="latin-1")
    except UnicodeDecodeError:
        data = Path(path).read_bytes().decode("utf-8", errors="ignore")
    return BeautifulSoup(data, "lxml")


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="andina_art", source_file=file_path)
    soup = _read_html(file_path)

    tables = soup.find_all("table")
    if not tables:
        reject(result, Path(file_path).name, "HTML sin tablas")
        return result

    fname = Path(file_path).name
    for tbl in tables:
        rows = tbl.find_all("tr")
        if not rows:
            continue
        # Encabezados: primera fila con las etiquetas conocidas
        header_idx = None
        headers: list[str] = []
        for i, tr in enumerate(rows):
            cells = [safe_str(c.get_text(strip=True)) for c in tr.find_all(["th", "td"])]
            upper = [normalize(c) for c in cells]
            if sum(1 for t in HEADER_TOKENS if any(normalize(t) in u for u in upper)) >= 6:
                header_idx = i
                headers = cells
                break
        if header_idx is None:
            continue

        # Mapear índices por nombre
        def col_index(*names: str) -> int | None:
            norm_hdr = [normalize(h) for h in headers]
            for n in names:
                n2 = normalize(n)
                for idx, h in enumerate(norm_hdr):
                    if n2 == h or n2 in h:
                        return idx
            return None

        i_pol = col_index("Poliza")
        i_razon = col_index("Razon social", "Razon")
        i_prima = col_index("Prima cobrada")
        i_com = col_index("Comision $")

        if None in (i_pol, i_razon, i_prima, i_com):
            reject(result, fname, f"Columnas insuficientes en ANDINA ART: headers={headers}")
            continue

        for r_i, tr in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
            cells = [safe_str(c.get_text(strip=True)) for c in tr.find_all(["th", "td"])]
            if not cells or len(cells) < max(i_pol, i_razon, i_prima, i_com) + 1:
                continue
            poliza = cells[i_pol]
            razon = cells[i_razon]
            # Saltar fila de totales
            if not poliza.strip() or normalize(poliza).startswith("TOTAL") or normalize(razon).startswith("TOTAL"):
                continue
            if to_float(poliza) is None and not poliza.isdigit():
                continue
            prima_v = cells[i_prima]
            comis_v = cells[i_com]
            # Manual: "CORREGIR PRIMA Y CALCULAR COMISION = 5% SOBRE PRIMA".
            # Si Comision $ viene vacía / None, la derivamos de la prima.
            # TODO confirmar con cliente: si esto debería aplicarse siempre o
            # solo como fallback.
            comis_num = to_float(comis_v)
            if comis_num is None:
                prima_num = to_float(prima_v)
                if prima_num is not None:
                    comis_v = prima_num * 0.05
            try:
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=razon,
                    seccion=SECCION,
                    compania=COMPANY,
                    tipo="PR",
                    comisiones=comis_v,
                    prima=prima_v,
                    premio=prima_v,
                    source_file=fname,
                    source_sheet=None,
                    source_row=r_i,
                )
                result.records.append(rec)
            except Exception as exc:
                log.warning("ANDINA ART fila %s: %s", r_i, exc)
                reject(result, fname, f"Error: {exc}", source_row=r_i, raw=cells)
    return result
