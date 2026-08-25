# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

from dataclasses import dataclass
from enum import IntEnum

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

@dataclass
class RuntimeState:
    step: Step = Step.INIT
    interruptions: int = 0

runtime_state = RuntimeState()
