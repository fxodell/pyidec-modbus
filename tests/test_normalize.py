"""Tests for IDEC operand normalization and validation."""

import pytest

from pyidec_modbus import normalize_tag
from pyidec_modbus.errors import InvalidTagError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("d7", "D0007"),
        ("D7", "D0007"),
        ("m12", "M0012"),
        ("M12", "M0012"),
        ("T2.PV", "T0002.PV"),
        ("t2.pv", "T0002.PV"),
        ("D8000", "D8000"),
        ("M8000", "M8000"),
        ("T0002", "T0002.CV"),
        ("C0002", "C0002.CV"),
        ("T2", "T0002.CV"),
        ("C2", "C0002.CV"),
        ("I0001", "I0001"),
        ("Q0001", "Q0001"),
    ],
)
def test_normalize_tag_canonical(raw: str, expected: str) -> None:
    assert normalize_tag(raw) == expected


@pytest.mark.parametrize(
    "malformed",
    [
        "",
        "   ",
        "X",
        "D",
        "D12abc",
        "D12345",
        "T2.XX",
        "M12.PV",
    ],
)
def test_normalize_tag_invalid_raises(malformed: str) -> None:
    with pytest.raises(InvalidTagError):
        normalize_tag(malformed)


def test_normalize_tag_preserves_explicit_padding() -> None:
    assert normalize_tag("D8000") == "D8000"
    assert normalize_tag("M8000") == "M8000"
    assert normalize_tag("D0001") == "D0001"
