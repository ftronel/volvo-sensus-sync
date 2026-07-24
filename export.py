#!/usr/bin/env python3
"""Module providing a way to transcode a set of music files into standardize MP3 files."""

import argparse
import logging
from pathlib import Path
import sys

import coloredlogs
from mutagen import File
from tqdm import tqdm


AUDIO_EXTENSIONS = { ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma", 
                    ".opus", ".aiff", ".alac" }

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
    parser.add_argument("-#","--number", action='store', dest='number_dirs',
                        type=int, default=2,\
                        help="Number of sub directories to create in the export directory to \
                            divide it equally.")

    args = parser.parse_args()
    logger.info('Arguments: %s',args)

    if args.verbose:
        logger.info('Setting logging to debug mode')
        coloredlogs.set_level(level=logging.DEBUG)

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

    directories = [ Path(args.input_dir) ]
    files = []

    logger.info('Searching for potential audio files')
    for root in directories:
        for inode in root.rglob("*"):
            if inode.is_file() and inode.suffix.lower() in AUDIO_EXTENSIONS:
                logger.debug("Parsing %s", inode)
                files.append(inode)
            elif inode.is_dir():
                directories.append(inode)

    logger.info('Found %d files', len(files))

    logger.info('Retrieving audio metadata')
    audios = {}
    for inode in tqdm(files):
        try:
            audio = File(inode, easy=True)
        except MutagenError:
            logger.warning(f"Impossible to read: {inode}")
            continue
        if audio is None:
            logger.warning(f"{inode} is not an audio file")
            continue

        artist = audio.get("artist", ["Inconnu"])[0]
        album = audio.get("album", ["Inconnu"])[0]
        title = audio.get("title", [inode.stem])[0]
        disc = audio.get("discnumber", [""])[0]
        disc = int(disc.split("/")[0])
        track = audio.get("tracknumber", [""])[0]
        track = int(track.split("/")[0])
        if artist not in audios:
            audios[artist] = {}
        albums = audios[artist]
        if album not in albums:
            albums[album] = []
        titles = albums[album]
        titles.append({'inode': inode, 'title': title, 'disc': disc, 'track': track})

    logger.info("Creating export directory structure ...")
    # TODO: replace "/" by "_" in artist, album, title
    for artist in audios.keys():
        dest = Path(f"{args.export_dir}/{artist}")
        if dest.exists() and not dest.is_dir():
            logger.error("A file with %s name exists under export directory.", artist)
            continue
        if not dest.exists():
            dest.mkdir()
        albums = audios[artist]
        for album in albums:
            dest = Path(f"{args.export_dir}/{artist}/{album}")
            if dest.exists() and not dest.is_dir():
                logger.error("A file with %s album exists under export directory.", album)
                continue
            if not dest.exists():
                dest.mkdir()
            titles = albums[album]
            for title in titles:
                logger.info("%s %s %s", artist, album, title)


if __name__ == "__main__":
    main()
