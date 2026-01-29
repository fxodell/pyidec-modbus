"""pyidec-modbus: IDEC operand read/write via pymodbus using native tag names."""

__version__ = "0.1.1"

from .client import IDECModbusClient
from .errors import InvalidTagError, ModbusIOError, PyIDECModbusError, UnknownTagError
from .normalize import normalize_tag
from .tagmap import TagMap, get_default_tagmap
from .types import ExplainInfo, ModbusTable, PLCProfile, TagDef

__all__ = [
    "__version__",
    "IDECModbusClient",
    "InvalidTagError",
    "ModbusIOError",
    "PyIDECModbusError",
    "UnknownTagError",
    "normalize_tag",
    "TagMap",
    "get_default_tagmap",
    "ExplainInfo",
    "ModbusTable",
    "PLCProfile",
    "TagDef",
]
