# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Production-ready Python package wrapping [pymodbus](https://github.com/pymodbus-dev/pymodbus) for IDEC PLC operands by native tag names (D, M, I, Q, T, C). Reads/writes PLC tags without exposing raw Modbus addresses. FC6A profile embedded as JSON resource.

## Development Commands

### Installation
```bash
# Standard install
pip install -e .

# With CLI support
pip install -e ".[cli]"

# Dev install (includes openpyxl for tagmap generation)
pip install -e ".[dev]"

# All extras
pip install -e ".[cli,dev]"
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

## CLI Architecture

The package includes a production-ready CLI (`cli.py`) built with Typer:

### Commands (7 total)
1. **ping** - Test connectivity (minimal Modbus read or specific tag)
2. **info** - Show version/profile, optionally test connectivity
3. **read** - Single tag read with --signed support
4. **write** - Single tag write (bool/int parsing, --signed support)
5. **explain** - Tag mapping info (NO CONNECTION REQUIRED - uses tagmap directly)
6. **read-many** - Batch reads with --partial flag for error handling
7. **poll** - Continuous monitoring with text/json/csv formats

### CLI Design Patterns

**Environment Variables**:
- Typer's `envvar` parameter handles env vars automatically
- Supported: `PYIDEC_HOST`, `PYIDEC_PORT`, `PYIDEC_UNIT_ID`, `PYIDEC_TIMEOUT`, `PYIDEC_RETRIES`, `PYIDEC_PROFILE`
- CLI args override env vars

**Exit Codes**:
- 0: Success
- 2: User input error (invalid tag/value)
- 3: Connection/Modbus error
- 4: Unexpected error

**Output Formats**:
- Text: Human-readable (default for most commands)
- JSON: Machine-readable (--json flag)
- CSV: For poll command (--format csv)

**Optimizations**:
- `explain` command: Uses tagmap directly, no client connection needed
- `read-many --partial`: Validates tags first, then batch reads valid ones (preserves coalescing)
- Poll: Reuses client connection across iterations

**Value Parsing**:
- Bool: true/false, 1/0, on/off, yes/no (case-insensitive)
- Int: Decimal or hex (0x prefix), validated to 16-bit range
- Signed: `--signed` flag converts to/from signed 16-bit

**Error Handling**:
- All commands have try/except with proper exit codes
- `--verbose` flag enables debug logging and stack traces
- Clear error messages to stderr

### CLI Testing Guidelines

- Use `typer.testing.CliRunner` for command tests
- Mock `IDECModbusClient` for integration tests
- Test value parsing functions directly (pure functions)
- `explain` command doesn't need mocking (uses tagmap directly)
- Test all exit codes and error paths

## Important Notes

- **Runtime never touches Excel file**: tagmap is embedded JSON loaded via `importlib.resources`
- **No external config required**: FC6A map is bundled; users never edit JSON
- **Supported operands**: D (data register), M (internal relay), I (input), Q (output), T (timer .C/.CV/.PV), C (counter .C/.CV/.PV)
- **Python 3.11+ required**: uses modern type hints and `importlib.resources.files()`
- **Context manager recommended**: `with IDECModbusClient(...) as plc:` ensures connection cleanup
- **CLI vs Library**: CLI is optional extra (`pip install ".[cli]"`), library has no CLI dependencies
