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

import hexdump

from .config import EncodingMode, EncodingSettings
from .crc16 import CRC16
from .id3 import skip_id3v2_tags
from .lametag import SourceFrequency, StereoMode, VbrMethod
from .io_utils import read_u32
from .xingheader import XingHeader

logger = logging.getLogger(__name__)


class MPEGVersion(IntEnum):
    """Raw MPEG audio version bits stored in the frame header.

    The numeric values intentionally match the two-bit MPEG version field:
    ``00`` for MPEG-2.5, ``10`` for MPEG-2 and ``11`` for MPEG-1.
    ``01`` is reserved by the format and must be rejected when validating
    a frame header.
    """
    MPEG2_5 = 0
    RESERVED = 1
    MPEG2 = 2
    MPEG1 = 3

class MPEGLayer(IntEnum):
    """Raw MPEG audio layer bits stored in the frame header.

    MP3 files are MPEG Audio Layer III, represented here by ``LIII``.
    The other layers are parsed so that the frame length and header
    validation logic can reject or handle non-MP3 MPEG audio frames
    consistently.
    """
    RESERVED = 0
    LIII = 1
    LII = 2
    LI = 3

class MPEGBitRate(IntEnum):
    """Bitrate index from the MPEG frame header.

    The enum value is the four-bit index stored in the header, not the
    bitrate itself. Use :meth:`kbs` with the MPEG version and layer to
    resolve the index to a bitrate in kbit/s.
    """
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
        """Resolve this MPEG bitrate index to a bitrate in kbit/s.

        The bitrate table depends on both MPEG version and audio layer.
        ``FREE`` and ``BAD`` are rejected because this project needs a
        deterministic frame length to parse and patch the first frame safely.

        Args:
            version: MPEG version parsed from the frame header.
            layer: MPEG audio layer parsed from the frame header.

        Returns:
            Bitrate in kbit/s.

        Raises:
            ValueError: If the bitrate, version or layer combination is invalid.
        """
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
    """Raw MPEG sample rate stored in the frame header."""
    RATE_0 = 0b00
    RATE_1 = 0b01
    RATE_2 = 0b10
    RESERVED = 0b11

    def hz(self, version: MPEGVersion) -> int:
        """Resolve this sample-rate index to a frequency in hertz.

        The same two-bit sample-rate index maps to different frequencies
        depending on the MPEG version.

        Args:
            version: MPEG version parsed from the frame header.

        Returns:
            Sample rate in hertz.

        Raises:
            ValueError: If the version or sample-rate index is reserved.
        """
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
    """Raw MPEG channel mode bits stored in the frame header."""
    STEREO = 0b00
    JOINT = 0b01
    DUAL = 0b10
    MONO = 0b11

class MPEGModeExtension(IntEnum):
    """Raw MPEG mode extension bits stored in the frame header."""
    NONE = 0b00
    INTENSITY = 0b01
    MS = 0b10
    INTENSITY_MS = 0b11

class MPEGEmphasis(IntEnum):
    """Raw MPEG emphasis bits stored in the frame header."""
    NONE = 0b00
    _50_15 = 0b01
    RESERVED = 0b10
    CCITT = 0b11

class InvalidMP3File(Exception):
    pass

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

def slot_size(layer: MPEGLayer) -> int:
    """Return the MPEG audio slot size in bytes for a layer.

    Layer I frames are expressed in four-byte slots. Layer II and Layer III
    frames are expressed in one-byte slots. The padding bit always adds one
    slot, not necessarily one byte.
    """
    if layer == MPEGLayer.LI:
        return 4
    return 1

