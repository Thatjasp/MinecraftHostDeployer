from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PASSWORD = "correct-horse-battery"


@pytest.fixture
def app_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        secret_key="test-secret",
        data_dir=tmp_path,
        frontend_dist=tmp_path / "no-frontend",
    )


@pytest.fixture
def make_client(app_settings: Settings) -> Iterator[Callable[[], TestClient]]:
    """Clients share one app/DB but keep separate cookie jars (i.e. separate browsers)."""
    app = create_app(app_settings)
    clients: list[TestClient] = []

    def factory() -> TestClient:
        client = TestClient(app)
        client.__enter__()  # runs lifespan: migrations + engine
        clients.append(client)
        return client

    yield factory
    for client in reversed(clients):
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[[], TestClient]) -> TestClient:
    return make_client()


def register(client: TestClient, username: str, password: str = PASSWORD):
    return client.post("/api/auth/register", json={"username": username, "password": password})


def login(client: TestClient, username: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})
