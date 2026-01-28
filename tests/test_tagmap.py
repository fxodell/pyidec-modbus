"""Tests for TagMap loading and lookup; FC6A default profile."""

import pytest

from pyidec_modbus import TagMap, get_default_tagmap
from pyidec_modbus.errors import UnknownTagError
from pyidec_modbus.types import ModbusTable, TagDef


def test_tagmap_from_override() -> None:
    fixture = [
        {"operand": "D0007", "table": "holding_register", "offset": 7, "width": 16},
        {"operand": "M0012", "table": "coil", "offset": 12, "width": 1},
    ]
    m = TagMap(map_override=fixture)
    assert m.lookup("D0007") == TagDef("D0007", ModbusTable.HOLDING_REGISTER, 7, 16)
    assert m.lookup("M0012") == TagDef("M0012", ModbusTable.COIL, 12, 1)


def test_tagmap_unknown_raises() -> None:
    m = TagMap(map_override=[{"operand": "D0007", "table": "holding_register", "offset": 7, "width": 16}])
    with pytest.raises(UnknownTagError) as exc_info:
        m.lookup("X9999")
    assert exc_info.value.tag == "X9999"


def test_tagmap_fc6a_default_profile() -> None:
    m = get_default_tagmap()
    assert m.profile == "fc6a"
    # Embedded map has at least these
    d7 = m.lookup("D0007")
    assert d7.operand == "D0007"
    assert d7.table == ModbusTable.HOLDING_REGISTER
    assert d7.offset == 7
    assert d7.width == 16


def test_tagmap_fc6a_known_operands() -> None:
    m = get_default_tagmap()
    m.lookup("M0012")
    m.lookup("Q0001")
    m.lookup("T0002.C")
    m.lookup("T0002.CV")
    m.lookup("T0002.PV")
    m.lookup("C0002.CV")


def test_tagmap_unknown_well_formed_raises() -> None:
    m = get_default_tagmap()
    with pytest.raises(UnknownTagError):
        m.lookup("D9999")


def test_tagmap_duplicate_override_raises() -> None:
    fixture = [
        {"operand": "D0007", "table": "holding_register", "offset": 7, "width": 16},
        {"operand": "D0007", "table": "coil", "offset": 0, "width": 1},
    ]
    with pytest.raises(ValueError, match="Duplicate operand"):
        TagMap(map_override=fixture)
