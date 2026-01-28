#!/usr/bin/env python3
"""Production-ready CLI for pyidec-modbus using Typer."""

import json
import logging
import time
from datetime import datetime, timezone
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
) -> None:
    """
    Read a single tag from the PLC.

    Returns the value as text by default, or JSON with --json.
    Use --signed to interpret register values as signed 16-bit integers.
    """
    setup_logging(verbose)

    try:
        client = create_client(host, port, unit_id, timeout, retries, profile)

        with client:
            value = client.read(tag)

            # Apply signed conversion if requested and value is int
            if signed and isinstance(value, int):
                value = to_signed(value)

            if json_output:
                typer.echo(json.dumps({"tag": tag, "value": value}))
            else:
                typer.echo(format_value(value, signed))
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
    tags: Annotated[list[str], typer.Argument(help="Tags to poll (space-separated)")],
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
) -> None:
    """
    Continuously poll tags at specified interval.

    Outputs format:
    - text: timestamp + tag=value pairs (default)
    - json: NDJSON with {"timestamp": "...", "values": {...}} per line
    - csv: Tags as columns, one row per poll cycle

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

    try:
        client = create_client(host, port, unit_id, timeout, retries, profile)

        # CSV header
        if format == "csv":
            typer.echo("timestamp," + ",".join(tags))

        with client:
            while True:
                try:
                    # Read all tags
                    results = client.read_many(tags)

                    # Apply signed conversion if requested
                    if signed:
                        results = {
                            tag: to_signed(val) if isinstance(val, int) else val
                            for tag, val in results.items()
                        }

                    # Format output
                    timestamp = datetime.now(timezone.utc).isoformat()

                    if format == "text":
                        tag_pairs = " ".join(f"{tag}={format_value(results[tag], signed)}" for tag in tags)
                        typer.echo(f"{timestamp} {tag_pairs}")
                    elif format == "json":
                        output = {
                            "timestamp": timestamp,
                            "values": results,
                        }
                        typer.echo(json.dumps(output))
                    elif format == "csv":
                        values = [format_value(results[tag], signed) for tag in tags]
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
