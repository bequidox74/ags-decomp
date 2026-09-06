from __future__ import annotations

import io
import os
import struct
from pathlib import Path
from typing import BinaryIO, Literal

from typing_extensions import Self

# Vibecoded with ChatGPT to avoid an external dependency.


class BinaryReader:
    """
    Small binary reader for bytes, files, and paths.

    By default, integers use little-endian byte order and strings use UTF-8.
    """

    def __init__(
        self,
        source: bytes | bytearray | memoryview | str | os.PathLike | BinaryIO,
        encoding: str = "utf-8",
        byteorder: Literal["big", "little"] = "little",
    ):
        if byteorder not in ("little", "big"):
            raise ValueError("byteorder must be 'little' or 'big'")

        self.encoding = encoding
        self.byteorder: Literal["big", "little"] = byteorder
        self._owns_file = False

        if isinstance(source, (bytes, bytearray, memoryview)):
            self._stream = io.BytesIO(bytes(source))
        elif isinstance(source, (str, os.PathLike, Path)):
            self._stream = open(source, "rb")  # noqa: SIM115
            self._owns_file = True
        elif hasattr(source, "read") and hasattr(source, "seek"):
            self._stream = source
        else:
            raise TypeError(
                "source must be bytes, a path, or a binary file-like object"
            )

    # ------------------------------------------------------------------
    # Position / searching
    # ------------------------------------------------------------------

    def tell(self) -> int:
        return self._stream.tell()

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        """Move the current position and return the new absolute position."""
        return self._stream.seek(offset, whence)

    def skip(self, count: int) -> int:
        """Advance by count bytes."""
        return self.seek(count, io.SEEK_CUR)

    def find(self, needle: bytes, start: int | None = None) -> int:
        """
        Find bytes starting at `start` (or the current position).

        Returns the absolute offset, or -1 if not found.
        Does not change the current position.
        """
        if not isinstance(needle, bytes):
            raise TypeError("needle must be bytes")

        current = self.tell()
        search_start = current if start is None else start

        self._stream.seek(0, io.SEEK_END)
        end = self._stream.tell()

        self._stream.seek(search_start)
        data = self._stream.read(end - search_start)

        result = data.find(needle)

        self._stream.seek(current)
        return -1 if result < 0 else search_start + result

    # ------------------------------------------------------------------
    # Raw bytes
    # ------------------------------------------------------------------

    def read(self, count: int = -1) -> bytes:
        data = self._stream.read(count)
        if count >= 0 and len(data) != count:
            raise EOFError(f"expected {count} bytes, got {len(data)}")
        return data

    def read_byte(self) -> int:
        return self.read(1)[0]

    def read_bytes(self, count: int) -> bytes:
        return self.read(count)

    # ------------------------------------------------------------------
    # Strings
    # ------------------------------------------------------------------

    def read_cstring(self, encoding: str | None = None) -> str:
        """
        Read a zero-terminated string.

        The terminating zero byte is consumed but not included.
        """
        data = bytearray()

        while True:
            b = self.read_byte()
            if b == 0:
                break
            data.append(b)

        return bytes(data).decode(encoding or self.encoding)

    def read_fixed_string(
        self,
        size: int,
        encoding: str | None = None,
        strip_nulls: bool = True,
    ) -> str:
        """
        Read exactly `size` bytes and decode them.

        By default, trailing NUL bytes are removed.
        """
        data = self.read(size)

        if strip_nulls:
            data = data.rstrip(b"\x00")

        return data.decode(encoding or self.encoding)

    # Alias that's sometimes convenient.
    read_zstring = read_cstring
    cstr = read_cstring
    zstr = read_cstring
    fstr = read_fixed_string

    # ------------------------------------------------------------------
    # Integers
    # ------------------------------------------------------------------

    def _read_int(self, size: int, signed: bool) -> int:
        data = self.read(size)
        return int.from_bytes(
            data,
            byteorder=self.byteorder,
            signed=signed,
        )

    def read_uint8(self) -> int:
        return self._read_int(1, False)

    def read_int8(self) -> int:
        return self._read_int(1, True)

    def read_uint16(self) -> int:
        return self._read_int(2, False)

    def read_int16(self) -> int:
        return self._read_int(2, True)

    def read_uint32(self) -> int:
        return self._read_int(4, False)

    def read_int32(self) -> int:
        return self._read_int(4, True)

    def read_uint64(self) -> int:
        return self._read_int(8, False)

    def read_int64(self) -> int:
        return self._read_int(8, True)

    # Short aliases.
    u8 = read_uint8
    i8 = read_int8
    u16 = read_uint16
    i16 = read_int16
    u32 = read_uint32
    i32 = read_int32
    u64 = read_uint64
    i64 = read_int64

    # ------------------------------------------------------------------
    # Floating point
    # ------------------------------------------------------------------

    def read_float32(self) -> float:
        prefix = "<" if self.byteorder == "little" else ">"
        return struct.unpack(f"{prefix}f", self.read(4))[0]

    def read_float64(self) -> float:
        prefix = "<" if self.byteorder == "little" else ">"
        return struct.unpack(f"{prefix}d", self.read(8))[0]

    f32 = read_float32
    f64 = read_float64

    # ------------------------------------------------------------------
    # File lifetime
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._owns_file:
            self._stream.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
