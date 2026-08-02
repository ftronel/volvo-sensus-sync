#!/usr/bin/env python3
"""export.py

A command‑line utility that scans a directory tree for audio files, extracts
metadata, and converts them to a uniform MP3 layout.  The resulting files are
organized by artist and album, optionally split into several export directories
to respect a maximum size per directory.

The script supports parallel conversion using ``ffmpeg`` and graceful shutdown
on SIGINT.  All public functions are type‑checked with :pypi:`typeguard` and
documented with clear docstrings for easier maintenance and automatic API
generation.
"""

from shutil import which
import argparse
import logging
from pathlib import Path
import sys
import re
import os
import shutil
import subprocess
import signal
from enum import IntEnum
from math import ceil
import unicodedata
from dataclasses import dataclass

import coloredlogs
from mutagen import File, MutagenError
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TALB, TPE1, TRCK, TPOS, ID3NoHeaderError
from tqdm import tqdm
from typeguard import typechecked


AUDIO_EXTENSIONS = { ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma",
                    ".opus", ".aiff", ".alac" }

INVALID = r'[<>:"/\\|?*\x00-\x1F]'

class Step(IntEnum):
    """Enumeration describing the current processing step.

    Used mainly for graceful shutdown handling.
    """

    INIT = 0
    ARGS_PROCESSING = 1
    FILES_ENUMERATION = 2
    METADATA_RETRIEVAL = 3
    SORTING_BY_ARTIST = 4
    EXPORT_STRUCTURE = 5
    CONVERSION = 6
    EXPORT_SIZE = 7
    STATS = 8
    SORTING_STATS = 9
    SEARCH_CUTS = 10

@dataclass(slots=True)
class ConversionProcess:
    ffmpeg: subprocess.Popen
    lame: subprocess.Popen
    ffmpeg_finished: bool = False
    ffmpeg_successful: bool = False
    lame_finished: bool = False
    lame_successful: bool = False
    finished: bool = False
    successful: bool = False

@dataclass(slots=True)
class Track:
    source: Path
    artist: str
    album: str
    title: str
    dest: Path | None = None
    track: int | None = None
    disc_id: int | None = None
    disc_total: int | None = None
    processes: ConversionProcess | None = None

    def __hash__(self):
        return hash(self.source)

    def write_tags(self):
        try:
            tags = ID3(self.dest)
        except ID3NoHeaderError:
            tags = ID3()

        tags.add(TIT2(encoding=3, text=self.title))
        tags.add(TALB(encoding=3, text=self.album))
        tags.add(TPE1(encoding=3, text=self.artist))
        tags.add(TRCK(encoding=3, text=f"{self.track_number}"))
        tags.add(TPOS(encoding=3, text=f"{self.disc_id}/{self.disc_total}"))
        tags.save(self.dest, v2_version=3)

STOP = 0
step = Step.INIT

def sigint_handler(signum, frame):
    """Handle SIGINT (Ctrl‑C).

    If the conversion step is active the handler sets a global flag to stop
    launching new jobs and allows the currently running subprocesses to finish
    gracefully.  During any earlier step the program exits immediately.
    """
    global STOP

    logger = logging.getLogger(__name__)
    if step != Step.CONVERSION:
        sys.exit(-1)
    STOP += 1
    logger.warning("Please wait during graceful shutdown")

@typechecked
def check_binaries() -> None:
    logger = logging.getLogger(__name__)

    binaries = [ 'ffmpeg', 'lame']
    for binary in binaries:
        if which(binary) is None:
            logger.error("%s is not installed.", binary)
            sys.exit(1)

@typechecked
def sanitize(name: str) -> str:
    """Return a filesystem‑safe version of *name*.

    The function replaces characters that are invalid on most platforms with an
    underscore and strips trailing spaces or dots.

    Args:
        name: The original string (typically metadata such as artist or title).

    Returns:
        A sanitized string safe to use as a file or directory name.
    """
    name = re.sub(INVALID, "_", name)
    name = name.rstrip(" .")
    return name

@typechecked
def sort_artist_path(path: Path) -> str:
    """Return a case‑folded, diacritics‑stripped representation of *path*.

    This helper is used to sort artist directories in a locale‑independent way.

    Args:
        path: A :class:`~pathlib.Path` instance whose ``name`` attribute is an
            artist name.

    Returns:
        A normalized string suitable for alphabetical sorting.
    """
    name = path.name
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return name.casefold()

