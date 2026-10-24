import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.curseforge import CurseForgeClient
from app.db import make_engine, run_migrations
from app.docker_service import DockerService
from app.routers import auth, modpacks, servers, users
from app.security import LoginLimiter
from app.servers import ServerManager
from app.uploads import UploadStore

log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    docker: DockerService | None = None,
    curseforge: CurseForgeClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.secret_key == Settings.model_fields["secret_key"].default:
            log.warning("SECRET_KEY is not set; using an insecure development key")
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        run_migrations(settings.database_url)
        app.state.engine = make_engine(settings.database_url)
        yield
        app.state.engine.dispose()

    app = FastAPI(
        title="MinecraftHostDeployer",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.login_limiter = LoginLimiter(max_failures=5, window_seconds=300)
    # The Docker client connects lazily, so the panel still starts (and logs in) without Docker.
    app.state.servers = ServerManager(
        docker or DockerService(), settings.mc_root, settings.cf_api_key
    )
    app.state.curseforge = curseforge or CurseForgeClient(settings.cf_api_key)
    app.state.uploads = UploadStore(app.state.servers.modpacks_dir())

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(servers.router)
    app.include_router(modpacks.router)

    _mount_frontend(app, settings.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA: real files as-is, everything else falls back to index.html."""
    if not (dist / "index.html").is_file():
        return
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            return FileResponse(file)
        return FileResponse(root / "index.html")


app = create_app()
