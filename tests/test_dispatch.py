"""Tests for pymodbus dispatch and read_many coalescing (mocked client)."""

from unittest.mock import MagicMock, patch

import pytest

from pyidec_modbus import IDECModbusClient
from pyidec_modbus.tagmap import TagMap
from pyidec_modbus.types import ModbusTable


@pytest.fixture
def mock_modbus_client() -> MagicMock:
    client = MagicMock()
    client.connect.return_value = True
    client.read_coils.return_value = MagicMock(isError=lambda: False, bits=[True])
    client.read_discrete_inputs.return_value = MagicMock(isError=lambda: False, bits=[False])
    client.read_input_registers.return_value = MagicMock(isError=lambda: False, registers=[100])
    client.read_holding_registers.return_value = MagicMock(isError=lambda: False, registers=[42])
    client.write_coil.return_value = MagicMock(isError=lambda: False)
    client.write_register.return_value = MagicMock(isError=lambda: False)
    return client


@pytest.fixture
def tagmap_fixture() -> TagMap:
    """TagMap with known layout for coalescing tests."""
    entries = [
        {"operand": "D0007", "table": "holding_register", "offset": 7, "width": 16},
        {"operand": "D0008", "table": "holding_register", "offset": 8, "width": 16},
        {"operand": "D0010", "table": "holding_register", "offset": 10, "width": 16},
        {"operand": "M0012", "table": "coil", "offset": 12, "width": 1},
        {"operand": "M0013", "table": "coil", "offset": 13, "width": 1},
    ]
    return TagMap(map_override=entries)


def test_read_dispatches_to_read_coils(tagmap_fixture: TagMap, mock_modbus_client: MagicMock) -> None:
    with patch("pyidec_modbus.client.ModbusTcpClient", return_value=mock_modbus_client):
        plc = IDECModbusClient(host="127.0.0.1", map_override=tagmap_fixture)
        plc._client = mock_modbus_client
        plc._get_client = lambda: mock_modbus_client
        v = plc.read("M0012")
    assert v is True
    mock_modbus_client.read_coils.assert_called_once()
    args = mock_modbus_client.read_coils.call_args
    assert args[0][0] == 12
    assert args[1].get("count") == 1 or args[0][1] == 1


def test_read_dispatches_to_read_holding_registers(tagmap_fixture: TagMap, mock_modbus_client: MagicMock) -> None:
    with patch("pyidec_modbus.client.ModbusTcpClient", return_value=mock_modbus_client):
        plc = IDECModbusClient(host="127.0.0.1", map_override=tagmap_fixture)
        plc._client = mock_modbus_client
        plc._get_client = lambda: mock_modbus_client
        v = plc.read("D0007")
    assert v == 42
    mock_modbus_client.read_holding_registers.assert_called_once()
    args = mock_modbus_client.read_holding_registers.call_args
    assert args[0][0] == 7


def test_write_dispatches_to_write_coil(tagmap_fixture: TagMap, mock_modbus_client: MagicMock) -> None:
    with patch("pyidec_modbus.client.ModbusTcpClient", return_value=mock_modbus_client):
        plc = IDECModbusClient(host="127.0.0.1", map_override=tagmap_fixture)
        plc._client = mock_modbus_client
        plc._get_client = lambda: mock_modbus_client
        plc.write("M0012", True)
    mock_modbus_client.write_coil.assert_called_once()
    args = mock_modbus_client.write_coil.call_args
    assert args[0][0] == 12
    assert args[0][1] is True


def test_write_dispatches_to_write_register(tagmap_fixture: TagMap, mock_modbus_client: MagicMock) -> None:
    with patch("pyidec_modbus.client.ModbusTcpClient", return_value=mock_modbus_client):
        plc = IDECModbusClient(host="127.0.0.1", map_override=tagmap_fixture)
        plc._client = mock_modbus_client
        plc._get_client = lambda: mock_modbus_client
        plc.write("D0007", 100)
    mock_modbus_client.write_register.assert_called_once()
    args = mock_modbus_client.write_register.call_args
    assert args[0][0] == 7
    assert args[0][1] == 100


def test_read_many_coalesces_contiguous(tagmap_fixture: TagMap, mock_modbus_client: MagicMock) -> None:
    # D0007,D0008 contiguous; D0010 separate -> 2 read_holding_registers calls
    mock_modbus_client.read_holding_registers.side_effect = [
        MagicMock(isError=lambda: False, registers=[40, 41]),
        MagicMock(isError=lambda: False, registers=[42]),
    ]
    with patch("pyidec_modbus.client.ModbusTcpClient", return_value=mock_modbus_client):
        plc = IDECModbusClient(host="127.0.0.1", map_override=tagmap_fixture)
        plc._client = mock_modbus_client
        plc._get_client = lambda: mock_modbus_client
        result = plc.read_many(["D0007", "D0008", "D0010"])
    assert result["D0007"] == 40
    assert result["D0008"] == 41
    assert result["D0010"] == 42
    assert mock_modbus_client.read_holding_registers.call_count == 2


def test_read_many_groups_by_table(tagmap_fixture: TagMap, mock_modbus_client: MagicMock) -> None:
    mock_modbus_client.read_coils.return_value = MagicMock(isError=lambda: False, bits=[True, False])
    mock_modbus_client.read_holding_registers.return_value = MagicMock(
        isError=lambda: False,
        registers=[100],
    )
    with patch("pyidec_modbus.client.ModbusTcpClient", return_value=mock_modbus_client):
        plc = IDECModbusClient(host="127.0.0.1", map_override=tagmap_fixture)
        plc._client = mock_modbus_client
        plc._get_client = lambda: mock_modbus_client
        result = plc.read_many(["M0012", "M0013", "D0007"])
    assert result["M0012"] is True
    assert result["M0013"] is False
    assert result["D0007"] == 100
    mock_modbus_client.read_coils.assert_called_once()
    mock_modbus_client.read_holding_registers.assert_called_once()
