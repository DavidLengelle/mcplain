"""Shared test setup: a guard that blocks every socket in the default tests"""

import socket

import pytest

OPEN_MARKERS: tuple[str, ...] = ("network", "docker")


def _refuse_network(*args: object, **kwargs: object) -> None:
    """Fail any attempt to open a connection"""

    raise RuntimeError("network access is not allowed in default tests")


@pytest.fixture(autouse=True)
def block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Block sockets in every test that is not marked network or docker"""

    if any(request.node.get_closest_marker(marker) is not None for marker in OPEN_MARKERS):
        return
    monkeypatch.setattr(socket.socket, "connect", _refuse_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse_network)
    monkeypatch.setattr(socket, "create_connection", _refuse_network)
