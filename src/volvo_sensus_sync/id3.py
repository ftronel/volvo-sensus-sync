# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements data classes and constants encountered in ID3v2 tags.
"""

from typing import BinaryIO


def decode_synchsafe_u32(data: bytes) -> int:
    """
    A 4-bytes integer encoded in big endian but limited to 2^28.
    Each byte has its higher bit set to 0.
    This eliminates the possibility for this integer to collide with the MPEG synchronization
    pattern: 0xFF 0xE?
    """
    if len(data) != 4:
        raise ValueError("synchsafe u32 must be exactly 4 bytes")

    if any(b & 0x80 for b in data):
        raise ValueError("invalid synchsafe u32: high bit is set")

    return (
        (data[0] << 21)
        | (data[1] << 14)
        | (data[2] << 7)
        | data[3]
    )

def skip_id3v2_tags(f: BinaryIO) -> int:
    """
    Skip one or more consecutive ID3v2 tags at the beginning of the file.

    Returns the offset where MPEG frame scanning should start.
    """
    offset = 0

    while True:
        f.seek(offset)
        header = f.read(10)

        if len(header) < 10:
            f.seek(offset)
            return offset

        if header[:3] != b"ID3":
            f.seek(offset)
            return offset

        major_version = header[3]
        flags = header[5]
        size = decode_synchsafe_u32(header[6:10])

        tag_total_size = 10 + size

        # ID3v2.4 optional footer.
        # The footer is not included in the stored tag size.
        if major_version == 4 and flags & 0x10:
            tag_total_size += 10

        offset += tag_total_size
