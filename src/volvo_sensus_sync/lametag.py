# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements the Lame tag parsing which is at the heart of Volvo Sensus incompatibility
with MP3 produced directly by FFMPEG.
"""

from enum import IntEnum
from dataclasses import dataclass
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


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
    ath_type: int

class SourceFrequency(IntEnum):
    KHZ_32_OR_LESS = 0
    KHZ_44_1 = 1
    KHZ_48 = 2
    ABOVE_48 = 3


    @classmethod
    def from_hz(cls, hz: int):
        if hz <= 32000:
            return cls.KHZ_32_OR_LESS
        if hz == 44100:
            return cls.KHZ_44_1
        if hz == 48000:
            return cls.KHZ_48
        return cls.ABOVE_48

    def hz(self) -> int:
        if self == 0:
            return 32000
        elif self == 1:
            return 44100
        elif self == 2:
            return 48000

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
    bitrate: int
    encoder_delay: int
    encoder_padding: int
    misc: MiscFlags
    mp3_gain: int
    preset: int
    music_length: int
    music_crc: int
    tag_crc: int

    def to_bytes(self) -> bytes:
        buf = BytesIO()
        buf.write(self.encoder.encode("ascii"))
        b = (self.revision<<4) + self.vbr_method
        buf.write(b.to_bytes(1))
        buf.write(int(self.lowpass/100).to_bytes(1))
        buf.write(self.replay_gain)
        flags = self.encoding_flags
        b = (flags.nogap_previous<<7) + (flags.nogap_next <<6) + (flags.safe_joint<<5) +\
            (flags.nspsytune<<4) + flags.ath_type
        buf.write(b.to_bytes(1))
        # Bitrate in kbits/s
        # Value higher than 255 are encoded as 0xFF
        if self.bitrate >= 256:
            buf.write(0xFF)
        else:
            buf.write(self.bitrate.to_bytes(1))

        b0 = (self.encoder_delay >> 4) & 0xFF
        b1 = ((self.encoder_delay & 0x0F) << 4) + ((self.encoder_padding >> 8) & 0x0F)
        b2 = self.encoder_padding & 0xFF
        buf.write(b0.to_bytes(1))
        buf.write(b1.to_bytes(1))
        buf.write(b2.to_bytes(1))
        b = ((self.misc.source_frequency & 0b11 )<<6) +((self.misc.unwise & 0b1) << 5) +\
            ((self.misc.stereo_mode & 0b111)<<2) + (self.misc.noise_shaping & 0b11)
        buf.write(b.to_bytes(1))
        buf.write(self.mp3_gain.to_bytes(1))
        buf.write(self.preset.to_bytes(2,'big'))
        buf.write(self.music_length.to_bytes(4,'big'))
        buf.write(self.music_crc.to_bytes(2, 'big'))
        buf.write(self.tag_crc.to_bytes(2,'big'))
        data = buf.getvalue()
        logger.debug("Lame length: %d", len(data))
        return data
