"""Bundled third-party modules: the regions a bundler marks with the path of each module it copied"""

import re
from dataclasses import dataclass

from mcplain.adapters.common import SourceText

MODULE_PATH_COMMENT = re.compile(r"// (\S+\.(?:js|mjs|cjs|jsx|ts|mts|cts|tsx|json|node))")
REGION_START_COMMENT = re.compile(r"//#region (\S+)")
REGION_END_COMMENT = "//#endregion"
DEPENDENCY_FOLDER = "node_modules/"
MODULE_WRAPPERS: frozenset[str] = frozenset({"__commonJS", "__commonJSMin", "__esm", "__esmMin"})


@dataclass(frozen=True)
class LibraryRegion:
    """Class that holds the byte range of one bundled module copied from node_modules, and its package"""

    start: int
    end: int
    package: str


def package_of(path: str) -> str | None:
    """Return the package of a module path that sits in node_modules, or None"""

    if DEPENDENCY_FOLDER not in path:
        return None
    parts = path.rsplit(DEPENDENCY_FOLDER, 1)[1].split("/")
    if parts[0].startswith("@") and len(parts) > 2:
        return f"{parts[0]}/{parts[1]}"
    if parts[0] and not parts[0].startswith("@") and len(parts) > 1:
        return parts[0]
    return None


def _markers(source: SourceText, comments: list[tuple[int, str]]) -> list[tuple[int, int, str, str | None]]:
    """Return the module comments written at the start of a line: offset, end, kind and module path"""

    markers: list[tuple[int, int, str, str | None]] = []
    for offset, text in comments:
        if offset > 0 and source.data[offset - 1 : offset] != b"\n":
            continue
        end = offset + len(text.encode("utf-8"))
        path = MODULE_PATH_COMMENT.fullmatch(text)
        region = REGION_START_COMMENT.fullmatch(text)
        if path is not None:
            markers.append((offset, end, "path", path.group(1)))
        elif region is not None:
            markers.append((offset, end, "region", region.group(1)))
        elif text.strip() == REGION_END_COMMENT:
            markers.append((offset, end, "end", None))
    return sorted(markers)


def library_regions(source: SourceText, comments: list[tuple[int, str]]) -> list[LibraryRegion]:
    """Return the regions of bundled node_modules code: a module comment up to the next one, or a closed #region"""

    markers = _markers(source, comments)
    regions: list[LibraryRegion] = []
    for index, (offset, end, kind, path) in enumerate(markers):
        if kind == "end" or path is None:
            continue
        following = markers[index + 1 :]
        if not following:
            continue
        closing = following[0]
        if kind == "region" and closing[2] != "end":
            continue
        package = package_of(path)
        if package is not None:
            regions.append(LibraryRegion(end, closing[0], package))
    return regions
