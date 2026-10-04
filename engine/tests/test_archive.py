"""Tests for safe archive extraction: every malicious archive must be refused"""

import io
import tarfile
from pathlib import Path

import pytest
from builders import tar_gz, tar_with_member, zip_bytes

from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.errors import ArchiveError
from mcplain.fetch.archive import extract_archive


def _extract(tmp_path: Path, data: bytes, limits: Limits = DEFAULT_LIMITS) -> Path:
    """Write archive bytes to disk and extract them"""

    archive = tmp_path / "archive.bin"
    archive.write_bytes(data)
    return extract_archive(archive, tmp_path / "out", limits)


def _refused(tmp_path: Path, data: bytes, code: str, limits: Limits = DEFAULT_LIMITS) -> None:
    """Assert that extraction fails with the given code and writes nothing outside"""

    with pytest.raises(ArchiveError) as error:
        _extract(tmp_path, data, limits)
    assert error.value.code == code
    assert not (tmp_path / "evil.txt").exists()


def test_valid_tar_gz_returns_single_top_folder(tmp_path: Path) -> None:
    """A normal archive is extracted and its single top folder is returned"""

    root = _extract(tmp_path, tar_gz({"package.json": b"{}", "src/index.js": b"x"}, prefix="package/"))
    assert root.name == "package"
    assert (root / "src" / "index.js").read_bytes() == b"x"
    assert not (root / "src" / "index.js").stat().st_mode & 0o111


def test_valid_zip(tmp_path: Path) -> None:
    """A normal zip, like a wheel, is extracted"""

    root = _extract(tmp_path, zip_bytes({"pkg/__init__.py": b"", "pkg-1.0.dist-info/METADATA": b"Name: pkg"}))
    assert (root / "pkg" / "__init__.py").exists()


def test_tar_path_traversal_is_refused(tmp_path: Path) -> None:
    """Refuse a member whose name climbs out with a parent segment"""

    _refused(tmp_path, tar_gz({"../evil.txt": b"x"}), "archive.path_traversal")


def test_tar_absolute_path_is_refused(tmp_path: Path) -> None:
    """Refuse a member with an absolute path"""

    _refused(tmp_path, tar_gz({"/tmp/evil.txt": b"x"}), "archive.absolute_path")


def test_tar_symlink_is_refused(tmp_path: Path) -> None:
    """Refuse symbolic links"""

    member = tarfile.TarInfo("package/link")
    member.type = tarfile.SYMTYPE
    member.linkname = "/etc/passwd"
    _refused(tmp_path, tar_with_member(member), "archive.link")


def test_tar_hardlink_is_refused(tmp_path: Path) -> None:
    """Refuse hard links"""

    member = tarfile.TarInfo("package/hard")
    member.type = tarfile.LNKTYPE
    member.linkname = "package/other"
    _refused(tmp_path, tar_with_member(member), "archive.link")


@pytest.mark.parametrize("kind", [tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE])
def test_tar_special_files_are_refused(tmp_path: Path, kind: bytes) -> None:
    """Refuse FIFOs and device files"""

    member = tarfile.TarInfo("package/device")
    member.type = kind
    _refused(tmp_path, tar_with_member(member), "archive.special_file")


def test_too_many_files_is_refused(tmp_path: Path) -> None:
    """Refuse an archive with more entries than allowed"""

    files = {f"f{index}.txt": b"x" for index in range(11)}
    _refused(tmp_path, tar_gz(files), "archive.too_many_files", Limits(max_extract_files=10))


def test_file_too_large_is_refused(tmp_path: Path) -> None:
    """Refuse an entry larger than the per-file limit"""

    _refused(tmp_path, tar_gz({"big.bin": b"a" * 2000}), "archive.file_too_large", Limits(max_extract_file_bytes=1000))


def test_total_too_large_is_refused(tmp_path: Path) -> None:
    """Refuse an archive whose content is larger than the total limit"""

    files = {f"part{index}.bin": bytes(range(256)) * 4 for index in range(5)}
    limits = Limits(max_extract_total_bytes=3000, max_compression_ratio=10_000)
    _refused(tmp_path, tar_gz(files), "archive.too_large", limits)


def test_compression_bomb_is_refused(tmp_path: Path) -> None:
    """Refuse an archive that is compressed far more than 100 times"""

    data = tar_gz({"zeros.bin": bytes(5 * 1024 * 1024)})
    assert len(data) * 100 < 5 * 1024 * 1024
    _refused(tmp_path, data, "archive.compression_ratio")


def test_zip_compression_bomb_is_refused(tmp_path: Path) -> None:
    """Refuse a zip bomb as well"""

    _refused(tmp_path, zip_bytes({"zeros.bin": bytes(5 * 1024 * 1024)}), "archive.compression_ratio")


def test_zip_traversal_is_refused(tmp_path: Path) -> None:
    """Refuse a zip entry that climbs out with a parent segment"""

    _refused(tmp_path, zip_bytes({"../evil.txt": b"x"}), "archive.path_traversal")


def test_zip_absolute_path_is_refused(tmp_path: Path) -> None:
    """Refuse a zip entry with an absolute path"""

    _refused(tmp_path, zip_bytes({"/evil.txt": b"x"}), "archive.absolute_path")


def test_zip_symlink_is_refused(tmp_path: Path) -> None:
    """Refuse a zip entry marked as a symbolic link"""

    _refused(tmp_path, zip_bytes({"ok.txt": b"x"}, symlink="link"), "archive.link")


def test_duplicate_entry_is_refused(tmp_path: Path) -> None:
    """Refuse an archive that writes the same file twice"""

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for content in (b"first", b"second"):
            member = tarfile.TarInfo("same.txt")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    _refused(tmp_path, buffer.getvalue(), "archive.duplicate_entry")


def test_unknown_format_is_refused(tmp_path: Path) -> None:
    """Refuse data that is not a tar or zip archive"""

    _refused(tmp_path, b"this is not an archive", "archive.unknown_format")


def test_corrupted_gzip_is_refused(tmp_path: Path) -> None:
    """Refuse a truncated archive"""

    data = tar_gz({"a.txt": b"hello" * 1000})
    _refused(tmp_path, data[: len(data) // 2], "archive.corrupted")
