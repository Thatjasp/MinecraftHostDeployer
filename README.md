# MinecraftHostDeployer

A localhost web panel for creating and running modded Minecraft servers from CurseForge
modpacks (pack name/URL or zip upload). It has accounts and a live console. Each Minecraft server
runs as an [`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server) container.

- **Backend:** Python, FastAPI (`backend/`)
- **Frontend:** React + TypeScript + Vite, built with Node (`frontend/`)
- **Deploy:** Docker Compose (panel + `docker-socket-proxy`)

## Run with Docker (Linux host)

```sh
cp .env.example .env            # set SECRET_KEY and CF_API_KEY
sudo mkdir -p /srv/mcpanel && sudo chown 1000:1000 /srv/mcpanel
docker compose up -d --build
```

The panel listens on `http://127.0.0.1:8080` only. From another PC, open an SSH tunnel:

```sh
ssh -L 8080:localhost:8080 user@linuxbox
```

## Local development

Backend (from `backend/`):

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Linux/macOS: .venv/bin/python
.venv/Scripts/uvicorn app.main:app --reload       # http://127.0.0.1:8000, docs at /api/docs
```

Frontend (from `frontend/`):

```sh
npm install
npm run dev        # http://127.0.0.1:5173, proxies /api to :8000 (override with API_TARGET)
```

Or run the backend in Docker with hot reload:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

and start the frontend with `API_TARGET=http://localhost:8080 npm run dev`.

## Checks

```sh
cd backend  && .venv/Scripts/python -m pytest && .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
cd frontend && npm run lint && npm test && npm run build
```