@typechecked
def get_audio_list(root: Path) -> list[Path]:
    """Recursively collect all supported audio files under *root*.

    Args:
        root: Directory to search.

    Returns:
        A list of :class:`~pathlib.Path` objects pointing to files whose suffix
        matches one of :data:`AUDIO_EXTENSIONS`.
    """
    logger = logging.getLogger(__name__)

    res = []

    logger.info('Searching for potential audio files')
    for inode in root.rglob("*"):
        if inode.is_file() and inode.suffix.lower() in AUDIO_EXTENSIONS:
            logger.debug("Parsing %s", inode)
            res.append(inode)

    return res

@typechecked
def get_metadata(files: list[Path]) -> dict[str,dict[str,dict[int,list[Track]]]]:
    """Extract relevant metadata from a list of audio files.

    The function groups files by *artist -> album -> disc* and stores a list of
    track dictionaries for each disc.  Each track dictionary contains the
    original file path, sanitized title and numeric track information.

    Args:
        files: List of audio file paths returned by :func:`get_audio_list`.

    Returns:
        A nested dictionary structured as

        ``{artist: {album: {disc_number: [track_dict, ...]}}}``

        where *track_dict* contains the keys ``inode``, ``title``, ``disc``,
        ``nb_discs`` and ``track``.
    """
    logger = logging.getLogger(__name__)

    res = {}
    for inode in tqdm(files):
        try:
            audio = File(inode, easy=True)
        except MutagenError:
            logger.warning("Impossible to read: %s", inode)
            continue
        if audio is None:
            logger.warning("%s is not an audio file", inode)
            continue

        artist = sanitize(audio.get("albumartist", ["Inconnu"])[0])
        album = sanitize(audio.get("album", ["Inconnu"])[0])
        title = sanitize(audio.get("title", [inode.stem])[0])
        disc = audio.get("discnumber", [""])[0]
        if "/" in disc:
            disc_id, nb_discs = map(int, disc.split("/", 1))
        else:
            disc_id = int(disc)
            nb_discs = 1
        track = audio.get("tracknumber", ["0"])[0]
        try:
            track = int(track.split("/")[0])
        except (ValueError,TypeError):
            logger.error("Bad track number: '%s' for inode %s", track, inode)
            sys.exit(-1)
        if artist not in res:
            res[artist] = {}
        albums = res[artist]
        if album not in albums:
            albums[album] = {}
            for d in range(0, nb_discs):
                albums[album][d+1] = []
        discs = albums[album]
        if disc_id not in discs:
            discs[disc_id] = []
        tracks = discs[disc_id]
        track = Track(source=inode, artist=artist, album=album, disc_id=disc_id,
                      disc_total=nb_discs, track=track, title=title)
        # tracks.append({'inode': inode, 'title': title, 'disc': disc_id, 'nb_discs': nb_discs,
        #               'track': track})
        tracks.append(track)

    return res

@typechecked
def determine_conversions(audios: dict[str,dict[str,dict[int,list[Track]]]],
                          export_dir: Path) -> list[Track]:
    """Create a conversion plan for all tracks.

    The plan consists of a list of dictionaries, each containing the source file,
    destination path and the metadata needed for conversion.

    Args:
        audios: Nested dictionary returned by :func:`get_metadata`.
        export_dir: Base directory where the final MP3 hierarchy will be created.

    Returns:
        A list of dictionaries, each with at least the keys ``inode``, ``title``,
        ``track`` and a newly added ``to`` (the destination :class:`Path`).
    """
    logger = logging.getLogger(__name__)
    res = []

    for artist in audios.keys():
        logger.debug("Considering artist %s", artist)
        path1 = f"{export_dir}/{artist}"
        dest = Path(path1)
        if dest.exists() and not dest.is_dir():
            logger.error("A file with %s name exists under export directory.", artist)
            continue
        if not dest.exists():
            dest.mkdir()
        albums = audios[artist]
        for album in albums:
            logger.debug("Considering album %s", album)
            path2 = f"{path1}/{album}"
            dest = Path(path2)
            if dest.exists() and not dest.is_dir():
                logger.error("A file with %s album exists under export directory.", album)
                continue
            if not dest.exists():
                dest.mkdir()
            discs = albums[album]
            nb_discs = len(discs.keys())
            for disc in discs.keys():
                logger.debug("Considering disc %d", disc)
                if nb_discs > 1:
                    path3 = f"{path2}/Disc {disc}"
                    dest = Path(path3)
                    if dest.exists() and not dest.is_dir():
                        logger.error("A file with %s disc exists under export directory.", album)
                        continue
                    if not dest.exists():
                        dest.mkdir()
                    dest_path = path3
                else:
                    dest_path = path2
                tracks = discs[disc]
                for track in tracks:
                    logger.debug("Considering title: %s", track.title)
                    final_path = f"{dest_path}/{track.track:02d}-{track.title}.mp3"
                    logger.debug("Testing if file %s exists", final_path)
                    dest = Path(final_path)
                    if dest.exists():
                        if dest.is_dir():
                            logger.error("There exist a directory whose name collides with target\
file: %s", dest_path)
                            continue
                    else:
                        track.dest = dest
                        res.append(track)

    return res

