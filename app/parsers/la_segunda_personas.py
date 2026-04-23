"""Parser de LA SEGUNDA PERSONAS (reutiliza la lógica de generales)."""
from __future__ import annotations

from datetime import date

from ..models import ParseResult
from . import la_segunda_grales


def parse(file_path: str, fecha: date) -> ParseResult:
    res = la_segunda_grales.parse(file_path, fecha, company_name="LA SEGUNDA PERSONAS")
    res.parser_name = "la_segunda_personas"
    return res
