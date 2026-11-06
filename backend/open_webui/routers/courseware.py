"""Instance-local, administrator-published courseware; every asset requires login."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from open_webui.utils.auth import get_verified_user

COURSEWARE_DIR = os.environ.get('COURSEWARE_DIR', '').strip()
router = APIRouter(dependencies=[Depends(get_verified_user)])


def is_enabled() -> bool:
    return bool(COURSEWARE_DIR) and (Path(COURSEWARE_DIR) / 'index.html').is_file()


@router.get('/')
async def get_courseware():
    if not is_enabled():
        raise HTTPException(status_code=404, detail='Courseware is not available')
    return {'entry': 'index.html'}


@router.get('/content/{filename}')
async def get_courseware_file(filename: str):
    if not is_enabled():
        raise HTTPException(status_code=404, detail='Courseware is not available')

    # This lesson is a flat directory: one HTML document and its MP4 videos.
    # Do not expose publishing logs, manifests, arbitrary files, or symlink targets.
    root = Path(COURSEWARE_DIR).resolve()
    path = (root / filename).resolve()
    if (
        '/' in filename
        or '\\' in filename
        or path.parent != root
        or not (filename == 'index.html' or path.suffix.lower() == '.mp4')
        or not path.is_file()
    ):
        raise HTTPException(status_code=404, detail='File not found')

    # FileResponse supports byte ranges, including seeking in videos. No public cache
    # may serve a previously authenticated response after the session has expired.
    headers = {
        'Cache-Control': 'private, no-store',
        'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "frame-ancestors 'self'",
    }
    return FileResponse(
        path,
        media_type='text/html' if filename == 'index.html' else 'video/mp4',
        headers=headers,
    )
