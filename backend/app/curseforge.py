"""CurseForge API lookups (pack previews) and helpers shared with zip inspection."""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

API_BASE = "https://api.curseforge.com/v1"
MINECRAFT_GAME_ID = 432
MODPACK_CLASS_ID = 4471
LOADERS = ("Forge", "NeoForge", "Fabric", "Quilt")

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
_PAGE_URL = re.compile(
    r"^https?://(?:www\.)?curseforge\.com/minecraft/modpacks/([a-z0-9-]+)(?:/files/(\d+))?/?(?:[?#].*)?$"
)
_MC_VERSION = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


class CurseForgeError(Exception):
    pass


@dataclass(frozen=True)
class PackRef:
    slug: str
    file_id: int | None = None


@dataclass(frozen=True)
class PackInfo:
    project_id: int
    name: str
    slug: str
    summary: str
    logo_url: str | None
    page_url: str
    file_id: int
    file_name: str
    mc_version: str | None
    loader: str | None


def parse_pack_ref(text: str) -> PackRef:
    """Accept a modpack slug or a curseforge.com modpack (or modpack file) URL."""
    text = text.strip()
    if match := _PAGE_URL.match(text):
        return PackRef(match[1], int(match[2]) if match[2] else None)
    if _SLUG.match(text):
        return PackRef(text)
    raise CurseForgeError("Enter a CurseForge modpack URL or slug, e.g. all-the-mods-9")


def suggest_image_tag(mc_version: str | None) -> str:
    """Pick the itzg Java tag a Minecraft version needs; `latest` when unknown."""
    if not mc_version:
        return "latest"
    try:
        parts = [int(p) for p in mc_version.split(".")]
    except ValueError:
        return "latest"
    if parts[0] >= 26:  # 2026+ year-based versions (26.1, ...) need Java 25
        return "java25"
    minor = parts[1] if len(parts) > 1 else 0
    patch = parts[2] if len(parts) > 2 else 0
    if minor <= 16:
        return "java8"
    if minor < 20 or (minor == 20 and patch <= 4):
        return "java17"
    if minor <= 21:
        return "java21"
    return "latest"


def split_game_versions(game_versions: list[str]) -> tuple[str | None, str | None]:
    """CurseForge mixes MC versions and loader names in one list; pull out one of each."""
    mc = next((v for v in game_versions if _MC_VERSION.match(v)), None)
    loader = next((v for v in game_versions if v in LOADERS), None)
    return mc, loader


Fetch = Callable[[str, dict[str, str]], dict]


def _urllib_fetch(url: str, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise CurseForgeError("CurseForge rejected the API key (check CF_API_KEY)") from e
        if e.code == 404:
            raise CurseForgeError("Not found on CurseForge") from e
        raise CurseForgeError(f"CurseForge API error {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise CurseForgeError(f"Could not reach CurseForge: {e}") from e


class CurseForgeClient:
    def __init__(self, api_key: str, fetch: Fetch = _urllib_fetch) -> None:
        self.api_key = api_key
        self._fetch = fetch

    def _get(self, path: str, **params: object) -> dict:
        if not self.api_key:
            raise CurseForgeError("CF_API_KEY is not set in .env")
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        headers = {"x-api-key": self.api_key, "Accept": "application/json"}
        return self._fetch(f"{API_BASE}{path}{query}", headers)["data"]

    def lookup(self, ref: PackRef) -> PackInfo:
        mods = self._get(
            "/mods/search", gameId=MINECRAFT_GAME_ID, classId=MODPACK_CLASS_ID, slug=ref.slug
        )
        mod = next((m for m in mods if m["slug"] == ref.slug), None)
        if mod is None:
            raise CurseForgeError(f"No CurseForge modpack with slug '{ref.slug}'")

        file_id = ref.file_id or mod["mainFileId"]
        file = next((f for f in mod.get("latestFiles", []) if f["id"] == file_id), None)
        if file is None:
            file = self._get(f"/mods/{mod['id']}/files/{file_id}")
        if file.get("isServerPack"):
            # AUTO_CURSEFORGE needs the client file (it has the manifest).
            raise CurseForgeError("That file is a server pack; use the pack page or a client file")
        mc_version, loader = split_game_versions(file.get("gameVersions", []))
        return PackInfo(
            project_id=mod["id"],
            name=mod["name"],
            slug=mod["slug"],
            summary=mod.get("summary", ""),
            logo_url=(mod.get("logo") or {}).get("thumbnailUrl"),
            page_url=(mod.get("links") or {}).get("websiteUrl")
            or f"https://www.curseforge.com/minecraft/modpacks/{mod['slug']}",
            file_id=file_id,
            file_name=file.get("displayName") or file.get("fileName", ""),
            mc_version=mc_version,
            loader=loader,
        )
