# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
This module implements data classes and constants encountered Xing header.
"""

from dataclasses import dataclass
from io import BytesIO
import logging

from .lametag import LameTag
from .config import EncodingMode

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
        if lame is not None:
            lame = self.lame.to_bytes()
            buf.write(lame)
        return buf.getvalue()
