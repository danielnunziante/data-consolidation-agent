"""Tests del OCR de VICTORIA ART (sin red ni PDFs reales)."""
from datetime import date

import pytest

from app.models import ParseResult
from app.parsers import victoria_art_pdf as v
from app.utils import ocr


# --------------------------------------------------------------------------- #
# Mapeo de columnas (calibrado contra la base manual MAYO 2026)
# --------------------------------------------------------------------------- #
def test_build_records_from_ocr_mapping():
    rows = [
        {"poliza": "000012295", "asegurado": "EGESAC SOCIEDAD ANONIM",
         "comisiones": 653844.78, "prima": 16346119.45, "premio": 16656695.72},
        # mismo registro pero con importes en formato argentino y póliza sucia
        {"poliza": "12736 ", "asegurado": "ITALCOM S R L",
         "comisiones": "11.080,48", "prima": "277.011,94", "premio": "282.275,17"},
    ]
    recs = v.build_records_from_ocr(rows, date(2026, 5, 1), "VICTORIA.pdf")
    assert len(recs) == 2

    r0 = recs[0]
    assert r0.poliza == "12295"  # ceros a la izquierda removidos
    assert r0.asegurado == "EGESAC SOCIEDAD ANONIM"
    assert r0.compania == "VICTORIA ART"
    assert r0.seccion == "A.R.T."
    assert r0.tipo == "PR"
    assert r0.comisiones == 653844.78
    assert r0.prima == 16346119.45
    assert r0.premio == 16656695.72

    r1 = recs[1]
    assert r1.poliza == "12736"
    assert r1.comisiones == 11080.48
    assert r1.prima == 277011.94
    assert r1.premio == 282275.17


def test_build_records_skips_garbage_rows():
    rows = [
        {"poliza": "", "asegurado": "Sub-totales dia 18"},
        {"poliza": None, "asegurado": "Totales"},
        "no soy un dict",
        {"poliza": "12736", "asegurado": "ITALCOM", "comisiones": 1, "prima": 2, "premio": 3},
    ]
    recs = v.build_records_from_ocr(rows, date(2026, 5, 1), "X.pdf")
    assert [r.poliza for r in recs] == ["12736"]


# --------------------------------------------------------------------------- #
# Config: round-trip y prioridad env > archivo
# --------------------------------------------------------------------------- #
def test_ocr_config_roundtrip(tmp_path, monkeypatch):
    cfg = tmp_path / "ocr.json"
    monkeypatch.setattr(ocr, "_config_path", lambda: cfg)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OCR_MODEL", raising=False)

    assert ocr.get_openai_api_key() is None

    ocr.write_ocr_config("sk-test-123", model="")
    assert cfg.exists()
    assert ocr.get_openai_api_key() == "sk-test-123"
    assert ocr.get_ocr_model() == ocr.DEFAULT_MODEL  # vacío -> default
    assert ocr.read_ocr_config()["openai_api_key"] == "sk-test-123"


def test_env_overrides_config_file(tmp_path, monkeypatch):
    cfg = tmp_path / "ocr.json"
    monkeypatch.setattr(ocr, "_config_path", lambda: cfg)
    ocr.write_ocr_config("sk-from-file", model="gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    monkeypatch.setenv("OCR_MODEL", "gpt-4.1")
    assert ocr.get_openai_api_key() == "sk-from-env"
    assert ocr.get_ocr_model() == "gpt-4.1"


# --------------------------------------------------------------------------- #
# Orquestación de _parse_via_ocr (visión mockeada)
# --------------------------------------------------------------------------- #
def test_parse_via_ocr_unavailable_rejects(monkeypatch):
    monkeypatch.setattr(v, "ocr_available", lambda: (False, "sin key"))
    result = ParseResult(parser_name="victoria_art_pdf", source_file="X.pdf")
    v._parse_via_ocr("X.pdf", date(2026, 5, 1), "X.pdf", result)
    assert not result.records
    assert len(result.rejected) == 1
    assert "OCR no disponible" in result.rejected[0].reason


def test_parse_via_ocr_success(monkeypatch):
    monkeypatch.setattr(v, "ocr_available", lambda: (True, "ok"))
    monkeypatch.setattr(v, "render_pdf_pages", lambda p: [b"fake-png"])
    monkeypatch.setattr(
        v, "vision_extract_json",
        lambda imgs, sys, usr: {"rows": [
            {"poliza": "12296", "asegurado": "RSC S.A.",
             "comisiones": 732429.23, "prima": 18310730.7, "premio": 18658634.58},
        ]},
    )
    result = ParseResult(parser_name="victoria_art_pdf", source_file="X.pdf")
    v._parse_via_ocr("X.pdf", date(2026, 5, 1), "X.pdf", result)
    assert len(result.records) == 1
    assert result.records[0].poliza == "12296"
    assert result.records[0].comisiones == 732429.23
    assert not result.rejected


def test_parse_via_ocr_empty_rejects(monkeypatch):
    monkeypatch.setattr(v, "ocr_available", lambda: (True, "ok"))
    monkeypatch.setattr(v, "render_pdf_pages", lambda p: [b"fake-png"])
    monkeypatch.setattr(v, "vision_extract_json", lambda imgs, sys, usr: {"rows": []})
    result = ParseResult(parser_name="victoria_art_pdf", source_file="X.pdf")
    v._parse_via_ocr("X.pdf", date(2026, 5, 1), "X.pdf", result)
    assert not result.records
    assert "no devolvió filas" in result.rejected[0].reason.lower()


def test_parse_via_ocr_api_error_rejects(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("llamada a OpenAI falló: 401")

    monkeypatch.setattr(v, "ocr_available", lambda: (True, "ok"))
    monkeypatch.setattr(v, "render_pdf_pages", lambda p: [b"fake-png"])
    monkeypatch.setattr(v, "vision_extract_json", boom)
    result = ParseResult(parser_name="victoria_art_pdf", source_file="X.pdf")
    v._parse_via_ocr("X.pdf", date(2026, 5, 1), "X.pdf", result)
    assert not result.records
    assert "OCR falló" in result.rejected[0].reason
