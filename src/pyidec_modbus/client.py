"""IDECModbusClient: high-level wrapper over pymodbus with tag-name API and block coalescing."""

import logging
import time
from collections import defaultdict
from typing import Any, Iterator

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException as PymodbusException

from .errors import InvalidTagError, ModbusIOError, UnknownTagError
from .normalize import normalize_tag
from .tagmap import TagMap, get_default_tagmap
from .types import ExplainInfo, ModbusTable, TagDef

logger = logging.getLogger(__name__)


def _coalesce_ranges(offset_to_tag: dict[int, str]) -> list[tuple[int, int, list[tuple[int, str]]]]:
    """
    Group (offset, tag) into contiguous ranges. Returns list of (start_offset, count, [(offset, tag), ...]).
    """
    if not offset_to_tag:
        return []
    sorted_offsets = sorted(offset_to_tag.keys())
    ranges: list[tuple[int, int, list[tuple[int, str]]]] = []
    start = sorted_offsets[0]
    prev = start
    group: list[tuple[int, str]] = [(start, offset_to_tag[start])]
    for off in sorted_offsets[1:]:
        if off == prev + 1:
            group.append((off, offset_to_tag[off]))
            prev = off
        else:
            ranges.append((start, len(group), group))
            start = off
            prev = off
            group = [(off, offset_to_tag[off])]
    ranges.append((start, len(group), group))
    return ranges


