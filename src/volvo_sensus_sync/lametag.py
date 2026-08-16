# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements the Lame tag parsing which is at the heart of Volvo Sensus incompatibility
with MP3 produced directly by FFMPEG.
"""

from enum import IntEnum
from dataclasses import dataclass


class VbrMethod(IntEnum):
    UNKNOWN = 0
    CBR = 1
    ABR = 2
    VBR_OLD = 3
    VBR_NEW = 4

@dataclass
class EncodingFlags:
    nspsytune: bool
    safe_joint: bool
    nogap_previous: bool
    nogap_next: bool

class SourceFrequency(IntEnum):
    KHZ_32_OR_LESS = 0
    KHZ_44_1 = 1
    KHZ_48 = 2
    ABOVE_48 = 3

class StereoMode(IntEnum):
    MONO = 0
    STEREO = 1
    DUAL = 2
    JOINT = 3
    FORCE_MS = 4
    UNKNOWN = 7

@dataclass
class MiscFlags:
    noise_shaping: int
    stereo_mode: StereoMode
    unwise: bool
    source_frequency: SourceFrequency

@dataclass
class LameTag:
    encoder: str
    revision: int
    vbr_method: VbrMethod
    lowpass: int
    replay_gain: bytes
    encoding_flags: EncodingFlags
    ath_type: int
    bitrate: int
    encoder_delay: int
    encoder_padding: int
    misc: MiscFlags
    mp3_gain: int
    preset: int
    music_length: int
    music_crc: int
    tag_crc: int
