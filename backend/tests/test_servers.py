import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.models import Server
from tests.conftest import login, register
from tests.fake_docker import FakeDocker


@pytest.fixture
def admin(make_client: Callable[[], TestClient]) -> TestClient:
    client = make_client()
    register(client, "steve")
    return client


@pytest.fixture
def member(admin: TestClient, make_client: Callable[[], TestClient]) -> TestClient:
    """An approved non-admin user."""
    client = make_client()
    user_id = register(client, "alex").json()["id"]
    admin.patch(f"/api/users/{user_id}", json={"status": "active"})
    login(client, "alex")
    return client


def create(client: TestClient, **overrides) -> dict:
    body = {"name": "Survival", "accept_eula": True, **overrides}
    response = client.post("/api/servers", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def wait(client: TestClient, server_id: int) -> dict:
    client.app.state.servers.wait(server_id, timeout=5)
    return client.get(f"/api/servers/{server_id}").json()


def test_create_starts_container_with_itzg_settings(
    admin: TestClient, fake_docker: FakeDocker, app_settings: Settings
) -> None:
    server = create(
        admin,
        memory="6G",
        motd="Hello",
        source={"type": "vanilla", "version": "1.21.1"},
        image_tag="java21",
    )
    assert server["port"] == 25565
    assert wait(admin, server["id"])["state"] == "online"

    spec = fake_docker.containers[f"mcpanel-{server['id']}"].spec
    assert spec.image == "itzg/minecraft-server:java21"
    assert spec.host_port == 25565
    assert spec.env == {
        "EULA": "TRUE",
        "TYPE": "VANILLA",
        "VERSION": "1.21.1",
        "MEMORY": "6G",
        "ENABLE_RCON": "true",
        "MOTD": "Hello",
    }
    assert Path(spec.data_dir) == (app_settings.mc_root / "servers" / str(server["id"])).resolve()
    assert Path(spec.data_dir).is_dir()
    assert fake_docker.pulled == ["itzg/minecraft-server:java21"]


def test_create_requires_eula(admin: TestClient) -> None:
    response = admin.post("/api/servers", json={"name": "x", "accept_eula": False})
    assert response.status_code == 422


def test_create_validation(admin: TestClient) -> None:
    for bad in (
        {"memory": "4GB"},
        {"port": 80},
        {"image_tag": "java99"},
        {"source": {"type": "vanilla", "version": "1.20; rm"}},
        {"source": {"type": "unknown"}},
    ):
        response = admin.post("/api/servers", json={"name": "x", "accept_eula": True, **bad})
        assert response.status_code == 422, bad


def test_ports_auto_increment_and_conflicts(admin: TestClient) -> None:
    assert create(admin, name="a", start=False)["port"] == 25565
    assert create(admin, name="b", start=False)["port"] == 25566
    assert (
        admin.post(
            "/api/servers", json={"name": "c", "port": 25565, "accept_eula": True}
        ).status_code
        == 409
    )
    assert admin.post("/api/servers", json={"name": "a", "accept_eula": True}).status_code == 409


def test_stop_and_start(admin: TestClient) -> None:
    server_id = create(admin)["id"]
    wait(admin, server_id)

    assert admin.post(f"/api/servers/{server_id}/stop").status_code == 202
    assert wait(admin, server_id)["state"] == "stopped"
    assert admin.post(f"/api/servers/{server_id}/stop").status_code == 409

    assert admin.post(f"/api/servers/{server_id}/start").status_code == 202
    assert wait(admin, server_id)["state"] == "online"
    assert admin.post(f"/api/servers/{server_id}/start").status_code == 409


def test_start_failure_is_reported(admin: TestClient, fake_docker: FakeDocker) -> None:
    fake_docker.fail_start = "port is already allocated"
    server = wait(admin, create(admin)["id"])
    assert server["state"] == "error"
    assert server["detail"] == "port is already allocated"


def test_changed_settings_recreate_container(admin: TestClient, fake_docker: FakeDocker) -> None:
    server_id = create(admin)["id"]
    wait(admin, server_id)
    admin.post(f"/api/servers/{server_id}/stop")
    wait(admin, server_id)

    # No edit endpoint yet (step 5); change the row directly.
    with Session(admin.app.state.engine) as db:
        server = db.get(Server, server_id)
        server.memory = "8G"
        db.add(server)
        db.commit()
        db.refresh(server)
        admin.app.state.servers.start(server)
    wait(admin, server_id)
    assert fake_docker.containers[f"mcpanel-{server_id}"].spec.env["MEMORY"] == "8G"


def test_command_runs_through_rcon(admin: TestClient, fake_docker: FakeDocker) -> None:
    server_id = create(admin)["id"]
    wait(admin, server_id)
    response = admin.post(f"/api/servers/{server_id}/command", json={"command": "/list"})
    assert response.status_code == 200
    assert "players online" in response.json()["output"]
    assert fake_docker.exec_calls == [(f"mcpanel-{server_id}", ["rcon-cli", "list"])]


def test_command_needs_online_server(admin: TestClient) -> None:
    server_id = create(admin, start=False)["id"]
    response = admin.post(f"/api/servers/{server_id}/command", json={"command": "list"})
    assert response.status_code == 409


def test_delete_removes_container_and_data(admin: TestClient, fake_docker: FakeDocker) -> None:
    server_id = create(admin)["id"]
    wait(admin, server_id)
    data_dir = Path(fake_docker.containers[f"mcpanel-{server_id}"].spec.data_dir)

    assert admin.delete(f"/api/servers/{server_id}").status_code == 204
    assert fake_docker.containers == {}
    assert not data_dir.exists()
    assert admin.get(f"/api/servers/{server_id}").status_code == 404


def test_delete_falls_back_to_docker_when_host_delete_fails(
    admin: TestClient, fake_docker: FakeDocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = create(admin)["id"]
    wait(admin, server_id)
    data_dir = Path(fake_docker.containers[f"mcpanel-{server_id}"].spec.data_dir)
    (data_dir / "world").mkdir()

    # Docker Desktop on Windows: files the container wrote are still held open by the file share.
    real_rmtree = shutil.rmtree
    calls = []

    def flaky_rmtree(path, *args, **kwargs):
        calls.append(path)
        if len(calls) == 1:
            raise OSError(145, "The directory is not empty")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("app.servers.shutil.rmtree", flaky_rmtree)
    assert admin.delete(f"/api/servers/{server_id}").status_code == 204
    assert fake_docker.wiped == [str(data_dir)]
    assert not data_dir.exists()


def test_members_can_operate_but_not_create_or_delete(
    admin: TestClient, member: TestClient
) -> None:
    server_id = create(admin)["id"]
    wait(admin, server_id)

    assert member.get("/api/servers").status_code == 200
    assert member.post(f"/api/servers/{server_id}/stop").status_code == 202
    assert member.post("/api/servers", json={"name": "x", "accept_eula": True}).status_code == 403
    assert member.delete(f"/api/servers/{server_id}").status_code == 403


def test_logged_out_is_rejected(client: TestClient) -> None:
    assert client.get("/api/servers").status_code == 401


def test_docker_unavailable(admin: TestClient, fake_docker: FakeDocker) -> None:
    server_id = create(admin, start=False)["id"]
    fake_docker.unavailable = True
    server = admin.get(f"/api/servers/{server_id}").json()
    assert server["state"] == "unknown"
    assert admin.post(f"/api/servers/{server_id}/start").status_code == 503


def test_console_streams_logs(admin: TestClient, fake_docker: FakeDocker) -> None:
    fake_docker.log_lines = [(1000.0, "[Server thread/INFO]: Starting"), (1001.0, "Done (3.2s)!")]
    server_id = create(admin)["id"]
    wait(admin, server_id)

    lines: list[str] = []
    with admin.websocket_connect(f"/api/servers/{server_id}/console") as ws:
        while len(lines) < 2:  # batching depends on timing
            message = ws.receive_json()
            assert message["type"] == "log"
            lines += message["lines"]
    assert lines == ["[Server thread/INFO]: Starting", "Done (3.2s)!"]
    assert fake_docker.logs_calls[0] == (f"mcpanel-{server_id}", None, 500)


def test_console_requires_login(admin: TestClient, make_client) -> None:
    server_id = create(admin, start=False)["id"]
    stranger = make_client()
    with pytest.raises(WebSocketDisconnect):
        with stranger.websocket_connect(f"/api/servers/{server_id}/console") as ws:
            ws.receive_json()


def test_console_rejects_cross_origin(admin: TestClient) -> None:
    server_id = create(admin, start=False)["id"]
    with pytest.raises(WebSocketDisconnect):
        with admin.websocket_connect(
            f"/api/servers/{server_id}/console", headers={"origin": "http://evil.example"}
        ) as ws:
            ws.receive_json()
