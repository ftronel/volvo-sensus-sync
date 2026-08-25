# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements data classes and constants encountered in MP3 format.
"""

import logging
from dataclasses import dataclass
from enum import IntEnum
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Self

from hexdump import hexdump

from .config import EncodingSettings
from .crc16 import CRC16
from .id3 import skip_id3v2_tags
from .lametag import SourceFrequency, StereoMode, VbrMethod
from .mp3 import read_u32
from .xingheader import XingHeader

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
    NONE = 0b00
    INTENSITY = 0b01
    MS = 0b10
    INTENSITY_MS = 0b11

class MPEGEmphasis(IntEnum):
    NONE = 0
    _50_15 = 1
    RESERVED = 2
    CCITT = 3


def samples_per_frame(version: MPEGVersion, layer: MPEGLayer) -> int:
    match version, layer:
        case _, MPEGLayer.LI:
            return 384
        case _, MPEGLayer.LII:
            return 1152
        case MPEGVersion.MPEG1, MPEGLayer.LIII:
            return 1152
        case (MPEGVersion.MPEG2 | MPEGVersion.MPEG2_5), MPEGLayer.LIII:
            return 576
        case _:
            raise ValueError(f"Invalid MPEG version/layer combination: {version}/{layer}")

def frame_length(version: MPEGVersion, layer: MPEGLayer, bitrate: MPEGBitRate,
                 sample_rate: MPEGSampleRate, padding: bool) -> int:
    samples = samples_per_frame(version, layer)
    length = int(samples/sample_rate.hz(version)*bitrate.kbs(version, layer)*1000/8)+int(padding)
    if layer == MPEGLayer.LI:
        length*=4
    return length

@dataclass
class MPEGHeader:
    length: int
    offset: int
    version: MPEGVersion
    layer: MPEGLayer
    no_crc: bool
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
    padding_length: int

    def to_bytes(self) -> bytes:
        buf = BytesIO()
        b0 = 0xFF
        b1 = (0b111<<5) | (self.version<<3) | (self.layer<<1) | self.no_crc
        b2 = (self.bitrate<<4) | (self.samplerate<<2) | (self.padding<<1) + self.private
        b3 = (self.channel_mode<<6) | (self.mode_extension<<4) | (self.copyright<<3) | \
            (self.original<<2) | self.emphasis
        header = b3|(b2<<8)|(b1<<16)|(b0<<24)
        buf.write(header.to_bytes(4, byteorder="big"))
        buf.write(self.sideinfo)
        if self.xing is not None:
            xing = self.xing.to_bytes()
            logger.debug("Xing: %d\n", len(xing))
            buf.write(xing)
        padding = bytes(self.padding_length)
        buf.write(padding)
        return buf.getvalue()

    @classmethod
    def parse(cls, source: Path | BinaryIO) -> Self | None:
        if isinstance(source, Path):
            with source.open("rb") as f:
                return cls.from_stream(f)

        return cls.from_stream(source)

    @classmethod
    def from_stream(cls, f: BinaryIO) -> Self | None:
        # Search for ID3v2 tags
        offset = skip_id3v2_tags(f)
        f.seek(offset)
        # Looking for the first MPEG synchronization
        synchro = f.read(2)
        if synchro[0] != 0xFF or (synchro[1] & 0xE0) != 0xE0:
            return None

        # Go back and read all header
        f.seek(-2,1)
        frame_offset = f.tell()
        header = read_u32(f)

        if (header >> 21) != 0x7FF:
            logger.error("No MPEG frame found in %s", f)
            return None

        version = MPEGVersion((header >> 19) & 0b11)
        layer = MPEGLayer((header >> 17) & 0b11)
        no_crc = bool((header >> 16) & 0b1)
        bitrate = MPEGBitRate((header >> 12) & 0b1111)
        samplerate = MPEGSampleRate((header >> 10) & 0b11)
        padding = bool((header >> 9) & 0b1)
        private = bool((header >> 8) & 0b1)
        channel_mode = MPEGChannelMode((header >> 6) & 0b11)
        mode_extension = MPEGModeExtension((header >> 4) & 0b11)
        cr = bool((header >> 3) & 0b1)
        original = bool((header >> 2) & 0b1)
        emphasis = MPEGEmphasis(header & 0b11)

        #
        # Compute side information size
        #
        if version is MPEGVersion.MPEG1:          # MPEG-1
            side_info_size = 17 if channel_mode == MPEGChannelMode.MONO else 32
        else:                              # MPEG-2 / 2.5
            side_info_size = 9 if channel_mode == MPEGChannelMode.MONO else 17

        side_info = f.read(side_info_size)
        xing = XingHeader.parse(f)
        end = f.tell()
        length = end-frame_offset
        expected_length = frame_length(version, layer, bitrate, samplerate, padding)
        if length > expected_length:
            # TODO: do something in case of inconsistency
            logger.error("MPEG header length (%d) is longer than expected (%d)",
                         length, expected_length)
        padding_length = expected_length - length
        padding_bytes = f.read(padding_length)
        if not all(b == 0x00 for b in padding_bytes):
            # TODO: do something when padding is not zeroed !
            hexdump(padding_bytes)
            logger.warning("Padding of %s is not zeroed !", f)
        length = expected_length

        return MPEGHeader(
            length = length,
            offset = frame_offset,
            version = version,
            layer = layer,
            no_crc = no_crc,
            bitrate = bitrate,
            samplerate = samplerate,
            padding = padding,
            private = private,
            channel_mode = channel_mode,
            mode_extension = mode_extension,
            copyright = cr,
            original = original,
            emphasis = emphasis,
            sideinfo = side_info,
            xing = xing,
            padding_length = padding_length)

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
        self.xing.lame.misc.source_frequency = SourceFrequency.from_hz(
                                                self.samplerate.hz(self.version))

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
