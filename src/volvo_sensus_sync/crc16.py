# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
CRC16 implementation
"""

def generate_table() -> tuple[int, ...]:
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
    TABLE = generate_table()

    @classmethod
    def update(cls, crc: int, value: int) -> int:
        return ((crc >> 8) ^ cls.TABLE[(crc ^ value) & 0xFF]) & 0xFFFF

    @classmethod
    def compute(cls, data: bytes) -> int:
        crc = 0
        for b in data:
            crc = cls.update(crc, b)
        return crc
