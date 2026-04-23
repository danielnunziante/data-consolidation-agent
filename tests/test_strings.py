from app.utils.strings import (
    clean_policy,
    contains_any,
    normalize,
    normalize_file_key,
    safe_str,
    strip_leading_zeros,
)


def test_safe_str_handles_nan():
    assert safe_str(None) == ""
    assert safe_str(float("nan")) == ""
    assert safe_str("  abc  ") == "abc"


def test_normalize_removes_accents_and_case():
    assert normalize("Póliza ÑÓ") == "POLIZA NO"


def test_normalize_file_key_strips_dates():
    assert "CTA CTE" in normalize_file_key("ALLIANZ CTA CTE MARZO 2026.xlsx")


def test_clean_policy_strips_quotes_and_floats():
    assert clean_policy("'12345'") == "12345"
    assert clean_policy("12345.0") == "12345"
    assert clean_policy("12,345") == "12345"


def test_strip_leading_zeros():
    assert strip_leading_zeros("000123") == "123"
    assert strip_leading_zeros("0") == "0"
    assert strip_leading_zeros("-00012") == "-12"


def test_contains_any():
    assert contains_any("COBERTURAS Y SERVICIOS", ["coberturas"])
    assert not contains_any("OTRO", ["coberturas"])
