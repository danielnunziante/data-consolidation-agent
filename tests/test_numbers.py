from app.utils.numbers import round2, to_float


def test_to_float_none_and_empty():
    assert to_float(None) is None
    assert to_float("") is None
    assert to_float("   ") is None
    assert to_float("nan") is None
    assert to_float("-") is None


def test_to_float_int_and_float():
    assert to_float(5) == 5.0
    assert to_float(5.5) == 5.5


def test_to_float_argentinian_format():
    assert to_float("$ 12.345,67") == 12345.67
    assert to_float("1.234,56") == 1234.56
    assert to_float("-1.234,56") == -1234.56
    assert to_float("(12.345,67)") == -12345.67


def test_to_float_us_format():
    assert to_float("1,234.56") == 1234.56
    assert to_float("$1,234.56") == 1234.56


def test_to_float_trailing_minus():
    assert to_float("1234,56-") == -1234.56


def test_to_float_simple_decimal_comma():
    assert to_float("12,5") == 12.5


def test_round2():
    assert round2(None) is None
    assert round2(1.2345) == 1.23
    assert round2(1.2358) == 1.24
