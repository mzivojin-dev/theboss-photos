"""
Finds the Sidecar of a media file in a Takeout export.

Takeout names a Sidecar after its media file, but not exactly:
- `IMG_1.jpg` gets `IMG_1.jpg.json` (older exports) or `IMG_1.jpg.supplemental-metadata.json`.
- A Sidecar name longer than 51 characters is cut to 46 characters plus `.json`, which
  shortens `.supplemental-metadata` (`IMG_1.jpg.supplemental-me.json`) or, for a long
  media name, the media name itself.
- A duplicate name `IMG_1(1).jpg` gets its counter after the rest of the Sidecar name:
  `IMG_1.jpg(1).json` or `IMG_1.jpg.supplemental-metadata(1).json`.
A Sidecar sits in the same folder as its media file, though possibly in another Takeout Archive.
"""
import posixpath
import re

SUPPLEMENTAL_METADATA = "supplemental-metadata"
# Takeout's limit on a Sidecar name, `.json` included.
MAX_SIDECAR_NAME_LENGTH = 51
MAX_SIDECAR_STEM_LENGTH = MAX_SIDECAR_NAME_LENGTH - len(".json")

_COUNTER = re.compile(r"^(?P<rest>.*)\((?P<counter>\d+)\)$")


class SidecarIndex:
    def __init__(self, sidecars: dict[str, bytes]):
        """`sidecars` maps each Sidecar's path in its Takeout Archive to its bytes."""
        self._sidecars: dict[tuple[str, str, int], bytes] = {}
        ambiguous: set[tuple[str, str, int]] = set()
        for path, sidecar in sidecars.items():
            for key in _keys_of_sidecar(path):
                if key in self._sidecars and self._sidecars[key] != sidecar:
                    ambiguous.add(key)
                self._sidecars[key] = sidecar
        # Two different Sidecars under one key (two long names cut to the same 46 characters):
        # matching neither is safer than indexing a file under another file's metadata.
        for key in ambiguous:
            del self._sidecars[key]

    def find(self, media_path: str) -> bytes | None:
        """The Sidecar of the media file at `media_path` in its Takeout Archive, if there is one."""
        folder, name = _split(media_path)
        for stem, counter in _stems_of_media(name):
            for candidate in (stem, stem[:MAX_SIDECAR_STEM_LENGTH]):
                sidecar = self._sidecars.get((folder, candidate, counter))
                if sidecar is not None:
                    return sidecar
        return None


def _split(path: str) -> tuple[str, str]:
    folder, name = posixpath.split(path.lower())
    return folder, name


def _keys_of_sidecar(path: str) -> list[tuple[str, str, int]]:
    """The (folder, media name, duplicate counter) keys a Sidecar can be found under."""
    folder, name = _split(path)
    if not name.endswith(".json"):
        return []
    stem, counter = _without_counter(name[:-len(".json")])
    keys = [(folder, stem, counter)]
    # `.supplemental-metadata`, possibly cut short, down to just the dot.
    rest, dot, suffix = stem.rpartition(".")
    if dot and rest and SUPPLEMENTAL_METADATA.startswith(suffix):
        keys.append((folder, rest, counter))
    return keys


def _stems_of_media(name: str) -> list[tuple[str, int]]:
    """The (Sidecar stem, duplicate counter) pairs a media file's Sidecar may be named with."""
    stems = [(name, 0)]
    base, extension = posixpath.splitext(name)
    without_counter, counter = _without_counter(base)
    if counter:
        # `IMG_1(1).jpg` is a duplicate of `IMG_1.jpg`; its Sidecar is `IMG_1.jpg(1).json`.
        stems.insert(0, (without_counter + extension, counter))
    return stems


def _without_counter(name: str) -> tuple[str, int]:
    match = _COUNTER.match(name)
    if not match:
        return name, 0
    return match["rest"], int(match["counter"])
