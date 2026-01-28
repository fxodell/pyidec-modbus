"""Tests for CLI module - value parsing and command structure."""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from pyidec_modbus.cli import (
    app,
    format_value,
    from_signed,
    parse_bool,
    parse_int,
    to_signed,
)

runner = CliRunner()


# ============================================================================
# Value Parsing Tests
# ============================================================================


class TestParseBool:
    """Test boolean value parsing."""

    def test_true_variants(self) -> None:
        """Test all valid true variants."""
        for val in ["true", "True", "TRUE", "1", "on", "ON", "yes", "YES"]:
            assert parse_bool(val) is True

    def test_false_variants(self) -> None:
        """Test all valid false variants."""
        for val in ["false", "False", "FALSE", "0", "off", "OFF", "no", "NO"]:
            assert parse_bool(val) is False

    def test_whitespace_handling(self) -> None:
        """Test whitespace is trimmed."""
        assert parse_bool("  true  ") is True
        assert parse_bool("  false  ") is False

    def test_invalid_values(self) -> None:
        """Test invalid boolean values raise ValueError."""
        with pytest.raises(ValueError, match="Invalid boolean value"):
            parse_bool("maybe")
        with pytest.raises(ValueError):
            parse_bool("2")
        with pytest.raises(ValueError):
            parse_bool("")


class TestParseInt:
    """Test integer value parsing."""

    def test_decimal_unsigned(self) -> None:
        """Test decimal unsigned integers."""
        assert parse_int("0") == 0
        assert parse_int("1234") == 1234
        assert parse_int("65535") == 65535

    def test_decimal_signed(self) -> None:
        """Test decimal signed integers."""
        assert parse_int("0", signed=True) == 0
        assert parse_int("1234", signed=True) == 1234
        assert parse_int("-100", signed=True) == -100
        assert parse_int("-32768", signed=True) == -32768
        assert parse_int("32767", signed=True) == 32767

    def test_hexadecimal(self) -> None:
        """Test hexadecimal parsing."""
        assert parse_int("0x00") == 0
        assert parse_int("0x10") == 16
        assert parse_int("0xFF") == 255
        assert parse_int("0xFFFF") == 65535

    def test_hexadecimal_signed(self) -> None:
        """Test hexadecimal with signed flag."""
        assert parse_int("0x7FFF", signed=True) == 32767
        with pytest.raises(ValueError, match="out of range"):
            parse_int("0x8000", signed=True)

    def test_whitespace_handling(self) -> None:
        """Test whitespace is trimmed."""
        assert parse_int("  1234  ") == 1234
        assert parse_int("  0xFF  ") == 255

    def test_unsigned_range_validation(self) -> None:
        """Test unsigned 16-bit range validation."""
        with pytest.raises(ValueError, match="out of range"):
            parse_int("-1")
        with pytest.raises(ValueError, match="out of range"):
            parse_int("65536")

    def test_signed_range_validation(self) -> None:
        """Test signed 16-bit range validation."""
        with pytest.raises(ValueError, match="out of range"):
            parse_int("-32769", signed=True)
        with pytest.raises(ValueError, match="out of range"):
            parse_int("32768", signed=True)

    def test_invalid_values(self) -> None:
        """Test invalid integer values."""
        with pytest.raises(ValueError):
            parse_int("abc")
        with pytest.raises(ValueError):
            parse_int("12.34")


class TestSignedConversion:
    """Test signed/unsigned conversion functions."""

    def test_to_signed(self) -> None:
        """Test unsigned to signed conversion."""
        assert to_signed(0) == 0
        assert to_signed(32767) == 32767
        assert to_signed(32768) == -32768
        assert to_signed(65535) == -1

    def test_from_signed(self) -> None:
        """Test signed to unsigned conversion."""
        assert from_signed(0) == 0
        assert from_signed(32767) == 32767
        assert from_signed(-32768) == 32768
        assert from_signed(-1) == 65535

    def test_round_trip(self) -> None:
        """Test round-trip conversion."""
        for val in [0, 100, 32767, -1, -100, -32768]:
            assert to_signed(from_signed(val)) == val


class TestFormatValue:
    """Test value formatting for display."""

    def test_bool_formatting(self) -> None:
        """Test boolean formatting."""
        assert format_value(True) == "true"
        assert format_value(False) == "false"

    def test_unsigned_int_formatting(self) -> None:
        """Test unsigned integer formatting."""
        assert format_value(0) == "0"
        assert format_value(1234) == "1234"
        assert format_value(65535) == "65535"

    def test_signed_int_formatting(self) -> None:
        """Test signed integer formatting."""
        assert format_value(0, signed=True) == "0"
        assert format_value(32767, signed=True) == "32767"
        assert format_value(32768, signed=True) == "-32768"
        assert format_value(65535, signed=True) == "-1"


# ============================================================================
# Command Structure Tests (with mocked client)
# ============================================================================


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_ping_command_default(mock_client_class: MagicMock) -> None:
    """Test ping command with default behavior."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client

    result = runner.invoke(app, ["--host", "192.168.1.10", "ping"])

    assert result.exit_code == 0
    assert "OK: Connected to 192.168.1.10:502" in result.stdout
    mock_client._get_client.assert_called_once()


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_ping_command_with_tag(mock_client_class: MagicMock) -> None:
    """Test ping command with specific tag."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client
    mock_client.read.return_value = 1234

    result = runner.invoke(app, ["--host", "192.168.1.10", "ping", "--tag", "D0007"])

    assert result.exit_code == 0
    assert "read D0007 = 1234" in result.stdout
    mock_client.read.assert_called_once_with("D0007")


