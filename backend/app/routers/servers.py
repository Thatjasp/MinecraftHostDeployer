import asyncio
import contextlib
import threading
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.websockets import WebSocketDisconnect

from app.db import DbSession
from app.deps import SESSION_COOKIE, AdminUser, CurrentUser, user_from_token
from app.docker_service import DockerException, DockerUnavailable, LogStream
from app.models import Server
from app.schemas import CommandIn, CommandOut, ServerCreate, ServerOut
from app.servers import CommandFailed, ServerBusy, ServerManager, ServerNotRunning

router = APIRouter(prefix="/api/servers", tags=["servers"])

FIRST_PORT = 25565


def get_manager(request: Request) -> ServerManager:
    return request.app.state.servers


Manager = Annotated[ServerManager, Depends(get_manager)]


def _out(server: Server, manager: ServerManager) -> ServerOut:
    current = manager.status(server.id)
    return ServerOut(
        **server.model_dump(exclude={"extra_env", "created_by_id"}),
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


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
def create_server(
    body: ServerCreate, db: DbSession, manager: Manager, admin: AdminUser
) -> ServerOut:
    server = Server(
        name=body.name,
        port=body.port or _next_free_port(db),
        memory=body.memory,
        image_tag=body.image_tag,
        server_type="VANILLA",
        version=body.version,
        motd=body.motd,
        created_by_id=admin.id,
    )
    db.add(server)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Name or port is already used") from None
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
    pump = asyncio.create_task(_pump_logs(websocket, app.state.servers, server_id))
    # The client never sends anything; receive() just tells us when it goes away.
    disconnect = asyncio.create_task(websocket.receive())
    await asyncio.wait({pump, disconnect}, return_when=asyncio.FIRST_COMPLETED)
    for task in (pump, disconnect):
        task.cancel()
    await asyncio.gather(pump, disconnect, return_exceptions=True)
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
