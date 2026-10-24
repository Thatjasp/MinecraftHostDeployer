import pytest

from app.curseforge import (
    CurseForgeClient,
    CurseForgeError,
    PackRef,
    parse_pack_ref,
    split_game_versions,
    suggest_image_tag,
)
from tests.fake_curseforge import fake_fetch


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("all-the-mods-9", PackRef("all-the-mods-9")),
        ("https://www.curseforge.com/minecraft/modpacks/rlcraft", PackRef("rlcraft")),
        ("https://curseforge.com/minecraft/modpacks/atm9/", PackRef("atm9")),
        ("https://www.curseforge.com/minecraft/modpacks/atm9/files/123", PackRef("atm9", 123)),
        ("https://www.curseforge.com/minecraft/modpacks/atm9?x=1", PackRef("atm9")),
        ("  atm9  ", PackRef("atm9")),
    ],
)
def test_parse_pack_ref(text: str, expected: PackRef) -> None:
    assert parse_pack_ref(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Has Spaces",
        "../etc",
        "https://evil.example/minecraft/modpacks/x",
        "https://www.curseforge.com/minecraft/mc-mods/jei",
    ],
)
def test_parse_pack_ref_rejects(text: str) -> None:
    with pytest.raises(CurseForgeError):
        parse_pack_ref(text)


@pytest.mark.parametrize(
    ("version", "tag"),
    [
        ("1.7.10", "java8"),
        ("1.12.2", "java8"),
        ("1.16.5", "java8"),
        ("1.17.1", "java17"),
        ("1.20.1", "java17"),
        ("1.20.4", "java17"),
        ("1.20.5", "java21"),
        ("1.21.1", "java21"),
        ("26.1", "java25"),
        (None, "latest"),
        ("LATEST", "latest"),
    ],
)
def test_suggest_image_tag(version: str | None, tag: str) -> None:
    assert suggest_image_tag(version) == tag


def test_split_game_versions() -> None:
    assert split_game_versions(["Forge", "1.20.1", "Client"]) == ("1.20.1", "Forge")
    assert split_game_versions(["1.12.2"]) == ("1.12.2", None)


def test_lookup_uses_main_file() -> None:
    info = CurseForgeClient("key", fetch=fake_fetch).lookup(PackRef("test-pack"))
    assert (info.name, info.file_id, info.mc_version, info.loader) == (
        "Test Pack",
        100,
        "1.20.1",
        "Forge",
    )
    assert info.page_url == "https://www.curseforge.com/minecraft/modpacks/test-pack"


def test_lookup_pinned_file_not_in_latest() -> None:
    info = CurseForgeClient("key", fetch=fake_fetch).lookup(PackRef("test-pack", 90))
    assert (info.file_id, info.file_name, info.mc_version) == (90, "Test Pack 0.9", "1.19.2")


def test_lookup_rejects_server_pack_file() -> None:
    with pytest.raises(CurseForgeError, match="server pack"):
        CurseForgeClient("key", fetch=fake_fetch).lookup(PackRef("test-pack", 101))


def test_lookup_unknown_slug() -> None:
    with pytest.raises(CurseForgeError, match="No CurseForge modpack"):
        CurseForgeClient("key", fetch=fake_fetch).lookup(PackRef("nope"))


def test_lookup_requires_key() -> None:
    with pytest.raises(CurseForgeError, match="CF_API_KEY"):
        CurseForgeClient("", fetch=fake_fetch).lookup(PackRef("test-pack"))