def test_info_command_local() -> None:
    """Test info command without host (local metadata only)."""
    result = runner.invoke(app, ["info"])

    assert result.exit_code == 0
    assert "version:" in result.stdout.lower()
    assert "profile:" in result.stdout.lower()


def test_info_command_json() -> None:
    """Test info command with JSON output."""
    result = runner.invoke(app, ["info", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "version" in data
    assert "profile" in data


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_read_command(mock_client_class: MagicMock) -> None:
    """Test read command."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client
    mock_client.read.return_value = 1234

    result = runner.invoke(app, ["--host", "192.168.1.10", "read", "D0007"])

    assert result.exit_code == 0
    assert "1234" in result.stdout
    mock_client.read.assert_called_once_with("D0007")


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_read_command_json(mock_client_class: MagicMock) -> None:
    """Test read command with JSON output."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client
    mock_client.read.return_value = 1234

    result = runner.invoke(app, ["--host", "192.168.1.10", "read", "D0007", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["tag"] == "D0007"
    assert data["value"] == 1234


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_read_command_signed(mock_client_class: MagicMock) -> None:
    """Test read command with signed interpretation."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client
    mock_client.read.return_value = 65535

    result = runner.invoke(app, ["--host", "192.168.1.10", "read", "D0007", "--signed"])

    assert result.exit_code == 0
    assert "-1" in result.stdout


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_write_command_bool(mock_client_class: MagicMock) -> None:
    """Test write command with boolean value."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client

    result = runner.invoke(app, ["--host", "192.168.1.10", "write", "Q0001", "true"])

    assert result.exit_code == 0
    assert "OK: Wrote Q0001 = true" in result.stdout
    mock_client.write.assert_called_once_with("Q0001", True)


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_write_command_int(mock_client_class: MagicMock) -> None:
    """Test write command with integer value."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client

    result = runner.invoke(app, ["--host", "192.168.1.10", "write", "D0007", "1234"])

    assert result.exit_code == 0
    assert "OK: Wrote D0007 = 1234" in result.stdout
    mock_client.write.assert_called_once_with("D0007", 1234)


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_write_command_signed(mock_client_class: MagicMock) -> None:
    """Test write command with signed value."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client

    result = runner.invoke(app, ["--host", "192.168.1.10", "write", "D0007", "-100", "--signed"])

    assert result.exit_code == 0
    # -100 signed = 65436 unsigned
    mock_client.write.assert_called_once_with("D0007", 65436)


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_explain_command(mock_client_class: MagicMock) -> None:
    """Test explain command."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.explain.return_value = {
        "normalized_tag": "D0007",
        "table": "holding_register",
        "offset": 6,
        "width": 16,
        "function_used": "read_holding_registers",
    }

    result = runner.invoke(app, ["explain", "d7"])

    assert result.exit_code == 0
    assert "D0007" in result.stdout
    assert "holding_register" in result.stdout
    mock_client.explain.assert_called_once_with("d7")


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_read_many_command(mock_client_class: MagicMock) -> None:
    """Test read-many command."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client
    mock_client.read_many.return_value = {"D0007": 1234, "M0012": True}

    result = runner.invoke(app, ["--host", "192.168.1.10", "read-many", "D0007", "M0012"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["D0007"] == 1234
    assert data["M0012"] is True
    mock_client.read_many.assert_called_once_with(["D0007", "M0012"])


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_poll_command_once(mock_client_class: MagicMock) -> None:
    """Test poll command with --once flag."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client
    mock_client.read_many.return_value = {"D0007": 1234}

    result = runner.invoke(app, ["--host", "192.168.1.10", "poll", "D0007", "--once"])

    assert result.exit_code == 0
    assert "D0007=1234" in result.stdout
    mock_client.read_many.assert_called_once_with(["D0007"])


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_poll_command_json_once(mock_client_class: MagicMock) -> None:
    """Test poll command with JSON format and --once flag."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client
    mock_client.read_many.return_value = {"D0007": 1234}

    result = runner.invoke(app, ["--host", "192.168.1.10", "poll", "D0007", "--once", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "timestamp" in data
    assert "values" in data
    assert data["values"]["D0007"] == 1234


@patch("pyidec_modbus.cli.IDECModbusClient")
def test_poll_command_csv_once(mock_client_class: MagicMock) -> None:
    """Test poll command with CSV format and --once flag."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.__enter__.return_value = mock_client
    mock_client.read_many.return_value = {"D0007": 1234, "M0012": True}

    result = runner.invoke(app, ["--host", "192.168.1.10", "poll", "D0007", "M0012", "--once", "--format", "csv"])

    assert result.exit_code == 0
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 2  # header + data
    assert lines[0] == "timestamp,D0007,M0012"
    assert "1234" in lines[1]
    assert "True" in lines[1]


def test_command_help() -> None:
    """Test that help text is available for all commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ping" in result.stdout
    assert "info" in result.stdout
    assert "read" in result.stdout
    assert "write" in result.stdout
    assert "explain" in result.stdout
    assert "read-many" in result.stdout
    assert "poll" in result.stdout


def test_version_flag() -> None:
    """Test --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "pyidec-modbus" in result.stdout
