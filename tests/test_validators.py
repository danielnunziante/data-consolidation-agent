from datetime import date

from app.models import Record
from app.validators import expected_counts_warnings, summarize_by_company, validate_records


def _rec(**overrides) -> Record:
    base = dict(
        fecha=date(2026, 3, 1),
        poliza="1",
        asegurado="X",
        seccion="S",
        compania="ALLIANZ",
        tipo="PR",
        comisiones=10.0,
        prima=100.0,
        premio=110.0,
        source_file="x.xlsx",
    )
    base.update(overrides)
    return Record(**base)


def test_validate_records_empty():
    assert validate_records([]) == []


def test_validate_records_flags_bad_tipo():
    w = validate_records([_rec(tipo="ZZ")])
    assert any("TIPO inválido" in x for x in w)


def test_validate_records_flags_ay_with_prima():
    w = validate_records([_rec(tipo="AY", prima=10.0, premio=None, comisiones=1.0)])
    assert any("PRIMA no vacía" in x for x in w)


def test_summarize_by_company():
    s = summarize_by_company([_rec(), _rec(compania="ZURICH"), _rec()])
    assert s == {"ALLIANZ": 2, "ZURICH": 1}


def test_expected_counts_warnings_only_present():
    w = expected_counts_warnings({"ALLIANZ": 10}, present_companies={"ALLIANZ"})
    assert any("ALLIANZ" in x for x in w)
    # compañías ausentes no generan ruido
    assert not any("ZURICH" in x for x in w)
