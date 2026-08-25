# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
MP3 parsing and compatibility checks.

This module provides utilities for parsing MPEG and Xing headers and
determining whether an existing MP3 file is compatible with the Volvo
Sensus firmware.
"""

import logging

logger = logging.getLogger(__name__)

def read_u8(f) -> int:
    return int.from_bytes(f.read(1), "big")

def read_u16(f) -> int:
    return int.from_bytes(f.read(2), "big")

def read_u32(f) -> int:
    return int.from_bytes(f.read(4), "big")
