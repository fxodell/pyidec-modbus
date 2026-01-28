# pyidec-modbus

Production-ready Python package that wraps [pymodbus](https://github.com/pymodbus-dev/pymodbus) and lets you read/write IDEC FC6A operands (D, M, I, Q, R, T, C, etc.) by **native tag names** — not raw Modbus addresses.

- **No runtime dependency on spreadsheets or XML.** The FC6A tag map is embedded in the package as a JSON resource and loaded via `importlib.resources`.
- **Default profile: FC6A.** Other profiles (e.g. FC5A) can be added later without breaking the API.
- **Python 3.11+**, full type hints, clear exceptions (`InvalidTagError`, `UnknownTagError`, `ModbusIOError`).

## Installation

```bash
pip install -e .

# With CLI support:
pip install -e ".[cli]"

# With dev tools (openpyxl for regenerating the tag map):
pip install -e ".[dev]"

# All extras:
pip install -e ".[cli,dev]"
```

## Quick example

```python
from pyidec_modbus import IDECModbusClient

with IDECModbusClient(host="192.168.1.10", port=502, unit_id=1) as plc:
    # Read/write by IDEC names
    val = plc.read("D0007")           # data register
    plc.write("M0012", True)           # internal relay
    preset = plc.read("T0002.PV")      # timer preset

    # Syntactic sugar
    x = plc["D0007"]
    plc["Q0001"] = True

    # Batch read (coalesced Modbus calls)
    snapshot = plc.read_many(["D0007", "M0012", "T0002.CV"])
```

## Supported operands

- **D** – Data Register (holding register)
- **M** – Internal Relay (coil)
- **I** – Input (discrete input)
- **Q** – Output (coil)
- **T####.C / .CV / .PV** – Timer contact, current value, preset
- **C####.C / .CV / .PV** – Counter contact, current value, preset

Input is normalized: `d7` → `D0007`, `T2.PV` → `T0002.PV`; timers/counters without a suffix default to `.CV`.

## Embedded tag map

The FC6A map lives in `src/pyidec_modbus/data/fc6a_tagmap.json` and is installed with the package. Runtime never touches the Excel file or the generator.

To **regenerate** the embedded map from the official IDEC spreadsheet (build-time only):

1. Place `FC6A_ModbusSlave_AddressMap_Xml.xlsx` in `data/` or pass its path.
2. Install dev extra: `pip install -e ".[dev]"`
3. Run: `python tools/generate_map_fc6a.py [path/to/file.xlsx]`

Output is written to `src/pyidec_modbus/data/fc6a_tagmap.json`. The generator is not required at runtime.

## API summary

- `IDECModbusClient(host, port=502, unit_id=1, profile="fc6a", map_override=None, timeout=3.0, retries=3)`
- `read(tag: str) -> bool | int`
- `write(tag: str, value: bool | int) -> None`
- `read_many(tags: list[str]) -> dict[str, bool | int]` — groups by table, coalesces contiguous reads
- `explain(tag: str) -> dict` — normalized tag, table, offset, function used
- `poll_iter(tags, interval_s)` — iterator yielding `read_many` snapshots every `interval_s` seconds
- `plc[tag]` / `plc[tag] = value` — get/set sugar

## CLI

A production-ready CLI is available via the `pyidec` command:

```bash
# Install with CLI support
pip install -e ".[cli]"

# Test connectivity
pyidec --host 192.168.1.10 ping

# Read a tag
pyidec --host 192.168.1.10 read D0007

# Write a tag
pyidec --host 192.168.1.10 write Q0001 true

# Batch read
pyidec --host 192.168.1.10 read-many D0007 D0008 M0012

# Poll tags continuously
pyidec --host 192.168.1.10 poll D0007 M0012 --interval 1.0 --format json

# Explain tag mapping
pyidec explain D0007
```

See [examples/cli_examples.md](examples/cli_examples.md) for comprehensive CLI documentation.

**Environment variables**: Set `PYIDEC_HOST`, `PYIDEC_PORT`, etc. to avoid repeating connection params.

## Tests

```bash
python -m pytest
```
