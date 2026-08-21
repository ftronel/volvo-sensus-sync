# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements data classes and constants encountered in MP3 format.
"""

from enum import IntEnum
from dataclasses import dataclass
from pathlib import Path
from io import BytesIO
import logging

from .crc16 import CRC16
from .config import EncodingSettings
from .xingheader import XingHeader
from .lametag import VbrMethod, SourceFrequency, StereoMode

logger = logging.getLogger(__name__)


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
    I_0001 = 1
    I_0010 = 2
    I_0011 = 3
    I_0100 = 4
    I_0101 = 5
    I_0110 = 6
    I_0111 = 7
    I_1000 = 8
    I_1001 = 9
    I_1010 = 10
    I_1011 = 11
    I_1100 = 12
    I_1101 = 13
    I_1110 = 14
    BAD = 15

    def kbs(self, version: MPEGVersion, layer: MPEGLayer) -> int:
        if self == MPEGBitRate.FREE:
            raise ValueError("Free bitrate is not supported")
        if self == MPEGBitRate.BAD:
            raise ValueError("Invalid bitrate index")
        if version == MPEGVersion.RESERVED:
            raise ValueError("Invalid MPEG version")
        if layer == MPEGLayer.RESERVED:
            raise ValueError("Invalid MPEG layer")

        table = {
            MPEGVersion.MPEG1: {
                MPEGLayer.LI: {
                    MPEGBitRate.I_0001: 32,
                    MPEGBitRate.I_0010: 64,
                    MPEGBitRate.I_0011: 96,
                    MPEGBitRate.I_0100: 128,
                    MPEGBitRate.I_0101: 160,
                    MPEGBitRate.I_0110: 192,
                    MPEGBitRate.I_0111: 224,
                    MPEGBitRate.I_1000: 256,
                    MPEGBitRate.I_1001: 288,
                    MPEGBitRate.I_1010: 320,
                    MPEGBitRate.I_1011: 352,
                    MPEGBitRate.I_1100: 384,
                    MPEGBitRate.I_1101: 416,
                    MPEGBitRate.I_1110: 448,
                },
                MPEGLayer.LII: {
                    MPEGBitRate.I_0001: 32,
                    MPEGBitRate.I_0010: 48,
                    MPEGBitRate.I_0011: 56,
                    MPEGBitRate.I_0100: 64,
                    MPEGBitRate.I_0101: 80,
                    MPEGBitRate.I_0110: 96,
                    MPEGBitRate.I_0111: 112,
                    MPEGBitRate.I_1000: 128,
                    MPEGBitRate.I_1001: 160,
                    MPEGBitRate.I_1010: 192,
                    MPEGBitRate.I_1011: 224,
                    MPEGBitRate.I_1100: 256,
                    MPEGBitRate.I_1101: 320,
                    MPEGBitRate.I_1110: 384,
                },
                MPEGLayer.LIII: {
                    MPEGBitRate.I_0001: 32,
                    MPEGBitRate.I_0010: 40,
                    MPEGBitRate.I_0011: 48,
                    MPEGBitRate.I_0100: 56,
                    MPEGBitRate.I_0101: 64,
                    MPEGBitRate.I_0110: 80,
                    MPEGBitRate.I_0111: 96,
                    MPEGBitRate.I_1000: 112,
                    MPEGBitRate.I_1001: 128,
                    MPEGBitRate.I_1010: 160,
                    MPEGBitRate.I_1011: 192,
                    MPEGBitRate.I_1100: 224,
                    MPEGBitRate.I_1101: 256,
                    MPEGBitRate.I_1110: 320,
                },
            },
            MPEGVersion.MPEG2: {
                MPEGLayer.LI: {
                    MPEGBitRate.I_0001: 32,
                    MPEGBitRate.I_0010: 48,
                    MPEGBitRate.I_0011: 56,
                    MPEGBitRate.I_0100: 64,
                    MPEGBitRate.I_0101: 80,
                    MPEGBitRate.I_0110: 96,
                    MPEGBitRate.I_0111: 112,
                    MPEGBitRate.I_1000: 128,
                    MPEGBitRate.I_1001: 144,
                    MPEGBitRate.I_1010: 160,
                    MPEGBitRate.I_1011: 176,
                    MPEGBitRate.I_1100: 192,
                    MPEGBitRate.I_1101: 224,
                    MPEGBitRate.I_1110: 256,
                },
                MPEGLayer.LII: {
                    MPEGBitRate.I_0001: 8,
                    MPEGBitRate.I_0010: 16,
                    MPEGBitRate.I_0011: 24,
                    MPEGBitRate.I_0100: 32,
                    MPEGBitRate.I_0101: 40,
                    MPEGBitRate.I_0110: 48,
                    MPEGBitRate.I_0111: 56,
                    MPEGBitRate.I_1000: 64,
                    MPEGBitRate.I_1001: 80,
                    MPEGBitRate.I_1010: 96,
                    MPEGBitRate.I_1011: 112,
                    MPEGBitRate.I_1100: 128,
                    MPEGBitRate.I_1101: 144,
                    MPEGBitRate.I_1110: 160,
                },
                MPEGLayer.LIII: {
                    MPEGBitRate.I_0001: 8,
                    MPEGBitRate.I_0010: 16,
                    MPEGBitRate.I_0011: 24,
                    MPEGBitRate.I_0100: 32,
                    MPEGBitRate.I_0101: 40,
                    MPEGBitRate.I_0110: 48,
                    MPEGBitRate.I_0111: 56,
                    MPEGBitRate.I_1000: 64,
                    MPEGBitRate.I_1001: 80,
                    MPEGBitRate.I_1010: 96,
                    MPEGBitRate.I_1011: 112,
                    MPEGBitRate.I_1100: 128,
                    MPEGBitRate.I_1101: 144,
                    MPEGBitRate.I_1110: 160,
                },
            },
        }

        table[MPEGVersion.MPEG2_5] = table[MPEGVersion.MPEG2]

        return table[version][layer][self]

class MPEGSampleRate(IntEnum):
    RATE_0 = 0
    RATE_1 = 1
    RATE_2 = 2
    RESERVED = 3

    def hz(self, version: MPEGVersion) -> int:
        table = {
            MPEGVersion.MPEG1: {
                MPEGSampleRate.RATE_0: 44100,
                MPEGSampleRate.RATE_1: 48000,
                MPEGSampleRate.RATE_2: 32000,
            },
            MPEGVersion.MPEG2: {
                MPEGSampleRate.RATE_0: 22050,
                MPEGSampleRate.RATE_1: 24000,
                MPEGSampleRate.RATE_2: 16000,
            },
            MPEGVersion.MPEG2_5: {
                MPEGSampleRate.RATE_0: 11025,
                MPEGSampleRate.RATE_1: 12000,
                MPEGSampleRate.RATE_2: 8000,
            },
        }

        if version == MPEGVersion.RESERVED or self == MPEGSampleRate.RESERVED:
            raise ValueError("Invalid MPEG sample rate combination")

        return table[version][self]

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
    length: int
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

    def to_bytes(self) -> bytes:
        buf = BytesIO()
        b0 = 0xFF
        b1 = (0b111<<5) + (self.version<<3) + (self.layer<<1) + self.crc
        b2 = (self.bitrate<<4) + (self.samplerate<<2) + (self.padding<<1) + self.private
        b3 = (self.channel_mode<<6) + (self.mode_extension<<4) + (self.copyright<<3) + \
            (self.original<<2) + self.emphasis
        header = b3+(b2<<8)+(b1<<16)+(b0<<24)
        buf.write(header.to_bytes(4, byteorder="big"))
        buf.write(self.sideinfo)
        xing = self.xing.to_bytes()
        logger.debug("Xing: %d\n", len(xing))
        buf.write(xing)
        return buf.getvalue()

    def is_sensus_compatible(self) -> bool:
        return self.channel_mode == MPEGChannelMode.JOINT and self.original

    def fix_sensus_compatibility(self, path: Path, encoding: EncodingSettings) -> None:
        self.channel_mode = MPEGChannelMode.JOINT
        self.original = True
        if self.xing.lame.vbr_method == VbrMethod.UNKNOWN:
            self.xing.lame.vbr_method = VbrMethod(int(encoding.mode)+1)
        if self.xing.lame.bitrate != self.bitrate.kbs(self.version, self.layer):
            self.xing.lame.bitrate = encoding.value
        if self.xing.lame.misc.stereo_mode != StereoMode.JOINT:
            self.xing.lame.misc.stereo_mode = StereoMode.JOINT
        if self.xing.lame.misc.source_frequency.hz() != self.samplerate.hz(self.version):
            self.xing.lame.misc.source_frequency = SourceFrequency.KHZ_44_1

        data = self.to_bytes()
        # Fix final CRC: excluding the CRC itself
        self.xing.lame.tag_crc = CRC16.compute(data[:-2])
        data = self.to_bytes()
        if len(data) != self.length:
            logger.error('Original header (%d) and rewritten header (%d) have not the same length !'
                         , self.length, len(data))
        with open(path.resolve(), 'r+b') as f:
            f.seek(self.offset)
            length = f.write(data)
            logger.debug("%d bytes written", length)
            f.flush()
