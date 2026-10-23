import socket

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Tests must never reach a live provider; HTTP is mocked with `responses`."""

    def guard(*args, **kwargs):
        raise RuntimeError("Network access is disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


@pytest.fixture(autouse=True)
def clear_cache():
    """Forecast responses and throttle counters are cached; isolate every test."""
    cache.clear()
    yield
    cache.clear()
