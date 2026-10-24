"""Maps Server rows to itzg containers and runs slow Docker operations in background threads."""

import hashlib
import json
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.docker_service import (
    ContainerSpec,
    DockerException,
    DockerService,
    DockerUnavailable,
    LogStream,
)
from app.models import Server

IMAGE_REPO = "itzg/minecraft-server"
IMAGE_TAGS = ("latest", "java25", "java21", "java17", "java11", "java8")
CONFIG_LABEL = "mcpanel.config-hash"
# itzg saves the world on SIGTERM; big modpacks can take a while.
STOP_TIMEOUT_SECONDS = 60


class ServerType(StrEnum):
    """itzg TYPE values the panel creates."""

    VANILLA = "VANILLA"
    AUTO_CURSEFORGE = "AUTO_CURSEFORGE"  # pack slug/URL, or a client-export zip
    CURSEFORGE = "CURSEFORGE"  # server-pack zip (deprecated in itzg, but still supported)


class ServerState(StrEnum):
    STOPPED = "stopped"
    PULLING = "pulling"  # downloading the itzg image
    STARTING = "starting"  # container up, Minecraft still loading (healthcheck pending)
    ONLINE = "online"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    ERROR = "error"
    UNKNOWN = "unknown"  # Docker unreachable


@dataclass(frozen=True)
class ServerStatus:
    state: ServerState
    detail: str | None = None


class ServerBusy(Exception):
    pass


class ServerNotRunning(Exception):
    pass


class CommandFailed(Exception):
    pass


def container_name(server_id: int) -> str:
    return f"mcpanel-{server_id}"


def build_env(server: Server, cf_api_key: str) -> dict[str, str]:
    env = {
        "EULA": "TRUE",  # only reachable after the user accepted the EULA on create
        "TYPE": server.server_type,
        "MEMORY": server.memory,
        "ENABLE_RCON": "true",  # rcon-cli inside the container is how console commands run
    }
    if server.server_type == ServerType.VANILLA:
        env["VERSION"] = server.version  # modpacks bring their own version
    if server.server_type == ServerType.AUTO_CURSEFORGE and cf_api_key:
        env["CF_API_KEY"] = cf_api_key  # injected, never stored in the DB
    if server.motd:
        env["MOTD"] = server.motd
    env.update(server.extra_env)
    return env


