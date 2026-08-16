# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements data classes and constants encountered in MP3 format.
"""

from enum import IntEnum
from dataclasses import dataclass

from .xingheader import XingHeader

class MPEGVersion(IntEnum):
    """ MPEG Version """
    MPEG2_5 = 0
    RESERVED = 1
    MPEG2 = 2
    MPEG1 = 3

class MPEGLayer(IntEnum):
    """ MPEG Layer """
    RESERVED = 0
    LIII = 1
    LII = 2
    LI = 3

class MPEGBitRate(IntEnum):
    """ MPEG Layer """
    FREE = 0
    _32KBS = 1
    _40KBS = 2
    _48KBS = 3
    _56KBS = 4
    _64KBS = 5
    _80KBS = 6
    _96KBS = 7
    _112KBS = 8
    _128KBS = 9
    _160KBS = 10
    _192KBS = 11
    _224KBS = 12
    _256KBS = 13
    _320KBS = 14
    BAD = 15


class MPEGSampleRate(IntEnum):
    _44KHZ = 0
    _48KHZ = 1
    _32KHZ = 2
    RESERVED = 3

class MPEGChannelMode(IntEnum):
    STEREO = 0
    JOINT = 1
    DUAL = 2
    MONO = 3

class MPEGModeExtension(IntEnum):
    INTENSITY = 0
    MS = 1
    INTENSITY_MS = 2
    RESERVED = 3

class MPEGEmphasis(IntEnum):
    NONE = 0
    _50_15 = 1
    RESERVED = 2
    CCITT = 3

@dataclass
class MPEGHeader:
    offset: int
    version: MPEGVersion
    layer: MPEGLayer
    crc: bool
    bitrate: MPEGBitRate
    samplerate: MPEGSampleRate
    padding: bool
    private: bool
    channel_mode: MPEGChannelMode
    mode_extension: MPEGModeExtension
    copyright: bool
    original: bool
    emphasis: MPEGEmphasis
    sideinfo: bytes
    xing: XingHeader | None
