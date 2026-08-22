# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements configuration data.
"""

from dataclasses import dataclass
from enum import IntEnum


class EncodingMode(IntEnum):
    """ MP3 encoding modes """
    CBR = 0
    ABR = 1
    VBR = 2
    VARIABLE = 3

@dataclass(slots=True)
class EncodingSettings:
    """ MP3 encoding settings """
    mode: EncodingMode
    value: int
