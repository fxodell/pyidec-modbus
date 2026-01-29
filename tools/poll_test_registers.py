#!/usr/bin/env python3
"""
Poll each register listed in data/test.csv and write a CSV of registers that
successfully return a value. D registers are read as 32-bit floats, M/I/Q as
bits, and T/C/others as integers.

Usage (from repo root, after pip install -e .):
  python tools/poll_test_registers.py [--host HOST] [--port PORT] [--input PATH] [--output PATH]

Environment: PYIDEC_HOST, PYIDEC_PORT (defaults: localhost, 502).
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pyidec_modbus.client import IDECModbusClient
from pyidec_modbus.errors import InvalidTagError, ModbusIOError, UnknownTagError

# Standard Modbus reference number bases (ref = base + 0-based offset)
_MODBUS_REF_BASE = {
    "coil": 1,
    "discrete_input": 100001,
    "input_register": 300001,
    "holding_register": 400001,
}


def modbus_register_number(table: str, offset: int) -> int:
    """Return standard Modbus register reference (e.g. 400001, 10001)."""
    return _MODBUS_REF_BASE.get(table, 400001) + offset


def load_register_list(path: Path) -> list[tuple[str, str, str]]:
    """Load CSV with columns: register, tag, description. Returns list of (register, tag, desc)."""
    rows: list[tuple[str, str, str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            reg = (row[0] or "").strip()
            if not reg:
                continue
            tag = (row[1] or "").strip() if len(row) > 1 else ""
            desc = (row[2] or "").strip() if len(row) > 2 else ""
            # Normalize description (collapse internal newlines to space)
            desc = " ".join(desc.split())
            rows.append((reg, tag, desc))
    return rows


def read_value(client: IDECModbusClient, register: str) -> bool | int | float | None:
    """
    Read one register. D -> float, M/I/Q -> bool, else int.
    Returns None on tag/IO error (caller skips).
    """
    reg_upper = register.upper()
    prefix = reg_upper[0] if reg_upper else ""
    try:
        if prefix == "D":
            return client.read_float(register)
        if prefix in ("M", "I", "Q"):
            return client.read(register)  # bool for coils/discrete
        return client.read(register)  # int for T, C, etc.
    except (InvalidTagError, UnknownTagError, ModbusIOError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Poll registers from test CSV and write CSV of those that return a value."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("PYIDEC_HOST", "localhost"),
        help="PLC host (default: PYIDEC_HOST or localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PYIDEC_PORT", "502")),
        help="Modbus TCP port (default: PYIDEC_PORT or 502)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "test.csv",
        help="Input CSV path (default: data/test.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "poll_results.csv",
        help="Output CSV path (default: data/poll_results.csv)",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 1

    rows = load_register_list(args.input)
    # Only poll rows that have a tag
    rows = [(reg, tag, desc) for reg, tag, desc in rows if tag]
    if not rows:
        print("No registers with a tag to poll.", file=sys.stderr)
        return 0

    # Each result: (register, tag, description, value, timestamp, modbus_register)
    results: list[tuple[str, str, str, str, str, int]] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        with IDECModbusClient(host=args.host, port=args.port) as client:
            for i, (register, tag, description) in enumerate(rows):
                value = read_value(client, register)
                if value is None:
                    continue
                info = client.explain(register)
                modbus_reg = modbus_register_number(info["table"], info["offset"])
                # Format value for CSV (floats: max 2 decimal places)
                if isinstance(value, bool):
                    value_str = "true" if value else "false"
                elif isinstance(value, float):
                    value_str = f"{value:.2f}"
                else:
                    value_str = str(value)
                results.append((register, tag, description, value_str, timestamp, modbus_reg))
                if (i + 1) % 100 == 0:
                    print(f"  Polled {i + 1}/{len(rows)} ...", file=sys.stderr)
    except ModbusIOError as e:
        print(f"Connection error: {e}", file=sys.stderr)
        return 3

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["register", "tag", "description", "value", "timestamp", "modbus_register"])
        w.writerows(results)

    print(f"Wrote {len(results)} registers with values to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
