# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements data classes and constants encountered Xing header.
"""

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Self

from .config import EncodingMode
from .lametag import LameTag
from .mp3 import read_u32

logger = logging.getLogger(__name__)


@dataclass
class XingHeader:
    """Information extracted from an MP3 Xing/LAME header."""
    encoding : EncodingMode
    frames: int | None
    audio_length: int | None
    toc: bytes | None
    quality: int | None
    lame: LameTag | None

    def to_bytes(self) -> bytes:
        buf = BytesIO()
        if self.encoding == EncodingMode.CBR:
            buf.write(b'Info')
        else:
            buf.write(b'Xing')
        flags = 0
        if self.frames is not None:
            flags |= 1
        if self.audio_length is not None:
            flags |= 2
        if self.toc is not None:
            flags |= 4
        if self.quality is not None:
            flags |= 8
        buf.write(flags.to_bytes(4, byteorder='big'))
        if self.frames is not None:
            buf.write(self.frames.to_bytes(4, byteorder="big"))
        if self.audio_length is not None:
            buf.write(self.audio_length.to_bytes(4, byteorder="big"))
        if self.toc is not None:
            buf.write(self.toc)
        if self.quality is not None:
            buf.write(self.quality.to_bytes(4, byteorder="big"))
        data = buf.getvalue()
        logger.debug("Xing length: %d", len(data))
        if self.lame is not None:
            lame = self.lame.to_bytes()
            buf.write(lame)
        return buf.getvalue()

    @classmethod
    def parse(cls, f: BinaryIO) -> Self | None:
        magic = f.read(4)

        if magic not in (b"Xing", b"Info"):
            f.seek(-4,1)
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
            toc = f.read(100)
        if flags & 0x0008:      # Quality
            quality = read_u32(f)

        lame = LameTag.parse(f)

        return XingHeader(
            encoding = encoding,
            frames = nb_frames,
            audio_length = audio_length,
            toc = toc,
            quality = quality,
            lame = lame)