class ServerManager:
    def __init__(self, docker: DockerService, mc_root: Path, cf_api_key: str = "") -> None:
        self.docker = docker
        self.mc_root = mc_root
        self.cf_api_key = cf_api_key
        self._lock = threading.Lock()
        self._ops: dict[int, ServerState] = {}  # in-flight background operation per server
        self._errors: dict[int, str] = {}  # last background failure, shown until the next action
        self._threads: dict[int, threading.Thread] = {}

    def data_dir(self, server_id: int) -> Path:
        return (self.mc_root / "servers" / str(server_id)).resolve()

    def modpacks_dir(self) -> Path:
        return (self.mc_root / "modpacks").resolve()

    def spec(self, server: Server) -> ContainerSpec:
        env = build_env(server, self.cf_api_key)
        image = f"{IMAGE_REPO}:{server.image_tag}"
        zip_path = str(self.modpacks_dir() / server.modpack_zip) if server.modpack_zip else None
        start_period = 120 if server.server_type == ServerType.VANILLA else 30 * 60
        fingerprint = json.dumps([image, server.port, env, zip_path, start_period], sort_keys=True)
        return ContainerSpec(
            name=container_name(server.id),
            image=image,
            env=env,
            host_port=server.port,
            data_dir=str(self.data_dir(server.id)),
            labels={
                "mcpanel.server-id": str(server.id),
                CONFIG_LABEL: hashlib.sha256(fingerprint.encode()).hexdigest()[:16],
            },
            modpack_zip=zip_path,
            health_start_period_s=start_period,
        )

    # --- status ---------------------------------------------------------------------------

    def status(self, server_id: int) -> ServerStatus:
        with self._lock:
            op = self._ops.get(server_id)
            error = self._errors.get(server_id)
        if op is not None:
            return ServerStatus(op)
        try:
            state = self.docker.state(container_name(server_id))
        except (DockerUnavailable, DockerException) as e:
            return ServerStatus(ServerState.UNKNOWN, str(e))

        if state is None:
            return (
                ServerStatus(ServerState.ERROR, error)
                if error
                else ServerStatus(ServerState.STOPPED)
            )
        if state.status == "running":
            return ServerStatus(
                {
                    "starting": ServerState.STARTING,
                    "unhealthy": ServerState.UNHEALTHY,
                }.get(state.health or "", ServerState.ONLINE)
            )
        if state.status == "restarting":
            return ServerStatus(ServerState.STARTING, "Restarting after a crash")
        if error:
            return ServerStatus(ServerState.ERROR, error)
        # 143 = SIGTERM, the normal result of a panel stop.
        if state.exit_code not in (0, 143):
            return ServerStatus(ServerState.STOPPED, f"Exited with code {state.exit_code}")
        return ServerStatus(ServerState.STOPPED)

    def is_running(self, server_id: int) -> bool:
        state = self.docker.state(container_name(server_id))
        return state is not None and state.status in ("running", "restarting")

    # --- lifecycle (non-blocking) ---------------------------------------------------------

    def start(self, server: Server) -> None:
        spec = self.spec(server)
        if self.is_running(server.id):
            raise ServerBusy("Server is already running")
        self._run(server.id, ServerState.PULLING, lambda: self._start(server.id, spec))

    def stop(self, server_id: int) -> None:
        if not self.is_running(server_id):
            raise ServerNotRunning("Server is not running")
        name = container_name(server_id)
        self._run(
            server_id,
            ServerState.STOPPING,
            lambda: self.docker.stop(name, STOP_TIMEOUT_SECONDS),
        )

    def restart(self, server: Server) -> None:
        spec = self.spec(server)

        def work() -> None:
            self._set_op(server.id, ServerState.STOPPING)
            self.docker.stop(spec.name, STOP_TIMEOUT_SECONDS)
            self._start(server.id, spec)

        self._run(server.id, ServerState.STOPPING, work)

    def _start(self, server_id: int, spec: ContainerSpec) -> None:
        self._set_op(server_id, ServerState.PULLING)
        self.docker.ensure_image(spec.image)
        self._set_op(server_id, ServerState.STARTING)
        existing = self.docker.state(spec.name)
        # Settings changed since the container was made: recreate it (world data lives in data_dir).
        if existing is not None and existing.labels.get(CONFIG_LABEL) != spec.labels[CONFIG_LABEL]:
            self.docker.remove(spec.name)
            existing = None
        if existing is None:
            Path(spec.data_dir).mkdir(parents=True, exist_ok=True)
            self.docker.create(spec)
        self.docker.start(spec.name)

    def _set_op(self, server_id: int, op: ServerState) -> None:
        with self._lock:
            self._ops[server_id] = op

    def _run(self, server_id: int, op: ServerState, work: Callable[[], None]) -> None:
        with self._lock:
            if server_id in self._ops:
                raise ServerBusy(f"Server is busy ({self._ops[server_id]})")
            self._ops[server_id] = op
            self._errors.pop(server_id, None)

        def target() -> None:
            try:
                work()
            except Exception as e:  # surfaced through status(); nothing else can catch it
                with self._lock:
                    self._errors[server_id] = str(e) or type(e).__name__
            finally:
                with self._lock:
                    self._ops.pop(server_id, None)
                    self._threads.pop(server_id, None)

        thread = threading.Thread(target=target, name=f"server-{server_id}-{op}", daemon=True)
        with self._lock:
            self._threads[server_id] = thread
        thread.start()

    def wait(self, server_id: int, timeout: float | None = None) -> None:
        """Block until the server's background operation finishes (used by tests)."""
        with self._lock:
            thread = self._threads.get(server_id)
        if thread is not None:
            thread.join(timeout)

    # --- blocking operations --------------------------------------------------------------

    def delete(self, server: Server) -> None:
        with self._lock:
            if server.id in self._ops:
                raise ServerBusy(f"Server is busy ({self._ops[server.id]})")
            self._errors.pop(server.id, None)
        spec = self.spec(server)
        self.docker.remove(spec.name)
        if spec.modpack_zip:
            Path(spec.modpack_zip).unlink(missing_ok=True)
        data_dir = Path(spec.data_dir)
        if not data_dir.exists():
            return
        try:
            shutil.rmtree(data_dir)
        except OSError:
            # Docker Desktop's file sharing (Windows/macOS) can keep files the container wrote
            # open after it's gone; deleting them through Docker works.
            self.docker.wipe_dir(spec.image, spec.data_dir)
            shutil.rmtree(data_dir)

    def command(self, server_id: int, command: str) -> str:
        if self.status(server_id).state not in (ServerState.ONLINE, ServerState.UNHEALTHY):
            raise ServerNotRunning("Server is not online yet")
        code, output = self.docker.exec(container_name(server_id), ["rcon-cli", command])
        if code != 0:
            raise CommandFailed(output.strip() or f"rcon-cli exited with code {code}")
        return output

    def log_stream(self, server_id: int, since: float | None) -> LogStream | None:
        # First connect shows recent history; reconnects (after a restart) resume where we left off.
        tail: int | str = 500 if since is None else "all"
        return self.docker.logs(container_name(server_id), since=since, tail=tail)