def frame_length(version: MPEGVersion, layer: MPEGLayer, bitrate: MPEGBitRate,
                 sample_rate: MPEGSampleRate, padding: bool) -> int:
    """Compute the full MPEG frame length in bytes.

    The returned length includes the four-byte MPEG header, optional MPEG
    protection CRC, side information and frame payload. For Layer I, the
    padding bit adds one four-byte slot; for Layer II and Layer III it adds
    one byte.

    Args:
        version: MPEG version from the frame header.
        layer: MPEG audio layer from the frame header.
        bitrate: Bitrate index from the frame header.
        sample_rate: Sample-rate index from the frame header.
        padding: Whether the frame padding bit is set.

    Returns:
        Full frame length in bytes.

    Raises:
        ValueError: If the version/layer/bitrate/sample-rate combination
            is invalid or unsupported.
    """
    samples = samples_per_frame(version, layer)
    slot = slot_size(layer)

    length_in_slots = int(samples/sample_rate.hz(version)*bitrate.kbs(version, layer)*1000/8/slot)\
                     + int(padding)

    return length_in_slots * slot

def validate_mpeg_header(f: BinaryIO, offset:int) -> bool:
    """Return whether a plausible MPEG frame header exists at *offset*.

    This function validates only the four-byte MPEG header. It rejects
    reserved version/layer/sample-rate values, free or invalid bitrates and
    reserved emphasis. The stream position is restored before returning so
    callers can use it safely while scanning through junk or ID3 padding.
    """
    current = f.tell()
    f.seek(offset)
    try:
        try:
            header = read_u32(f)
        except EOFError:
            return False

        # Recheck synchro
        if (header >> 21) != 0x7FF:
            logger.warning("No synchro at offset: %x", offset)
            return False

        # If any of these fields cannot be parsed we reject the candidate
        try:
            version = MPEGVersion((header >> 19) & 0b11)
            layer = MPEGLayer((header >> 17) & 0b11)
            bitrate = MPEGBitRate((header >> 12) & 0b1111)
            samplerate = MPEGSampleRate((header >> 10) & 0b11)
            MPEGChannelMode((header >> 6) & 0b11)
            MPEGModeExtension((header >> 4) & 0b11)
            emphasis = MPEGEmphasis(header & 0b11)
        except ValueError:
            return False

        if version == MPEGVersion.RESERVED:
            return False

        if layer == MPEGLayer.RESERVED:
            return False

        if bitrate in (MPEGBitRate.FREE, MPEGBitRate.BAD):
            return False

        if samplerate == MPEGSampleRate.RESERVED:
            return False

        if emphasis == MPEGEmphasis.RESERVED:
            return False

        return True
    finally:
        f.seek(current)

def search_for_mpeg_synchro(f: BinaryIO, start_offset: int,
                            max_scan: int = 1024 * 1024) -> int | None:
    """Search forward for the first plausible MPEG frame synchronization.

    Scanning starts after the declared end of the leading ID3v2 tag. This is
    deliberately tolerant because real-world MP3 files can contain extra zero
    padding or junk between ID3v2 and the first MPEG frame.

    Args:
        f: Binary stream positioned anywhere.
        start_offset: Offset where scanning should begin.
        max_scan: Maximum number of bytes to inspect.

    Returns:
        Offset of the first plausible MPEG frame header, or ``None`` if no
        valid candidate is found within the scan window.
    """
    f.seek(start_offset)

    end_offset = start_offset + max_scan
    pos = start_offset

    previous = f.read(1)
    if not previous:
        return None

    pos += 1

    while pos < end_offset:
        current = f.read(1)
        if not current:
            return None

        b0 = previous[0]
        b1 = current[0]

        candidate = f.tell()-2

        if b0 == 0xFF and (b1 & 0xE0) == 0xE0:
            if validate_mpeg_header(f, candidate):
                return candidate
            logger.debug("Skipping candidate at offset: %x", candidate)

        previous = current
        pos += 1

    return None

