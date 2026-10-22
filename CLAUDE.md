# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A localhost-only web panel for creating and running CurseForge modded Minecraft servers, with
accounts and a live console. The Python (FastAPI) backend is in `backend/`. The React/TS/Vite frontend,
built with Node, is in `frontend/`. It deploys with Docker Compose on a Linux host. The project is being
built in stages: the scaffold, accounts and the vanilla server lifecycle with console are done; next come
CurseForge install, then admin pages (server settings editing, file browser).

## Commands

Backend (run from `backend/`, venv at `backend/.venv`; on Windows use `.venv/Scripts/`, on Linux `.venv/bin/`):
- Install: `.venv/Scripts/python -m pip install -e ".[dev]"`
- Dev server: `MC_ROOT=<absolute local folder> .venv/Scripts/uvicorn app.main:app --reload` (port 8000,
  OpenAPI at `/api/docs`). It talks to the local Docker (Docker Desktop works); without `MC_ROOT` server
  data goes to `/srv/mcpanel`.
- Tests: `.venv/Scripts/python -m pytest`; single test: `... -m pytest tests/test_health.py::test_health`
- Lint/format: `.venv/Scripts/ruff check .` and `.venv/Scripts/ruff format .`
- Migrations (after changing `app/models.py`): `.venv/Scripts/alembic revision --autogenerate -m "..."`,
  then rename the file to the next `NNNN_name.py` and set `revision = "NNNN"`. `.venv/Scripts/alembic check`
  confirms models and migrations match. The app runs `upgrade head` itself at startup.

Frontend (run from `frontend/`):
- `npm run dev` (port 5173; proxies `/api`, including WebSockets, to `API_TARGET`, default `http://localhost:8000`)
- `npm run build` (type-checks with `tsc -b` first), `npm run lint`, `npm test` (Vitest with `--passWithNoTests`;
  no frontend tests exist yet; single file: `npx vitest run src/x.test.ts`)

Docker: `docker compose up -d --build` (panel on `127.0.0.1:${PANEL_PORT:-8080}`); backend hot reload with
`docker compose -f compose.yaml -f compose.dev.yaml up --build`, then point Vite at it with
`API_TARGET=http://localhost:8080 npm run dev`. Compose requires a `.env` (see `.env.example`: `SECRET_KEY`,
`CF_API_KEY`, `MC_ROOT`, `PANEL_PORT`).

Full pre-commit check (same as README): backend `pytest` + `ruff check .` + `ruff format --check .`;
frontend `npm run lint && npm test && npm run build`. Ruff uses line length 100, Python 3.12 target.

## Architecture

- **One image, two stages** (`Dockerfile`): Node builds `frontend/dist`, then Python serves both the API and
  the SPA. `app/main.py` mounts a catch-all that returns real files from the dist folder or falls back to
  `index.html`. Every API route must live under `/api/` so it isn't swallowed by the SPA fallback.
  The fallback is only registered when `FRONTEND_DIST/index.html` exists, so local dev and tests run API-only.
- **Settings** come from `app/config.py` (`pydantic-settings`). `create_app(settings)` stores them, the DB
  engine and the login rate limiter on `app.state`. Route code reads them through the `AppSettings` / `DbSession`
  dependencies, never `get_settings()` directly, so tests can inject a temp `data_dir`. The lifespan creates the
  engine and runs migrations, so `TestClient` must be entered (`with` / `__enter__`); `tests/conftest.py`'s
  `make_client` handles this and gives each client its own cookie jar.
- **Datetimes are timezone-aware UTC** (`models.utcnow()`): SQLModel's `UTCDateTime` rejects naive values.
- **Auth** (`app/routers/auth.py`, `app/deps.py`): sessions are stored server-side in the `sessions` table
  as an HMAC (keyed by `SECRET_KEY`) of a random cookie token (`mcpanel_session`, httpOnly, SameSite=strict).
  Logout and disabling a user delete the rows, which revokes access immediately. Protect routes with the `CurrentUser` /
  `AdminUser` dependencies. WebSockets can't use those dependencies, so they call `user_from_token()` directly.
  The first registered user becomes an active admin and is logged in. Later users are `pending` until an
  admin approves them in `/api/users`. Usernames are stored lowercase. Admins can't change or delete
  their own account, which guarantees an active admin always exists.
