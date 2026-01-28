#!/usr/bin/env python3
"""Example: poll a list of tags on an interval using poll_iter; graceful shutdown on Ctrl+C."""

import sys

from pyidec_modbus import IDECModbusClient
from pyidec_modbus.errors import InvalidTagError, ModbusIOError, UnknownTagError


def main() -> None:
    host = "192.168.1.10"  # change to your PLC IP
    port = 502
    unit_id = 1
    tags = ["D0007", "M0012", "T0002.CV"]
    interval_s = 1.0

    try:
        with IDECModbusClient(host=host, port=port, unit_id=unit_id) as plc:
            print(f"Polling {tags} every {interval_s}s (Ctrl+C to stop)...")
            for snapshot in plc.poll_iter(tags, interval_s):
                print(snapshot)
    except KeyboardInterrupt:
        print("\nStopped.")
    except InvalidTagError as e:
        print(f"Invalid tag: {e}", file=sys.stderr)
        sys.exit(1)
    except UnknownTagError as e:
        print(f"Unknown tag: {e}", file=sys.stderr)
        sys.exit(1)
    except ModbusIOError as e:
        print(f"Modbus/connection error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
