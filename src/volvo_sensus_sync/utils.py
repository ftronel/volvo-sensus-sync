import re
import unicodedata
from pathlib import Path

from typeguard import typechecked

INVALID = r'[<>:"/\\|?*\x00-\x1F]'

@typechecked
def sanitize(name: str) -> str:
    """Return a filesystem‑safe version of *name*.

    The function replaces characters that are invalid on most platforms with an
    underscore and strips trailing spaces or dots.

    Args:
        name: The original string (typically metadata such as artist or title).

    Returns:
        A sanitized string safe to use as a file or directory name.
    """
    name = re.sub(INVALID, "_", name)
    name = name.rstrip(" .")
    return name

@typechecked
def sort_artist_path(path: Path) -> str:
    """Return a case‑folded, diacritics‑stripped representation of *path*.

    This helper is used to sort artist directories in a locale‑independent way.

    Args:
        path: A :class:`~pathlib.Path` instance whose ``name`` attribute is an
            artist name.

    Returns:
        A normalized string suitable for alphabetical sorting.
    """
    name = path.name
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return name.casefold()
