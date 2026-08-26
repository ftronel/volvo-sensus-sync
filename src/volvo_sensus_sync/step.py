# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

from dataclasses import dataclass
from enum import IntEnum
from typing import Self


class Step(IntEnum):
    """High-level execution step of the synchronization command.

    The runtime state uses this enum to know which phase is currently running.
    This is mainly useful for logging and graceful shutdown: an interruption
    during conversion should not be handled the same way as an interruption
    while enumerating files or computing export statistics.

    Values are ordered according to the normal execution flow so
    :meth:`next` can advance to the following step.
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

    def next(self) -> Self:
        """Return the next processing step.

        Returns:
            The enum member immediately following the current one.

        Raises:
            ValueError: If the current step is the last known step.
        """
        try:
            return Step(self.value + 1)
        except ValueError as exc:
            raise ValueError(f"No step after {self.name}") from exc

@dataclass
class RuntimeState:
    """Mutable process-wide runtime state.

    The application updates this object as it moves through the synchronization
    pipeline. Signal handlers also use it to count interruptions and decide
    whether to stop launching new conversions or abort more aggressively.
    """
    step: Step = Step.INIT
    interruptions: int = 0

runtime_state = RuntimeState()
"""Shared runtime state used by the CLI, scheduler and signal handlers."""
