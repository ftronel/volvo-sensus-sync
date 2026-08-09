# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel


import argparse
import logging
import os
import signal
from math import ceil
from pathlib import Path

import coloredlogs
from typeguard import typechecked

from .library import determine_conversions, get_audio_list, get_metadata
from .mp3 import EncodingMode, EncodingSettings
from .partition import create_partitions, find_cuts, mp3_total_size, stats_by_artist
from .scheduler import scheduler
from .step import step
from .system import STOP, check_binaries, sigint_handler
from .utils import sort_artist_path


@typechecked
def main() -> int:
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

    # Encoding settings
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cbr", type=int,
                       help="Bitrate for CBR encoding (in kbits/s).")
    group.add_argument("--abr", type=int,
                       help="Bitrate for ABR encoding (in kbits/s).")
    group.add_argument("--vbr", type=int,
                       help="Quality for VBR encoding [0-9].")

    step+=1
    args = parser.parse_args()
    logger.info('Arguments: %s',args)

    if args.verbose:
        logger.info('Setting logging to debug mode')
        coloredlogs.set_level(level=logging.DEBUG)

    if args.nb_threads is None:
        args.nb_threads = os.cpu_count() or 1

    if args.cbr is not None:
        settings = EncodingSettings(EncodingMode.CBR, args.cbr)
    elif args.abr is not None:
        settings = EncodingSettings(EncodingMode.ABR, args.abr)
    elif args.vbr is not None:
        if args.vbr >= 0 and args.vbr <=9:
            settings = EncodingSettings(EncodingMode.VBR, args.vbr)
        else:
            logger.error("VBR quality must be in interval [0-9]")
            return -1
    else:
        settings = EncodingSettings(EncodingMode.VBR, 5)  # valeur par défaut

    logger.debug('Arguments: %s',args)

    check_binaries()

    music = Path(args.input_dir)
    if not music.exists():
        logger.error('Input path must exist')
        return -1
    if not music.is_dir():
        logger.error('Input path must be a directory')
        return -1

    export = Path(args.export_dir)
    if not export.exists():
        logger.error('Export path must exist')
        return -1
    if not export.is_dir():
        logger.error('Export path must be a directory')
        return -1

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

    scheduler(conversions, args.nb_threads, settings)

    if STOP > 0:
        logger.info("Exiting as requested.")
        return -1

    step+=1
    logger.info("Determining MP3 total size")
    size = mp3_total_size(export_all)
    logger.info("MP3 total size: %d", size)

    if args.max_dir_size * args.number_dirs < size:
        logger.error("Impossible to store %d bytes into %d directories of %d bytes each.", size,
                     args.number_dirs, args.max_dir_size)
        return -1

    if args.full_size:
        ideal_size = args.max_dir_size
    else:
        ideal_size = ceil(size/args.number_dirs)
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
        return -1

    logger.info("Creating final partitions images")
    create_partitions(export, export_all, parts)

    return 0
