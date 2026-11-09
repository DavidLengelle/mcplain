"""Third-party code cloned for the tests stays out of git, like the private corpus"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
EXTERNAL_RELATIVE = "engine/tests/fixtures/external"


def git_available() -> bool:
    """Tell whether git and the repository are there, which is not the case in every copy of the code"""

    return shutil.which("git") is not None and (REPOSITORY / ".git").exists()


def git(*args: str) -> str:
    """Run a read-only git command in the repository and return its output"""

    completed = subprocess.run(["git", *args], cwd=REPOSITORY, capture_output=True, text=True, check=False)
    return completed.stdout


@pytest.mark.skipif(not git_available(), reason="git or the repository is not available")
def test_no_external_file_is_tracked_by_git() -> None:
    """Not one file of the external folder is in the git index"""

    assert git("ls-files", "--", EXTERNAL_RELATIVE) == ""


@pytest.mark.skipif(not git_available(), reason="git or the repository is not available")
def test_external_folder_is_ignored_by_git() -> None:
    """The external folder and anything inside it are ignored"""

    assert git("check-ignore", f"{EXTERNAL_RELATIVE}/").strip() != ""
    assert git("check-ignore", f"{EXTERNAL_RELATIVE}/dvmcp/README.md").strip() != ""