- **Frontend auth state** is the TanStack Query `["me"]` query (`src/auth.ts`, `null` = logged out).
  `components/Layout.tsx` gates logged-in routes and `RequireAdmin` gates admin ones. API calls go through
  `src/api.ts`, which turns FastAPI `detail` errors into `ApiError` messages.
- **Minecraft servers are not compose services.** The panel creates `itzg/minecraft-server` containers at
  runtime through the Docker SDK. It talks to `tecnativa/docker-socket-proxy` (`DOCKER_HOST=tcp://socket-proxy:2375`),
  never the raw socket. If a new Docker API call is refused, enable that section in the proxy env in
  `compose.yaml`.
- **Server lifecycle layers:**
  - `app/docker_service.py` is the only module that touches the Docker SDK. Everything in it is blocking.
    Tests replace it with `tests/fake_docker.py`, passed in as `create_app(settings, docker=FakeDocker())`.
    New Docker calls need a matching fake method.
  - `app/servers.py` (`ServerManager`, stored on `app.state.servers`) turns a `Server` row into a `ContainerSpec`.
    It runs start/stop/restart in background threads, tracking the in-flight op in `_ops` and the last failure in `_errors`.
    `status()` combines those with the container's Docker state and itzg healthcheck
    (healthy → `online`, starting → `starting`). Tests call `manager.wait(id)` to join the thread.
  - Containers are named `mcpanel-<id>` and labelled `mcpanel.managed` / `mcpanel.server-id` / `mcpanel.config-hash`.
    On start, a container whose config hash no longer matches the row (env/image/port changed) is removed and
    recreated. World data lives in the bind-mounted folder, so it survives. `extra_env` on `Server` holds
    type-specific itzg env (CurseForge settings go there).
- **Console:** `WS /api/servers/{id}/console` is read-only. It streams `docker logs --follow` batched as
  `{"type":"log","lines":[...]}`. When a container stops it re-polls and resumes with `since` (last log
  timestamp), so a restart continues the same stream. Auth uses the cookie plus an Origin == Host check;
  for that reason the Vite proxy must not set `changeOrigin`. Commands go through `POST /api/servers/{id}/command`
  → `docker exec rcon-cli` (itzg configures RCON itself), and a leading `/` is stripped.
- **Permissions:** any active user can view, start, stop and restart servers and send console commands.
  Creating and deleting servers is admin-only. Creating requires `accept_eula: true`, which is the only path to `EULA=TRUE`.
- **Deleting a server** removes the container and its data folder. On Docker Desktop (Windows/macOS) the
  file share can keep files the container wrote open (Windows reports "directory not empty"), so
  `ServerManager.delete` falls back to `DockerService.wipe_dir` (a throwaway container that deletes the contents).
- **`MC_ROOT` same-path mount:** server data (`$MC_ROOT/servers/<id>`) and uploaded zips
  (`$MC_ROOT/modpacks`) are bind-mounted into the panel at the identical absolute path. Paths the panel
  hands to Docker for itzg bind mounts are therefore valid host paths. Keep it that way.
- Panel and itzg both run as **UID 1000** so both can write server folders.
- The panel port is published on `127.0.0.1` only; Minecraft ports are published on all interfaces for LAN players.

## Planned design (not built yet)

- Modpack sources map to itzg env (stored in `Server.extra_env`): pack slug/URL → `TYPE=AUTO_CURSEFORGE` +
  `CF_SLUG`/`CF_PAGE_URL`; client-export zip (has `manifest.json`) → `AUTO_CURSEFORGE` + `CF_MODPACK_ZIP`;
  server-pack zip → `TYPE=CURSEFORGE` + `CF_SERVER_MOD`. The image tag will be suggested from the MC version
  (≤1.16 java8, ≤1.20.4 java17, ≤1.21.x java21, 26.1+ java25). Available tags are `IMAGE_TAGS` in
  `app/servers.py`, mirrored in `frontend/src/servers.ts`.
