"""Tests del normalizador de SECCION (app/utils/seccion.py)."""
from __future__ import annotations

from datetime import date

import pytest

from app.models import Record
from app.utils import seccion as sec


@pytest.fixture(autouse=True)
def _clear_cache():
    sec.reset_cache()
    yield
    sec.reset_cache()


def _rec(compania: str, seccion: str) -> Record:
    return Record(
        fecha=date(2026, 4, 1),
        poliza="123",
        asegurado="X",
        seccion=seccion,
        compania=compania,
        tipo="PR",
        comisiones=1.0,
        prima=1.0,
        premio=1.0,
        source_file="f.xlsx",
    )


@pytest.mark.parametrize(
    "compania,raw,expected",
    [
        # Código de texto con prefijo numérico (ALLIANZ)
        ("ALLIANZ", "001 Incendio", "INCENDIO"),
        # Código numérico entero (FEDERACION PATRONAL)
        ("FEDERACION PATRONAL", "4", "AUTOMOTORES"),
        ("FEDERACION PATRONAL", 4, "AUTOMOTORES"),
        # Ceros a la izquierda (INTEGRITY emite '01','02'...)
        ("INTEGRITY", "01", "AUTOMOTORES"),
        ("INTEGRITY", "12", "CAUCION"),
        # Texto con espacios sobrantes (ATM viene con padding)
        ("ATM", "  4 -   MOTOVEHICULOS  ", "MOTOVEHICULOS"),
        # Case-insensitive (EXPERTA SAU)
        ("EXPERTA SAU", "autos", "AUTOMOTORES"),
        # Texto con código y guion (ZURICH)
        ("ZURICH", "09 - AUTOMOTORES", "AUTOMOTORES"),
        # SMG LIFE por segmento alfanumérico
        ("SMG LIFE", "CVO9", "VIDA OBLIGATORIO"),
    ],
)
def test_normaliza_valores_conocidos(compania, raw, expected):
    assert sec.normalize_seccion(compania, raw) == expected


def test_fallback_usd_reusa_tabla_base():
    # SAN CRISTOBAL USD no está en la tabla; debe caer a SAN CRISTOBAL.
    assert sec.normalize_seccion("SAN CRISTOBAL USD", "Automotor") == "AUTOMOTORES"


def test_sin_equivalencia_devuelve_none():
    assert sec.normalize_seccion("MERCANTIL ANDINA", "99") is None
    assert sec.normalize_seccion("COMPANIA INEXISTENTE", "X") is None


def test_normalize_records_inplace_y_reporte():
    records = [
        _rec("FEDERACION PATRONAL", "4"),   # -> AUTOMOTORES
        _rec("SAN CRISTOBAL", "Automotor"),  # -> AUTOMOTORES
        _rec("ANDINA ART", "A.R.T."),        # sin equivalencia (ya canónico)
        _rec("MERCANTIL ANDINA", "99"),      # sin equivalencia
        _rec("MERCANTIL ANDINA", "99"),      # sin equivalencia (cuenta 2)
    ]
    unmapped = sec.normalize_records(records)

    assert records[0].seccion == "AUTOMOTORES"
    assert records[1].seccion == "AUTOMOTORES"
    # Los no mapeados conservan el valor crudo.
    assert records[2].seccion == "A.R.T."
    assert records[3].seccion == "99"

    assert unmapped[("ANDINA ART", "A.R.T.")] == 1
    assert unmapped[("MERCANTIL ANDINA", "99")] == 2


def test_override_config(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "equivalencias_seccion.json").write_text(
        '{"MERCANTIL ANDINA": {"51": "AUTOMOTORES"}, "SANCOR": {"300": "RIESGOS VARIOS"}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    sec.reset_cache()

    assert sec.normalize_seccion("MERCANTIL ANDINA", "51") == "AUTOMOTORES"
    assert sec.normalize_seccion("SANCOR", "300") == "RIESGOS VARIOS"
