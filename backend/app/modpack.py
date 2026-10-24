"""Inspect uploaded CurseForge zips without extracting them (itzg does the extracting)."""

import json
import re
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

MAX_MANIFEST_BYTES = 5 * 1024 * 1024

_FORGE_INSTALLER = re.compile(r"(?:^|/)forge-(\d+\.\d+(?:\.\d+)?)-[\w.]+-installer\.jar$")
_NEOFORGE_INSTALLER = re.compile(r"(?:^|/)neoforge-(\d+)\.(\d+)\.[\w.-]+-installer\.jar$")
_FABRIC_LAUNCHER = re.compile(r"(?:^|/)fabric-server-mc\.(\d+\.\d+(?:\.\d+)?)-")
_START_SCRIPTS = {"startserver.sh", "start.sh", "run.sh", "startserver.bat", "start.bat", "run.bat"}


class InvalidModpack(Exception):
    pass


class ZipKind(StrEnum):
    CLIENT = "client"  # CurseForge export: manifest.json + overrides/, mods fetched via the API
    SERVER = "server"  # server pack: mods/ and start scripts included


@dataclass(frozen=True)
class ZipInfo:
    kind: ZipKind
    name: str | None
    mc_version: str | None
    loader: str | None


def _check_entries(names: list[str]) -> None:
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", name):
            raise InvalidModpack(f"Zip contains an unsafe path: {name}")


def _read_client_manifest(zf: zipfile.ZipFile) -> ZipInfo | None:
    try:
        info = zf.getinfo("manifest.json")
    except KeyError:
        return None
    if info.file_size > MAX_MANIFEST_BYTES:
        raise InvalidModpack("manifest.json is unreasonably large")
    try:
        manifest = json.loads(zf.read(info))
    except (ValueError, UnicodeDecodeError) as e:
        raise InvalidModpack("manifest.json is not valid JSON") from e
    if not isinstance(manifest, dict) or manifest.get("manifestType") != "minecraftModpack":
        return None
    minecraft = manifest.get("minecraft") or {}
    loaders = minecraft.get("modLoaders") or [{}]
    loader_id = str(
        (next((x for x in loaders if x.get("primary")), loaders[0]) or {}).get("id", "")
    )
    loader = {"forge": "Forge", "neoforge": "NeoForge", "fabric": "Fabric", "quilt": "Quilt"}.get(
        loader_id.split("-")[0].lower()
    )
    name = " ".join(str(manifest[k]) for k in ("name", "version") if manifest.get(k)) or None
    return ZipInfo(ZipKind.CLIENT, name, minecraft.get("version"), loader)


def _read_server_pack(zf: zipfile.ZipFile, names: list[str]) -> ZipInfo | None:
    lowered = [n.replace("\\", "/").lower() for n in names]
    has_mods = any(re.search(r"(?:^|/)mods/[^/]+\.jar$", n) for n in lowered)
    has_script = any(PurePosixPath(n).name in _START_SCRIPTS for n in lowered)
    if not (has_mods or has_script):
        return None

    mc_version = loader = None
    for name in names:
        n = name.replace("\\", "/")
        if m := _FORGE_INSTALLER.search(n):
            mc_version, loader = m[1], "Forge"
        elif m := _NEOFORGE_INSTALLER.search(n):
            # NeoForge 21.1.x is for MC 1.21.1; 26.1.x (year-based) is for MC 26.1.
            major, minor = int(m[1]), int(m[2])
            mc_version = (
                f"{major}.{minor}" if major >= 26 else f"1.{major}" + (f".{minor}" if minor else "")
            )
            loader = "NeoForge"
        elif m := _FABRIC_LAUNCHER.search(n):
            mc_version, loader = m[1], "Fabric"
        if mc_version:
            break

    # Newer CurseForge server packs describe themselves in variables.txt.
    variables = next((n for n in names if PurePosixPath(n).name == "variables.txt"), None)
    if variables and zf.getinfo(variables).file_size < 64 * 1024:
        text = zf.read(variables).decode("utf-8", errors="replace")
        if m := re.search(r"^MINECRAFT_VERSION=([\w.-]+)", text, re.M):
            mc_version = m[1]
        if m := re.search(r"^MODLOADER=(\w+)", text, re.M):
            loader = {"forge": "Forge", "neoforge": "NeoForge", "fabric": "Fabric"}.get(
                m[1].lower(), loader
            )
    return ZipInfo(ZipKind.SERVER, None, mc_version, loader)


def inspect_zip(path: str) -> ZipInfo:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            _check_entries(names)
            info = _read_client_manifest(zf) or _read_server_pack(zf, names)
    except zipfile.BadZipFile as e:
        raise InvalidModpack("Not a valid zip file") from e
    if info is None:
        raise InvalidModpack(
            "This doesn't look like a CurseForge modpack: expected a manifest.json (client export) "
            "or a server pack with a mods/ folder"
        )
    return info
