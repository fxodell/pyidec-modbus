"""TagMap: load embedded JSON via importlib.resources, profile selection, O(1) lookup."""

import json
import logging
from importlib import resources
from typing import Any

from .errors import UnknownTagError
from .types import ModbusTable, TagDef

logger = logging.getLogger(__name__)

_PROFILE_RESOURCE: dict[str, str] = {
    "fc6a": "pyidec_modbus.data.fc6a_tagmap",
    # "fc5a": "pyidec_modbus.data.fc5a_tagmap",
}


def _ref_to_table_offset(ref: int) -> tuple[ModbusTable, int]:
    """Convert Modbus reference number to (table, 0-based offset). Not exposed in public API."""
    if 1 <= ref <= 99_999:
        return ModbusTable.COIL, ref - 1
    if 100_001 <= ref <= 199_999:
        return ModbusTable.DISCRETE_INPUT, ref - 100_001
    if 300_001 <= ref <= 399_999:
        return ModbusTable.INPUT_REGISTER, ref - 300_001
    if 400_001 <= ref <= 499_999:
        return ModbusTable.HOLDING_REGISTER, ref - 400_001
    raise ValueError(f"Invalid Modbus reference: {ref}")


def _parse_entry(raw: dict[str, Any]) -> TagDef:
    """Build TagDef from a JSON entry (operand, table, offset, width, meta)."""
    operand = raw["operand"]
    table_str = raw["table"]
    try:
        table = ModbusTable(table_str)
    except ValueError:
        raise ValueError(f"Unknown table {table_str!r} for operand {operand!r}")
    offset = int(raw["offset"])
    width = int(raw["width"])
    meta = raw.get("meta")
    if meta is not None and not isinstance(meta, dict):
        meta = None  # tolerate malformed JSON
    return TagDef(operand=operand, table=table, offset=offset, width=width, meta=meta)


class TagMap:
    """
    In-memory map of normalized operands to TagDef. Loaded from packaged JSON.
    Supports profile selection (default fc6a); extensible for fc5a etc.
    """

    def __init__(self, profile: str = "fc6a", map_override: list[dict[str, Any]] | None = None) -> None:
        """
        Load tag map for the given profile, or use map_override (list of entry dicts).
        Default profile is fc6a.
        """
        self._profile = profile.lower()
        self._by_operand: dict[str, TagDef] = {}

        if map_override is not None:
            for entry in map_override:
                tag_def = _parse_entry(entry)
                if tag_def.operand in self._by_operand:
                    raise ValueError(f"Duplicate operand in map: {tag_def.operand}")
                self._by_operand[tag_def.operand] = tag_def
            logger.debug("TagMap loaded from override: %d entries", len(self._by_operand))
            return

        resource_name = _PROFILE_RESOURCE.get(self._profile)
        if not resource_name:
            raise ValueError(f"Unknown profile: {profile!r}")

        # Load from package resource: e.g. pyidec_modbus.data.fc6a_tagmap -> fc6a_tagmap.json
        pkg = resource_name.rsplit(".", 1)[0]  # pyidec_modbus.data
        name = resource_name.rsplit(".", 1)[-1]  # fc6a_tagmap
        json_name = f"{name}.json"
        try:
            with resources.files(pkg).joinpath(json_name).open("r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Tag map resource not found: {pkg}/{json_name}") from None

        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict) and "entries" in data:
            entries = data["entries"]
        elif isinstance(data, dict):
            entries = list(data.values())
        else:
            entries = []

        for entry in entries:
            if isinstance(entry, dict):
                tag_def = _parse_entry(entry)
            else:
                continue
            if tag_def.operand in self._by_operand:
                raise ValueError(f"Duplicate operand in map: {tag_def.operand}")
            self._by_operand[tag_def.operand] = tag_def

        logger.debug("TagMap loaded for profile %s: %d entries", self._profile, len(self._by_operand))

    def lookup(self, tag: str) -> TagDef:
        """Return TagDef for the normalized operand; raise UnknownTagError if not in map."""
        if tag not in self._by_operand:
            raise UnknownTagError(tag)
        return self._by_operand[tag]

    def __len__(self) -> int:
        return len(self._by_operand)

    @property
    def profile(self) -> str:
        return self._profile


def get_default_tagmap(profile: str = "fc6a") -> TagMap:
    """Load and return the default TagMap for the given profile (default fc6a)."""
    return TagMap(profile=profile)
