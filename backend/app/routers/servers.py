import asyncio
import contextlib
import threading
from typing import Annotated
from urllib.parse import urlsplit

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.websockets import WebSocketDisconnect

from app.curseforge import CurseForgeClient, CurseForgeError, parse_pack_ref, suggest_image_tag
from app.db import DbSession
from app.deps import SESSION_COOKIE, AdminUser, AppSettings, CurrentUser, user_from_token
from app.docker_service import MODPACK_ZIP_PATH, DockerException, DockerUnavailable, LogStream
from app.models import Server
from app.modpack import InvalidModpack, ZipKind, inspect_zip
from app.routers.modpacks import CurseForge, Uploads
from app.schemas import (
    CommandIn,
    CommandOut,
    CurseForgeSource,
    ServerCreate,
    ServerOut,
    UploadSource,
    VanillaSource,
)
from app.servers import CommandFailed, ServerBusy, ServerManager, ServerNotRunning, ServerType
from app.uploads import UploadNotFound, UploadStore

router = APIRouter(prefix="/api/servers", tags=["servers"])

FIRST_PORT = 25565


def get_manager(request: Request) -> ServerManager:
    return request.app.state.servers


Manager = Annotated[ServerManager, Depends(get_manager)]


def _out(server: Server, manager: ServerManager) -> ServerOut:
    current = manager.status(server.id)
    return ServerOut(
        **server.model_dump(exclude={"extra_env", "created_by_id", "modpack_zip"}),
        data_dir=str(manager.data_dir(server.id)),
        state=current.state,
        detail=current.detail,
    )


def _get_server(db: Session, server_id: int) -> Server:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Server not found")
    return server


def _next_free_port(db: Session) -> int:
    used = set(db.exec(select(Server.port)))
    port = FIRST_PORT
    while port in used:
        port += 1
    return port


def _docker_call(fn, *args):
    """Run a manager call, mapping its failures to HTTP errors."""
    try:
        return fn(*args)
    except ServerBusy as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ServerNotRunning as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except CommandFailed as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    except DockerUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    except DockerException as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Docker error: {e}") from e
    except OSError as e:  # deleting server files
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"File error: {e}") from e


@router.get("", response_model=list[ServerOut])
def list_servers(db: DbSession, manager: Manager, _user: CurrentUser) -> list[ServerOut]:
    return [_out(s, manager) for s in db.exec(select(Server).order_by(Server.name))]


def _source_fields(
    body: ServerCreate, curseforge: CurseForgeClient, uploads: UploadStore, cf_api_key: str
) -> dict:
    """Server columns (type, version, itzg env, ...) for the requested source."""
    source = body.source
    # Where itzg reads mods CurseForge won't let it download (users drop them in the server folder).
    manual_downloads = {"CF_DOWNLOADS_REPO": "/data/downloads"}

    if isinstance(source, VanillaSource):
        return {"server_type": ServerType.VANILLA, "version": source.version}

    if isinstance(source, CurseForgeSource):
        try:
            info = curseforge.lookup(parse_pack_ref(source.ref))
        except CurseForgeError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
        return {
            "server_type": ServerType.AUTO_CURSEFORGE,
            "version": info.mc_version or "",
            "loader": info.loader or "",
            "modpack": f"{info.name} · {info.file_name}"[:200],
            # Pin the file looked up now, so restarts don't silently update the pack.
            "extra_env": {
                "CF_SLUG": info.slug,
                "CF_FILE_ID": str(info.file_id),
                **manual_downloads,
            },
        }

    try:
        zip_info = inspect_zip(str(uploads.path(source.upload_id)))
    except (UploadNotFound, InvalidModpack) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    fields = {
        "version": zip_info.mc_version or "",
        "loader": zip_info.loader or "",
        "modpack": (zip_info.name or uploads.original_name(source.upload_id))[:200],
    }
    if zip_info.kind == ZipKind.CLIENT:
        if not cf_api_key:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "CF_API_KEY is not set in .env; it's needed to download mods",
            )
        fields["server_type"] = ServerType.AUTO_CURSEFORGE
        # itzg requires a slug even for unpublished packs; any identifier works.
        env = {"CF_MODPACK_ZIP": MODPACK_ZIP_PATH, "CF_SLUG": "custom", **manual_downloads}
    else:
        fields["server_type"] = ServerType.CURSEFORGE
        env = {"CF_SERVER_MOD": MODPACK_ZIP_PATH, "CF_BASE_DIR": "/data"}
    return {**fields, "extra_env": env}


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
def create_server(
    body: ServerCreate,
    db: DbSession,
    manager: Manager,
    curseforge: CurseForge,
    uploads: Uploads,
    settings: AppSettings,
    admin: AdminUser,
) -> ServerOut:
    fields = _source_fields(body, curseforge, uploads, settings.cf_api_key)
    server = Server(
        name=body.name,
        port=body.port or _next_free_port(db),
        memory=body.memory,
        image_tag=body.image_tag or suggest_image_tag(fields["version"]),
        motd=body.motd,
        created_by_id=admin.id,
        **fields,
    )
    db.add(server)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Name or port is already used") from None
    db.refresh(server)

    if isinstance(body.source, UploadSource):
        server.modpack_zip = uploads.claim(body.source.upload_id, server.id)
        db.add(server)
        db.commit()
        db.refresh(server)
    if body.start:
        _docker_call(manager.start, server)
    return _out(server, manager)


