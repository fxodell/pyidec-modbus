# CLI Examples

This document demonstrates common usage patterns for the `pyidec` CLI tool.

## Installation

```bash
# Install with CLI support
pip install -e ".[cli]"

# Or install both dev and CLI extras
pip install -e ".[dev,cli]"
```

## Environment Variables

Set default connection parameters to avoid repeating them:

```bash
export PYIDEC_HOST=192.168.1.10
export PYIDEC_PORT=502
export PYIDEC_UNIT_ID=1
export PYIDEC_TIMEOUT=3.0
export PYIDEC_RETRIES=3
export PYIDEC_PROFILE=fc6a
```

CLI arguments override environment variables.

## Basic Commands

### Test Connectivity

```bash
# Minimal connectivity test (reads holding register 0)
pyidec --host 192.168.1.10 ping

# Test by reading a specific tag
pyidec --host 192.168.1.10 ping --tag D0007
```

### Show Package Info

```bash
# Local metadata only
pyidec info

# With connectivity test
pyidec --host 192.168.1.10 info

# JSON output
pyidec --host 192.168.1.10 info --json
```

## Reading Tags

### Single Tag Read

```bash
# Read data register
pyidec --host 192.168.1.10 read D0007

# Read internal relay
pyidec --host 192.168.1.10 read M0012

# Read timer preset value
pyidec --host 192.168.1.10 read T0002.PV

# Read with JSON output
pyidec --host 192.168.1.10 read D0007 --json

# Read as signed 16-bit integer
pyidec --host 192.168.1.10 read D0007 --signed
```

### Batch Read

```bash
# Read multiple tags (JSON output by default)
pyidec --host 192.168.1.10 read-many D0007 D0008 M0012 T0002.CV

# Read with signed interpretation
pyidec --host 192.168.1.10 read-many D0007 D0008 --signed

# Partial results (continue on errors)
pyidec --host 192.168.1.10 read-many D0007 INVALID D0008 --partial
```

Example output:
```json
{
  "D0007": 1234,
  "D0008": 5678,
  "M0012": true,
  "T0002.CV": 100
}
```

## Writing Tags

### Write Coil/Relay

```bash
# Boolean values: true/false, 1/0, on/off, yes/no (case-insensitive)
pyidec --host 192.168.1.10 write Q0001 true
pyidec --host 192.168.1.10 write M0012 on
pyidec --host 192.168.1.10 write Q0002 1
```

### Write Register

```bash
# Decimal value
pyidec --host 192.168.1.10 write D0007 1234

# Hexadecimal value
pyidec --host 192.168.1.10 write D0007 0x04D2

# Signed value (negative numbers)
pyidec --host 192.168.1.10 write D0007 -100 --signed

# Timer preset
pyidec --host 192.168.1.10 write T0002.PV 5000
```

## Tag Debugging

```bash
# Show how a tag is mapped
pyidec explain D0007

# Output (human-readable):
# Normalized tag:  D0007
# Modbus table:    holding_register
# Offset:          6
# Width:           16
# Function:        read_holding_registers

# JSON format
pyidec explain d7 --json
```

## Polling / Monitoring

### Continuous Polling

```bash
# Poll tags every 1 second (default interval)
pyidec --host 192.168.1.10 poll D0007 M0012 T0002.CV

# Custom interval (2 seconds)
pyidec --host 192.168.1.10 poll D0007 M0012 --interval 2.0

# Poll once and exit
pyidec --host 192.168.1.10 poll D0007 M0012 --once
```

### Poll Output Formats

**Text (default)**:
```bash
pyidec --host 192.168.1.10 poll D0007 M0012 --format text
# Output:
# 2025-01-28T10:30:00.123456+00:00 D0007=1234 M0012=true
# 2025-01-28T10:30:01.123456+00:00 D0007=1235 M0012=false
```

**JSON (NDJSON - one object per line)**:
```bash
pyidec --host 192.168.1.10 poll D0007 M0012 --format json
# Output:
# {"timestamp": "2025-01-28T10:30:00.123456+00:00", "values": {"D0007": 1234, "M0012": true}}
# {"timestamp": "2025-01-28T10:30:01.123456+00:00", "values": {"D0007": 1235, "M0012": false}}
```

