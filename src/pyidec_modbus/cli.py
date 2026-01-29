#!/usr/bin/env python3
"""Production-ready CLI for pyidec-modbus using Typer."""

import csv
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import typer
from typing_extensions import Annotated

from . import __version__  # type: ignore
from .client import IDECModbusClient
from .errors import InvalidTagError, ModbusIOError, UnknownTagError

app = typer.Typer(
    name="pyidec",
    help="Production-ready CLI for IDEC FC6A PLC operations via Modbus TCP.",
    no_args_is_help=True,
)

logger = logging.getLogger(__name__)

# ============================================================================
# Shared options and helpers
# ============================================================================

HostOption = Annotated[
    Optional[str],
    typer.Option("--host", "-h", help="PLC hostname or IP address", envvar="PYIDEC_HOST"),
]
PortOption = Annotated[
    int,
    typer.Option("--port", "-p", help="Modbus TCP port", envvar="PYIDEC_PORT"),
]
UnitIdOption = Annotated[
    int,
    typer.Option("--unit-id", "-u", help="Modbus unit ID", envvar="PYIDEC_UNIT_ID"),
]
TimeoutOption = Annotated[
    float,
    typer.Option("--timeout", "-t", help="Connection timeout in seconds", envvar="PYIDEC_TIMEOUT"),
]
RetriesOption = Annotated[
    int,
    typer.Option("--retries", "-r", help="Number of retries on failure", envvar="PYIDEC_RETRIES"),
]
ProfileOption = Annotated[
    str,
    typer.Option("--profile", help="PLC profile", envvar="PYIDEC_PROFILE"),
]
VerboseOption = Annotated[
    bool,
    typer.Option("--verbose", "-v", help="Enable debug logging"),
]
JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Output as JSON"),
]
SignedOption = Annotated[
    bool,
    typer.Option("--signed", help="Interpret register values as signed 16-bit integers"),
]
FloatOption = Annotated[
    bool,
    typer.Option("--float", help="Read as 32-bit IEEE 754 float (two consecutive registers)"),
]


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbose flag."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s" if not verbose else "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def create_client(
    host: Optional[str],
    port: int,
    unit_id: int,
    timeout: float,
    retries: int,
    profile: str,
) -> IDECModbusClient:
    """Create and return an IDECModbusClient instance."""
    if not host:
        typer.echo("Error: --host is required for this command", err=True)
        raise typer.Exit(2)
    return IDECModbusClient(
        host=host,
        port=port,
        unit_id=unit_id,
        timeout=timeout,
        retries=retries,
        profile=profile,
    )


def parse_bool(value: str) -> bool:
    """Parse boolean value from string."""
    v = value.lower().strip()
    if v in ("true", "1", "on", "yes"):
        return True
    if v in ("false", "0", "off", "no"):
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def parse_int(value: str, signed: bool = False) -> int:
    """Parse integer value from string, supporting hex and validation."""
    v = value.strip()
    # Parse hex if starts with 0x
    if v.lower().startswith("0x"):
        num = int(v, 16)
    else:
        num = int(v)

    # Validate range
    if signed:
        if not (-32768 <= num <= 32767):
            raise ValueError(f"Signed 16-bit integer out of range: {num}")
    else:
        if not (0 <= num <= 65535):
            raise ValueError(f"Unsigned 16-bit integer out of range: {num}")

    return num


def format_value(value: bool | int, signed: bool = False) -> str:
    """Format value for display."""
    if isinstance(value, bool):
        return str(value).lower()
    if signed and isinstance(value, int):
        # Convert from unsigned to signed if needed
        if value > 32767:
            return str(value - 65536)
    return str(value)


