from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.curseforge import CurseForgeClient
from app.main import create_app
from tests.fake_curseforge import fake_fetch
from tests.fake_docker import FakeDocker

PASSWORD = "correct-horse-battery"


@pytest.fixture
def app_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        secret_key="test-secret",
        cf_api_key="test-cf-key",
        data_dir=tmp_path / "data",
        mc_root=tmp_path / "mc",
        frontend_dist=tmp_path / "no-frontend",
    )


@pytest.fixture
def fake_docker() -> FakeDocker:
    return FakeDocker()


@pytest.fixture
def make_client(
    app_settings: Settings, fake_docker: FakeDocker
) -> Iterator[Callable[[], TestClient]]:
    """Clients share one app/DB but keep separate cookie jars (i.e. separate browsers)."""
    curseforge = CurseForgeClient(app_settings.cf_api_key, fetch=fake_fetch)
    app = create_app(app_settings, docker=fake_docker, curseforge=curseforge)
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
