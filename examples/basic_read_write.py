#!/usr/bin/env python3
"""Example: connect to an FC6A PLC and read/write a few tags by IDEC names."""

import sys

from pyidec_modbus import IDECModbusClient
from pyidec_modbus.errors import InvalidTagError, ModbusIOError, UnknownTagError


def main() -> None:
    host = "192.168.1.10"  # change to your PLC IP
    port = 502
    unit_id = 1

    try:
        with IDECModbusClient(host=host, port=port, unit_id=unit_id) as plc:
            # Read data register
            v = plc.read("D0007")
            print(f"D0007 = {v}")

            # Read internal relay (allow alternate forms)
            v = plc.read("m12")
            print(f"m12 (M0012) = {v}")

            # Read timer preset
            v = plc.read("T0002.PV")
            print(f"T0002.PV = {v}")

            # Write coil (example; uncomment if your PLC allows)
            # plc.write("Q0001", True)

            # Explain a tag
            info = plc.explain("d7")
            print(f"explain(d7): {info}")

            # Batch read
            snapshot = plc.read_many(["D0007", "M0012", "T0002.CV"])
            print(f"read_many: {snapshot}")
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