@router.get("/{server_id}", response_model=ServerOut)
def get_server(server_id: int, db: DbSession, manager: Manager, _user: CurrentUser) -> ServerOut:
    return _out(_get_server(db, server_id), manager)


@router.post("/{server_id}/start", response_model=ServerOut, status_code=status.HTTP_202_ACCEPTED)
def start_server(server_id: int, db: DbSession, manager: Manager, _user: CurrentUser) -> ServerOut:
    server = _get_server(db, server_id)
    _docker_call(manager.start, server)
    return _out(server, manager)


@router.post("/{server_id}/stop", response_model=ServerOut, status_code=status.HTTP_202_ACCEPTED)
def stop_server(server_id: int, db: DbSession, manager: Manager, _user: CurrentUser) -> ServerOut:
    server = _get_server(db, server_id)
    _docker_call(manager.stop, server.id)
    return _out(server, manager)


@router.post("/{server_id}/restart", response_model=ServerOut, status_code=status.HTTP_202_ACCEPTED)
def restart_server(
    server_id: int, db: DbSession, manager: Manager, _user: CurrentUser
) -> ServerOut:
    server = _get_server(db, server_id)
    _docker_call(manager.restart, server)
    return _out(server, manager)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_server(server_id: int, db: DbSession, manager: Manager, _admin: AdminUser) -> None:
    server = _get_server(db, server_id)
    _docker_call(manager.delete, server)
    db.delete(server)
    db.commit()


@router.post("/{server_id}/command", response_model=CommandOut)
def run_command(
    server_id: int, body: CommandIn, db: DbSession, manager: Manager, _user: CurrentUser
) -> CommandOut:
    server = _get_server(db, server_id)
    # Console users type "/op steve" out of habit; RCON wants it without the slash.
    output = _docker_call(manager.command, server.id, body.command.removeprefix("/"))
    return CommandOut(output=output)


# --- live console (read-only log stream; commands go through POST /command) ------------------


def _same_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    return origin is None or urlsplit(origin).netloc == websocket.headers.get("host")


@router.websocket("/{server_id}/console")
async def console(websocket: WebSocket, server_id: int) -> None:
    app = websocket.app
    with Session(app.state.engine) as db:
        user = user_from_token(db, app.state.settings, websocket.cookies.get(SESSION_COOKIE))
        server = db.get(Server, server_id)
    if not _same_origin(websocket) or user is None or server is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    # anyio task group (not bare asyncio tasks) so Starlette/uvicorn cancellation unwinds cleanly.
    async with anyio.create_task_group() as tasks:
        tasks.start_soon(_pump_logs, websocket, app.state.servers, server_id)
        # The client never sends anything; receive() just tells us when it goes away.
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass
        tasks.cancel_scope.cancel()
    # The client may already be gone (the pump only notices when a send fails).
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        await websocket.close()


async def _pump_logs(websocket: WebSocket, manager: ServerManager, server_id: int) -> None:
    since: float | None = None
    while True:
        try:
            stream = await asyncio.to_thread(manager.log_stream, server_id, since)
        except (DockerUnavailable, DockerException) as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            await asyncio.sleep(5)
            continue
        if stream is None:  # container not created yet
            await asyncio.sleep(2)
            continue
        try:
            since = await _forward(websocket, stream, since)
        except WebSocketDisconnect:
            return
        finally:
            stream.close()
        await asyncio.sleep(1)  # stream ends when the container stops; poll for the next start


async def _forward(websocket: WebSocket, stream: LogStream, since: float | None) -> float | None:
    """Send log lines in batches until the stream ends; returns the resume timestamp."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[float, str] | None] = asyncio.Queue()

    def read() -> None:
        try:
            for item in stream:
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception:
            pass  # closed underneath us, or Docker went away; the pump loop retries
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=read, daemon=True).start()
    while True:
        item = await queue.get()
        batch: list[str] = []
        while item is not None:
            ts, line = item
            if ts:
                since = ts + 1e-6  # docker's `since` is inclusive
            batch.append(line)
            if len(batch) >= 500 or queue.empty():
                break
            item = queue.get_nowait()
        if batch:
            await websocket.send_json({"type": "log", "lines": batch})
        if item is None:
            return since
