"""Configuración central del consolidador."""
from __future__ import annotations

from dataclasses import dataclass

BASE_SHEET_NAME = "BASE"

BASE_COLUMNS: list[str] = [
    "FECHA",
    "POLIZA",
    "ASEGURADO",
    "SECCION",
    "COMPAÑÍA",
    "TIPO",
    "COMISIONES",
    "PRIMA",
    "PREMIO",
    "COMPROBACION DE DUPLICADOS",
    "Columna1",
]

ALLOWED_TIPOS = {"PR", "AY", "IND"}

COMPANY_ORDER: list[str] = [
    "ALLIANZ",
    "ANDINA ART",
    "ASOCIART SA",
    "EXPERTA ART",
    "EXPERTA SAU",
    "FEDERACION PATRONAL",
    "GALENO LIFE",
    "GALICIA SEGUROS",
    "INTEGRITY",
    "LA HOLANDO ART",
    "LA HOLANDO GENERALES",
    "LA SEGUNDA ART",
    "LA SEGUNDA GENERALES",
    "LA SEGUNDA PERSONAS",
    "LIBRA SEGUROS",
    "MERCANTIL ANDINA",
    "MERCANTIL ANDINA USD",
    "PREMIAR",
    "PREVENCION ART",
    "PROVINCIA ART",
    "SAN CRISTOBAL",
    "SAN CRISTOBAL USD",
    "SANCOR",
    "SMG",
    "SMG ART",
    "SMG LIFE",
    "VICTORIA ART",
    "ZURICH",
    "PARANA ART",
]

EXPECTED_COUNTS: dict[str, int] = {
    "ALLIANZ": 76,
    "ANDINA ART": 67,
    "ASOCIART SA": 10,
    "EXPERTA ART": 63,
    "EXPERTA SAU": 203,
    "FEDERACION PATRONAL": 2186,
    "GALENO LIFE": 131,
    "GALICIA SEGUROS": 48,
    "INTEGRITY": 113,
    "LA HOLANDO ART": 4,
    "LA HOLANDO GENERALES": 11,
    "MERCANTIL ANDINA": 3663,
    "MERCANTIL ANDINA USD": 190,
    "LA SEGUNDA ART": 22,
    "LA SEGUNDA GENERALES": 123,
    "LA SEGUNDA PERSONAS": 195,
    "LIBRA SEGUROS": 8,
    "PREMIAR": 11,
    "PREVENCION ART": 14,
    "PROVINCIA ART": 19,
    "SAN CRISTOBAL": 2323,
    "SAN CRISTOBAL USD": 7,
    "SANCOR": 405,
    "SMG": 1678,
    "SMG ART": 340,
    "SMG LIFE": 194,
    "VICTORIA ART": 4,
    "ZURICH": 73,
}

# Mapping de identificadores normalizados -> nombre de parser
PARSER_BY_FILE_KEY: dict[str, str] = {
    "ALLIANZ CTA CTE": "allianz",
    "ANDINA ART CTA CTE": "andina_art",
    "ASOCIART CTA CTE": "asociart",
    "EXPERTA ART CTA CTE": "experta_art",
    "EXPERTA SAU CTA CTE": "experta_sau",
    "FEDPAT CTA CTE": "fedpat",
    "GALENO LIFE CTA CTE": "galeno_life",
    "GALICIA CTA CTE": "galicia",
    "INTEGRITY CTA CTE": "integrity",
    "LA HOLANDO CTA CTE": "la_holando",
    "LA MERCANTIL ANDINA USD CTA CTE": "mercantil_andina_usd",
    "LA MERCANTIL ANDINA CTA CTE": "mercantil_andina",
    "LA SEGUNDA ART CTA CTE": "la_segunda_art",
    "LA SEGUNDA GRALES CTA CTE": "la_segunda_grales",
    "LA SEGUNDA PERSONAS CTA CTE": "la_segunda_personas",
    "LIBRA CTA CTE": "libra_pdf",
    "PREMIAR CTA CTE": "premiar",
    "PREVENCION ART CTA CTE": "prevencion_art",
    "PROVINCIA ART CTA CTE": "provincia_art",
    "SAN CRISTOBAL USD CTA CTE": "san_cristobal_usd",
    "SAN CRISTOBAL CTA CTE": "san_cristobal",
    "SANCOR CTA CTE": "sancor",
    "SMG ART CTA CTE": "smg_art",
    "SMG LIFE CTA CTE": "smg_life",
    "SMG CTA CTE": "smg",
    "VICTORIA ART CTA CTE": "victoria_art_pdf",
    "ZURICH CTA CTE": "zurich",
    "PARANA ART CTA CTE": "parana_art",
}


@dataclass(frozen=True)
class RunParams:
    input_dir: str
    output_file: str
    period: str  # YYYY-MM
