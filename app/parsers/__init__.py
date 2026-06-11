"""Registry de parsers disponibles."""
from __future__ import annotations

from datetime import date
from typing import Callable

from ..models import ParseResult
from . import (
    agc_pdf,
    allianz,
    andina_art,
    asociart,
    atm,
    berkley_art,
    berkley_generales,
    cnp,
    experta_art,
    experta_sau,
    fedpat,
    galeno_life,
    galeno_prepaga,
    galicia,
    hdi,
    integrity,
    la_holando,
    la_segunda_art,
    la_segunda_grales,
    la_segunda_personas,
    libra_pdf,
    lugo,
    mercantil_andina,
    omint,
    parana_art,
    premiar,
    prevencion_art,
    provincia_art,
    qbe_zurich,
    san_cristobal,
    sancor,
    smg,
    smg_art,
    smg_life,
    victoria_art_pdf,
    zurich,
)

ParserFn = Callable[[str, date], ParseResult]

REGISTRY: dict[str, ParserFn] = {
    "agc_pdf": agc_pdf.parse,
    "allianz": allianz.parse,
    "andina_art": andina_art.parse,
    "asociart": asociart.parse,
    "atm": atm.parse,
    "berkley_art": berkley_art.parse,
    "berkley_generales": berkley_generales.parse,
    "cnp": cnp.parse,
    "experta_art": experta_art.parse,
    "experta_sau": experta_sau.parse,
    "fedpat": fedpat.parse,
    "galeno_life": galeno_life.parse,
    "galeno_prepaga": galeno_prepaga.parse,
    "galicia": galicia.parse,
    "hdi": hdi.parse,
    "integrity": integrity.parse,
    "la_holando": la_holando.parse,
    "la_segunda_art": la_segunda_art.parse,
    "la_segunda_grales": la_segunda_grales.parse,
    "la_segunda_personas": la_segunda_personas.parse,
    "libra_pdf": libra_pdf.parse,
    "lugo": lugo.parse,
    "mercantil_andina": mercantil_andina.parse_pesos,
    "mercantil_andina_usd": mercantil_andina.parse_usd,
    "omint": omint.parse,
    "parana_art": parana_art.parse,
    "premiar": premiar.parse,
    "prevencion_art": prevencion_art.parse,
    "provincia_art": provincia_art.parse,
    "qbe_zurich": qbe_zurich.parse,
    "san_cristobal": san_cristobal.parse_pesos,
    "san_cristobal_usd": san_cristobal.parse_usd,
    "sancor": sancor.parse,
    "smg": smg.parse,
    "smg_art": smg_art.parse,
    "smg_life": smg_life.parse,
    "victoria_art_pdf": victoria_art_pdf.parse,
    "zurich": zurich.parse,
}


def get_parser(name: str) -> ParserFn | None:
    return REGISTRY.get(name)
