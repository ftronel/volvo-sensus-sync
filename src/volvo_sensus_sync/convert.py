import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mutagen import File
from typeguard import typechecked

from .mp3 import EncodingMode, EncodingSettings, check_sensus_compatibility


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
    logger = logging.getLogger(__name__)

    logger.debug("Converting %s into %s with parameters: %s", input_file, output_file, settings)

    if output_file.exists():
        logger.warning('Destination file %s already exists !', output_file)
        return None

    audio = File(input_file)
    compat = check_sensus_compatibility(audio, input_file)
    if compat:
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
                    "-write_xing", "0",  "-map", "0:a:0", "-map_metadata", "-1",
                ]

    match settings.mode:
        case EncodingMode.CBR:
            ffmpeg_cmd += ["-b:a", f"{settings.value}k"]
        case EncodingMode.ABR:
            ffmpeg_cmd += ["-abr", "1", "-b:a", f"{settings.value}k"]
        case EncodingMode.VBR:
            ffmpeg_cmd += ["-q:a", str(settings.value)]

    ffmpeg_cmd += [ str(output_file) ]

    ffmpeg = subprocess.Popen(ffmpeg_cmd, start_new_session=True)

    return ConversionProcess(ffmpeg=ffmpeg)
