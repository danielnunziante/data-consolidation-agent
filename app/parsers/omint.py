"""Parser de OMINT -> compañía "OMINT SERVICIOS".

Formato "Detalle" (MAYO 2026+): Período liquidación | ... | Socio |
N° Beneficiario | Parentesco | Nombre | ... | Tipo Comisión | % Comisión |
Comisión | ...

Mapeo (validado contra la consolidación manual MAYO 2026):
- POLIZA = Socio, ASEGURADO = Nombre (beneficiario).
- SECCION = "PREPAGA MEDICA".
- TIPO: "On Going" -> AY; "One Shot" -> PR. Sólo COMISIONES (sin prima/premio).

El formato viejo agregado por empresa (ABRIL 2026, sin nro de socio) no se
procesa: la consolidación manual de ese mes tampoco lo incluyó.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import to_float
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

COMPANY = "OMINT SERVICIOS"
SECCION = "PREPAGA MEDICA"


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="omint", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    fname = Path(file_path).name

    for sheet_name, df_raw in sheets.items():
        if df_raw.empty:
            continue
        header_row = detect_header_row(
            df_raw, ["Socio", "Nombre", "Tipo Comisión", "Comisión"]
        )
        if header_row is None:
            continue
        df = slice_as_dataframe(df_raw, header_row)
        cols = list(df.columns)
        c_socio = find_col(cols, "Socio")
        c_nombre = find_col(cols, "Nombre")
        c_tipo = find_col(cols, "Tipo Comisión", "Tipo Comision")
        c_com = find_col(cols, "Comisión", "Comision")
        c_dni = find_col(cols, "DNI / CUIL", "DNI", "CUIL")
        if not all([c_socio, c_nombre, c_com]):
            continue
        for idx, row in df.iterrows():
            socio = safe_str(row[c_socio])
            if not socio or socio.lower() == "nan" or normalize(socio).startswith("TOTAL"):
                continue
            com_v = to_float(row[c_com])
            if com_v is None:
                continue
            tipo_raw = normalize(row[c_tipo]) if c_tipo else ""
            tipo = "PR" if "ONESHOT" in tipo_raw.replace(" ", "") else "AY"
            poliza = socio
            if tipo == "PR" and c_dni:
                # One Shot (alta nueva): el cliente usa el DNI (parte media
                # del CUIL) como póliza en lugar del nro de socio.
                dni_digits = "".join(ch for ch in safe_str(row[c_dni]) if ch.isdigit())
                if len(dni_digits) == 11:
                    poliza = dni_digits[2:-1]
                elif dni_digits:
                    poliza = dni_digits
            try:
                rec = make_record(
                    fecha=fecha,
                    poliza=poliza,
                    asegurado=row[c_nombre],
                    seccion=SECCION,
                    compania=COMPANY,
                    tipo=tipo,
                    comisiones=com_v,
                    prima=None,
                    premio=None,
                    source_file=fname,
                    source_sheet=sheet_name,
                    source_row=idx + header_row + 2,
                )
                result.records.append(rec)
            except Exception as exc:
                log.warning("OMINT fila %s: %s", idx, exc)
                reject(result, fname, f"Error: {exc}", source_sheet=sheet_name, source_row=idx, raw=row.to_dict())
    if not result.records and not result.rejected:
        reject(result, fname, "Formato sin filas procesables (¿reporte agregado sin nro de socio?)")
    return result
