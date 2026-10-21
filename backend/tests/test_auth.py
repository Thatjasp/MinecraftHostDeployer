from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import login, register


def test_setup_status_flips_after_first_user(client: TestClient) -> None:
    assert client.get("/api/auth/setup").json() == {"needs_setup": True}
    register(client, "steve")
    assert client.get("/api/auth/setup").json() == {"needs_setup": False}


def test_first_user_is_logged_in_admin(client: TestClient) -> None:
    response = register(client, "Steve")
    assert response.status_code == 201
    body = response.json()
    assert (body["username"], body["role"], body["status"]) == ("steve", "admin", "active")
    assert client.get("/api/auth/me").json()["username"] == "steve"


def test_later_users_are_pending_and_cannot_log_in(
    make_client: Callable[[], TestClient],
) -> None:
    register(make_client(), "steve")
    other = make_client()

    response = register(other, "alex")
    assert response.status_code == 201
    assert (response.json()["role"], response.json()["status"]) == ("user", "pending")
    assert other.get("/api/auth/me").status_code == 401

    response = login(other, "alex")
    assert response.status_code == 403
    assert "approval" in response.json()["detail"]


def test_duplicate_username_is_case_insensitive(client: TestClient) -> None:
    register(client, "steve")
    assert register(client, "STEVE").status_code == 409


def test_register_validation(client: TestClient) -> None:
    assert register(client, "ab").status_code == 422
    assert register(client, "has space").status_code == 422
    assert register(client, "steve", "short").status_code == 422


def test_login_logout(make_client: Callable[[], TestClient]) -> None:
    register(make_client(), "steve")
    browser = make_client()

    assert login(browser, "steve", "wrong-password").status_code == 401
    assert login(browser, "nobody").status_code == 401
    response = login(browser, "  Steve ")
    assert response.status_code == 200
    assert browser.get("/api/auth/me").status_code == 200

    assert browser.post("/api/auth/logout").status_code == 204
    assert browser.get("/api/auth/me").status_code == 401


def test_logout_revokes_session_server_side(make_client: Callable[[], TestClient]) -> None:
    owner = make_client()
    register(owner, "steve")
    token = owner.cookies.get("mcpanel_session")
    owner.post("/api/auth/logout")

    stolen = make_client()
    stolen.cookies.set("mcpanel_session", token)
    assert stolen.get("/api/auth/me").status_code == 401


def test_failed_logins_are_rate_limited(make_client: Callable[[], TestClient]) -> None:
    register(make_client(), "steve")
    browser = make_client()
    for _ in range(5):
        assert login(browser, "steve", "wrong-password").status_code == 401
    # Even the right password is refused while blocked.
    assert login(browser, "steve").status_code == 429
