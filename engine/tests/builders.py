"""Helpers that build archives in memory for the tests"""

import io
import stat
import tarfile
import zipfile


def tar_gz(files: dict[str, bytes], prefix: str = "") -> bytes:
    """Build a tar.gz archive from a mapping of names to contents"""

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(prefix + name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def tar_with_member(member: tarfile.TarInfo, content: bytes = b"") -> bytes:
    """Build a tar.gz archive holding one hand-made member"""

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        if member.isreg():
            archive.addfile(member, io.BytesIO(content))
        else:
            archive.addfile(member)
    return buffer.getvalue()


def zip_bytes(files: dict[str, bytes], symlink: str | None = None) -> bytes:
    """Build a zip archive, optionally with one entry marked as a symbolic link"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        if symlink is not None:
            info = zipfile.ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "/etc/passwd")
    return buffer.getvalue()
