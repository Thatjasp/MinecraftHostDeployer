from pathlib import Path

import pytest

from app.modpack import InvalidModpack, ZipKind, inspect_zip
from tests.fake_curseforge import client_export, make_zip, server_pack


def test_client_export(tmp_path: Path) -> None:
    info = inspect_zip(str(client_export(tmp_path / "p.zip", "1.21.1", "neoforge-21.1.77")))
    assert (info.kind, info.name, info.mc_version, info.loader) == (
        ZipKind.CLIENT,
        "My Pack 2.0",
        "1.21.1",
        "NeoForge",
    )


def test_server_pack_with_forge_installer(tmp_path: Path) -> None:
    info = inspect_zip(str(server_pack(tmp_path / "s.zip")))
    assert (info.kind, info.mc_version, info.loader) == (ZipKind.SERVER, "1.20.1", "Forge")


@pytest.mark.parametrize(
    ("files", "mc_version", "loader"),
    [
        (
            {"Pack/mods/a.jar": b"", "Pack/neoforge-21.1.77-installer.jar": b""},
            "1.21.1",
            "NeoForge",
        ),
        ({"mods/a.jar": b"", "neoforge-20.4.237-installer.jar": b""}, "1.20.4", "NeoForge"),
        ({"mods/a.jar": b"", "neoforge-21.0.10-beta-installer.jar": b""}, "1.21", "NeoForge"),
        (
            {"mods/a.jar": b"", "fabric-server-mc.1.20.1-loader.0.15.0-launcher.1.0.0.jar": b""},
            "1.20.1",
            "Fabric",
        ),
        (
            {"mods/a.jar": b"", "variables.txt": "MINECRAFT_VERSION=1.19.2\nMODLOADER=Forge\n"},
            "1.19.2",
            "Forge",
        ),
        ({"start.sh": "#!/bin/sh"}, None, None),
    ],
)
def test_server_pack_detection(tmp_path: Path, files, mc_version, loader) -> None:
    info = inspect_zip(str(make_zip(tmp_path / "s.zip", files)))
    assert (info.kind, info.mc_version, info.loader) == (ZipKind.SERVER, mc_version, loader)


@pytest.mark.parametrize(
    "files",
    [
        {"../evil.sh": "x", "mods/a.jar": b""},
        {"/etc/passwd": "x", "mods/a.jar": b""},
        {"C:/Windows/x": "x", "mods/a.jar": b""},
    ],
)
def test_rejects_unsafe_paths(tmp_path: Path, files) -> None:
    with pytest.raises(InvalidModpack, match="unsafe"):
        inspect_zip(str(make_zip(tmp_path / "bad.zip", files)))


def test_rejects_unrelated_zip(tmp_path: Path) -> None:
    with pytest.raises(InvalidModpack, match="doesn't look like"):
        inspect_zip(str(make_zip(tmp_path / "x.zip", {"readme.txt": "hi"})))


def test_rejects_non_modpack_manifest(tmp_path: Path) -> None:
    with pytest.raises(InvalidModpack):
        inspect_zip(str(make_zip(tmp_path / "x.zip", {"manifest.json": '{"name": "web app"}'})))


def test_rejects_non_zip(tmp_path: Path) -> None:
    path = tmp_path / "x.zip"
    path.write_bytes(b"not a zip")
    with pytest.raises(InvalidModpack, match="Not a valid zip"):
        inspect_zip(str(path))