class IDECModbusClient:
    """
    High-level Modbus client that reads/writes by IDEC tag names (e.g. D0007, M0012, T0002.PV).
    Wraps pymodbus TCP client; uses embedded tag map (FC6A default) and caches TagDef lookups.
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        profile: str = "fc6a",
        map_override: TagMap | None = None,
        timeout: float = 3.0,
        retries: int = 3,
    ) -> None:
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = timeout
        self._retries = retries
        self._tagmap = map_override if map_override is not None else get_default_tagmap(profile)
        self._client: ModbusTcpClient | None = None
        self._cache: dict[str, TagDef] = {}

    def _get_client(self) -> ModbusTcpClient:
        if self._client is None:
            self._client = ModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=self._timeout,
                retries=self._retries,
            )
            if not self._client.connect():
                raise ModbusIOError(
                    f"Failed to connect to {self._host}:{self._port}",
                    cause=None,
                )
        return self._client

    def _resolve(self, tag: str) -> TagDef:
        normalized = normalize_tag(tag)
        if normalized not in self._cache:
            self._cache[normalized] = self._tagmap.lookup(normalized)
        return self._cache[normalized]

    def _read_one(self, defn: TagDef) -> bool | int:
        client = self._get_client()
        addr = defn.offset
        count = 1  # one coil or one 16-bit register
        if defn.table == ModbusTable.COIL:
            rr = client.read_coils(addr, count=count, device_id=self._unit_id)
        elif defn.table == ModbusTable.DISCRETE_INPUT:
            rr = client.read_discrete_inputs(addr, count=count, device_id=self._unit_id)
        elif defn.table == ModbusTable.INPUT_REGISTER:
            rr = client.read_input_registers(addr, count=count, device_id=self._unit_id)
        elif defn.table == ModbusTable.HOLDING_REGISTER:
            rr = client.read_holding_registers(addr, count=count, device_id=self._unit_id)
        else:
            raise ModbusIOError(f"Unknown table: {defn.table}", table=defn.table.value, offset=addr)

        if rr.isError():
            raise ModbusIOError(
                str(rr),
                tag=defn.operand,
                table=defn.table.value,
                offset=addr,
                cause=getattr(rr, "exception", None),
            )
        if defn.table in (ModbusTable.COIL, ModbusTable.DISCRETE_INPUT):
            bits = getattr(rr, "bits", None)
            if not bits or len(bits) < 1:
                raise ModbusIOError(
                    "Empty bit response",
                    tag=defn.operand,
                    table=defn.table.value,
                    offset=addr,
                )
            return bool(rr.bits[0])
        registers = getattr(rr, "registers", None)
        if not registers or len(registers) < 1:
            raise ModbusIOError(
                "Empty register response",
                tag=defn.operand,
                table=defn.table.value,
                offset=addr,
            )
        return int(rr.registers[0])

    def _write_one(self, defn: TagDef, value: bool | int) -> None:
        client = self._get_client()
        addr = defn.offset
        if defn.table == ModbusTable.COIL:
            rr = client.write_coil(addr, bool(value), device_id=self._unit_id)
        elif defn.table == ModbusTable.HOLDING_REGISTER:
            rr = client.write_register(addr, int(value), device_id=self._unit_id)
        else:
            raise ModbusIOError(
                f"Write not supported for table {defn.table.value}",
                tag=defn.operand,
                table=defn.table.value,
                offset=addr,
            )
        if rr.isError():
            raise ModbusIOError(
                str(rr),
                tag=defn.operand,
                table=defn.table.value,
                offset=addr,
                cause=getattr(rr, "exception", None),
            )

    def connect(self) -> None:
        """Establish TCP connection to the PLC."""
        self._get_client()

    def close(self) -> None:
        """Close the TCP connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.warning("Error closing Modbus client: %s", e)
            self._client = None

    def __enter__(self) -> "IDECModbusClient":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def read(self, tag: str) -> bool | int:
        """Read a single tag; returns bool for bits, int for registers."""
        defn = self._resolve(tag)
        return self._read_one(defn)

    def write(self, tag: str, value: bool | int) -> None:
        """Write a single tag (coils and holding registers only)."""
        defn = self._resolve(tag)
        self._write_one(defn, value)

    def read_many(self, tags: list[str]) -> dict[str, bool | int]:
        """
        Read multiple tags. Groups by table and coalesces contiguous offsets into
        minimal pymodbus read calls, then demultiplexes results per tag.
        """
        if not tags:
            return {}
        # Resolve all; group by table (offset -> operand); track original tag per operand
        by_table: dict[ModbusTable, dict[int, str]] = defaultdict(dict)
        operand_to_originals: dict[str, list[str]] = defaultdict(list)
        for t in tags:
            defn = self._resolve(t)
            operand_to_originals[defn.operand].append(t)
            by_table[defn.table][defn.offset] = defn.operand

        out: dict[str, bool | int] = {}
        client = self._get_client()

        for table, offset_to_operand in by_table.items():
            ranges = _coalesce_ranges(offset_to_operand)
            for start, count, group in ranges:
                try:
                    if table == ModbusTable.COIL:
                        rr = client.read_coils(start, count=count, device_id=self._unit_id)
                        if rr.isError():
                            raise ModbusIOError(str(rr), tag=group[0][1], table=table.value, offset=start)
                        bits = getattr(rr, "bits", None)
                        if not bits or len(bits) < count:
                            raise ModbusIOError(
                                "Short bit response",
                                tag=group[0][1],
                                table=table.value,
                                offset=start,
                            )
                        for i, (_off, op) in enumerate(group):
                            val = bool(rr.bits[i])
                            for orig in operand_to_originals[op]:
                                out[orig] = val
                    elif table == ModbusTable.DISCRETE_INPUT:
                        rr = client.read_discrete_inputs(start, count=count, device_id=self._unit_id)
                        if rr.isError():
                            raise ModbusIOError(str(rr), tag=group[0][1], table=table.value, offset=start)
                        bits = getattr(rr, "bits", None)
                        if not bits or len(bits) < count:
                            raise ModbusIOError(
                                "Short bit response",
                                tag=group[0][1],
                                table=table.value,
                                offset=start,
                            )
                        for i, (_off, op) in enumerate(group):
                            val = bool(rr.bits[i])
                            for orig in operand_to_originals[op]:
                                out[orig] = val
                    elif table == ModbusTable.INPUT_REGISTER:
                        rr = client.read_input_registers(start, count=count, device_id=self._unit_id)
                        if rr.isError():
                            raise ModbusIOError(str(rr), tag=group[0][1], table=table.value, offset=start)
                        registers = getattr(rr, "registers", None)
                        if not registers or len(registers) < count:
                            raise ModbusIOError(
                                "Short register response",
                                tag=group[0][1],
                                table=table.value,
                                offset=start,
                            )
                        for i, (_off, op) in enumerate(group):
                            val = int(rr.registers[i])
                            for orig in operand_to_originals[op]:
                                out[orig] = val
                    elif table == ModbusTable.HOLDING_REGISTER:
                        rr = client.read_holding_registers(start, count=count, device_id=self._unit_id)
                        if rr.isError():
                            raise ModbusIOError(str(rr), tag=group[0][1], table=table.value, offset=start)
                        registers = getattr(rr, "registers", None)
                        if not registers or len(registers) < count:
                            raise ModbusIOError(
                                "Short register response",
                                tag=group[0][1],
                                table=table.value,
                                offset=start,
                            )
                        for i, (_off, op) in enumerate(group):
                            val = int(rr.registers[i])
                            for orig in operand_to_originals[op]:
                                out[orig] = val
                except PymodbusException as e:
                    raise ModbusIOError(str(e), tag=group[0][1], table=table.value, offset=start, cause=e) from e
        return out

    def explain(self, tag: str) -> dict[str, Any]:
        """Return normalized tag, table, offset, and function used (for debugging)."""
        norm = normalize_tag(tag)
        defn = self._resolve(tag)
        func = {
            ModbusTable.COIL: "read_coils",
            ModbusTable.DISCRETE_INPUT: "read_discrete_inputs",
            ModbusTable.INPUT_REGISTER: "read_input_registers",
            ModbusTable.HOLDING_REGISTER: "read_holding_registers",
        }.get(defn.table, "unknown")
        info = ExplainInfo(
            normalized_tag=norm,
            table=defn.table,
            offset=defn.offset,
            width=defn.width,
            function_used=func,
        )
        return {
            "normalized_tag": info.normalized_tag,
            "table": info.table.value,
            "offset": info.offset,
            "width": info.width,
            "function_used": info.function_used,
        }

    def poll_iter(
        self,
        tags: list[str],
        interval_s: float,
    ) -> Iterator[dict[str, bool | int]]:
        """
        Yield read_many(tags) every interval_s seconds indefinitely.
        Cache ensures resolved TagDefs are reused each cycle.
        """
        while True:
            yield self.read_many(tags)
            time.sleep(interval_s)

    def __getitem__(self, tag: str) -> bool | int:
        return self.read(tag)

    def __setitem__(self, tag: str, value: bool | int) -> None:
        self.write(tag, value)
