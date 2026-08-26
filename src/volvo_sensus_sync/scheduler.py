# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
Parallel conversion scheduler.

This module schedules multiple FFmpeg conversion processes while limiting
the maximum number of concurrent jobs.
"""

import logging
import os

from tqdm import tqdm
from typeguard import typechecked

from .config import EncodingSettings
from .convert import convert
from .mpegheader import InvalidMP3File
from .step import runtime_state
from .track import Track

logger = logging.getLogger(__name__)


@typechecked
def finish_conversion(track: Track, settings: EncodingSettings) -> None:
    """Finalize one converted or copied track.

    The function verifies the destination MP3, applies the Volvo Sensus MPEG
    header patch when needed, checks the result, then writes ID3 metadata.

    Args:
        track: Track whose destination file has been produced.
        settings: Encoding settings used for FFmpeg conversions.
    """
    header = track.get_mpeg_header()
    if header is None:
        logger.error("Cannot find MPEG header in %s", track.dest)
        return
    if not header.is_sensus_compatible():
        header.fix_sensus_compatibility(track.dest, False, settings)
    else:
        logger.warning("%s is already compatible !!", track)
    logger.debug("Check compatibility fix.")
    header = track.get_mpeg_header()
    if header is None:
        logger.error("MPEG header was corrupted during Volvo Sensus fix in %s", track.dest)
        return
    fixed = header.is_sensus_compatible()
    if not fixed:
        logger.error("Impossible to fix Volvo compatibility of: %s", track.dest)
    # Write metadata
    track.write_tags()

def find_next_track(tracks_by_pid: dict[int, Track] , active_tracks: set[Track],
                    conversions: list[Track], settings: EncodingSettings) -> bool:
    """Start or process the next pending track.

    If the source is an existing MP3 and no FFmpeg process is needed, the track
    is finalized immediately and the function returns ``True`` so the progress
    bar can be advanced. If FFmpeg is started, the process is registered in
    ``tracks_by_pid`` and ``active_tracks`` and the function returns ``False``.

    Returns:
        ``True`` when the track completed synchronously, otherwise ``False``.
    """
    track = conversions.pop()
    try:
        conv = convert(track.source, track.dest, settings)
    except InvalidMP3File:
        return True

    # If we draw an MP3 file we keep on trying to fill processor with conversion
    if conv is None:
        finish_conversion(track, settings)
        return True

    track.process = conv
    tracks_by_pid[conv.ffmpeg.pid] = track
    active_tracks.add(track)
    return False

def check_ffmpeg_warnings(track: Track) -> bool:
    """Return whether FFmpeg produced stderr output for a successful track.

    Empty log files are removed. Non-empty log files are kept so the caller can
    report the track as completed with warnings.
    """
    stderr_path = track.process.stderr_path

    if not stderr_path.exists():
        return False

    if stderr_path.stat().st_size == 0:
        stderr_path.unlink()
        return False

    return True


@typechecked
def scheduler(conversions: list[Track], nb_threads: int, settings: EncodingSettings) -> None:
    """Run multiple conversions in parallel, respecting *nb_threads*.

    A simple process pool is implemented manually to allow graceful handling of
    SIGINT.  The function updates a tqdm progress bar and logs any conversion
    failures.

    Args:
        conversions: List of conversion dictionaries returned by
            :func:`determine_conversions`.
        nb_threads: Maximum number of simultaneous ``ffmpeg`` processes.
        bitrate: Desired MP3 bitrate (passed to :func:`convert`).
    """
    tracks_by_pid = {}
    active_tracks: set[Track] = set()
    errors: set[Track] = set()
    warnings: set[Track] = set()

    with tqdm(total=len(conversions), desc="Conversions", unit="Track") as progress:
        progress.set_postfix(active=len(active_tracks), warnings=len(warnings), errors=len(errors))
        # Fill up the buffer with nb_threads conversions
        logger.debug("Filling CPUs with %d conversions", nb_threads)
        while (len(active_tracks) < nb_threads) and (len(conversions) >0):
            if find_next_track(tracks_by_pid, active_tracks, conversions, settings):
                progress.update(1)
        progress.set_postfix(active=len(active_tracks), warnings=len(warnings), errors=len(errors))

        # Keep on launching conversions until completion or interrupt is requested.
        while len(active_tracks) > 0:
            # Wait for completion of a subprocess
            logger.debug("Waiting for conversion completion")
            try:
                # Wait for next process to end up
                pid, status = os.wait()
            except KeyboardInterrupt:
                logger.debug("Waiting for end of current conversions")
                continue
            status = os.WEXITSTATUS(status)
            track = tracks_by_pid[pid]
            process = track.process
            logger.debug('ffmpeg finished for %s', track)
            process.finished = True
            process.successful = status == 0
            if status != 0:
                logger.error('Conversion was not successful for %s', track)
                failed_path = track.dest
                failed_path.unlink(missing_ok = True)
                errors.add(track)
            logger.debug("Track status: %s", track)
            if process.finished:
                if process.successful:
                    if check_ffmpeg_warnings(track):
                        logger.warning("FFmpeg warnings for %s", track.source)
                        warnings.add(track)
                    finish_conversion(track, settings)
                    logger.debug('Conversion of %s was successful', track)
                # Closing and flushing error log
                # track.stderr_path.flush()
                # track.stderr_path.close()
                active_tracks.remove(track)
                tracks_by_pid.pop(pid)
            progress.update(1)
            progress.set_postfix(active=len(active_tracks), warnings=len(warnings),
                                 errors=len(errors))

            # If we can admit a new conversion, find a candidate
            while len(active_tracks) < nb_threads and len(conversions)>0 \
                and runtime_state.interruptions == 0:
                if find_next_track(tracks_by_pid, active_tracks, conversions, settings):
                    progress.update(1)
                progress.set_postfix(active=len(active_tracks), warnings=len(warnings),
                                     errors=len(errors))
