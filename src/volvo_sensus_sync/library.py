import logging
from pathlib import Path

from mutagen import File, MutagenError
from tqdm import tqdm
from typeguard import typechecked

from .track import Track
from .utils import sanitize

AUDIO_EXTENSIONS = { ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma",
                    ".opus", ".aiff", ".alac" }


@typechecked
def get_audio_list(root: Path) -> list[Path]:
    """Recursively collect all supported audio files under *root*.

    Args:
        root: Directory to search.

    Returns:
        A list of :class:`~pathlib.Path` objects pointing to files whose suffix
        matches one of :data:`AUDIO_EXTENSIONS`.
    """
    logger = logging.getLogger(__name__)

    res = []

    logger.info('Searching for potential audio files')
    for inode in root.rglob("*"):
        if inode.is_file() and inode.suffix.lower() in AUDIO_EXTENSIONS:
            logger.debug("Parsing %s", inode)
            res.append(inode)

    return res

@typechecked
def get_metadata(files: list[Path]) -> dict[str,dict[str,dict[int,list[Track]]]]:
    """Extract relevant metadata from a list of audio files.

    The function groups files by *artist -> album -> disc* and stores a list of
    track dictionaries for each disc.  Each track dictionary contains the
    original file path, sanitized title and numeric track information.

    Args:
        files: List of audio file paths returned by :func:`get_audio_list`.

    Returns:
        A nested dictionary structured as

        ``{artist: {album: {disc_number: [track_dict, ...]}}}``

        where *track_dict* contains the keys ``inode``, ``title``, ``disc``,
        ``nb_discs`` and ``track``.
    """
    logger = logging.getLogger(__name__)

    res = {}
    for inode in tqdm(files):
        try:
            audio = File(inode, easy=True)
        except MutagenError:
            logger.warning("Impossible to read: %s", inode)
            continue
        if audio is None:
            logger.warning("%s is not an audio file", inode)
            continue

        artist = sanitize(audio.get("albumartist", ["Inconnu"])[0])
        album = sanitize(audio.get("album", ["Inconnu"])[0])
        title = sanitize(audio.get("title", [inode.stem])[0])
        disc = audio.get("discnumber", [""])[0]
        if "/" in disc:
            disc_id, nb_discs = map(int, disc.split("/", 1))
        else:
            disc_id = int(disc)
            nb_discs = 1
        tracknumber = audio.get("tracknumber", ["0"])[0]
        if "/" in tracknumber:
            track_id, track_total = map(int, tracknumber.split("/", 1))
        else:
            track_id = int(tracknumber)
            track_total = 1
        if artist not in res:
            res[artist] = {}
        albums = res[artist]
        if album not in albums:
            albums[album] = {}
            for d in range(nb_discs):
                albums[album][d+1] = []
        discs = albums[album]
        if disc_id not in discs:
            discs[disc_id] = []
        tracks = discs[disc_id]
        track = Track(source=inode, artist=artist, album=album, disc_id=disc_id,
                      disc_total=nb_discs, track_id=track_id, track_total=track_total, title=title)
        tracks.append(track)

    return res

@typechecked
def determine_conversions(audios: dict[str,dict[str,dict[int,list[Track]]]],
                          export_dir: Path) -> list[Track]:
    """Create a conversion plan for all tracks.

    The plan consists of a list of dictionaries, each containing the source file,
    destination path and the metadata needed for conversion.

    Args:
        audios: Nested dictionary returned by :func:`get_metadata`.
        export_dir: Base directory where the final MP3 hierarchy will be created.

    Returns:
        A list of dictionaries, each with at least the keys ``inode``, ``title``,
        ``track`` and a newly added ``to`` (the destination :class:`Path`).
    """
    logger = logging.getLogger(__name__)
    res = []

    for artist in audios:
        logger.debug("Considering artist %s", artist)
        path1 = f"{export_dir}/{artist}"
        dest = Path(path1)
        if dest.exists() and not dest.is_dir():
            logger.error("A file with %s name exists under export directory.", artist)
            continue
        if not dest.exists():
            dest.mkdir()
        albums = audios[artist]
        for album in albums:
            logger.debug("Considering album %s", album)
            path2 = f"{path1}/{album}"
            dest = Path(path2)
            if dest.exists() and not dest.is_dir():
                logger.error("A file with %s album exists under export directory.", album)
                continue
            if not dest.exists():
                dest.mkdir()
            discs = albums[album]
            nb_discs = len(discs.keys())
            for disc in discs.keys():
                logger.debug("Considering disc %d", disc)
                if nb_discs > 1:
                    path3 = f"{path2}/Disc {disc}"
                    dest = Path(path3)
                    if dest.exists() and not dest.is_dir():
                        logger.error("A file with %s disc exists under export directory.", album)
                        continue
                    if not dest.exists():
                        dest.mkdir()
                    dest_path = path3
                else:
                    dest_path = path2
                tracks = discs[disc]
                for track in tracks:
                    logger.debug("Considering title: %s", track.title)
                    final_path = f"{dest_path}/{track.track_id:02d}-{track.title}.mp3"
                    logger.debug("Testing if file %s exists", final_path)
                    dest = Path(final_path)
                    if dest.exists():
                        if dest.is_dir():
                            logger.error("There exist a directory whose name collides with target\
file: %s", dest_path)
                            continue
                    else:
                        track.dest = dest
                        res.append(track)

    return res
