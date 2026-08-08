import logging
import sys
from shutil import which

from typeguard import typechecked

from .step import step, Step


STOP = 0

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
    logger = logging.getLogger(__name__)

    binaries = [ 'ffmpeg']
    for binary in binaries:
        if which(binary) is None:
            logger.error("%s is not installed.", binary)
            sys.exit(1)
