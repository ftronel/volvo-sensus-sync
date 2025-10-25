#!/usr/bin/env python3
"""Module providing a way to transcode a set of music files into standardize MP3 files."""

import argparse
import logging
import coloredlogs

def main():
    """Main function of the program."""
    logger = logging.getLogger(__name__)
    coloredlogs.install()
    parser = argparse.ArgumentParser()
    parser.add_argument("-v","--verbose", action='store_true', dest='verbose', help="Debug.")

    args = parser.parse_args()
    logger.info('Arguments: %s',args)

    if args.verbose:
        logger.info('Setting logging to debug mode')
        coloredlogs.set_level(level=logging.DEBUG)

    logger.debug('Arguments: %s',args)


if __name__ == "__main__":
    main()
