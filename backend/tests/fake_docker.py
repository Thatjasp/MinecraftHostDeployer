import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.docker_service import ContainerSpec, ContainerState, DockerException, DockerUnavailable


class FakeLogStream:
    def __init__(self, lines: list[tuple[float, str]]) -> None:
        self.lines = lines
        self.closed = False

    def __iter__(self):
        return iter(self.lines)

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeContainer:
    spec: ContainerSpec
    status: str = "created"
    health: str | None = None
    exit_code: int = 0


@dataclass
class FakeDocker:
    """In-memory stand-in for DockerService; containers become healthy as soon as they start."""

    containers: dict[str, FakeContainer] = field(default_factory=dict)
    pulled: list[str] = field(default_factory=list)
    wiped: list[str] = field(default_factory=list)
    exec_calls: list[tuple[str, list[str]]] = field(default_factory=list)
    logs_calls: list[tuple[str, float | None, int | str]] = field(default_factory=list)
    log_lines: list[tuple[float, str]] = field(default_factory=list)
    fail_start: str | None = None
    unavailable: bool = False

    def _check(self) -> None:
        if self.unavailable:
            raise DockerUnavailable("Docker is not reachable: fake")

    def state(self, name: str) -> ContainerState | None:
        self._check()
        c = self.containers.get(name)
        if c is None:
            return None
        return ContainerState(c.status, c.health, c.exit_code, c.spec.labels)

    def ensure_image(self, image: str) -> None:
        self._check()
        if image not in self.pulled:
            self.pulled.append(image)

    def create(self, spec: ContainerSpec) -> None:
        self.containers[spec.name] = FakeContainer(spec)

    def start(self, name: str) -> None:
        if self.fail_start:
            raise DockerException(self.fail_start)
        c = self.containers[name]
        c.status, c.health, c.exit_code = "running", "healthy", 0

    def stop(self, name: str, timeout: int) -> None:
        c = self.containers.get(name)
        if c is not None:
            c.status, c.health, c.exit_code = "exited", None, 143

    def remove(self, name: str) -> None:
        self.containers.pop(name, None)

    def wipe_dir(self, image: str, host_dir: str) -> None:
        self.wiped.append(host_dir)
        for child in Path(host_dir).iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()

    def logs(self, name: str, since: float | None, tail: int | str) -> FakeLogStream | None:
        self._check()
        self.logs_calls.append((name, since, tail))
        if name not in self.containers:
            return None
        return FakeLogStream([line for line in self.log_lines if since is None or line[0] >= since])

    def exec(self, name: str, cmd: list[str]) -> tuple[int, str]:
        self.exec_calls.append((name, cmd))
        return 0, "There are 0 of a max of 20 players online:\n"
