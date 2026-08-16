# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements data classes and constants encountered Xing header.
"""

from dataclasses import dataclass

from .lametag import LameTag
from .config import EncodingMode

@dataclass
class XingHeader:
    """Information extracted from an MP3 Xing/LAME header."""
    encoding : EncodingMode
    frames: int | None
    audio_length: int | None
    toc: bytes | None
    quality: int | None
    lame: LameTag | None
