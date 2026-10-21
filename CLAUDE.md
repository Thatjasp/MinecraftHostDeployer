# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A localhost-only web panel for creating and running CurseForge modded Minecraft servers, with
accounts and a live console. The Python (FastAPI) backend is in `backend/`. The React/TS/Vite frontend,
built with Node, is in `frontend/`. It deploys with Docker Compose on a Linux host. The project is being
built in stages: the scaffold and accounts are done; next come the server lifecycle, CurseForge install,
and admin pages.

## Commands

Backend (run from `backend/`, venv at `backend/.venv`; on Windows use `.venv/Scripts/`, on Linux `.venv/bin/`):
- Install: `.venv/Scripts/python -m pip install -e ".[dev]"`
- Dev server: `.venv/Scripts/uvicorn app.main:app --reload` (port 8000, OpenAPI at `/api/docs`)
- Tests: `.venv/Scripts/python -m pytest`; single test: `... -m pytest tests/test_health.py::test_health`
- Lint/format: `.venv/Scripts/ruff check .` and `.venv/Scripts/ruff format .`
- Migrations (after changing `app/models.py`): `.venv/Scripts/alembic revision --autogenerate -m "..."`,
  then rename the file to the next `NNNN_name.py` and set `revision = "NNNN"`. `.venv/Scripts/alembic check`
  confirms models and migrations match. The app runs `upgrade head` itself at startup.

Frontend (run from `frontend/`):
- `npm run dev` (port 5173; proxies `/api`, including WebSockets, to `API_TARGET`, default `http://localhost:8000`)
- `npm run build` (type-checks with `tsc -b` first), `npm run lint`, `npm test` (Vitest; single file: `npx vitest run src/x.test.ts`)

Docker: `docker compose up -d --build`; backend hot reload with
`docker compose -f compose.yaml -f compose.dev.yaml up --build`. Compose requires a `.env` (see `.env.example`).

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
  `AdminUser` dependencies. `user_from_token()` is the shared resolver for future WebSocket auth.
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
- **`MC_ROOT` same-path mount:** server data (`$MC_ROOT/servers/<id>`) and uploaded zips
  (`$MC_ROOT/modpacks`) are bind-mounted into the panel at the identical absolute path. Paths the panel
  hands to Docker for itzg bind mounts are therefore valid host paths. Keep it that way.
- Panel and itzg both run as **UID 1000** so both can write server folders.
- The panel port is published on `127.0.0.1` only; Minecraft ports are published on all interfaces for LAN players.

## Planned design (not built yet)

- Modpack sources map to itzg env: pack slug/URL → `TYPE=AUTO_CURSEFORGE` + `CF_SLUG`/`CF_PAGE_URL`;
  client-export zip (has `manifest.json`) → `AUTO_CURSEFORGE` + `CF_MODPACK_ZIP`; server-pack zip →
  `TYPE=CURSEFORGE` + `CF_SERVER_MOD`. `EULA=TRUE` is set only after the user ticks the checkbox.
  The Java image tag is chosen from the MC version (≤1.16 java8, ≤1.20.4 java17, else java21).
- Console: WebSocket streams container logs; commands run via `docker exec rcon-cli`.
