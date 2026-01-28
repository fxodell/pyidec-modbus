"""Normalize and validate IDEC operand strings; timer/counter suffix defaults."""

import re
from .errors import InvalidTagError

# Operand letter + 1–4 digit number + optional .C | .CV | .PV (Timer/Counter only)
_OPERAND_PATTERN = re.compile(
    r"^([A-Z])(\d{1,4})(\.(C|CV|PV))?$",
    re.IGNORECASE,
)

# Valid suffix for Timer/Counter: .C, .CV, .PV only
_VALID_SUFFIXES = frozenset({".C", ".CV", ".PV"})


def normalize_tag(raw: str) -> str:
    """
    Normalize an IDEC operand string to canonical form.

    - Uppercase operand letter, zero-pad number to 4 digits.
    - Timer/Counter without suffix default to .CV.
    - Preserve explicitly provided forms (e.g. D8000, M8000).

    Raises InvalidTagError for malformed tags.
    """
    s = raw.strip()
    if not s:
        raise InvalidTagError(raw, "Tag cannot be empty")

    m = _OPERAND_PATTERN.match(s)
    if not m:
        raise InvalidTagError(raw, f"Malformed operand: {raw!r}")

    letter = m.group(1).upper()
    num_str = m.group(2)
    suffix_group = m.group(3)  # e.g. ".PV"
    suffix_raw = m.group(4)    # e.g. "PV"

    # Non-T/C operands must not have a suffix
    if letter not in ("T", "C") and suffix_group is not None:
        raise InvalidTagError(raw, f"Operand {letter} does not support suffix {suffix_group!r}")

    # Zero-pad number to 4 digits (preserve explicit D8000, M8000, etc.)
    num = int(num_str)
    if num < 0 or num > 9999:
        raise InvalidTagError(raw, f"Operand number out of range 0–9999: {num}")
    padded = f"{num:04d}"

    # Timer (T) and Counter (C): no suffix -> .CV
    if letter in ("T", "C"):
        if suffix_group is None:
            suffix = ".CV"
        else:
            suffix = "." + suffix_raw.upper()
            if suffix not in _VALID_SUFFIXES:
                raise InvalidTagError(raw, f"Invalid Timer/Counter suffix: {suffix!r}")
    else:
        suffix = None

    base = f"{letter}{padded}"
    return f"{base}{suffix}" if suffix else base