@typechecked
def convert(input_file: Path, output_file: Path, bitrate: int) -> ConversionProcess:
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

    logger.debug("Converting %s into %s", input_file, output_file)

    if output_file.exists():
        logger.warning('Destination file %s already exists !', output_file)
        return None

    audio = File(input_file)
    if isinstance(audio, MP3):
        try:
            output_file.hardlink_to(input_file)
        except OSError:
            # Volumes différents ou hard links non supportés
            shutil.copy2(input_file, output_file)
        return None

    ffmpeg_cmd = [ "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                  "-i", str(input_file), "-f", "wav", "-" ]

    lame_cmd = [ "lame", "-b", f"{bitrate:d}", "-", str(output_file) ]

    ffmpeg = subprocess.Popen( ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              stdin=subprocess.DEVNULL, start_new_session=True)

    lame = subprocess.Popen( lame_cmd, stdin=ffmpeg.stdout, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)

    ffmpeg.stdout.close()

    return ConversionProcess(ffmpeg=ffmpeg, lame=lame)

@typechecked
def scheduler(conversions: list[Track], nb_threads: int, bitrate: int) -> None:
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
    logger = logging.getLogger(__name__)

    tracks_by_pid = {}
    active_tracks = set()
    errors = set()
    with tqdm(total=len(conversions), desc="Conversions", unit="Track") as progress:
        progress.set_postfix(active=len(active_tracks), errors=len(errors))
        # Fill up the buffer with nb_threads conversions
        logger.debug("Filling CPUs with %d conversions", nb_threads)
        while (len(active_tracks) < nb_threads) and (len(conversions) >0):
            track = conversions.pop()
            conv = convert(track.source, track.dest, bitrate)
            # If we draw an MP3 file we keep on trying to fill processor with conversion
            if conv is None:
                progress.update(1)
                progress.set_postfix(active=len(active_tracks), errors=len(errors))
                continue
            track.processes = conv
            tracks_by_pid[conv.lame.pid] = track
            tracks_by_pid[conv.ffmpeg.pid] = track
            active_tracks.add(track)
            progress.set_postfix(active=len(active_tracks), errors=len(errors))

        # Keep on launching conversions until completion or interrupt is requested.
        while ((len(conversions) > 0)  and (len(active_tracks) > 0) and (STOP == 0)\
            or ((len(active_tracks) > 0) and (STOP > 0))) :
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
            processes = track.processes
            ffmpeg_pid = processes.ffmpeg.pid
            lame_pid = processes.lame.pid
            if pid == ffmpeg_pid:
                logger.debug('ffmpeg finished for %s', track)
                processes.ffmpeg_finished = True
                processes.ffmpeg_successful = status == 0
            if pid == lame_pid:
                logger.debug('lame finished for %s', track)
                processes.lame_finished = True
                processes.lame_successful = status == 0
            processes.finished = processes.ffmpeg_finished and processes.lame_finished
            if processes.finished:
                processes.successful = processes.ffmpeg_successful and processes.lame_successful
            if status != 0:
                logger.error('Conversion was not successful for %s', track)
                failed_path = track.dest
                failed_path.unlink(missing_ok = True)
                errors.add(track)
            logger.debug("Track status: %s", track)
            if processes.finished:
                if processes.successful:
                    active_tracks.remove(track)
                    progress.update(1)
                    track.write_tags()
                    logger.debug('Conversion of %s was successful', track)
                tracks_by_pid.pop(pid)
            progress.set_postfix(active=len(active_tracks), errors=len(errors))

            # If we can admit a new conversion, find a candidate
            while (len(active_tracks) < nb_threads) and STOP == 0:
                track = conversions.pop()
                conv = convert(track.source, track.dest, bitrate)
                # If we draw an MP3 file we keep on trying to fill processor with conversion
                if conv is None:
                    progress.update(1)
                    progress.set_postfix(active=len(active_tracks), errors=len(errors))
                    continue
                track.processes = conv
                tracks_by_pid[conv.lame.pid] = track
                tracks_by_pid[conv.ffmpeg.pid] = track
                active_tracks.add(track)
                progress.set_postfix(active=len(active_tracks), errors=len(errors))

@typechecked
def mp3_total_size(export_dir: Path) -> int:
    """Calculate the total size (in bytes) of all MP3 files under *export_dir*.

    Args:
        export_dir: Root directory containing the exported MP3 hierarchy.

    Returns:
        Total size in bytes as an integer.
    """
    size = 0
    for inode in export_dir.rglob("*"):
        if inode.is_file() and inode.suffix.lower() == '.mp3':
            size += inode.stat().st_size

    return size

@typechecked
def stats_by_artist(export_dir: Path) -> dict[Path, int]:
    """Return a mapping from each artist directory to its total MP3 size.

    Args:
        export_dir: The ``all`` directory where all converted files are stored.

    Returns:
        ``{artist_path: size_in_bytes}``
    """
    stats = {}
    for artist in export_dir.glob("*"):
        size = mp3_total_size(artist)
        stats[artist] = size

    return stats

@typechecked
def find_cuts(stats: dict[Path, int], max_size:int, nb_parts: int) -> list[list[Path]] | None:
    """Group artist directories into partitions that respect *max_size*.

    A naïve first‑fit algorithm is used: artists are added to the current part
    until adding the next one would exceed *max_size*.  If the resulting number
    of parts exceeds *nb_parts* the function returns ``None``.

    Args:
        stats: Mapping from artist directory to its size (as returned by
            :func:`stats_by_artist`).
        max_size: Maximum allowed size per part (in bytes).
        nb_parts: Desired maximum number of parts.

    Returns:
        A list of partitions (each a list of artist :class:`Path`s) or ``None`` if
        a satisfactory partitioning is impossible.
    """
    logger = logging.getLogger(__name__)

    res = []
    part = []
    total = 0
    for artist in stats:
        size = stats[artist]
        if total+size > max_size:
            if len(part)>0:
                total = 0
                res.append(part)
                part = []
            else:
                logger.warning("Impossible to include %s in a single directory.", artist)
                return None
        else:
            total += size
            part.append(artist)

    res.append(part)

    if len(res) > nb_parts:
        logger.warning("Solution requires more parts (%d) than allowed (%d)", len(res), nb_parts)
        return None

    return res

@typechecked
def create_partitions(export: Path, all_tracks: Path, partitions: list[list[Path]]):
    """Populate the final export directory with hard‑linked copies of the tracks.

    The function creates numbered sub‑directories (``1``, ``2`` …) under
    *export* and mirrors the internal artist/albums hierarchy from *all_tracks*
    using hard links to avoid duplicating data.

    Args:
        export: Root directory where the partitioned copies will be created.
        all_tracks: Path to the ``all`` directory containing the complete MP3
            collection.
        partitions: List of partitions returned by :func:`find_cuts`.
    """
    logger = logging.getLogger(__name__)

    part_num = 1
    for part in partitions:
        part_path = export / f"{part_num}"
        part_path.mkdir(exist_ok=True, parents=True)
        for artist in part:
            for inode in artist.rglob("*"):
                rel_path = inode.relative_to(all_tracks)
                target_path = part_path / rel_path
                if inode.is_file():
                    if not target_path.exists():
                        target_path.hardlink_to(inode)
                    else:
                        logger.warning("Target file exists: %s", target_path)
                elif inode.is_dir():
                    target_path.mkdir(exist_ok=True, parents=True)
        part_num += 1

def main():
    """Entry point for the command‑line interface.

    Parses arguments, validates input/output directories, orchestrates the
    conversion pipeline and finally creates the requested partitions.
    """
    global step

    logger = logging.getLogger(__name__)

    # Install signal handler
    signal.signal(signal.SIGINT, sigint_handler)

    coloredlogs.install()
    parser = argparse.ArgumentParser()
    parser.add_argument("-v","--verbose", action='store_true', dest='verbose', help="Debug.")
    parser.add_argument("-i","--input", action='store', dest='input_dir', required=True,
                        help="Directory containing music to convert.")
    parser.add_argument("-e","--export", action='store', dest='export_dir', required=True,
                        help="Directory where to export MP3.")
    parser.add_argument("-T","--threads", action='store', dest='nb_threads', required=False,
                        help="Number of conversion to launch simultaneously.")
    parser.add_argument("-#","--number", action='store', dest='number_dirs',
                        type=int, default=2,\
                        help="Number of sub directories to create in the export directory to \
                            divide it equally.")
    parser.add_argument("-S","--size", action='store', dest='max_dir_size',
                        type=int, default=14500000000,\
                        help="Maximal size of each export directory")
    parser.add_argument("-F","--fullsize", action='store_true', dest='full_size',
                        help="Fill first partitions to their maximal size.")
    parser.add_argument("-B","--bitrate", action='store', dest='bitrate',
                        type=int, default=128,\
                        help="MP3 bitrate")

    step+=1
    args = parser.parse_args()
    logger.info('Arguments: %s',args)

    if args.verbose:
        logger.info('Setting logging to debug mode')
        coloredlogs.set_level(level=logging.DEBUG)

    if args.nb_threads is None:
        args.nb_threads = os.cpu_count() or 1

    logger.debug('Arguments: %s',args)

    check_binaries()

    music = Path(args.input_dir)
    if not music.exists():
        logger.error('Input path must exist')
        sys.exit(-1)
    if not music.is_dir():
        logger.error('Input path must be a directory')
        sys.exit(-1)

    export = Path(args.export_dir)
    if not export.exists():
        logger.error('Export path must exist')
        sys.exit(-1)
    if not export.is_dir():
        logger.error('Export path must be a directory')
        sys.exit(-1)

    export_all = export / "all"
    export_all.mkdir(exist_ok=True)

    step+=1
    files = get_audio_list(music)
    logger.info('Found %d files', len(files))

    step+=1
    logger.info('Retrieving audio metadata')
    audios = get_metadata(files)

    step+=1
    logger.info('Sorting files by artist')
    audios = dict(sorted(audios.items()))

    step+=1
    logger.info("Creating export directory structure ...")
    conversions = determine_conversions(audios, export_all)

    step+=1
    logger.info("There are %d files to convert.", len(conversions))

    scheduler(conversions, args.nb_threads, args.bitrate)

    if STOP > 0:
        logger.info("Exiting as requested.")
        sys.exit(-1)

    step+=1
    logger.info("Determining MP3 total size")
    size = mp3_total_size(export_all)
    logger.info("MP3 total size: %d", size)

    if args.max_dir_size * args.number_dirs < size:
        logger.error("Impossible to store %d bytes into %d directories of %d bytes each.", size,
                     args.number_dirs, args.max_dir_size)
        sys.exit(-1)

    if args.full_size:
        ideal_size = args.max_dir_size
    else:
        ideal_size = int(ceil(size/args.number_dirs))
    logger.info("We are seeking %d directories of %d bytes each.", args.number_dirs, ideal_size)

    step+=1
    stats = stats_by_artist(export_all)

    logger.info("Sorting by alphabetic order")
    step+=1
    stats = dict(sorted(stats.items(), key=lambda item: sort_artist_path(item[0])))

    step+=1
    logger.info("Computing cuts by artist")
    parts = find_cuts(stats, ideal_size, args.number_dirs)
    if parts is None:
        logger.error("Impossible to find a solution")
        sys.exit(-1)

    logger.info("Creating final partitions images")
    create_partitions(export, export_all, parts)

if __name__ == "__main__":
    main()
