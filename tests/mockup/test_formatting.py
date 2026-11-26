from datetime import date, datetime
from decimal import Decimal as D

import pytest

from ec_quote.mockup.formatting import (
    format_date_ro, format_lei, format_number, format_quantity, format_unit_price,
)


@pytest.mark.parametrize("value, expected", [
    ("1234.5", "1.234,50 lei"),
    ("0", "0,00 lei"),
    ("0.5", "0,50 lei"),
    ("999.999", "1.000,00 lei"),
    ("1234567.891", "1.234.567,89 lei"),
    ("12", "12,00 lei"),
    ("0.125", "0,13 lei"),
    ("0.135", "0,14 lei"),
    ("-1234.5", "-1.234,50 lei"),
    ("-0.001", "0,00 lei"),
    ("1E+3", "1.000,00 lei"),
])
def test_format_lei(value, expected):
    assert format_lei(D(value)) == expected


@pytest.mark.parametrize("value, expected", [
    ("0.998", "0,998 lei"),
    ("0.80", "0,80 lei"),
    ("0.4954", "0,4954 lei"),
    ("0.49545", "0,4955 lei"),
    ("1234", "1.234,00 lei"),
])
def test_format_unit_price_keeps_sub_bani(value, expected):
    assert format_unit_price(D(value)) == expected


def test_money_must_be_decimal():
    with pytest.raises(TypeError):
        format_lei(12.5)
    with pytest.raises(ValueError):
        format_lei(D("NaN"))
    with pytest.raises(ValueError):
        format_number(D("1"), 3, 2)


def test_format_quantity():
    assert format_quantity(500) == "500 buc"
    assert format_quantity(1000) == "1.000 buc"
    assert format_quantity(1250000) == "1.250.000 buc"
    assert format_quantity(-1500) == "-1.500 buc"
    with pytest.raises(TypeError):
        format_quantity(True)
    with pytest.raises(TypeError):
        format_quantity(1.5)


def test_format_date_ro():
    assert format_date_ro(datetime(2026, 12, 3, 23, 59)) == "3 decembrie 2026"
    assert format_date_ro(date(2027, 1, 31)) == "31 ianuarie 2027"
    assert format_date_ro(date(2027, 5, 1)) == "1 mai 2027"
