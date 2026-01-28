"""Core data model: Modbus table enum, PLC profile, TagDef, and ExplainInfo."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ModbusTable(str, Enum):
    """Modbus table types used for pymodbus dispatch."""

    COIL = "coil"
    DISCRETE_INPUT = "discrete_input"
    INPUT_REGISTER = "input_register"
    HOLDING_REGISTER = "holding_register"


class PLCProfile(str, Enum):
    """Supported PLC profiles (extensible)."""

    FC6A = "fc6a"
    # FC5A = "fc5a"  # future


@dataclass(frozen=True)
class TagDef:
    """Normalized tag definition: table, offset, width; no Modbus reference numbers."""

    operand: str
    table: ModbusTable
    offset: int
    width: int
    meta: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError(f"offset must be >= 0, got {self.offset}")
        if self.width not in (1, 16):
            raise ValueError(f"width must be 1 or 16, got {self.width}")


@dataclass(frozen=True)
class ExplainInfo:
    """Result of client.explain(tag): normalized tag, table, offset, function used."""

    normalized_tag: str
    table: ModbusTable
    offset: int
    width: int
    function_used: str
