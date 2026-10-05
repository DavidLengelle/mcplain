"""Tests of the settings read from the environment"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from mcplain_api.settings import Settings


def test_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every setting has its documented variable and default"""

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("MCPLAIN_JOBS_DIR", "/srv/jobs")
    monkeypatch.setenv("MCPLAIN_CORS_ORIGINS", "http://localhost:3000, https://mcplain.example")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    settings = Settings()
    assert settings.jobs_dir == Path("/srv/jobs")
    assert settings.cors_origin_list() == ["http://localhost:3000", "https://mcplain.example"]
    assert (settings.atelier_image, settings.atelier_timeout) == ("mcplain-atelier:dev", 120)
    assert (settings.max_parallel, settings.max_queued) == (2, 100)
    assert settings.github_token is None
    assert settings.dispatcher_id == "main"


def test_empty_github_token_is_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """compose passes an empty GITHUB_TOKEN when it is not set"""

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("GITHUB_TOKEN", "")
    assert Settings().github_token is None


def test_relative_jobs_folder_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The jobs folder must be an absolute path, the same on the host and in the dispatcher"""

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("MCPLAIN_JOBS_DIR", "var/jobs")
    with pytest.raises(ValidationError):
        Settings()


def test_dispatcher_identifier_is_a_safe_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCPLAIN_DISPATCHER_ID is kept as given when it is a plain name, refused otherwise"""

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("MCPLAIN_DISPATCHER_ID", "blue-2")
    assert Settings().dispatcher_id == "blue-2"
    for value in ("", "a=b", "with space", "x" * 64, "-dash"):
        monkeypatch.setenv("MCPLAIN_DISPATCHER_ID", value)
        with pytest.raises(ValidationError):
            Settings()
