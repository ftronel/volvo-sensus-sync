# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""Binary I/O helpers used by MP3 parsers.

The functions in this module read exact-size big-endian integers from binary
streams and raise EOFError when the requested number of bytes cannot be read.
"""

import logging
from typing import BinaryIO

logger = logging.getLogger(__name__)

def read_exact(f: BinaryIO, size: int) -> bytes:
    """Read exactly *size* bytes from a binary stream.

    Raises:
        EOFError: If the stream ends before enough bytes are available.
    """
    data = f.read(size)
    if len(data) != size:
        raise EOFError(f"Expected {size} bytes, got {len(data)}")
    return data

def read_u8(f: BinaryIO) -> int:
    """Read an unsigned 8-bit integer from a binary stream."""
    return int.from_bytes(read_exact(f, 1), "big")

def read_u16(f: BinaryIO) -> int:
    """Read an unsigned 16-bit integer from a binary stream."""
    return int.from_bytes(read_exact(f, 2), "big")

def read_u32(f: BinaryIO) -> int:
    """Read an unsigned 32-bit integer from a binary stream."""
    return int.from_bytes(read_exact(f, 4), "big")
