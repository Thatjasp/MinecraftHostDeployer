from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from tests.conftest import login, register
from tests.fake_curseforge import client_export, make_zip, server_pack
from tests.fake_docker import FakeDocker


@pytest.fixture
def admin(make_client: Callable[[], TestClient]) -> TestClient:
    client = make_client()
    register(client, "steve")
    return client


def upload(client: TestClient, path: Path, filename: str = "pack.zip"):
    return client.post(
        f"/api/modpacks/upload?filename={filename}",
        content=path.read_bytes(),
        headers={"Content-Type": "application/zip"},
    )


def create(client: TestClient, source: dict, **overrides) -> dict:
    body = {"name": "Modded", "source": source, "accept_eula": True, **overrides}
    response = client.post("/api/servers", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def spec_of(fake_docker: FakeDocker, server_id: int):
    return fake_docker.containers[f"mcpanel-{server_id}"].spec


def wait(client: TestClient, server_id: int) -> None:
    client.app.state.servers.wait(server_id, timeout=5)


# --- lookup ---------------------------------------------------------------------------------


def test_lookup_preview(admin: TestClient) -> None:
    response = admin.post(
        "/api/modpacks/lookup",
        json={"ref": "https://www.curseforge.com/minecraft/modpacks/test-pack"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["mc_version"], body["loader"]) == ("Test Pack", "1.20.1", "Forge")
    assert body["suggested_image_tag"] == "java17"
    assert body["file_name"] == "Test Pack 1.0"


def test_lookup_errors_are_400(admin: TestClient) -> None:
    assert admin.post("/api/modpacks/lookup", json={"ref": "missing-pack"}).status_code == 400
    assert admin.post("/api/modpacks/lookup", json={"ref": "not a slug"}).status_code == 400


def test_modpack_endpoints_are_admin_only(admin: TestClient, make_client, tmp_path: Path) -> None:
    member = make_client()
    user_id = register(member, "alex").json()["id"]
    admin.patch(f"/api/users/{user_id}", json={"status": "active"})
    login(member, "alex")
    assert member.post("/api/modpacks/lookup", json={"ref": "test-pack"}).status_code == 403
    assert upload(member, client_export(tmp_path / "p.zip")).status_code == 403


# --- create from CurseForge -------------------------------------------------------------------


def test_create_from_curseforge_pins_file_and_injects_key(
    admin: TestClient, fake_docker: FakeDocker
) -> None:
    server = create(admin, {"type": "curseforge", "ref": "test-pack"}, memory="8G")
    assert (server["server_type"], server["version"], server["loader"]) == (
        "AUTO_CURSEFORGE",
        "1.20.1",
        "Forge",
    )
    assert server["modpack"] == "Test Pack · Test Pack 1.0"
    assert server["image_tag"] == "java17"  # suggested from 1.20.1

    wait(admin, server["id"])
    spec = spec_of(fake_docker, server["id"])
    assert spec.env == {
        "EULA": "TRUE",
        "TYPE": "AUTO_CURSEFORGE",
        "MEMORY": "8G",
        "ENABLE_RCON": "true",
        "CF_API_KEY": "test-cf-key",
        "CF_SLUG": "test-pack",
        "CF_FILE_ID": "100",
        "CF_DOWNLOADS_REPO": "/data/downloads",
    }
    assert spec.image == "itzg/minecraft-server:java17"
    assert spec.modpack_zip is None
    assert spec.health_start_period_s == 30 * 60


def test_create_from_curseforge_respects_explicit_tag(admin: TestClient) -> None:
    server = create(admin, {"type": "curseforge", "ref": "test-pack"}, image_tag="java21")
    assert server["image_tag"] == "java21"


def test_create_from_bad_ref_creates_nothing(admin: TestClient) -> None:
    response = admin.post(
        "/api/servers",
        json={"name": "x", "source": {"type": "curseforge", "ref": "missing"}, "accept_eula": True},
    )
    assert response.status_code == 400
    assert admin.get("/api/servers").json() == []


def test_vanilla_keeps_short_health_period_and_no_cf_key(
    admin: TestClient, fake_docker: FakeDocker
) -> None:
    server = create(admin, {"type": "vanilla"})
    wait(admin, server["id"])
    spec = spec_of(fake_docker, server["id"])
    assert spec.health_start_period_s == 120
    assert "CF_API_KEY" not in spec.env
    assert spec.env["VERSION"] == "LATEST"


# --- uploads ----------------------------------------------------------------------------------


def test_upload_client_export_preview(admin: TestClient, tmp_path: Path) -> None:
    response = upload(admin, client_export(tmp_path / "p.zip", "1.21.1"), "My Pack.zip")
    assert response.status_code == 201
    body = response.json()
    assert (body["kind"], body["name"], body["mc_version"], body["suggested_image_tag"]) == (
        "client",
        "My Pack 2.0",
        "1.21.1",
        "java21",
    )
    assert len(body["upload_id"]) == 32


def test_upload_server_pack_named_after_file(admin: TestClient, tmp_path: Path) -> None:
    body = upload(admin, server_pack(tmp_path / "s.zip"), "Cool Server 1.2.zip").json()
    assert (body["kind"], body["name"], body["mc_version"]) == (
        "server",
        "Cool Server 1.2",
        "1.20.1",
    )


def test_upload_rejects_non_modpack_and_cleans_up(
    admin: TestClient, tmp_path: Path, app_settings: Settings
) -> None:
    response = upload(admin, make_zip(tmp_path / "x.zip", {"readme.txt": "hi"}))
    assert response.status_code == 422
    pending = app_settings.mc_root / "modpacks" / "pending"
    assert list(pending.glob("*.zip")) == []


def test_upload_too_large(admin: TestClient, tmp_path: Path) -> None:
    admin.app.state.settings = admin.app.state.settings.model_copy(update={"max_upload_mb": 1})
    big = tmp_path / "big.zip"
    big.write_bytes(b"0" * (2 * 2**20))
    assert upload(admin, big).status_code == 413


def test_create_from_client_export_upload(
    admin: TestClient, fake_docker: FakeDocker, tmp_path: Path, app_settings: Settings
) -> None:
    upload_id = upload(admin, client_export(tmp_path / "p.zip")).json()["upload_id"]
    server = create(admin, {"type": "upload", "upload_id": upload_id})
    assert (server["server_type"], server["modpack"], server["loader"]) == (
        "AUTO_CURSEFORGE",
        "My Pack 2.0",
        "Forge",
    )

    wait(admin, server["id"])
    spec = spec_of(fake_docker, server["id"])
    zip_path = (app_settings.mc_root / "modpacks" / f"server-{server['id']}.zip").resolve()
    assert spec.modpack_zip == str(zip_path)
    assert zip_path.is_file()
    assert spec.env["CF_MODPACK_ZIP"] == "/modpacks/pack.zip"
    assert spec.env["CF_SLUG"] == "custom"
    assert spec.env["CF_API_KEY"] == "test-cf-key"
    assert list((app_settings.mc_root / "modpacks" / "pending").iterdir()) == []

    # The same upload can't be used twice.
    response = admin.post(
        "/api/servers",
        json={
            "name": "again",
            "source": {"type": "upload", "upload_id": upload_id},
            "accept_eula": True,
        },
    )
    assert response.status_code == 400


def test_create_from_server_pack_upload(
    admin: TestClient, fake_docker: FakeDocker, tmp_path: Path
) -> None:
    upload_id = upload(admin, server_pack(tmp_path / "s.zip")).json()["upload_id"]
    server = create(admin, {"type": "upload", "upload_id": upload_id})
    assert server["server_type"] == "CURSEFORGE"

    wait(admin, server["id"])
    env = spec_of(fake_docker, server["id"]).env
    assert env["CF_SERVER_MOD"] == "/modpacks/pack.zip"
    assert env["CF_BASE_DIR"] == "/data"
    assert "CF_API_KEY" not in env


def test_client_export_needs_api_key(admin: TestClient, tmp_path: Path) -> None:
    upload_id = upload(admin, client_export(tmp_path / "p.zip")).json()["upload_id"]
    admin.app.state.settings = admin.app.state.settings.model_copy(update={"cf_api_key": ""})
    response = admin.post(
        "/api/servers",
        json={
            "name": "x",
            "source": {"type": "upload", "upload_id": upload_id},
            "accept_eula": True,
        },
    )
    assert response.status_code == 400
    assert "CF_API_KEY" in response.json()["detail"]


def test_delete_removes_uploaded_zip(
    admin: TestClient, tmp_path: Path, app_settings: Settings
) -> None:
    upload_id = upload(admin, server_pack(tmp_path / "s.zip")).json()["upload_id"]
    server = create(admin, {"type": "upload", "upload_id": upload_id})
    wait(admin, server["id"])
    zip_path = app_settings.mc_root / "modpacks" / f"server-{server['id']}.zip"
    assert zip_path.is_file()
    assert admin.delete(f"/api/servers/{server['id']}").status_code == 204
    assert not zip_path.exists()
