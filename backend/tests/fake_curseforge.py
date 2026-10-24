"""Canned CurseForge API responses for CurseForgeClient(fetch=fake_fetch)."""

import json
import zipfile
from pathlib import Path

from app.curseforge import CurseForgeError

PACK = {
    "id": 1,
    "name": "Test Pack",
    "slug": "test-pack",
    "summary": "A pack for tests",
    "logo": {"thumbnailUrl": "https://media.example/logo.png"},
    "links": {"websiteUrl": "https://www.curseforge.com/minecraft/modpacks/test-pack"},
    "mainFileId": 100,
    "latestFiles": [
        {"id": 100, "displayName": "Test Pack 1.0", "gameVersions": ["Forge", "1.20.1"]},
        {
            "id": 101,
            "displayName": "Test Pack Server 1.0",
            "gameVersions": ["1.20.1"],
            "isServerPack": True,
        },
    ],
}
OLD_FILE = {"id": 90, "displayName": "Test Pack 0.9", "gameVersions": ["1.19.2", "Forge"]}


def fake_fetch(url: str, headers: dict[str, str]) -> dict:
    assert headers["x-api-key"]
    if "/mods/search?" in url:
        return {"data": [PACK] if "slug=test-pack" in url else []}
    if url.endswith("/mods/1/files/90"):
        return {"data": OLD_FILE}
    raise CurseForgeError("Not found on CurseForge")


def make_zip(path: Path, files: dict[str, str | bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def client_export(path: Path, mc_version: str = "1.20.1", loader: str = "forge-47.2.0") -> Path:
    manifest = {
        "minecraft": {"version": mc_version, "modLoaders": [{"id": loader, "primary": True}]},
        "manifestType": "minecraftModpack",
        "manifestVersion": 1,
        "name": "My Pack",
        "version": "2.0",
        "files": [{"projectID": 1, "fileID": 2, "required": True}],
        "overrides": "overrides",
    }
    return make_zip(path, {"manifest.json": json.dumps(manifest), "overrides/config/a.toml": "x=1"})


def server_pack(path: Path) -> Path:
    return make_zip(
        path,
        {
            "mods/jei.jar": b"jar",
            "startserver.sh": "#!/bin/sh",
            "forge-1.20.1-47.2.0-installer.jar": b"jar",
        },
    )
