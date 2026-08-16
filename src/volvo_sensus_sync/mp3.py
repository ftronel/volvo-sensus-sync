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
import sys
from pathlib import Path

from mutagen.mp3 import MP3

from .config import EncodingMode
from .xingheader import XingHeader
from .lametag import LameTag, VbrMethod, EncodingFlags, StereoMode, SourceFrequency, MiscFlags
from .mpegheader import MPEGHeader, MPEGVersion, MPEGLayer, MPEGBitRate, MPEGSampleRate,\
                        MPEGChannelMode, MPEGModeExtension, MPEGEmphasis


logger = logging.getLogger(__name__)


def read_u8(f) -> int:
    return int.from_bytes(f.read(1), "big")

def read_u16(f) -> int:
    return int.from_bytes(f.read(2), "big")

def read_u32(f) -> int:
    return int.from_bytes(f.read(4), "big")

def parse_mpeg_header(path: Path) -> MPEGHeader | None:
    with path.open("rb") as f:

        # Searching for the first MPEG synchronization
        while True:
            b = f.read(1)
            if not b:
                raise ValueError("No MPEG frame")
            if b[0] != 0xFF:
                continue
            b = f.read(1)
            if not b:
                raise ValueError("EOF")
            if (b[0] & 0xE0) == 0xE0:
                f.seek(-2, 1)
                break
            f.seek(-1, 1)

        frame_offset = f.tell()
        header = read_u32(f)

        if (header >> 21) != 0x7FF:
            logger.error("No MPEG frame found in %s", path)
            sys.exit(-1)

        version = MPEGVersion((header >> 19) & 0b11)
        layer = MPEGLayer((header >> 17) & 0b11)
        crc = bool((header >> 15) & 0b1)
        bitrate = MPEGBitRate((header >> 14) & 0b1111)
        samplerate = MPEGSampleRate((header >> 10) & 0b11)
        padding = bool((header >> 8) & 0b1)
        private = bool((header >> 7) & 0b1)
        channel_mode = MPEGChannelMode((header >> 6) & 0b11)
        mode_extension = MPEGModeExtension((header >> 4) & 0b11)
        cr = bool((header >> 2) & 0b1)
        original = bool((header >> 1) & 0b1)
        emphasis = MPEGEmphasis(header & 0b11)

        #
        # Compute side information size
        #
        if version is MPEGVersion.MPEG1:          # MPEG-1
            side_info_size = 17 if channel_mode == MPEGChannelMode.MONO else 32
        else:                              # MPEG-2 / 2.5
            side_info_size = 9 if channel_mode == MPEGChannelMode.MONO else 17

        side_info = f.read(side_info_size)
        magic = f.read(4)

        if magic not in (b"Xing", b"Info"):
            # No Xing header
            return None

        if magic == b"Info":
            encoding = EncodingMode.CBR
        else:
            encoding = EncodingMode.VARIABLE

        flags = read_u32(f)

        nb_frames = None
        audio_length = None
        toc = None
        quality = None
        if flags & 0x0001:      # Frames
            nb_frames = read_u32(f)
        if flags & 0x0002:      # Bytes
            audio_length = read_u32(f)
        if flags & 0x0004:      # TOC
            toc = f.read(100,1)
        if flags & 0x0008:      # Quality
            quality = read_u32(f)

        # According to ChatGPT
        #       Offset  Taille  Description
        #       ------  ------  ----------------------------------
        #        00      9       Encoder string
        #        09      1       Revision + VBR method
        #        0A      1       Lowpass filter
        #        0B      8       ReplayGain
        #        13      1       Encoding flags
        #        14      1       ATH type
        #        15      1       Bitrate
        #        16      3       Encoder delay + padding
        #        19      1       Misc
        #        1A      1       MP3 gain
        #        1B      2       Preset / Surround
        #        1D      4       Music length
        #        21      2       Music CRC
        #        23      2       Tag CRC
        encoder = f.read(9).decode("ascii", errors="replace")
        b = read_u8(f)
        revision = b>>4
        vbr_method = VbrMethod(b&0x0F)
        lowpass_hz = read_u8(f)*100
        replaygain = f.read(8)
        b = read_u8(f)
        nspsytune = bool(b&0x1 == 1)
        nssafejoint = bool(b&0x2 == 2)
        nogap_prev = bool(b&0x4 == 4)
        nogap_next = bool(b&0x8 == 8)
        encoding_flags = EncodingFlags(nspsytune, nssafejoint, nogap_prev, nogap_next)
        ath_type = read_u8(f)
        bitrate = read_u8(f)
        b0 = read_u8(f)
        b1 = read_u8(f)
        b2 = read_u8(f)
        delay = (b0 << 4) | (b1 >> 4)
        padding = ((b1 & 0x0F) << 8) | b2
        # To decode more carefully
        misc = read_u8(f)
        noise_shaping = misc & 0x03
        stereo_mode = StereoMode((misc>>2)&0x07)
        unwise = bool((misc >> 5) & 0x01)
        source_frequency = SourceFrequency((misc >> 6) & 0x03)
        misc = MiscFlags(noise_shaping, stereo_mode, unwise, source_frequency)
        mp3_gain = read_u8(f)
        preset = read_u16(f)
        music_length = read_u32(f)
        music_crc = read_u16(f)
        tag_crc = read_u16(f)
        lame_tag = LameTag(encoder, revision, vbr_method, lowpass_hz, replaygain, encoding_flags,
                           ath_type, bitrate, delay, padding, misc, mp3_gain, preset, music_length,
                           music_crc, tag_crc)

        xing_header = XingHeader(
            encoding = encoding,
            frames = nb_frames,
            audio_length = audio_length,
            toc = toc,
            quality = quality,
            lame = lame_tag,
            )

        return MPEGHeader(frame_offset, version, layer, crc, bitrate, samplerate, padding, private,
                          channel_mode, mode_extension, cr, original, emphasis, side_info,
                          xing_header)


def check_sensus_compatibility(audio, path) -> bool:
    if not isinstance(audio, MP3):
        return False

    header = parse_mpeg_header(path)
    # header must be present and ...
    return header is not None and header.channel_mode != MPEGChannelMode.JOINT \
                  and not header.original
