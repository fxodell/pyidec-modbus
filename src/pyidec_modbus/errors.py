"""Clear exceptions for pyidec-modbus: invalid/unknown tags and Modbus I/O errors."""


class PyIDECModbusError(Exception):
    """Base exception for pyidec-modbus."""

    pass


class InvalidTagError(PyIDECModbusError):
    """Raised when a tag string is malformed (syntax validation failed)."""

    def __init__(self, tag: str, message: str | None = None) -> None:
        self.tag = tag
        self._msg = message or f"Invalid tag: {tag!r}"
        super().__init__(self._msg)


class UnknownTagError(PyIDECModbusError):
    """Raised when a tag is well-formed but not in the current profile's map."""

    def __init__(self, tag: str, message: str | None = None) -> None:
        self.tag = tag
        self._msg = message or f"Unknown tag: {tag!r}"
        super().__init__(self._msg)


class ModbusIOError(PyIDECModbusError):
    """Raised when a Modbus read/write fails (wraps pymodbus or connection errors)."""

    def __init__(
        self,
        message: str,
        *,
        tag: str | None = None,
        table: str | None = None,
        offset: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.tag = tag
        self.table = table
        self.offset = offset
        self.cause = cause
        super().__init__(message)
