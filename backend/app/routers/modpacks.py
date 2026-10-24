from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.curseforge import CurseForgeClient, CurseForgeError, parse_pack_ref, suggest_image_tag
from app.deps import AdminUser, AppSettings
from app.modpack import InvalidModpack, inspect_zip
from app.schemas import LookupIn, PackPreview
from app.uploads import UploadStore, UploadTooLarge

router = APIRouter(prefix="/api/modpacks", tags=["modpacks"])


def get_curseforge(request: Request) -> CurseForgeClient:
    return request.app.state.curseforge


def get_uploads(request: Request) -> UploadStore:
    return request.app.state.uploads


CurseForge = Annotated[CurseForgeClient, Depends(get_curseforge)]
Uploads = Annotated[UploadStore, Depends(get_uploads)]


@router.post("/lookup", response_model=PackPreview)
def lookup(body: LookupIn, curseforge: CurseForge, _admin: AdminUser) -> PackPreview:
    try:
        info = curseforge.lookup(parse_pack_ref(body.ref))
    except CurseForgeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return PackPreview(
        name=info.name,
        mc_version=info.mc_version,
        loader=info.loader,
        suggested_image_tag=suggest_image_tag(info.mc_version),
        summary=info.summary,
        logo_url=info.logo_url,
        page_url=info.page_url,
        file_name=info.file_name,
    )


@router.post("/upload", response_model=PackPreview, status_code=status.HTTP_201_CREATED)
async def upload(
    request: Request,
    uploads: Uploads,
    settings: AppSettings,
    _admin: AdminUser,
    filename: Annotated[str, Query(max_length=200)] = "modpack.zip",
) -> PackPreview:
    """Raw zip in the request body (not multipart), streamed straight to disk."""
    max_bytes = settings.max_upload_mb * 2**20
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Max upload is {settings.max_upload_mb} MB"
        )
    try:
        upload_id = await uploads.save(request.stream(), filename, max_bytes)
    except UploadTooLarge as e:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(e)) from e

    try:
        info = inspect_zip(str(uploads.path(upload_id)))
    except InvalidModpack as e:
        uploads.discard(upload_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    return PackPreview(
        name=info.name or uploads.original_name(upload_id).removesuffix(".zip"),
        mc_version=info.mc_version,
        loader=info.loader,
        suggested_image_tag=suggest_image_tag(info.mc_version),
        upload_id=upload_id,
        kind=info.kind.value,
    )
