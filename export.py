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

import coloredlogs
from mutagen import File, MutagenError
from mutagen.mp3 import MP3
from tqdm import tqdm
from typeguard import typechecked


AUDIO_EXTENSIONS = { ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma",
                    ".opus", ".aiff", ".alac" }

INVALID = r'[<>:"/\\|?*\x00-\x1F]'


@typechecked
def sanitize(name: str) -> str:
    name = re.sub(INVALID, "_", name)
    name = name.rstrip(" .")
    return name

@typechecked
def get_audio_list(root: str) -> list[Path]:
    logger = logging.getLogger(__name__)

    directories = [ Path(root) ]
    res = []

    logger.info('Searching for potential audio files')
    for d in directories:
        for inode in d.rglob("*"):
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
                          export_dir: str) -> list[dict[str, int|str|Path]]:
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

def convert(input_file: Path, output_file: Path):
    logger = logging.getLogger(__name__)


    logger.debug("Converting %s into %s", input_file, output_file)
    audio = File(input_file)
    if isinstance(audio, MP3):
        try:
            output_file.hardlink_to(input_file)
        except OSError:
            # Volumes différents ou hard links non supportés
            shutil.copy2(input_file, output_file)
        return None

    cmd = [ "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(input_file),
                "-codec:a", "libmp3lame", "-q:a", "2", str(output_file)]
    process = subprocess.Popen(cmd)

    return process

def main():
    """Main function of the program."""
    logger = logging.getLogger(__name__)
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

    files = get_audio_list(args.input_dir)

    logger.info('Found %d files', len(files))

    logger.info('Retrieving audio metadata')
    audios = get_metadata(files)

    logger.info("Creating export directory structure ...")
    conversions = determine_conversions(audios, args.export_dir)

    logger.info("There are %d files to convert.", len(conversions))

    converters = {}
    # Fill up the buffer with nb_threads conversions
    nb_procs = 0
    logger.info("Filling CPUs with %d conversions", args.nb_threads)
    while (nb_procs < args.nb_threads) and (len(conversions) >0):
        current = conversions.pop()
        proc = convert(current['inode'], current['to'])
        # If we draw an MP3 file we keep on trying to fill processor with conversion
        if proc is None:
            continue
        converters[proc.pid] = current
        nb_procs += 1

    logger.info("Waiting for conversion completion")
    while (len(conversions) > 0)  and (len(converters) > 0):
        # Wait for completion of a subprocess
        pid, status = os.wait()
        if  os.WEXITSTATUS(status) != 0:
            logger.error('Conversion was not successuful for %s', converters[pid])
        else:
            logger.info('Conversion of %s was successful', converters[pid])
        del converters[pid]
        while len(conversions) > 0:
            current = conversions.pop()
            proc = convert(current['inode'], current['to'])
            if proc is None:
                continue
            converters[proc.pid] = current

if __name__ == "__main__":
    main()
