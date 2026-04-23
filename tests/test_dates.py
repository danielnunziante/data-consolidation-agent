from datetime import date

import pytest

from app.utils.dates import first_day_of_period, is_valid_period


def test_first_day_of_period_ok():
    assert first_day_of_period("2026-03") == date(2026, 3, 1)
    assert first_day_of_period("2026-3") == date(2026, 3, 1)
    assert first_day_of_period("202603") == date(2026, 3, 1)


def test_first_day_of_period_bad():
    with pytest.raises(ValueError):
        first_day_of_period("2026-13")
    with pytest.raises(ValueError):
        first_day_of_period("abc")


def test_is_valid_period():
    assert is_valid_period("2026-03")
    assert not is_valid_period("")
    assert not is_valid_period(None)
    assert not is_valid_period("2026-99")
