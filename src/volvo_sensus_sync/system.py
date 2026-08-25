# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

"""
System-related utilities.

This module contains signal handling and external dependency checks.
"""

import logging
import sys
from shutil import which

from typeguard import typechecked

from .step import Step, runtime_state

logger = logging.getLogger(__name__)

def sigint_handler(signum, frame):
    """Handle SIGINT (Ctrl‑C).

    If the conversion step is active the handler sets a global flag to stop
    launching new jobs and allows the currently running subprocesses to finish
    gracefully.  During any earlier step the program exits immediately.
    """

    runtime_state.interruptions += 1
    if runtime_state.step != Step.CONVERSION or runtime_state.interruptions>1:
        logger.warning("Shutting down as requested.")
        sys.exit(-1)
    logger.warning("Please wait during graceful shutdown")

@typechecked
def check_binaries() -> None:
    """
    Verify that the external command‑line tools required by the application are
    available in the current ``PATH``.

    The program depends on the ``ffmpeg`` binary to perform audio
    decoding and MP3 encoding.  This helper checks for their presence using
    :func:`shutil.which`.  If a binary cannot be located, an error is logged and
    the program terminates with a non‑zero exit status.

    Raises
    ------
    SystemExit
        The function calls ``sys.exit(1)`` when one or more required binaries
        are missing, causing the whole script to stop immediately.

    Notes
    -----
    - No return value is produced; the function either completes silently (all
      binaries found) or aborts the process.
    - The check is performed at import/initialisation time in many scripts, so
      that missing dependencies are caught early rather than failing during a
      conversion job.
    """
    binaries = [ 'ffmpeg']
    for binary in binaries:
        if which(binary) is None:
            logger.error("%s is not installed.", binary)
            sys.exit(1)
