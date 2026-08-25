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
from .mpegheader import MPEGHeader

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class ConversionProcess:
    """
    Container that tracks the life‑cycle of the external processes used to
    convert a single audio file.

    This implementation launch a single process:

    * **ffmpeg**: performs the decoding / re‑encoding of the source audio
      to a MP3 compatible with Volvo Sensus.

    Attributes
    ----------
    ffmpeg: subprocess.Popen
        The ``ffmpeg`` process handling the decoding step.  ``None`` is not
        allowed: a ``ConversionProcess`` is always instantiated with a valid
        process object.
    finished: bool, default ``False``
        ``True`` when ffmpeg subprocess has finished.
    successful: bool, default ``False``
        ``True`` when ffmpeg subprocess have finished *and* was
        successful.
    """
    ffmpeg: subprocess.Popen
    stderr_path: Path
    finished: bool = False
    successful: bool = False

@typechecked
def convert(input_file: Path, output_file: Path,
            settings: EncodingSettings) -> ConversionProcess | None:
    """Convert *input_file* to MP3 using ``ffmpeg`` at the requested *quality*.

    If the source file is already an MP3 a hard‑link (or a copy if hard‑links are
    not supported) is created instead of invoking ``ffmpeg``.

    Args:
        input_file: Path to the original audio file.
        output_file: Desired MP3 destination (must not already exist).
        bitrate: MP3 bitrate.

    Returns:
        ``None`` if no conversion was necessary, otherwise a :class:`subprocess.Popen`
        object representing the running ``ffmpeg`` process.
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
            return None
        compat = header.is_sensus_compatible()
        if not compat:
            header.fix_sensus_compatibility(output_file, settings)
        header = MPEGHeader.parse(output_file)
        if header is None:
            logger.error("Impossible to parse MPEG header of %s", output_file)
            return None
        compat = header.is_sensus_compatible()
        if not compat:
            logger.error("Impossible to fix MP3 compatibility of %s", input_file)
            return None
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
