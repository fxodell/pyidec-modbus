# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Production-ready Python package wrapping [pymodbus](https://github.com/pymodbus-dev/pymodbus) for IDEC PLC operands by native tag names (D, M, I, Q, T, C). Reads/writes PLC tags without exposing raw Modbus addresses. FC6A profile embedded as JSON resource.

## Development Commands

### Installation
```bash
# Standard install
pip install -e .

# Dev install (includes openpyxl for tagmap generation)
pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_normalize.py
```

### Regenerating Tag Map (Build-Time Only)
```bash
# Place FC6A_ModbusSlave_AddressMap_Xml.xlsx in data/ then:
python tools/generate_map_fc6a.py [path/to/file.xlsx]

# Output: src/pyidec_modbus/data/fc6a_tagmap.json (embedded in package)
```

## Architecture

### Three-Layer Design

1. **Normalization Layer** (`normalize.py`)
   - Converts user input (e.g., `d7`, `M12`, `T2`) to canonical form (`D0007`, `M0012`, `T0002.CV`)
   - Timer/Counter operands default to `.CV` suffix if not specified
   - Validates syntax before lookup

2. **Tag Map Layer** (`tagmap.py`)
   - Loads embedded JSON resource via `importlib.resources`
   - Maps normalized operands to `TagDef` (table, offset, width)
   - Profile-based (default: fc6a; extensible to fc5a)
   - O(1) lookup with in-memory dict cache

3. **Client Layer** (`client.py`)
   - Wraps pymodbus TCP client with tag-name API
   - **Block coalescing**: `read_many()` groups tags by table, coalesces contiguous offsets into minimal Modbus calls
   - Context manager for automatic connection/cleanup
   - Cache of resolved TagDef to avoid repeated lookups

### Data Flow Example
```
User: plc.read("d7")
  ↓
normalize_tag("d7") → "D0007"
  ↓
tagmap.lookup("D0007") → TagDef(table=HOLDING_REGISTER, offset=6, width=16)
  ↓
client.read_holding_registers(addr=6, count=1)
  ↓
Return int value
```

### Key Types (`types.py`)
- `ModbusTable`: enum for COIL, DISCRETE_INPUT, INPUT_REGISTER, HOLDING_REGISTER
- `TagDef`: frozen dataclass mapping operand to table/offset/width
- `ExplainInfo`: debugging info returned by `client.explain()`

### Error Hierarchy (`errors.py`)
- `PyIDECModbusError` (base)
  - `InvalidTagError`: malformed tag syntax (e.g., `D99999`)
  - `UnknownTagError`: well-formed but not in tag map (e.g., `D9000` if not in fc6a)
  - `ModbusIOError`: connection or Modbus protocol failure

## Modbus Address Mapping

The package hides Modbus reference numbers from users. Internally:
- Reference 1–99,999 → COIL (0-based offset: ref - 1)
- Reference 100,001–199,999 → DISCRETE_INPUT (offset: ref - 100,001)
- Reference 300,001–399,999 → INPUT_REGISTER (offset: ref - 300,001)
- Reference 400,001–499,999 → HOLDING_REGISTER (offset: ref - 400,001)

This conversion is only used by `generate_map_fc6a.py` at build time.

## Cursor Rules (Inherited)

Always read:
- `docs/CONTEXT.md` and `docs/TASKS.md` before making changes
- `.cursorrules.md` and `.cursor/rules/guardrails.md` for repository-wide rules

Key constraints:
- Minimal diffs only; no architecture changes without ADR in `docs/DECISIONS.md`
- Match existing code style and patterns exactly
- Never guess file paths, URLs, or config values—read first
- Keep changes reversible; prefer edits over rewrites
- No throwaway files in repo root (use `/scratch` if needed)
- Add tests or provide manual test steps after logic changes

## Important Notes

- **Runtime never touches Excel file**: tagmap is embedded JSON loaded via `importlib.resources`
- **No external config required**: FC6A map is bundled; users never edit JSON
- **Supported operands**: D (data register), M (internal relay), I (input), Q (output), T (timer .C/.CV/.PV), C (counter .C/.CV/.PV)
- **Python 3.11+ required**: uses modern type hints and `importlib.resources.files()`
- **Context manager recommended**: `with IDECModbusClient(...) as plc:` ensures connection cleanup