@dataclass
class MPEGHeader:
    """Parsed representation of the first MPEG audio frame.

    The object stores the MPEG frame header fields, optional protection CRC,
    side information, and either a Xing/Info metadata block or the audio main
    data found in the remainder of the frame.

    Volvo Sensus compatibility is determined from the first MPEG frame header:
    the player accepts files when the first frame is marked as Joint Stereo and
    Original. When a Xing/LAME block is present, the whole first frame can be
    rewritten to keep metadata consistent. When no Xing/Info block is present,
    only the four MPEG header bytes should be patched, because the rest of the
    frame contains audio data.
    """
    length: int
    offset: int
    version: MPEGVersion
    layer: MPEGLayer
    no_crc: bool
    crc: bytes
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
    audio: bytes


    def mpeg_header_bytes(self) -> bytes:
        """Serialize only the four-byte MPEG frame header.

        This is the safe representation to write when applying the minimal Volvo
        Sensus compatibility patch. It does not include CRC, side information,
        Xing/LAME metadata, padding or audio data.
        """
        b0 = 0xFF
        b1 = (0b111 << 5) | (self.version << 3) | (self.layer << 1) | int(self.no_crc)
        b2 = (self.bitrate << 4) | (self.samplerate << 2) | (int(self.padding) << 1) |\
            int(self.private)
        b3 = (self.channel_mode << 6) | (self.mode_extension << 4) | (int(self.copyright) << 3) |\
            (int(self.original) << 2) | self.emphasis

        return bytes([b0, b1, b2, b3])

    def patch_mpeg_header_only(self, path: Path) -> None:
        """Patch only the first frame's MPEG header in *path*.

        This is used for existing MP3 files and for files without a valid Xing/LAME
        block. It preserves the rest of the first frame unchanged, which avoids
        corrupting audio main data.
        """
        with path.open("r+b") as f:
            f.seek(self.offset)
            f.write(self.mpeg_header_bytes())

    def to_bytes(self) -> bytes:
        """Serialize the parsed first MPEG frame.

        If a Xing/Info block is present, the serialized frame contains the MPEG
        header, optional protection CRC, side information, Xing/LAME metadata and
        zero padding. If no Xing/Info block is present, the stored audio bytes are
        written back unchanged.

        Prefer :meth:`patch_mpeg_header_only` when only Volvo Sensus compatibility
        bits need to be changed.
        """
        buf = BytesIO()
        header = self.mpeg_header_bytes()
        buf.write(header)
        if not self.no_crc:
            buf.write(self.crc)
        buf.write(self.sideinfo)
        if self.xing is not None:
            xing = self.xing.to_bytes()
            logger.debug("Xing: %d\n", len(xing))
            buf.write(xing)
            # In case of presence of a Xing header the rest of the frame is padding.
            padding = bytes(self.padding_length)
            buf.write(padding)
        else:
            # When there is no Xing info the rest of frame is dedicated to audio data.
            if len(self.audio) > 0:
                buf.write(self.audio)
        return buf.getvalue()

    @classmethod
    def parse(cls, source: Path | BinaryIO) -> Self | None:
        """Parse the first MPEG frame from a path or binary stream.

        Leading ID3v2 tags are skipped, then the stream is scanned for a plausible
        MPEG frame synchronization. The parser returns ``None`` if no suitable frame
        can be found.
        """
        if isinstance(source, Path):
            with source.open("rb") as f:
                return cls.from_stream(f)

        return cls.from_stream(source)

    @classmethod
    def from_stream(cls, f: BinaryIO) -> Self | None:
        """Parse the first MPEG frame from an open binary stream.

        The parser handles leading ID3v2 tags, junk between ID3 and MPEG data,
        optional MPEG protection CRC, side information, and optional Xing/Info plus
        LAME metadata. If the first frame has no Xing/Info block, the remaining
        bytes are treated as audio data and preserved.
        """
        # Search for ID3v2 tags
        id3_offset = skip_id3v2_tags(f)
        logger.debug("Skipping ID3 tags at offset %x", id3_offset)
        f.seek(id3_offset)
        # Searching for the first MPEG synchronization
        frame_offset = search_for_mpeg_synchro(f, id3_offset)
        if frame_offset is None:
            return None
        logger.debug("Found synchronization at offset %x", frame_offset)
        f.seek(frame_offset)
        header = read_u32(f)

        if (header >> 21) != 0x7FF:
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

        # There is a CRC
        crc = bytes()
        if not no_crc:
            crc = f.read(2)

        side_info = f.read(side_info_size)
        xing = XingHeader.parse(f)
        expected_length = frame_length(version, layer, bitrate, samplerate, padding)
        actual_end = f.tell()
        actual_length = actual_end-frame_offset
        padding_length = 0
        if actual_length > expected_length:
            # TODO: do something in case of inconsistency
            logger.error("MPEG header length (%d) is longer than expected (%d)",
                            actual_length, expected_length)
            return None
        padding_length = expected_length - actual_length
        audio = bytes()
        remaining = f.read(padding_length)
        if xing is None:
            logger.warning("Found first frame with audio for %s.", f)
            audio = remaining
        else:
            if not all(b == 0x00 for b in remaining):
                # TODO: do something when padding is not zeroed !
                logger.debug(hexdump.dump(remaining))
                logger.warning("Padding of %s is not zeroed. Frame offset: %d", f, frame_offset)

        return MPEGHeader(
            length = expected_length,
            offset = frame_offset,
            version = version,
            layer = layer,
            no_crc = no_crc,
            crc = crc,
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
            audio = audio,
            padding_length = padding_length)

    def is_sensus_compatible(self) -> bool:
        """Return whether the first MPEG frame matches Volvo Sensus expectations.

        Current testing shows that Volvo Sensus requires the first MPEG frame to be
        marked as Joint Stereo and Original.
        """
        return self.channel_mode == MPEGChannelMode.JOINT and self.original

    def fix_sensus_compatibility(self, path: Path, minimal: bool,
                                 encoding: EncodingSettings) -> None:
        """Patch an MP3 file so its first frame is accepted by Volvo Sensus.

        The method always sets the first MPEG frame to Joint Stereo and Original.
        In minimal mode, or when Xing/LAME metadata is missing, only the four-byte
        MPEG header is written. When a full Xing/LAME block is available, selected
        LAME fields and the LAME tag CRC are updated before rewriting the full
        first frame.

        Args:
            path: MP3 file to patch in place.
            minimal: If true, patch only the MPEG header.
            encoding: Encoding settings used for converted files. May be ``None``
                for existing MP3 files patched in minimal mode.
        """
        self.channel_mode = MPEGChannelMode.JOINT
        self.original = True

        if minimal or self.xing is None or self.xing.lame is None:
            self.patch_mpeg_header_only(path)
            return

        if not minimal and encoding is not None and self.xing is not None and\
            self.xing.lame is not None:
            if self.xing.lame.vbr_method == VbrMethod.UNKNOWN:
                self.xing.lame.vbr_method = VbrMethod(int(encoding.mode)+1)
            if encoding.mode in (EncodingMode.CBR, EncodingMode.ABR)\
                and self.xing.lame.bitrate != self.bitrate.kbs(self.version, self.layer):
                self.xing.lame.bitrate = encoding.value
            if self.xing.lame.misc.stereo_mode != StereoMode.JOINT:
                self.xing.lame.misc.stereo_mode = StereoMode.JOINT
            self.xing.lame.misc.source_frequency = SourceFrequency.from_hz(
                                                    self.samplerate.hz(self.version))

        data = self.to_bytes()
        # Fix final CRC: excluding the CRC itself
        if self.xing is not None and self.xing.lame is not None:
            data_length = self.length - self.padding_length - 2
            self.xing.lame.tag_crc = CRC16.compute(data[:data_length])
        data = self.to_bytes()

        if len(data) != self.length:
            raise ValueError(
                f"Rewritten frame has invalid length: original={self.length}, new={len(data)}"
            )
        with open(path.resolve(), 'r+b') as f:
            f.seek(self.offset)
            length = f.write(data)
            logger.debug("%d bytes written", length)
            f.flush()
