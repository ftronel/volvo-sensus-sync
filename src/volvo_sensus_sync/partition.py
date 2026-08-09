import logging
from pathlib import Path

from typeguard import typechecked

from .syncplan import PLANSH


@typechecked
def mp3_total_size(export_dir: Path) -> int:
    """Calculate the total size (in bytes) of all MP3 files under *export_dir*.

    Args:
        export_dir: Root directory containing the exported MP3 hierarchy.

    Returns:
        Total size in bytes as an integer.
    """
    size = 0
    for inode in export_dir.rglob("*"):
        if inode.is_file() and inode.suffix.lower() == '.mp3':
            size += inode.stat().st_size

    return size

@typechecked
def stats_by_artist(export_dir: Path) -> dict[Path, int]:
    """Return a mapping from each artist directory to its total MP3 size.

    Args:
        export_dir: The ``all`` directory where all converted files are stored.

    Returns:
        ``{artist_path: size_in_bytes}``
    """
    stats = {}
    for artist in export_dir.glob("*"):
        size = mp3_total_size(artist)
        stats[artist] = size

    return stats

@typechecked
def find_cuts(stats: dict[Path, int], max_size:int, nb_parts: int) -> list[list[Path]] | None:
    """Group artist directories into partitions that respect *max_size*.

    A naïve first‑fit algorithm is used: artists are added to the current part
    until adding the next one would exceed *max_size*.  If the resulting number
    of parts exceeds *nb_parts* the function returns ``None``.

    Args:
        stats: Mapping from artist directory to its size (as returned by
            :func:`stats_by_artist`).
        max_size: Maximum allowed size per part (in bytes).
        nb_parts: Desired maximum number of parts.

    Returns:
        A list of partitions (each a list of artist :class:`Path`s) or ``None`` if
        a satisfactory partitioning is impossible.
    """
    logger = logging.getLogger(__name__)

    res = []
    part : list[Path] = []
    total = 0
    for artist, size in stats.items():
        if total+size > max_size:
            if len(part)>0:
                total = 0
                res.append(part)
                part = []
            else:
                logger.warning("Impossible to include %s in a single directory.", artist)
                return None
        else:
            total += size
            part.append(artist)

    res.append(part)

    if len(res) > nb_parts:
        logger.warning("Solution requires more parts (%d) than allowed (%d)", len(res), nb_parts)
        return None

    return res

@typechecked
def create_partitions(export: Path, all_tracks: Path, partitions: list[list[Path]]):
    """Populate the final export directory with hard‑linked copies of the tracks.

    The function creates numbered sub‑directories (``1``, ``2`` …) under
    *export* and mirrors the internal artist/albums hierarchy from *all_tracks*
    using hard links to avoid duplicating data.

    Args:
        export: Root directory where the partitioned copies will be created.
        all_tracks: Path to the ``all`` directory containing the complete MP3
            collection.
        partitions: List of partitions returned by :func:`find_cuts`.
    """
    logger = logging.getLogger(__name__)

    part_num = 1
    for part in partitions:
        part_path = export / f"{part_num}"
        part_path.mkdir(exist_ok=True, parents=True)
        plan_path = part_path / "sync-partition.sh"
        with plan_path.open("w", encoding="utf-8") as plan:
            plan.write(PLANSH)
            for artist in part:
                tracks = sorted(artist.rglob("*"))
                for track in tracks:
                    rel_path = track.relative_to(all_tracks)
                    target_path = part_path / rel_path
                    if track.is_file():
                        plan.write(f"./{rel_path}\n")
                        target_path.parent.mkdir(exist_ok=True, parents=True)
                        if not target_path.exists():
                            target_path.hardlink_to(track)
                        else:
                            logger.warning("Target file exists: %s", target_path)
                    elif track.is_dir():
                        target_path.mkdir(exist_ok=True, parents=True)
            plan.write("__SYNC_PLAN__\n")
        part_num += 1
