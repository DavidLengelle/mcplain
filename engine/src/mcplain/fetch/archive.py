"""Safe extraction of tar and zip archives"""

import gzip
import re
import stat
import tarfile
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

from mcplain.config import DEFAULT_LIMITS, MEGABYTE, Limits
from mcplain.errors import ArchiveError

GZIP_MAGIC = b"\x1f\x8b"
ZIP_MAGICS: tuple[bytes, ...] = (b"PK\x03\x04", b"PK\x05\x06")
TAR_MAGIC = b"ustar"
TAR_MAGIC_OFFSET = 257
COPY_CHUNK = 64 * 1024
TAR_HEADER_ALLOWANCE = 3 * 512
WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")
ZIP_ENCRYPTED_FLAG = 0x1
UNIX_ZIP_SYSTEM = 3


class _Readable(Protocol):
    """Class protocol for objects that can be read in chunks"""

    def read(self, size: int = -1) -> bytes:
        """Read up to size bytes"""


class _Budget:
    """Class that enforces size, count and compression limits during extraction"""

    def __init__(self, limits: Limits, compressed_size: int) -> None:
        """Start counting from zero"""

        self.limits = limits
        self.compressed_size = max(compressed_size, 1)
        self.entries = 0
        self.total = 0

    def add_entry(self) -> None:
        """Count one archive entry"""

        self.entries += 1
        if self.entries > self.limits.max_extract_files:
            raise ArchiveError("archive.too_many_files", limit=self.limits.max_extract_files)

    def check_declared(self, name: str, size: int) -> None:
        """Refuse an entry whose declared size is above the per-file limit"""

        if size > self.limits.max_extract_file_bytes:
            raise ArchiveError(
                "archive.file_too_large",
                name=name,
                limit_mb=max(1, self.limits.max_extract_file_bytes // MEGABYTE),
            )

    def add_bytes(self, count: int) -> None:
        """Count extracted bytes and check the total and the compression ratio"""

        self.total += count
        if self.total > self.limits.max_extract_total_bytes:
            raise ArchiveError(
                "archive.too_large", limit_mb=max(1, self.limits.max_extract_total_bytes // MEGABYTE)
            )
        ratio_limit = self.compressed_size * self.limits.max_compression_ratio
        if self.total > max(ratio_limit, self.limits.compression_ratio_floor_bytes):
            raise ArchiveError("archive.compression_ratio", ratio=self.limits.max_compression_ratio)


class _BoundedReader:
    """Class that stops reading a decompressed stream past a byte cap"""

    def __init__(self, inner: _Readable, cap: int, limits: Limits) -> None:
        """Wrap a readable stream"""

        self._inner = inner
        self._cap = cap
        self._limits = limits
        self._read = 0

    def read(self, size: int = -1) -> bytes:
        """Read from the wrapped stream and enforce the cap"""

        if size is None or size < 0:
            size = COPY_CHUNK
        data = self._inner.read(size)
        self._read += len(data)
        if self._read > self._cap:
            raise ArchiveError(
                "archive.too_large", limit_mb=max(1, self._limits.max_extract_total_bytes // MEGABYTE)
            )
        return data


def extract_archive(archive_path: Path, destination: Path, limits: Limits = DEFAULT_LIMITS) -> Path:
    """Extract an archive safely and return its root folder"""

    with archive_path.open("rb") as handle:
        head = handle.read(512)
    budget = _Budget(limits, archive_path.stat().st_size)
    stream_cap = limits.max_extract_total_bytes + limits.max_extract_files * TAR_HEADER_ALLOWANCE
    destination.mkdir(parents=True, exist_ok=True)
    try:
        if head.startswith(GZIP_MAGIC):
            with archive_path.open("rb") as raw, gzip.GzipFile(fileobj=raw) as unzipped:
                _extract_tar(_BoundedReader(unzipped, stream_cap, limits), destination, budget)
        elif head.startswith(ZIP_MAGICS):
            _extract_zip(archive_path, destination, budget)
        elif head[TAR_MAGIC_OFFSET:TAR_MAGIC_OFFSET + len(TAR_MAGIC)] == TAR_MAGIC:
            with archive_path.open("rb") as raw:
                _extract_tar(_BoundedReader(raw, stream_cap, limits), destination, budget)
        else:
            raise ArchiveError("archive.unknown_format")
    except FileExistsError as error:
        raise ArchiveError("archive.duplicate_entry") from error
    except (tarfile.TarError, zipfile.BadZipFile, gzip.BadGzipFile, EOFError, zlib.error) as error:
        raise ArchiveError("archive.corrupted") from error
    except OSError as error:
        raise ArchiveError("archive.invalid_layout") from error
    return _content_root(destination)


def safe_relative_path(name: str) -> PurePosixPath | None:
    """Return a safe relative path for an entry name, None for the root itself"""

    if not name or "\x00" in name or "\\" in name:
        raise ArchiveError("archive.bad_name", name=name)
    if name.startswith("/") or WINDOWS_DRIVE_PATTERN.match(name):
        raise ArchiveError("archive.absolute_path", name=name)
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if ".." in parts:
        raise ArchiveError("archive.path_traversal", name=name)
    if not parts:
        return None
    return PurePosixPath(*parts)


def _extract_tar(stream: _BoundedReader, destination: Path, budget: _Budget) -> None:
    """Extract a tar stream member by member"""

    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            budget.add_entry()
            relative = safe_relative_path(member.name)
            if member.issym() or member.islnk():
                raise ArchiveError("archive.link", name=member.name)
            if member.isdir():
                if relative is not None:
                    _make_directory(destination, relative)
                continue
            if not member.isreg() or member.issparse():
                raise ArchiveError("archive.special_file", name=member.name)
            if relative is None:
                raise ArchiveError("archive.bad_name", name=member.name)
            budget.check_declared(member.name, member.size)
            source = archive.extractfile(member)
            if source is None:
                raise ArchiveError("archive.special_file", name=member.name)
            _write_file(destination, relative, source, budget, member.size)


def _extract_zip(archive_path: Path, destination: Path, budget: _Budget) -> None:
    """Extract a zip file entry by entry"""

    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            budget.add_entry()
            relative = safe_relative_path(info.filename)
            file_type = stat.S_IFMT(info.external_attr >> 16)
            if info.create_system == UNIX_ZIP_SYSTEM and file_type:
                if stat.S_ISLNK(file_type):
                    raise ArchiveError("archive.link", name=info.filename)
                if not (stat.S_ISREG(file_type) or stat.S_ISDIR(file_type)):
                    raise ArchiveError("archive.special_file", name=info.filename)
            if info.flag_bits & ZIP_ENCRYPTED_FLAG:
                raise ArchiveError("archive.encrypted", name=info.filename)
            if info.is_dir():
                if relative is not None:
                    _make_directory(destination, relative)
                continue
            if relative is None:
                raise ArchiveError("archive.bad_name", name=info.filename)
            budget.check_declared(info.filename, info.file_size)
            with archive.open(info) as source:
                _write_file(destination, relative, source, budget, info.file_size)


def _target_path(destination: Path, relative: PurePosixPath) -> Path:
    """Build the output path and make sure it stays inside the destination"""

    target = destination.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(destination.resolve()):
        raise ArchiveError("archive.path_traversal", name=str(relative))
    return target


def _make_directory(destination: Path, relative: PurePosixPath) -> None:
    """Create a directory from the archive"""

    _target_path(destination, relative).mkdir(parents=True, exist_ok=True)


def _write_file(
    destination: Path,
    relative: PurePosixPath,
    source: BinaryIO,
    budget: _Budget,
    declared_size: int,
) -> None:
    """Copy one entry to disk without overwriting and without exec bits"""

    target = _target_path(destination, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("xb") as handle:
        while True:
            chunk = source.read(COPY_CHUNK)
            if not chunk:
                break
            written += len(chunk)
            if written > declared_size:
                raise ArchiveError("archive.corrupted")
            budget.check_declared(str(relative), written)
            budget.add_bytes(len(chunk))
            handle.write(chunk)


def _content_root(destination: Path) -> Path:
    """Return the single top folder of an archive, or the destination itself"""

    children = list(destination.iterdir())
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return destination
