import sys
import logging
from dataclasses import dataclass
from pathlib import Path
from enum import IntEnum

from mutagen.mp3 import MP3


@dataclass(slots=True)
class XingHeader:
    present: bool
    magic: str | None = None
    is_lame: bool = False
    encoder: str | None = None

class EncodingMode(IntEnum):
    CBR = 0
    ABR = 1
    VBR = 2

@dataclass(slots=True)
class EncodingSettings:
    mode: EncodingMode
    value: int

def parse_xing(path: Path) -> XingHeader:
    logger = logging.getLogger(__name__)

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
        header = int.from_bytes(f.read(4), "big")

        if (header >> 21) != 0x7FF:
            logger.error("No MPEG frame found in %s", path)
            sys.exit(-1)

        version_bits = (header >> 19) & 0b11
        channel_mode = (header >> 6) & 0b11

        #
        # Compute side information size
        #
        if version_bits == 0b11:          # MPEG-1
            side_info = 17 if channel_mode == 3 else 32
        else:                              # MPEG-2 / 2.5
            side_info = 9 if channel_mode == 3 else 17

        xing_offset = frame_offset + 4 + side_info

        f.seek(xing_offset)

        magic = f.read(4)

        if magic not in (b"Xing", b"Info"):
            return XingHeader(
                present=False,
            )

        flags = int.from_bytes(f.read(4), "big")

        if flags & 0x0001:      # Frames
            f.seek(4, 1)

        if flags & 0x0002:      # Bytes
            f.seek(4, 1)

        if flags & 0x0004:      # TOC
            f.seek(100, 1)

        if flags & 0x0008:      # Quality
            f.seek(4, 1)

        lame_id = f.read(9).decode("ascii", errors="replace")
        is_lame = lame_id.startswith("LAME")

        return XingHeader(
            present=True,
            magic = magic,
            is_lame = is_lame,
            encoder = lame_id,
        )

def check_sensus_compatibility(audio, path) -> bool:
    if not isinstance(audio, MP3):
        return False

    xing = parse_xing(path)
    # Either Xing header is not present or encoder is Lame
    return (not xing.present) or xing.is_lame
