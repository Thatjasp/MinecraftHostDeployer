from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.conftest import login, register


@pytest.fixture
def admin(make_client: Callable[[], TestClient]) -> TestClient:
    client = make_client()
    register(client, "steve")
    return client


def _user_id(admin: TestClient, username: str) -> int:
    users = admin.get("/api/users").json()
    return next(u["id"] for u in users if u["username"] == username)


def _approve(admin: TestClient, username: str) -> None:
    user_id = _user_id(admin, username)
    response = admin.patch(f"/api/users/{user_id}", json={"status": "active"})
    assert response.status_code == 200


def test_admin_approves_pending_user(admin: TestClient, make_client) -> None:
    alex = make_client()
    register(alex, "alex")
    _approve(admin, "alex")
    assert login(alex, "alex").status_code == 200
    assert alex.get("/api/auth/me").json()["role"] == "user"


def test_non_admin_cannot_manage_users(admin: TestClient, make_client) -> None:
    alex = make_client()
    register(alex, "alex")
    _approve(admin, "alex")
    login(alex, "alex")
    assert alex.get("/api/users").status_code == 403
    assert alex.patch("/api/users/1", json={"status": "disabled"}).status_code == 403


def test_logged_out_requests_are_rejected(client: TestClient) -> None:
    assert client.get("/api/users").status_code == 401


def test_disabling_user_ends_their_session(admin: TestClient, make_client) -> None:
    alex = make_client()
    register(alex, "alex")
    _approve(admin, "alex")
    login(alex, "alex")
    assert alex.get("/api/auth/me").status_code == 200

    admin.patch(f"/api/users/{_user_id(admin, 'alex')}", json={"status": "disabled"})
    assert alex.get("/api/auth/me").status_code == 401
    assert login(alex, "alex").status_code == 403


def test_admin_cannot_change_or_delete_self(admin: TestClient) -> None:
    my_id = _user_id(admin, "steve")
    assert admin.patch(f"/api/users/{my_id}", json={"role": "user"}).status_code == 400
    assert admin.delete(f"/api/users/{my_id}").status_code == 400


def test_promoted_admin_can_manage_other_admins(admin: TestClient, make_client) -> None:
    alex = make_client()
    register(alex, "alex")
    _approve(admin, "alex")
    admin.patch(f"/api/users/{_user_id(admin, 'alex')}", json={"role": "admin"})

    login(alex, "alex")
    steve_id = _user_id(alex, "steve")
    assert alex.patch(f"/api/users/{steve_id}", json={"role": "user"}).status_code == 200
    assert admin.get("/api/users").status_code == 403


def test_delete_user(admin: TestClient, make_client) -> None:
    register(make_client(), "alex")
    alex_id = _user_id(admin, "alex")
    assert admin.delete(f"/api/users/{alex_id}").status_code == 204
    assert admin.delete(f"/api/users/{alex_id}").status_code == 404
