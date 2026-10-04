"""Shared test setup: fixture paths and a guard that blocks real network access"""

import socket
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _refuse_network(*args: object, **kwargs: object) -> None:
    """Fail any attempt to open a real connection"""

    raise RuntimeError("network access is not allowed in offline tests")


def pytest_ignore_collect(collection_path: Path) -> bool | None:
    """Never collect or import anything from the fixture servers, whatever the working directory"""

    if collection_path.resolve().is_relative_to(FIXTURES.resolve()):
        return True
    return None


@pytest.fixture(autouse=True)
def block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Block sockets in every test that is not marked network"""

    if request.node.get_closest_marker("network") is not None:
        return
    monkeypatch.setattr(socket.socket, "connect", _refuse_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse_network)
    monkeypatch.setattr(socket, "create_connection", _refuse_network)


@pytest.fixture
def fixtures() -> Path:
    """Return the folder that holds the fixture servers"""

    return FIXTURES
