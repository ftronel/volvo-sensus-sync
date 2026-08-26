# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

from dataclasses import dataclass
from pathlib import Path

from mutagen.id3 import ID3, TALB, TIT2, TPE1, TPOS, TRCK, ID3NoHeaderError

from .convert import ConversionProcess
from .mpegheader import MPEGHeader


@dataclass(slots=True)
class Track:
    """Audio track scheduled for export.

    A ``Track`` groups the source file, the metadata that should be written to
    the exported MP3, and the destination path used during synchronization.

    During FFmpeg transcoding, ``process`` references the running conversion.
    Existing MP3 files may not need a subprocess: they can be linked, copied or
    minimally patched before finalization.

    Equality is not overridden, but hashing is based on ``source`` so tracks can
    be stored in sets used by the scheduler.
    """
    source: Path
    artist: str
    album: str
    title: str
    dest: Path | None = None
    track_id: int | None = None
    track_total: int | None = None
    disc_id: int | None = None
    disc_total: int | None = None
    process: ConversionProcess | None = None

    def __hash__(self):
        """Return a hash based on the source path.

        The scheduler stores ``Track`` objects in sets. Using the source path keeps
        the hash stable even if runtime fields such as ``dest`` or ``process`` are
        updated during conversion.
        """
        return hash(self.source)

    def get_mpeg_header(self):
        """Parse the first MPEG frame from the destination MP3.

        Returns:
            Parsed MPEG header, or ``None`` if no valid MPEG frame can be found.

        Raises:
            ValueError: If the destination path has not been assigned yet.
        """
        if self.dest is None:
            raise ValueError("Cannot parse MPEG header before destination is set")

        return MPEGHeader.parse(self.dest)

    def write_tags(self):
        """Write ID3v2.3 metadata to the destination MP3.

        The method creates an ID3 tag if needed, then writes title, album, artist,
        track number and disc number. Version 2.3 is used for compatibility with
        older players such as Volvo Sensus.

        Raises:
            ValueError: If the destination path has not been assigned yet.
            mutagen.id3.ID3Error: If Mutagen cannot read or write the tag.
        """
        try:
            tags = ID3(self.dest)
        except ID3NoHeaderError:
            tags = ID3()

        tags.add(TIT2(encoding=3, text=self.title))
        tags.add(TALB(encoding=3, text=self.album))
        tags.add(TPE1(encoding=3, text=self.artist))
        tags.add(TRCK(encoding=3, text=f"{self.track_id}/{self.track_total}"))
        tags.add(TPOS(encoding=3, text=f"{self.disc_id}/{self.disc_total}"))
        tags.save(self.dest, v2_version=3)
