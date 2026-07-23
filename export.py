#!/usr/bin/env python3
"""Module providing a way to transcode a set of music files into standardize MP3 files."""

import argparse
import logging
from pathlib import Path

import coloredlogs
from mutagen import File



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


    directories = [ Path(args.input_dir) ]
    files = {}

    for root in directories:
        for inode in root.rglob("*"):
            if inode.is_file() and inode.suffix.lower() in AUDIO_EXTENSIONS:
                logger.debug("Parsing %s", inode)
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
                files[inode] = { 'artist': artist, 'album': album, 'title': title }
            elif inode.is_dir():
                directories.append(inode)


    for f in files:
        print(f)

if __name__ == "__main__":
    main()
