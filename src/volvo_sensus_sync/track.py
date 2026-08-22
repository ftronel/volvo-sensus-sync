# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel

from dataclasses import dataclass
from pathlib import Path

from mutagen.id3 import ID3, TALB, TIT2, TPE1, TPOS, TRCK, ID3NoHeaderError

from .convert import ConversionProcess
from .mp3 import parse_mpeg_header


@dataclass(slots=True)
class Track:
    """
    Representation of a single audio track that will be converted to MP3.

    The class stores both source metadata (artist, album, title, etc.) and the
    destination path where the final MP3 will be written.  It also holds a
    reference to a :class:`ConversionProcess` when the track is currently being
    converted.

    Equality and hashing are based solely on the *source* path so that a
    ``Track`` can be used as a dictionary key or stored in a ``set`` without
    needing to compare all metadata fields.

    Methods
    -------
    __hash__():
        Return a hash value derived from the ``source`` attribute.
    write_tags():
        Write ID3v2.3 tags (title, album, artist, track number, disc number) to
        the destination MP3 file.  Missing tags are created if the file does not
        already contain an ID3 header.
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
        """
        Compute a hash based on the source file path.

        Using the source path as the unique identifier ensures that two ``Track``
        objects pointing to the same original file are considered equal in hash‑
        based collections.

        Returns
        -------
        int
            The hash of ``self.source``.
        """
        return hash(self.source)

    def get_mpeg_header(self):
        return parse_mpeg_header(self.dest)

    def write_tags(self):
        """
        Write or update ID3v2.3 tags on the destination MP3 file.

        The method creates an ``ID3`` object (adding a new header if one does not
        already exist) and populates the following frames:

        * ``TIT2`` – Title
        * ``TALB`` – Album
        * ``TPE1`` – Artist (lead performer)
        * ``TRCK`` – Track number/total (e.g. ``"5/12"``)
        * ``TPOS`` – Disc number/total (e.g. ``"1/2"``)

        The tags are saved using version 2.3 of the ID3 specification to retain
        broad compatibility with older players.

        Raises
        ------
        mutagen.id3.ID3Error
            Propagated if Mutagen fails to write the tags (e.g., permission
            issues or file corruption).
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
