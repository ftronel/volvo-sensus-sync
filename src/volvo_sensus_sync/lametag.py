# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements the Lame tag parsing which is at the heart of Volvo Sensus incompatibility
with MP3 produced directly by FFMPEG.
"""

import logging
from dataclasses import dataclass
from enum import IntEnum
from io import BytesIO
from typing import BinaryIO, Self

from .io_utils import read_u8, read_u16, read_u32

logger = logging.getLogger(__name__)

SIGNATURES = ['LAME', 'Lavf', 'Lavc', 'GOGO']

class VbrMethod(IntEnum):
    """LAME VBR method stored in the low nibble of the revision/method byte."""
    UNKNOWN = 0
    CBR = 1
    ABR = 2
    VBR_OLD = 3
    VBR_NEW = 4

@dataclass
class EncodingFlags:
    """Decoded LAME encoding flags and ATH type.

    These values are packed into one byte in the LAME tag. The high bits store
    encoder flags such as nspsytune, safe joint stereo and nogap markers; the
    low nibble stores the ATH type.
    """
    nspsytune: bool
    safe_joint: bool
    nogap_previous: bool
    nogap_next: bool
    ath_type: int

class SourceFrequency(IntEnum):
    """Source frequency category stored in the LAME misc byte.

    The LAME tag stores a category, not an exact sample rate. Use
    :meth:`from_hz` to map an MPEG sample rate to the closest LAME category.
    """
    KHZ_32_OR_LESS = 0
    KHZ_44_1 = 1
    KHZ_48 = 2
    ABOVE_48 = 3


    @classmethod
    def from_hz(cls, hz: int) -> Self:
        """Map a sample rate in hertz to the LAME source-frequency category."""
        if hz <= 32000:
            return cls.KHZ_32_OR_LESS
        if hz == 44100:
            return cls.KHZ_44_1
        if hz == 48000:
            return cls.KHZ_48
        return cls.ABOVE_48

    def hz(self) -> int:
        match(int(self)):
            case 0: return 32000
            case 1: return 44100
            case 2: return 48000
            case _: return 48000

class StereoMode(IntEnum):
    """Stereo mode category stored in the LAME misc byte."""
    MONO = 0
    STEREO = 1
    DUAL = 2
    JOINT = 3
    FORCE_MS = 4
    UNKNOWN = 7

@dataclass
class MiscFlags:
    """Decoded LAME misc byte.

    The byte contains noise shaping, stereo mode, the unwise-settings flag and
    the source-frequency category.
    """
    noise_shaping: int
    stereo_mode: StereoMode
    unwise: bool
    source_frequency: SourceFrequency

@dataclass
class LameTag:
    """Parsed 36-byte LAME extension following a Xing/Info header.

    The LAME tag stores encoder information, replay gain bytes, delay/padding,
    misc flags, music length and two CRC fields. Volvo Sensus appears not to
    depend directly on these fields, but they are preserved and updated when
    rewriting the first Xing/LAME frame.
    """
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
        """Serialize this LAME tag to its 36-byte binary representation."""
        buf = BytesIO()
        buf.write(self.encoder.encode("ascii"))
        b = (self.revision<<4) | self.vbr_method
        buf.write(b.to_bytes(1))
        buf.write(int(self.lowpass/100).to_bytes(1))
        buf.write(self.replay_gain)
        flags = self.encoding_flags
        b = (flags.nogap_previous<<7) | (flags.nogap_next <<6) | (flags.safe_joint<<5) |\
            (flags.nspsytune<<4) | flags.ath_type
        buf.write(b.to_bytes(1))
        # Bitrate in kbits/s
        # Value higher than 255 are encoded as 0xFF
        if self.bitrate >= 255:
            buf.write((0xFF).to_bytes(1))
        else:
            buf.write(self.bitrate.to_bytes(1))

        b0 = (self.encoder_delay >> 4) & 0xFF
        b1 = ((self.encoder_delay & 0x0F) << 4) | ((self.encoder_padding >> 8) & 0x0F)
        b2 = self.encoder_padding & 0xFF
        buf.write(b0.to_bytes(1))
        buf.write(b1.to_bytes(1))
        buf.write(b2.to_bytes(1))
        b = ((self.misc.source_frequency & 0b11 )<<6) | ((self.misc.unwise & 0b1) << 5) |\
            ((self.misc.stereo_mode & 0b111)<<2) | (self.misc.noise_shaping & 0b11)
        buf.write(b.to_bytes(1))
        buf.write(self.mp3_gain.to_bytes(1))
        buf.write(self.preset.to_bytes(2,'big'))
        buf.write(self.music_length.to_bytes(4,'big'))
        buf.write(self.music_crc.to_bytes(2, 'big'))
        buf.write(self.tag_crc.to_bytes(2,'big'))
        data = buf.getvalue()
        logger.debug("Lame length: %d", len(data))
        return data

    @classmethod
    def parse(cls, f: BinaryIO) -> Self | None:
        """Parse a LAME-like tag at the current stream position.

        If no known encoder signature is found, or if a required bitfield contains
        an unsupported value, the stream position is restored and ``None`` is
        returned. This allows callers to distinguish a valid LAME extension from
        arbitrary bytes following a Xing/Info header.
        """
        original_offset = f.tell()
        encoder = f.read(9).decode("ascii", errors="replace")
        signature_found = False
        for sig in SIGNATURES:
            if encoder.startswith(sig):
                signature_found = True
                break
        if not signature_found:
            f.seek(original_offset)
            return None
        b = read_u8(f)
        revision = b>>4
        try:
            vbr_method = VbrMethod(b&0x0F)
        except ValueError:
            f.seek(original_offset)
            return None
        lowpass_hz = read_u8(f)*100
        replaygain = f.read(8)
        b = read_u8(f)
        nspsytune = bool(b&0x10 == 0x10)
        nssafejoint = bool(b&0x20 == 0x20)
        nogap_next = bool(b&0x40 == 0x40)
        nogap_prev = bool(b&0x80 == 0x80)
        ath_type = b&0x0F
        encoding_flags = EncodingFlags(nspsytune, nssafejoint, nogap_prev, nogap_next, ath_type)
        bitrate = read_u8(f)
        b0 = read_u8(f)
        b1 = read_u8(f)
        b2 = read_u8(f)
        delay = (b0 << 4) | (b1 >> 4)
        padding = ((b1 & 0x0F) << 8) | b2
        # To decode more carefully
        misc = read_u8(f)
        noise_shaping = misc & 0x03
        try:
            stereo_mode = StereoMode((misc>>2)&0x07)
        except ValueError:
            f.seek(original_offset)
            return None
        unwise = bool((misc >> 5) & 0x01)
        try:
            source_frequency = SourceFrequency((misc >> 6) & 0x03)
        except ValueError:
            f.seek(original_offset)
            return None
        misc_flags = MiscFlags(noise_shaping, stereo_mode, unwise, source_frequency)
        mp3_gain = read_u8(f)
        preset = read_u16(f)
        music_length = read_u32(f)
        music_crc = read_u16(f)
        tag_crc = read_u16(f)

        return LameTag(
            encoder = encoder,
            revision = revision,
            vbr_method = vbr_method,
            lowpass = lowpass_hz,
            replay_gain = replaygain,
            encoding_flags = encoding_flags,
            bitrate = bitrate,
            encoder_delay = delay,
            encoder_padding =  padding,
            misc = misc_flags,
            mp3_gain = mp3_gain,
            preset = preset,
            music_length = music_length,
            music_crc = music_crc,
            tag_crc = tag_crc)
