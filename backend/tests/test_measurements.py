import pytest
from app.domain.measurements import to_mm, from_mm, normalize_numerals

def test_to_mm_units():
    assert to_mm(1, "mm") == 1
    assert to_mm(1, "cm") == 10
    assert to_mm(1, "m") == 1000
    assert to_mm(3.2, "m") == 3200

def test_from_mm():
    assert from_mm(3200, "mm") == 3200
    assert from_mm(1000, "m") == 1.0

def test_normalize_persian_numerals():
    assert normalize_numerals("۳۲۰۰") == "3200"
    assert normalize_numerals("۱۲۳") == "123"
    assert normalize_numerals("3٫5") == "3.5"

def test_int_mm_storage():
    # Ensure integers stored, no float drift
    assert isinstance(to_mm(1.234, "m"), int)