**CSV (tags as columns)**:
```bash
pyidec --host 192.168.1.10 poll D0007 M0012 --format csv
# Output:
# timestamp,D0007,M0012
# 2025-01-28T10:30:00.123456+00:00,1234,true
# 2025-01-28T10:30:01.123456+00:00,1235,false
```

### Piping Poll Output

```bash
# Save to file
pyidec --host 192.168.1.10 poll D0007 M0012 --format csv > data.csv

# Process with jq
pyidec --host 192.168.1.10 poll D0007 --format json | jq '.values.D0007'

# Monitor specific value changes
pyidec --host 192.168.1.10 poll D0007 --format json --interval 0.5 | \
  jq -r 'select(.values.D0007 > 1000) | .timestamp + ": " + (.values.D0007 | tostring)'
```

## Advanced Usage

### Using Alternate Tag Formats

The CLI normalizes tag names automatically:

```bash
# These are all equivalent (normalized to D0007)
pyidec --host 192.168.1.10 read D0007
pyidec --host 192.168.1.10 read d7
pyidec --host 192.168.1.10 read D7

# Timer/Counter suffixes (defaults to .CV if omitted)
pyidec --host 192.168.1.10 read T0002      # reads T0002.CV
pyidec --host 192.168.1.10 read T0002.CV   # explicit
pyidec --host 192.168.1.10 read T0002.PV   # preset value
pyidec --host 192.168.1.10 read T0002.C    # contact status
```

### Verbose Logging

```bash
# Enable debug logging to see Modbus operations
pyidec --host 192.168.1.10 read D0007 --verbose

# Shows connection details, tag resolution, Modbus calls
```

### Custom Port and Unit ID

```bash
# Non-standard port
pyidec --host 192.168.1.10 --port 5020 read D0007

# Custom unit ID (default is 1)
pyidec --host 192.168.1.10 --unit-id 2 read D0007
```

### Timeout and Retry Settings

```bash
# Custom timeout (default 3.0 seconds)
pyidec --host 192.168.1.10 --timeout 5.0 read D0007

# Custom retry count (default 1)
pyidec --host 192.168.1.10 --retries 5 poll D0007
```

## Real-World Examples

### Monitor Production Counter

```bash
# Poll production counter and alarm status every second
pyidec --host 192.168.1.10 poll D0100 M0050 --interval 1.0 --format csv > production_log.csv
```

### Set Multiple Outputs

```bash
# Use shell loop to set multiple outputs
for i in {1..8}; do
  pyidec --host 192.168.1.10 write Q000$i true
done
```

### Data Collection Script

```bash
#!/bin/bash
# Collect hourly snapshots
while true; do
  timestamp=$(date +%Y%m%d_%H%M%S)
  pyidec --host 192.168.1.10 read-many D0100 D0101 D0102 M0050 > "snapshot_${timestamp}.json"
  sleep 3600
done
```

### Check Tag Mapping

```bash
# Verify what Modbus function will be used for a tag
pyidec explain I0001
pyidec explain Q0001
pyidec explain D0007
pyidec explain T0002.PV
```

## Error Handling

### Exit Codes

- `0`: Success
- `2`: Invalid tag or value (user input error)
- `3`: Connection or Modbus I/O error
- `4`: Unexpected error

### Example Error Scenarios

```bash
# Invalid tag syntax
pyidec --host 192.168.1.10 read INVALID
# Error: Invalid tag: ...
# Exit code: 2

# Unknown tag (not in FC6A map)
pyidec --host 192.168.1.10 read D9999
# Error: Unknown tag: ...
# Exit code: 2

# Connection failure
pyidec --host 192.168.1.99 read D0007
# Error: Connection/Modbus error: ...
# Exit code: 3
```

## Shell Completion

Get help for any command:

```bash
pyidec --help
pyidec read --help
pyidec poll --help
```

## Tips

1. **Use environment variables** for connection settings in your automation scripts
2. **Use `--once` with poll** for scripted periodic checks (with cron)
3. **Use `--partial` with read-many** when reading many tags and some might be invalid
4. **Use `--signed`** when working with temperature sensors or other signed data
5. **Use `--format json`** for easy integration with other tools (jq, Python scripts, etc.)
6. **Use `--verbose`** when troubleshooting connection or tag mapping issues
