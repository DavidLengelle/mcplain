"""Tests of the fingerprint that tells which commit an image was built from"""

from pathlib import Path

from mcplain_api.source_tree import blob_sha1, digest, folder_entries


def test_blob_identifier_is_the_one_of_git() -> None:
    """git hash-object of hello and a new line gives this identifier"""

    assert blob_sha1(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_entries_skip_compiled_files_and_other_folders(tmp_path: Path) -> None:
    """Only the two source folders count, without __pycache__"""

    (tmp_path / "api" / "src" / "pkg" / "__pycache__").mkdir(parents=True)
    (tmp_path / "engine" / "src").mkdir(parents=True)
    (tmp_path / "api" / "src" / "pkg" / "a.py").write_bytes(b"hello\n")
    (tmp_path / "api" / "src" / "pkg" / "__pycache__" / "a.pyc").write_bytes(b"x")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "b.ts").write_bytes(b"x")
    entries = folder_entries(tmp_path)
    assert entries == {"api/src/pkg/a.py": "ce013625030ba8dba906f756967f9e9ca394464a"}
    assert digest(entries) == digest(dict(reversed(list(entries.items()))))
    assert digest(entries) != digest({**entries, "engine/src/b.py": blob_sha1(b"")})
