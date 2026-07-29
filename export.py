#!/usr/bin/env python3
"""Module providing a way to transcode a set of music files into standardize MP3 files."""

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

import coloredlogs
from mutagen import File, MutagenError
from mutagen.mp3 import MP3
from tqdm import tqdm
from typeguard import typechecked


AUDIO_EXTENSIONS = { ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma",
                    ".opus", ".aiff", ".alac" }

INVALID = r'[<>:"/\\|?*\x00-\x1F]'

class Step(IntEnum):
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

stop_requested = 0
step = Step.INIT

def sigint_handler(signum, frame):
    logger = logging.getLogger(__name__)
    global step
    global stop_requested
    if step != Step.CONVERSION:
        sys.exit(-1)
    stop_requested += 1
    logger.warning("Please wait during graceful shutdown")

@typechecked
def sanitize(name: str) -> str:
    name = re.sub(INVALID, "_", name)
    name = name.rstrip(" .")
    return name

@typechecked
def get_audio_list(root: Path) -> list[Path]:
    logger = logging.getLogger(__name__)

    res = []

    logger.info('Searching for potential audio files')
    for inode in root.rglob("*"):
        if inode.is_file() and inode.suffix.lower() in AUDIO_EXTENSIONS:
            logger.debug("Parsing %s", inode)
            res.append(inode)

    return res

@typechecked
def get_metadata(files: list[Path]) -> dict[str,dict[str,dict[int,list[dict[str, int|str|Path]]]]]:
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
        tracks.append({'inode': inode, 'title': title, 'disc': disc_id, 'nb_discs': nb_discs,
                       'track': track})

    return res

@typechecked
def determine_conversions(audios: dict[str,dict[str,dict[int,list[dict[str, int|str|Path]]]]],
                          export_dir: Path) -> list[dict[str, int|str|Path]]:
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
                    logger.debug("Considering title: %s", track['title'])
                    final_path = f"{dest_path}/{track['track']:02d}-{track['title']}.mp3"
                    logger.debug("Testing if file %s exists", final_path)
                    dest = Path(final_path)
                    if dest.exists():
                        if dest.is_dir():
                            logger.error("There exist a directory whose name collides with target\
file: %s", dest_path)
                            continue
                    else:
                        track['to'] = dest
                        res.append(track)

    return res

def convert(input_file: Path, output_file: Path, quality: int):
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

    cmd = [ "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(input_file),
                "-codec:a", "libmp3lame", "-q:a", quality, str(output_file)]
    # ffmpeg processes are not in the same session as the Python script.
    # Otherwise they would receive SIGINT during interrupt
    process = subprocess.Popen(cmd, start_new_session=True)

    return process

@typechecked
def mp3_total_size(export_dir: Path) -> int:

    size = 0
    for inode in export_dir.rglob("*"):
        if inode.is_file() and inode.suffix.lower() == '.mp3':
            size += inode.stat().st_size

    return size

@typechecked
def stats_by_artist(export_dir: Path) -> dict[Path, int]:
    stats = {}
    for artist in export_dir.glob("*"):
        size = mp3_total_size(artist)
        stats[artist] = size

    return stats

@typechecked
def find_cut_artist(stats: dict[Path, int], max_size:int) -> (Path|None, int):
    prev_artist = None
    total = 0
    for artist in stats:
        size = stats[artist]
        if total+size > max_size:
            return prev_artist, total
        total += size
        prev_artist = artist

    return prev_artist, total

@typechecked
def find_cuts(stats: dict[Path, int], max_size:int, nb_parts: int) -> list[list[Path]] | None:
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

def main():
    """Main function of the program."""

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
    parser.add_argument("-Q","--quality", action='store', dest='quality',
                        type=int, default=2,\
                        help="Audio quality")

    step+=1
    args = parser.parse_args()
    logger.info('Arguments: %s',args)

    if args.verbose:
        logger.info('Setting logging to debug mode')
        coloredlogs.set_level(level=logging.DEBUG)

    if args.nb_threads is None:
        args.nb_threads = os.cpu_count() or 1

    logger.debug('Arguments: %s',args)

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

    # TODO: write a function
    running = {}
    errors = []
    progress = tqdm(total=len(conversions), desc="Conversions", unit="Track")
    progress.set_postfix(active=len(running), errors=len(errors))
    # Fill up the buffer with nb_threads conversions
    nb_procs = 0
    logger.debug("Filling CPUs with %d conversions", args.nb_threads)
    while (nb_procs < args.nb_threads) and (len(conversions) >0):
        current = conversions.pop()
        proc = convert(current['inode'], current['to'], args.quality)
        # If we draw an MP3 file we keep on trying to fill processor with conversion
        if proc is None:
            progress.update(1)
            progress.set_postfix(active=len(running), errors=len(errors))
            continue
        current['process'] = proc
        running[proc.pid] = current
        progress.set_postfix(active=len(running), errors=len(errors))
        nb_procs += 1

    while ((len(conversions) > 0)  and (len(running) > 0) and (stop_requested == 0)\
        or ((len(running) > 0) and (stop_requested > 0))) :
        # Wait for completion of a subprocess
        logger.debug("Waiting for conversion completion")
        try:
            # Wait for next process to end up
            pid, status = os.wait()
        except KeyboardInterrupt:
            logger.debug("Waiting for end of current conversions")
            continue
        if  os.WEXITSTATUS(status) != 0:
            failed = running[pid]
            logger.error('Conversion was not successuful for %s', failed)
            failed_path = failed['to']
            failed_path.unlink(missing_ok = True)
            errors.append(failed)
        else:
            logger.debug('Conversion of %s was successful', running[pid])
        running.pop(pid)
        progress.update(1)
        progress.set_postfix(active=len(running), errors=len(errors))
        while (len(running) != args.nb_threads) and (len(conversions) > 0) \
                and (stop_requested == 0):
            current = conversions.pop()
            proc = convert(current['inode'], current['to'], args.quality)
            if proc is None:
                progress.update(1)
                progress.set_postfix(active=len(running), errors=len(errors))
                continue
            current['process'] = proc
            running[proc.pid] = current
            progress.set_postfix(active=len(running), errors=len(errors))

    if stop_requested > 0:
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
    ideal_size = int(ceil(size/args.number_dirs))
    logger.info("We are seeking %d directories of %d bytes each.", args.number_dirs, ideal_size)

    step+=1
    stats = stats_by_artist(export_all)

    logger.info("Sorting by alphabetic order")
    step+=1
    stats = dict(sorted(stats.items()))

    step+=1
    logger.info("Computing cuts by artist")
    parts = find_cuts(stats, ideal_size, args.number_dirs)
    if parts is None:
        logger.error("Impossible to find a solution")
        sys.exit(-1)

    progress.close()

    #TODO: create a function
    logger.info("Creating final partitions images")
    part_num = 1
    for part in parts:
        part_path = export / f"{part_num}"
        part_path.mkdir(exist_ok=True, parents=True)
        for artist in part:
            for inode in artist.rglob("*"):
                rel_path = inode.relative_to(export_all)
                target_path = part_path / rel_path
                if inode.is_file():
                    if not target.exists():
                        target_path.hardlink_to(inode)
                    elif not target.is_hardlink():
                        logger.error("Target file exists and is not a hardlink")
                elif inode.is_dir():
                    target_path.mkdir(exist_ok=True, parents=True)
        part_num += 1

if __name__ == "__main__":
    main()
