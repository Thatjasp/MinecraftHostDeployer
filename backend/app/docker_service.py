"""Thin wrapper over the Docker SDK: the only module that talks to Docker.

Everything here is blocking; callers run it in threads. Tests swap in a fake with the same methods.
"""

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime

import docker
from docker.errors import DockerException, ImageNotFound, NotFound
from docker.models.containers import Container

MANAGED_LABEL = "mcpanel.managed"


class DockerUnavailable(Exception):
    pass


@dataclass(frozen=True)
class ContainerSpec:
    name: str
    image: str
    env: dict[str, str]
    host_port: int
    data_dir: str
    labels: dict[str, str]
    modpack_zip: str | None = None  # host file, mounted read-only at MODPACK_ZIP_PATH
    # Grace period before failed healthchecks count; modpack installs need far more than vanilla.
    health_start_period_s: int = 120


MODPACK_ZIP_PATH = "/modpacks/pack.zip"


@dataclass(frozen=True)
class ContainerState:
    status: str  # docker state: created, running, restarting, exited, ...
    health: str | None  # itzg healthcheck: starting, healthy, unhealthy
    exit_code: int
    labels: dict[str, str]


class LogStream:
    """Follows a container's log as (unix_timestamp, line) pairs; close() unblocks the reader."""

    def __init__(self, raw) -> None:
        self._raw = raw

    def __iter__(self) -> Iterator[tuple[float, str]]:
        buffer = ""
        for chunk in self._raw:
            buffer += chunk.decode("utf-8", errors="replace")
            *lines, buffer = buffer.split("\n")
            for line in lines:
                yield _split_timestamp(line.rstrip("\r"))
        if buffer:
            yield _split_timestamp(buffer)

    def close(self) -> None:
        self._raw.close()


def _split_timestamp(line: str) -> tuple[float, str]:
    # With timestamps=True every line starts with RFC3339Nano, e.g. 2026-10-21T04:27:05.514177123Z
    stamp, _, text = line.partition(" ")
    try:
        whole, _, frac = stamp.rstrip("Z").partition(".")
        ts = datetime.fromisoformat(f"{whole}.{frac[:6] or '0'}+00:00").timestamp()
    except ValueError:
        return 0.0, line
    return ts, text


class DockerService:
    def __init__(self, client_factory: Callable[[], docker.DockerClient] = docker.from_env) -> None:
        self._client_factory = client_factory
        self._client: docker.DockerClient | None = None
        self._lock = threading.Lock()

    @property
    def client(self) -> docker.DockerClient:
        with self._lock:
            if self._client is None:
                try:
                    self._client = self._client_factory()
                except DockerException as e:
                    raise DockerUnavailable(f"Docker is not reachable: {e}") from e
            return self._client

    def _get(self, name: str) -> Container | None:
        try:
            return self.client.containers.get(name)
        except NotFound:
            return None

    def state(self, name: str) -> ContainerState | None:
        container = self._get(name)
        if container is None:
            return None
        state = container.attrs["State"]
        return ContainerState(
            status=state["Status"],
            health=(state.get("Health") or {}).get("Status"),
            exit_code=state.get("ExitCode", 0),
            labels=container.labels,
        )

    def ensure_image(self, image: str) -> None:
        try:
            self.client.images.get(image)
        except ImageNotFound:
            repo, _, tag = image.rpartition(":")
            self.client.images.pull(repo, tag=tag)

    def create(self, spec: ContainerSpec) -> None:
        volumes = {spec.data_dir: {"bind": "/data", "mode": "rw"}}
        if spec.modpack_zip:
            volumes[spec.modpack_zip] = {"bind": MODPACK_ZIP_PATH, "mode": "ro"}
        seconds = 1_000_000_000
        self.client.containers.create(
            spec.image,
            name=spec.name,
            environment=spec.env,
            ports={"25565/tcp": spec.host_port},
            volumes=volumes,
            # itzg's own check, with a start period long enough for the server to finish loading.
            healthcheck={
                "test": ["CMD-SHELL", "mc-health"],
                "interval": 30 * seconds,
                "start_period": spec.health_start_period_s * seconds,
                "retries": 2,
            },
            labels={MANAGED_LABEL: "true", **spec.labels},
            # Comes back after a host reboot unless it was stopped through the panel.
            restart_policy={"Name": "unless-stopped"},
        )

    def start(self, name: str) -> None:
        self.client.containers.get(name).start()

    def stop(self, name: str, timeout: int) -> None:
        container = self._get(name)
        if container is not None:
            container.stop(timeout=timeout)

    def remove(self, name: str) -> None:
        container = self._get(name)
        if container is not None:
            container.remove(force=True)

    def wipe_dir(self, image: str, host_dir: str) -> None:
        """Delete a bind-mounted folder's contents from inside a throwaway container."""
        self.ensure_image(image)
        self.client.containers.run(
            image,
            entrypoint=["find", "/data", "-mindepth", "1", "-delete"],
            volumes={host_dir: {"bind": "/data", "mode": "rw"}},
            labels={MANAGED_LABEL: "true"},
            remove=True,
        )

    def logs(self, name: str, since: float | None, tail: int | str) -> LogStream | None:
        container = self._get(name)
        if container is None:
            return None
        raw = container.logs(stream=True, follow=True, timestamps=True, since=since, tail=tail)
        return LogStream(raw)

    def exec(self, name: str, cmd: list[str]) -> tuple[int, str]:
        result = self.client.containers.get(name).exec_run(cmd)
        return result.exit_code, result.output.decode("utf-8", errors="replace")


__all__ = [
    "ContainerSpec",
    "ContainerState",
    "DockerException",
    "DockerService",
    "DockerUnavailable",
    "LogStream",
]
