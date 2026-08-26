# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
Audio conversion routines.

This module determines whether tracks require transcoding and invokes
FFmpeg to produce Volvo Sensus compatible MP3 files.
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mutagen import File
from mutagen.mp3 import MP3
from typeguard import typechecked

from .config import EncodingMode, EncodingSettings
from .mpegheader import MPEGHeader, InvalidMP3File

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class ConversionProcess:
    """State associated with one running FFmpeg conversion.

    Attributes:
        ffmpeg: Running FFmpeg subprocess.
        stderr_path: Path where FFmpeg stderr is captured.
        finished: Whether the subprocess has completed.
        successful: Whether the subprocess exited with status code 0.
    """
    ffmpeg: subprocess.Popen
    stderr_path: Path
    finished: bool = False
    successful: bool = False

@typechecked
def convert(input_file: Path, output_file: Path,
            settings: EncodingSettings) -> ConversionProcess | None:
    """Create the destination MP3 for one source audio file.

    Existing MP3 files are handled without FFmpeg. If the MP3 is already
    compatible with Volvo Sensus, it is hard-linked to the destination when
    possible, or copied otherwise. If it is not compatible, it is copied first
    and the copy is patched in minimal mode so the source file is never modified.

    Non-MP3 sources are transcoded asynchronously with FFmpeg and the running
    process is returned.

    Args:
        input_file: Source audio file.
        output_file: Destination MP3 path. It must not already exist.
        settings: Encoding mode and value passed to FFmpeg for transcoding.

    Returns:
        ``None`` when no FFmpeg process was started, otherwise a
        :class:`ConversionProcess` wrapping the running FFmpeg process.

    Raises:
        InvalidMP3File: If an existing MP3 cannot be parsed.
    """
    logger.debug("Converting %s into %s with parameters: %s", input_file, output_file, settings)

    if output_file.exists():
        logger.warning('Destination file %s already exists !', output_file)
        return None

    audio = File(input_file)

    # In case of MP3 we check if it is already compatible with Volvo Sensus
    if isinstance(audio, MP3):
        header = MPEGHeader.parse(input_file)
        if header is None:
            logger.error("Impossible to parse MPEG header of %s", input_file)
            raise InvalidMP3File()
        compat = header.is_sensus_compatible()
        if not compat:
            # We modifiy original version.
            shutil.copy2(input_file, output_file)
            header.fix_sensus_compatibility(output_file, True, None)
            # Verify compatibility
            header = MPEGHeader.parse(output_file)
            if header is None:
                logger.error("Impossible to parse MPEG header of %s", output_file)
                raise InvalidMP3File()
            compat = header.is_sensus_compatible()
            if not compat:
                logger.error("Impossible to fix MP3 compatibility of %s", input_file)
                return None
        else:
            # Try to create a hardlink
            try:
                output_file.hardlink_to(input_file)
            except OSError:
                # Volumes différents ou hard links non supportés
                shutil.copy2(input_file, output_file)
        return None

    # We only transcode the audio track to MP3 and suppress all others metadata
    # since they will be written later by mutagen.
    ffmpeg_cmd = [ "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                    "-i", str(input_file),"-codec:a", "libmp3lame",
                    "-map", "0:a:0", "-map_metadata", "-1",
                ]

    match settings.mode:
        case EncodingMode.CBR:
            ffmpeg_cmd += ["-b:a", f"{settings.value}k"]
        case EncodingMode.ABR:
            ffmpeg_cmd += ["-abr", "1", "-b:a", f"{settings.value}k"]
        case EncodingMode.VBR:
            ffmpeg_cmd += ["-q:a", str(settings.value)]

    ffmpeg_cmd += [ str(output_file) ]

    stderr_path = output_file.with_suffix(output_file.suffix + ".ffmpeg.log")
    stderr_file = stderr_path.open("wb")

    ffmpeg = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.DEVNULL,
        stderr=stderr_file,
        start_new_session=True)

    return ConversionProcess(ffmpeg=ffmpeg,
                             stderr_path=stderr_path)
