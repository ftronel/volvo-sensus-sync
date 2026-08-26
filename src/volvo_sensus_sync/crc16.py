# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
CRC-16 helpers used by the LAME tag writer.

The LAME tag CRC uses the reflected CRC-16 polynomial 0xA001, with an
initial value of 0 and no final XOR.
"""

def generate_table() -> tuple[int, ...]:
    """Generate the lookup table for the reflected CRC-16 polynomial.

    The generated table is used by :class:`CRC16` to update the checksum one
    byte at a time. The polynomial is ``0xA001``, which is the reflected form
    used by the LAME tag CRC.
    """
    poly = 0xA001
    table = []

    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
        table.append(crc & 0xFFFF)

    return tuple(table)


class CRC16:
    """Stateless CRC-16 calculator for LAME tag checksums.

    The class exposes only class methods and keeps the precomputed lookup table
    as a class attribute. It implements the CRC variant used by LAME for the
    tag CRC field: reflected polynomial ``0xA001``, initial value ``0`` and no
    final XOR.

    The computed value is used when rewriting the Xing/LAME frame so the LAME
    metadata remains internally consistent.
    """
    TABLE = generate_table()

    @classmethod
    def update(cls, crc: int, value: int) -> int:
        """Update a CRC-16 value with one byte.

        Args:
            crc: Current CRC value.
            value: Byte value to incorporate. Only the low eight bits are used.

        Returns:
            Updated CRC value, masked to 16 bits.
        """
        return ((crc >> 8) ^ cls.TABLE[(crc ^ value) & 0xFF]) & 0xFFFF

    @classmethod
    def compute(cls, data: bytes) -> int:
        """Compute the CRC-16 of a byte sequence.

        Args:
            data: Bytes over which the checksum should be computed.

        Returns:
            CRC-16 value using the LAME tag CRC variant.
        """
        crc = 0
        for b in data:
            crc = cls.update(crc, b)
        return crc
