from pathlib import Path


class NoteStore:
    """Notes kept in a local folder"""

    def __init__(self, folder: str) -> None:
        self.folder = Path(folder)

    def read(self, name: str) -> str:
        """Read one note"""
        return (self.folder / name).read_text(encoding="utf-8")

    @classmethod
    def count(cls, folder: str) -> int:
        """Count the notes of a folder"""
        return len(list(Path(folder).iterdir()))
