"""Parser de ANDINA ART.

Históricamente llegaba como .xls que era HTML; desde ABRIL 2026 llega como
xlsx real con hoja "Comisiones". Se soportan ambos.

Columnas: F. pago prima | Poliza | CUIT | Razon social | Periodo DDJJ |
Prima cobrada | Comision % | Comision $ | Impuestos | Total a facturar

Mapeo (validado contra consolidación manual ABRIL 2026):
- POLIZA=Poliza, ASEGURADO=Razon social, SECCION="A.R.T.", TIPO=PR.
- PRIMA=PREMIO=Prima cobrada (formato "$ 12.345,67").
- COMISIONES = Prima cobrada * Comision % (la columna "Comision $" viene con
  el separador decimal perdido, no es confiable). Se incluyen filas en cero.
- La fila de totales (sin Poliza) se descarta.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from ..models import ParseResult
from ..utils.numbers import round2, to_float
from ..utils.strings import normalize, safe_str
from .base_parser import (
    detect_header_row,
    find_col,
    log,
    make_record,
    read_excel_sheets,
    reject,
    slice_as_dataframe,
)

COMPANY = "ANDINA ART"
SECCION = "A.R.T."


def _emit(result: ParseResult, fname: str, sheet, row_no, poliza, razon, prima_raw, pct_raw, comis_raw, fecha: date) -> None:
    prima = to_float(prima_raw)
    pct = to_float(pct_raw)
    if pct is not None and 0 < pct < 1 and prima is not None:
        comis = round2(prima * pct)
    else:
        comis = to_float(comis_raw)
    try:
        rec = make_record(
            fecha=fecha,
            poliza=poliza,
            asegurado=razon,
            seccion=SECCION,
            compania=COMPANY,
            tipo="PR",
            comisiones=comis,
            prima=prima,
            premio=prima,
            source_file=fname,
            source_sheet=sheet,
            source_row=row_no,
        )
        result.records.append(rec)
    except Exception as exc:
        log.warning("ANDINA ART fila %s: %s", row_no, exc)
        reject(result, fname, f"Error: {exc}", source_sheet=sheet, source_row=row_no)


def _parse_excel(result: ParseResult, file_path: str, fecha: date) -> bool:
    """Devuelve True si pudo leerse como Excel real."""
    try:
        sheets = read_excel_sheets(file_path)
    except Exception:
        return False
    fname = Path(file_path).name
    for sheet_name, df_raw in sheets.items():
        header_row = detect_header_row(
            df_raw, ["Poliza", "Razon social", "Prima cobrada", "Comision %"]
        )
        if header_row is None:
            continue
        df = slice_as_dataframe(df_raw, header_row)
        cols = list(df.columns)
        c_pol = find_col(cols, "Poliza")
        c_razon = find_col(cols, "Razon social", "Razon")
        c_prima = find_col(cols, "Prima cobrada")
        c_pct = find_col(cols, "Comision %")
        c_com = find_col(cols, "Comision $")
        if not all([c_pol, c_razon, c_prima]):
            continue
        for idx, row in df.iterrows():
            poliza = safe_str(row[c_pol])
            if not poliza or poliza.lower() == "nan" or normalize(poliza).startswith("TOTAL"):
                continue
            _emit(
                result,
                fname,
                sheet_name,
                idx + header_row + 2,
                poliza,
                row[c_razon],
                row[c_prima],
                row[c_pct] if c_pct else None,
                row[c_com] if c_com else None,
                fecha,
            )
        return True
    return bool(result.records)


def _read_html(path: str) -> BeautifulSoup:
    try:
        data = Path(path).read_text(encoding="latin-1")
    except UnicodeDecodeError:
        data = Path(path).read_bytes().decode("utf-8", errors="ignore")
    return BeautifulSoup(data, "lxml")


def _parse_html(result: ParseResult, file_path: str, fecha: date) -> None:
    soup = _read_html(file_path)
    tables = soup.find_all("table")
    fname = Path(file_path).name
    if not tables:
        reject(result, fname, "HTML sin tablas")
        return
    for tbl in tables:
        rows = tbl.find_all("tr")
        if not rows:
            continue
        header_idx = None
        headers: list[str] = []
        for i, tr in enumerate(rows):
            cells = [safe_str(c.get_text(strip=True)) for c in tr.find_all(["th", "td"])]
            upper = [normalize(c) for c in cells]
            score = sum(
                1
                for t in ("POLIZA", "RAZON SOCIAL", "PRIMA COBRADA", "COMISION %")
                if any(normalize(t) in u for u in upper)
            )
            if score >= 3:
                header_idx = i
                headers = cells
                break
        if header_idx is None:
            continue

        norm_hdr = [normalize(h) for h in headers]

        def col_index(*names: str):
            for n in names:
                n2 = normalize(n)
                for idx, h in enumerate(norm_hdr):
                    if n2 == h or n2 in h:
                        return idx
            return None

        i_pol = col_index("Poliza")
        i_razon = col_index("Razon social", "Razon")
        i_prima = col_index("Prima cobrada")
        i_pct = col_index("Comision %")
        i_com = col_index("Comision $")
        if None in (i_pol, i_razon, i_prima):
            continue
        for r_i, tr in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
            cells = [safe_str(c.get_text(strip=True)) for c in tr.find_all(["th", "td"])]
            if not cells or len(cells) <= max(i_pol, i_razon, i_prima):
                continue
            poliza = cells[i_pol]
            razon = cells[i_razon]
            if not poliza.strip() or normalize(poliza).startswith("TOTAL") or normalize(razon).startswith("TOTAL"):
                continue
            if to_float(poliza) is None and not poliza.isdigit():
                continue
            _emit(
                result,
                fname,
                None,
                r_i,
                poliza,
                razon,
                cells[i_prima],
                cells[i_pct] if i_pct is not None and i_pct < len(cells) else None,
                cells[i_com] if i_com is not None and i_com < len(cells) else None,
                fecha,
            )


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="andina_art", source_file=file_path)
    if _parse_excel(result, file_path, fecha):
        return result
    _parse_html(result, file_path, fecha)
    return result
