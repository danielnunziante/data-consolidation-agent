"""Parser de CNP (archivo "CNP CUENTA CORRIENTE ..." / "CNP CTA CTE ...").

El archivo trae uno o más bloques tabulares, cada uno con su propia fila de
cabecera (los bloques pueden diferir levemente en columnas):

Bloque VIDA (USD):  ... | N° de póliza | Asegurado | ... | Producto | ... |
    Moneda | Tipo de Cambio | Prima de tarifa | Prima de tarifa en $ |
    Premio en $ | ... | Comisión Bruta | Comisión adelanto | [COMISION PESOS]
Bloque ACCIDENTES ($): ... | N° de póliza | Asegurado | ... | Producto | ... |
    Prima de tarifa | Premio en $ | % Comisión | ... | Comisión Bruta | ...

Mapeo (validado contra las consolidaciones manuales ABRIL/MAYO 2026):
- POLIZA = N° de póliza, ASEGURADO = Asegurado (o Tomador si falta).
- SECCION: producto con "Confiance"/"Universal"/"Vida" -> VIDA;
  "Accidente..." -> ACCIDENTES PERSONALES; si no, el producto tal cual.
- TIPO = PR.
- COMISIONES: "COMISION PESOS" si existe; si no, Comisión Bruta (o Comisión
  adelanto cuando la bruta es 0, o Descuento adelanto como negativo) por el
  Tipo de Cambio si la fila es U$S.
- PRIMA = "Prima de tarifa en $" si existe; si no "Prima de tarifa".
- PREMIO = "Premio en $"; si viene 0, se toma el de la fila hermana de la
  misma póliza/prima (el cliente lo replica).
- Pares que se cancelan (misma póliza/prima, comisión +x y -x) se descartan.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import ParseResult
from ..utils.numbers import round2, to_float
from ..utils.strings import normalize, safe_str
from .base_parser import log, make_record, read_excel_sheets, reject

COMPANY = "CNP"


def _seccion_for(producto: str) -> str:
    n = normalize(producto)
    if any(tok in n for tok in ("CONFIANCE", "UNIVERSAL", "VIDA")):
        return "VIDA"
    if "ACCIDENTE" in n:
        return "ACCIDENTES PERSONALES"
    return safe_str(producto)


def parse(file_path: str, fecha: date) -> ParseResult:
    result = ParseResult(parser_name="cnp", source_file=file_path)
    sheets = read_excel_sheets(file_path)
    fname = Path(file_path).name

    rows_out: list[dict] = []

    for sheet_name, df in sheets.items():
        col_map: dict[str, int] = {}

        def col(*names: str) -> int | None:
            for n in names:
                nn = normalize(n)
                if nn in col_map:
                    return col_map[nn]
            for n in names:
                nn = normalize(n)
                for k, v in col_map.items():
                    if nn and nn in k:
                        return v
            return None

        for i in range(len(df)):
            cells = [safe_str(c).replace("\n", " ") for c in df.iloc[i].tolist()]
            joined = normalize(" ".join(cells))
            if "POLIZA" in joined and "ASEGURADO" in joined and "PRODUCTO" in joined:
                col_map = {normalize(c): j for j, c in enumerate(cells) if c and c.lower() != "nan"}
                continue
            if not col_map:
                continue
            i_pol = col("N° de póliza", "N de poliza", "poliza")
            i_aseg = col("Asegurado")
            i_tom = col("Tomador")
            i_prod = col("Producto")
            i_mon = col("Moneda")
            i_tc = col("Tipo de Cambio")
            i_prima_pesos = col("Prima de tarifa en $")
            i_prima = col("Prima de tarifa")
            i_premio = col("Premio en $", "Premio")
            i_com_pesos = col("COMISION PESOS")
            i_com_bruta = col("Comisión Bruta", "Comision Bruta")
            i_com_adel = col("Comisión adelanto", "Comision adelanto")
            i_desc_adel = col("Descuento adelanto")
            if i_pol is None or i_prod is None:
                continue

            def cell(ix):
                return cells[ix] if ix is not None and ix < len(cells) else ""

            poliza = cell(i_pol)
            if not poliza or poliza.lower() == "nan" or to_float(poliza) is None:
                continue
            producto = cell(i_prod)
            if not producto or producto.lower() == "nan":
                continue
            asegurado = ""
            if cell(i_aseg).lower() not in {"", "nan"}:
                asegurado = cell(i_aseg)
            elif cell(i_tom).lower() not in {"", "nan"}:
                asegurado = cell(i_tom)

            es_usd = "U$" in cell(i_mon).upper() or "USD" in cell(i_mon).upper()
            tc = to_float(cell(i_tc)) if es_usd else None
            if not tc or tc <= 0:
                tc = 1.0

            com_v = to_float(cell(i_com_pesos)) if i_com_pesos is not None else None
            if com_v is None or com_v == 0:
                bruta = to_float(cell(i_com_bruta))
                adel = to_float(cell(i_com_adel))
                desc = to_float(cell(i_desc_adel))
                if bruta:
                    com_v = round2(bruta * tc)
                elif adel:
                    com_v = round2(adel * tc)
                elif desc:
                    com_v = round2(desc * tc)
                elif bruta is not None:
                    com_v = 0.0

            prima_v = to_float(cell(i_prima_pesos)) if i_prima_pesos is not None else None
            if prima_v is None:
                prima_v = to_float(cell(i_prima))
            premio_v = to_float(cell(i_premio))
            if com_v is None and prima_v is None:
                continue
            rows_out.append(
                {
                    "sheet": sheet_name,
                    "row": i + 1,
                    "poliza": poliza,
                    "asegurado": asegurado,
                    "seccion": _seccion_for(producto),
                    "com": com_v,
                    "prima": prima_v,
                    "premio": premio_v,
                }
            )

    # Premio replicado: si una fila quedó con premio 0/None y otra fila de la
    # misma póliza+prima lo tiene, se copia.
    for r in rows_out:
        if not r["premio"]:
            for o in rows_out:
                if o is r:
                    continue
                if o["poliza"] == r["poliza"] and o["prima"] == r["prima"] and o["premio"]:
                    r["premio"] = o["premio"]
                    break

    # Pares que se cancelan (comisión +x / -x para la misma póliza y prima).
    drop: set[int] = set()
    for a in range(len(rows_out)):
        if a in drop:
            continue
        ra = rows_out[a]
        if not ra["com"] or ra["com"] >= 0:
            continue
        for b in range(len(rows_out)):
            if b == a or b in drop:
                continue
            rb = rows_out[b]
            if (
                rb["poliza"] == ra["poliza"]
                and rb["prima"] == ra["prima"]
                and rb["com"] is not None
                and abs(rb["com"] + ra["com"]) < 0.01
            ):
                drop.add(a)
                drop.add(b)
                break

    for n, r in enumerate(rows_out):
        if n in drop:
            continue
        try:
            rec = make_record(
                fecha=fecha,
                poliza=r["poliza"],
                asegurado=r["asegurado"],
                seccion=r["seccion"],
                compania=COMPANY,
                tipo="PR",
                comisiones=r["com"],
                prima=r["prima"],
                premio=r["premio"],
                source_file=fname,
                source_sheet=r["sheet"],
                source_row=r["row"],
            )
            result.records.append(rec)
        except Exception as exc:
            log.warning("CNP fila %s: %s", r["row"], exc)
            reject(result, fname, f"Error: {exc}", source_sheet=r["sheet"], source_row=r["row"], raw=str(r))

    if not result.records and not result.rejected:
        reject(result, fname, "No se encontraron filas válidas")
    return result