def load_tag_map(csv_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """
    Load tag name -> register and register -> tag name from a CSV with columns
    (register, tag, ...). Returns (tag_to_register, register_to_tag). Only rows
    with non-empty tag are included.
    """
    tag_to_register: dict[str, str] = {}
    register_to_tag: dict[str, str] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            reg = (row[0] or "").strip()
            tag = (row[1] or "").strip()
            if not reg or not tag:
                continue
            if tag not in tag_to_register:
                tag_to_register[tag] = reg
            register_to_tag[reg] = tag
    return tag_to_register, register_to_tag


def format_poll_value(value: bool | int | float, signed: bool = False) -> str:
    """Format value for poll output: numbers with 2 decimal places."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        if signed and isinstance(value, int) and value > 32767:
            value = value - 65536
        return f"{value:.2f}"
    return str(value)


def to_signed(value: int) -> int:
    """Convert unsigned 16-bit to signed."""
    if value > 32767:
        return value - 65536
    return value


def from_signed(value: int) -> int:
    """Convert signed 16-bit to unsigned."""
    if value < 0:
        return value + 65536
    return value


# ============================================================================
# Commands
# ============================================================================

@app.command()
def ping(
    host: HostOption = None,
    port: PortOption = 502,
    unit_id: UnitIdOption = 1,
    timeout: TimeoutOption = 3.0,
    retries: RetriesOption = 1,
    profile: ProfileOption = "fc6a",
    verbose: VerboseOption = False,
    tag: Annotated[Optional[str], typer.Option("--tag", help="Specific tag to read (default: holding register 0)")] = None,
) -> None:
    """
    Test connectivity to the PLC by performing a minimal Modbus read.

    By default, reads 1 holding register at offset 0.
    Use --tag to test a specific operand.
    """
    setup_logging(verbose)

    try:
        client = create_client(host, port, unit_id, timeout, retries, profile)

        with client:
            if tag:
                # Read specific tag
                value = client.read(tag)
                typer.echo(f"OK: Connected to {host}:{port}, read {tag} = {value}")
            else:
                # Minimal read: holding register offset 0
                rr = client._get_client().read_holding_registers(0, count=1, device_id=unit_id)
                if rr.isError():
                    raise ModbusIOError(str(rr), table="holding_register", offset=0)
                typer.echo(f"OK: Connected to {host}:{port}")
    except InvalidTagError as e:
        typer.echo(f"Error: Invalid tag: {e}", err=True)
        raise typer.Exit(2)
    except UnknownTagError as e:
        typer.echo(f"Error: Unknown tag: {e}", err=True)
        raise typer.Exit(2)
    except ModbusIOError as e:
        typer.echo(f"Error: Connection/Modbus error: {e}", err=True)
        raise typer.Exit(3)
    except Exception as e:
        typer.echo(f"Error: Unexpected error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(4)


@app.command()
def info(
    host: HostOption = None,
    port: PortOption = 502,
    unit_id: UnitIdOption = 1,
    timeout: TimeoutOption = 3.0,
    retries: RetriesOption = 1,
    profile: ProfileOption = "fc6a",
    verbose: VerboseOption = False,
    json_output: JsonOption = False,
) -> None:
    """
    Show package version, profile, and optionally test connectivity.

    Without --host: shows local metadata only.
    With --host: also tests connectivity.
    """
    setup_logging(verbose)

    info_data = {
        "version": __version__,
        "profile": profile,
    }

    # Test connectivity if host provided
    if host:
        try:
            client = create_client(host, port, unit_id, timeout, retries, profile)
            with client:
                rr = client._get_client().read_holding_registers(0, count=1, device_id=unit_id)
                if rr.isError():
                    raise ModbusIOError(str(rr), table="holding_register", offset=0)
                info_data["connectivity"] = {
                    "status": "connected",
                    "host": host,
                    "port": port,
                    "unit_id": unit_id,
                }
        except ModbusIOError:
            info_data["connectivity"] = {
                "status": "failed",
                "host": host,
                "port": port,
                "unit_id": unit_id,
            }
        except Exception as e:
            info_data["connectivity"] = {
                "status": "error",
                "error": str(e),
            }

    if json_output:
        typer.echo(json.dumps(info_data, indent=2))
    else:
        typer.echo(f"pyidec-modbus version: {info_data['version']}")
        typer.echo(f"Profile: {info_data['profile']}")
        if "connectivity" in info_data:
            status = info_data["connectivity"]["status"]
            if status == "connected":
                typer.echo(f"Connectivity: OK ({host}:{port})")
            elif status == "failed":
                typer.echo(f"Connectivity: FAILED ({host}:{port})")
            else:
                typer.echo(f"Connectivity: ERROR - {info_data['connectivity'].get('error', 'unknown')}")


@app.command()
def read(
    tag: Annotated[str, typer.Argument(help="Tag to read (e.g., D0007, M0012, T0002.PV)")],
    host: HostOption = None,
    port: PortOption = 502,
    unit_id: UnitIdOption = 1,
    timeout: TimeoutOption = 3.0,
    retries: RetriesOption = 1,
    profile: ProfileOption = "fc6a",
    verbose: VerboseOption = False,
    json_output: JsonOption = False,
    signed: SignedOption = False,
    as_float: FloatOption = False,
) -> None:
    """
    Read a single tag from the PLC.

    Returns the value as text by default, or JSON with --json.
    Use --signed to interpret register values as signed 16-bit integers.
    Use --float to read two consecutive holding registers as IEEE 754 float (e.g. D1000 = D1000,D1001).
    """
    setup_logging(verbose)

    try:
        client = create_client(host, port, unit_id, timeout, retries, profile)

        with client:
            if as_float:
                value = client.read_float(tag)
            else:
                value = client.read(tag)
                if signed and isinstance(value, int):
                    value = to_signed(value)

            if json_output:
                typer.echo(json.dumps({"tag": tag, "value": value}))
            else:
                typer.echo(format_value(value, signed) if not as_float else f"{value:.2f}")
    except InvalidTagError as e:
        typer.echo(f"Error: Invalid tag: {e}", err=True)
        raise typer.Exit(2)
    except UnknownTagError as e:
        typer.echo(f"Error: Unknown tag: {e}", err=True)
        raise typer.Exit(2)
    except ModbusIOError as e:
        typer.echo(f"Error: Connection/Modbus error: {e}", err=True)
        raise typer.Exit(3)
    except Exception as e:
        typer.echo(f"Error: Unexpected error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(4)


@app.command()
def write(
    tag: Annotated[str, typer.Argument(help="Tag to write (e.g., Q0001, D0007)")],
    value: Annotated[str, typer.Argument(help="Value to write (bool: true/false/1/0/on/off/yes/no; int: decimal or 0x hex)")],
    host: HostOption = None,
    port: PortOption = 502,
    unit_id: UnitIdOption = 1,
    timeout: TimeoutOption = 3.0,
    retries: RetriesOption = 1,
    profile: ProfileOption = "fc6a",
    verbose: VerboseOption = False,
    signed: SignedOption = False,
) -> None:
    """
    Write a value to a single tag on the PLC.

    For coil/discrete tags: accepts true/false, 1/0, on/off, yes/no (case-insensitive).
    For register tags: accepts integers (decimal or hex with 0x prefix).
    Use --signed to allow negative values for registers (-32768 to 32767).
    """
    setup_logging(verbose)

    try:
        client = create_client(host, port, unit_id, timeout, retries, profile)

        # Parse value - try bool first, then int
        parsed_value: bool | int
        try:
            parsed_value = parse_bool(value)
        except ValueError:
            try:
                parsed_value = parse_int(value, signed)
                # Convert signed to unsigned for Modbus
                if signed and parsed_value < 0:
                    parsed_value = from_signed(parsed_value)
            except ValueError as e:
                typer.echo(f"Error: Invalid value: {e}", err=True)
                raise typer.Exit(2)

        with client:
            client.write(tag, parsed_value)
            typer.echo(f"OK: Wrote {tag} = {value}")
    except InvalidTagError as e:
        typer.echo(f"Error: Invalid tag: {e}", err=True)
        raise typer.Exit(2)
    except UnknownTagError as e:
        typer.echo(f"Error: Unknown tag: {e}", err=True)
        raise typer.Exit(2)
    except ModbusIOError as e:
        typer.echo(f"Error: Connection/Modbus error: {e}", err=True)
        raise typer.Exit(3)
    except Exception as e:
        typer.echo(f"Error: Unexpected error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(4)


@app.command()
def explain(
    tag: Annotated[str, typer.Argument(help="Tag to explain (e.g., d7, T2.PV)")],
    profile: ProfileOption = "fc6a",
    verbose: VerboseOption = False,
    json_output: JsonOption = False,
) -> None:
    """
    Show normalized tag, Modbus table, offset, and function used.

    Does not require connection; uses embedded tag map only.
    """
    setup_logging(verbose)

    try:
        # Use tag map directly without creating a client
        from .tagmap import get_default_tagmap
        from .normalize import normalize_tag
        from .types import ModbusTable

        tagmap = get_default_tagmap(profile)
        normalized = normalize_tag(tag)
        defn = tagmap.lookup(normalized)

        # Build explain info
        func = {
            ModbusTable.COIL: "read_coils",
            ModbusTable.DISCRETE_INPUT: "read_discrete_inputs",
            ModbusTable.INPUT_REGISTER: "read_input_registers",
            ModbusTable.HOLDING_REGISTER: "read_holding_registers",
        }.get(defn.table, "unknown")

        info = {
            "normalized_tag": normalized,
            "table": defn.table.value,
            "offset": defn.offset,
            "width": defn.width,
            "function_used": func,
        }

        if json_output:
            typer.echo(json.dumps(info, indent=2))
        else:
            typer.echo(f"Normalized tag:  {info['normalized_tag']}")
            typer.echo(f"Modbus table:    {info['table']}")
            typer.echo(f"Offset:          {info['offset']}")
            typer.echo(f"Width:           {info['width']}")
            typer.echo(f"Function:        {info['function_used']}")
    except InvalidTagError as e:
        typer.echo(f"Error: Invalid tag: {e}", err=True)
        raise typer.Exit(2)
    except UnknownTagError as e:
        typer.echo(f"Error: Unknown tag: {e}", err=True)
        raise typer.Exit(2)
    except Exception as e:
        typer.echo(f"Error: Unexpected error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(4)


@app.command(name="read-many")
def read_many(
    tags: Annotated[list[str], typer.Argument(help="Tags to read (space-separated)")],
    host: HostOption = None,
    port: PortOption = 502,
    unit_id: UnitIdOption = 1,
    timeout: TimeoutOption = 3.0,
    retries: RetriesOption = 1,
    profile: ProfileOption = "fc6a",
    verbose: VerboseOption = False,
    signed: SignedOption = False,
    partial: Annotated[bool, typer.Option("--partial", help="Return partial results if some tags fail")] = False,
) -> None:
    """
    Read multiple tags in a single batch operation.

    Groups tags by table and coalesces contiguous reads for efficiency.
    By default, fails entirely if any tag is invalid.
    Use --partial to return results for valid tags only.
    """
    setup_logging(verbose)

    try:
        client = create_client(host, port, unit_id, timeout, retries, profile)

        with client:
            if partial:
                # Partial mode: validate tags first, then batch read valid ones
                from .normalize import normalize_tag as norm_tag

                valid_tags: list[str] = []
                errors: dict[str, str] = {}

                # Validate all tags first (no connection needed)
                for tag in tags:
                    try:
                        normalized = norm_tag(tag)
                        client._tagmap.lookup(normalized)
                        valid_tags.append(tag)
                    except (InvalidTagError, UnknownTagError) as e:
                        errors[tag] = str(e)

                # Batch read all valid tags
                results: dict[str, Any] = {}
                if valid_tags:
                    try:
                        results = client.read_many(valid_tags)
                        # Apply signed conversion if requested
                        if signed:
                            results = {
                                tag: to_signed(val) if isinstance(val, int) else val
                                for tag, val in results.items()
                            }
                    except ModbusIOError as e:
                        # If batch read fails, mark all valid tags as errored
                        for tag in valid_tags:
                            errors[tag] = f"Modbus error: {e}"
                        results = {}

                output = {"values": results}
                if errors:
                    output["errors"] = errors
                typer.echo(json.dumps(output, indent=2))
            else:
                # Normal mode: fail entirely if any error
                results = client.read_many(tags)

                # Apply signed conversion if requested
                if signed:
                    results = {
                        tag: to_signed(val) if isinstance(val, int) else val
                        for tag, val in results.items()
                    }

                typer.echo(json.dumps(results, indent=2))
    except InvalidTagError as e:
        typer.echo(f"Error: Invalid tag: {e}", err=True)
        raise typer.Exit(2)
    except UnknownTagError as e:
        typer.echo(f"Error: Unknown tag: {e}", err=True)
        raise typer.Exit(2)
    except ModbusIOError as e:
        typer.echo(f"Error: Connection/Modbus error: {e}", err=True)
        raise typer.Exit(3)
    except Exception as e:
        typer.echo(f"Error: Unexpected error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(4)


@app.command()
def poll(
    tags: Annotated[list[str], typer.Argument(help="Tags to poll: register names (D0007, M0012) and/or tag names (FC_001) when --tag-map is set")],
    host: HostOption = None,
    port: PortOption = 502,
    unit_id: UnitIdOption = 1,
    timeout: TimeoutOption = 3.0,
    retries: RetriesOption = 1,
    profile: ProfileOption = "fc6a",
    verbose: VerboseOption = False,
    signed: SignedOption = False,
    interval: Annotated[float, typer.Option("--interval", "-i", help="Polling interval in seconds")] = 1.0,
    once: Annotated[bool, typer.Option("--once", help="Poll once and exit")] = False,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: text, json, csv")] = "text",
    tag_map: Annotated[
        Optional[str],
        typer.Option("--tag-map", envvar="PYIDEC_TAG_MAP", help="CSV path (register,tag,...): poll by tag name or register; can mix (e.g. FC_001 D0007)"),
    ] = None,
) -> None:
    """
    Continuously poll tags at specified interval.

    You can poll by register name (D0007, M0012) or by tag name (FC_001, LIT_001_Raw).
    With --tag-map (or PYIDEC_TAG_MAP): pass either tag names or register names; you can mix
    (e.g. pyidec poll FC_001 D0007 M0012 --tag-map data/test.csv). Without --tag-map: pass only register names.

    Outputs format:
    - text: timestamp + name=value pairs (default)
    - json: NDJSON with {"timestamp": "...", "values": {...}} per line
    - csv: Names as columns, one row per poll cycle

    Use --once to poll once and exit.
    Press Ctrl+C to stop gracefully.
    """
    setup_logging(verbose)

    if format not in ("text", "json", "csv"):
        typer.echo(f"Error: Invalid format '{format}'. Must be text, json, or csv.", err=True)
        raise typer.Exit(2)

    if interval <= 0:
        typer.echo(f"Error: Interval must be positive, got {interval}", err=True)
        raise typer.Exit(2)

    if not tags:
        typer.echo("Error: At least one tag is required for poll", err=True)
        raise typer.Exit(2)

    # Resolve tag names to registers and build display names (can mix tag names and register names)
    tag_map_path: Path | None = Path(tag_map) if tag_map else None
    tag_to_register: dict[str, str] = {}
    register_to_tag: dict[str, str] = {}
    if tag_map_path is not None:
        if not tag_map_path.is_file():
            typer.echo(f"Error: Tag map file not found: {tag_map_path}", err=True)
            raise typer.Exit(2)
        tag_to_register, register_to_tag = load_tag_map(tag_map_path)

    display_names: list[str] = []
    registers_to_poll: list[str] = []
    for arg in tags:
        if arg in tag_to_register:
            reg = tag_to_register[arg]
            registers_to_poll.append(reg)
            display_names.append(arg)
        else:
            registers_to_poll.append(arg)
            display_names.append(register_to_tag.get(arg, arg))

    try:
        client = create_client(host, port, unit_id, timeout, retries, profile)

        # CSV header uses display names
        if format == "csv":
            typer.echo("timestamp," + ",".join(display_names))

        with client:
            while True:
                try:
                    # Read all by register
                    results = client.read_many(registers_to_poll)

                    # Apply signed conversion if requested
                    if signed:
                        results = {
                            reg: to_signed(val) if isinstance(val, int) else val
                            for reg, val in results.items()
                        }

                    # Format output (2 decimal places); key by display name for output
                    timestamp = datetime.now(timezone.utc).isoformat()
                    formatted_by_display = {
                        display_names[i]: format_poll_value(results[reg], signed)
                        for i, reg in enumerate(registers_to_poll)
                    }

                    if format == "text":
                        tag_pairs = " ".join(f"{name}={formatted_by_display[name]}" for name in display_names)
                        typer.echo(f"{timestamp} {tag_pairs}")
                    elif format == "json":
                        output = {
                            "timestamp": timestamp,
                            "values": formatted_by_display,
                        }
                        typer.echo(json.dumps(output))
                    elif format == "csv":
                        values = [formatted_by_display[name] for name in display_names]
                        typer.echo(timestamp + "," + ",".join(values))

                    # Exit after one iteration if --once
                    if once:
                        break

                    # Sleep for interval
                    time.sleep(interval)

                except ModbusIOError as e:
                    # Retry logic: if we've exhausted retries, exit
                    typer.echo(f"Error: Connection/Modbus error: {e}", err=True)
                    raise typer.Exit(3)

    except InvalidTagError as e:
        typer.echo(f"Error: Invalid tag: {e}", err=True)
        raise typer.Exit(2)
    except UnknownTagError as e:
        typer.echo(f"Error: Unknown tag: {e}", err=True)
        raise typer.Exit(2)
    except ModbusIOError as e:
        typer.echo(f"Error: Connection/Modbus error: {e}", err=True)
        raise typer.Exit(3)
    except KeyboardInterrupt:
        typer.echo("\nStopped by user", err=True)
        raise typer.Exit(0)
    except Exception as e:
        typer.echo(f"Error: Unexpected error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(4)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        typer.echo(f"pyidec-modbus {__version__}")
        raise typer.Exit(0)


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version and exit"),
    ] = None,
) -> None:
    """pyidec - Production-ready CLI for IDEC FC6A PLC operations via Modbus TCP."""
    pass


if __name__ == "__main__":
    app()
