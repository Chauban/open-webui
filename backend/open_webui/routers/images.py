from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import mimetypes
import re
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from open_webui.config import (
    CACHE_DIR,
    IMAGE_AUTO_SIZE_MODELS_REGEX_PATTERN,
    IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN,
)
from open_webui.constants import ERROR_MESSAGES
from open_webui.env import AIOHTTP_CLIENT_ALLOW_REDIRECTS, AIOHTTP_CLIENT_SESSION_SSL, ENABLE_FORWARD_USER_INFO_HEADERS
from open_webui.internal.db import get_async_session
from open_webui.models.chats import Chats
from open_webui.retrieval.web.utils import validate_url
from open_webui.routers.files import get_file_content_by_id, upload_file_handler
from open_webui.utils.access_control import has_permission
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.headers import include_user_info_headers
from open_webui.utils.session_pool import get_session
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# An image can lie as easily as it can illuminate. Let what
# is generated here be honest about what it shows.
IMAGE_CACHE_DIR = CACHE_DIR / 'image' / 'generations'
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()


async def set_image_model(request: Request, model: str):
    log.info(f'Setting image model to {model}')
    request.app.state.config.IMAGE_GENERATION_MODEL = model
    return request.app.state.config.IMAGE_GENERATION_MODEL


async def get_image_model(request):
    if request.app.state.config.IMAGE_GENERATION_ENGINE == 'openai':
        return (
            request.app.state.config.IMAGE_GENERATION_MODEL
            if request.app.state.config.IMAGE_GENERATION_MODEL
            else 'dall-e-2'
        )
    elif request.app.state.config.IMAGE_GENERATION_ENGINE == 'gemini':
        return (
            request.app.state.config.IMAGE_GENERATION_MODEL
            if request.app.state.config.IMAGE_GENERATION_MODEL
            else 'imagen-3.0-generate-002'
        )


class ImagesConfig(BaseModel):
    ENABLE_IMAGE_GENERATION: bool
    ENABLE_IMAGE_PROMPT_GENERATION: bool

    IMAGE_GENERATION_ENGINE: str
    IMAGE_GENERATION_MODEL: str
    IMAGE_SIZE: str | None
    IMAGE_STEPS: int | None

    IMAGES_OPENAI_API_BASE_URL: str
    IMAGES_OPENAI_API_KEY: str
    IMAGES_OPENAI_API_VERSION: str
    IMAGES_OPENAI_API_PARAMS: dict | str | None

    IMAGES_GEMINI_API_BASE_URL: str
    IMAGES_GEMINI_API_KEY: str
    IMAGES_GEMINI_ENDPOINT_METHOD: str

    ENABLE_IMAGE_EDIT: bool
    IMAGE_EDIT_ENGINE: str
    IMAGE_EDIT_MODEL: str
    IMAGE_EDIT_SIZE: str | None

    IMAGES_EDIT_OPENAI_API_BASE_URL: str
    IMAGES_EDIT_OPENAI_API_KEY: str
    IMAGES_EDIT_OPENAI_API_VERSION: str
    IMAGES_EDIT_GEMINI_API_BASE_URL: str
    IMAGES_EDIT_GEMINI_API_KEY: str


@router.get('/config', response_model=ImagesConfig)
async def get_config(request: Request, user=Depends(get_admin_user)):
    return {
        "ENABLE_IMAGE_GENERATION": request.app.state.config.ENABLE_IMAGE_GENERATION,
        "ENABLE_IMAGE_PROMPT_GENERATION": request.app.state.config.ENABLE_IMAGE_PROMPT_GENERATION,
        "IMAGE_GENERATION_ENGINE": request.app.state.config.IMAGE_GENERATION_ENGINE,
        "IMAGE_GENERATION_MODEL": request.app.state.config.IMAGE_GENERATION_MODEL,
        "IMAGE_SIZE": request.app.state.config.IMAGE_SIZE,
        "IMAGE_STEPS": request.app.state.config.IMAGE_STEPS,
        "IMAGES_OPENAI_API_BASE_URL": request.app.state.config.IMAGES_OPENAI_API_BASE_URL,
        "IMAGES_OPENAI_API_KEY": request.app.state.config.IMAGES_OPENAI_API_KEY,
        "IMAGES_OPENAI_API_VERSION": request.app.state.config.IMAGES_OPENAI_API_VERSION,
        "IMAGES_OPENAI_API_PARAMS": request.app.state.config.IMAGES_OPENAI_API_PARAMS,
        "IMAGES_GEMINI_API_BASE_URL": request.app.state.config.IMAGES_GEMINI_API_BASE_URL,
        "IMAGES_GEMINI_API_KEY": request.app.state.config.IMAGES_GEMINI_API_KEY,
        "IMAGES_GEMINI_ENDPOINT_METHOD": request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD,
        "ENABLE_IMAGE_EDIT": request.app.state.config.ENABLE_IMAGE_EDIT,
        "IMAGE_EDIT_ENGINE": request.app.state.config.IMAGE_EDIT_ENGINE,
        "IMAGE_EDIT_MODEL": request.app.state.config.IMAGE_EDIT_MODEL,
        "IMAGE_EDIT_SIZE": request.app.state.config.IMAGE_EDIT_SIZE,
        "IMAGES_EDIT_OPENAI_API_BASE_URL": request.app.state.config.IMAGES_EDIT_OPENAI_API_BASE_URL,
        "IMAGES_EDIT_OPENAI_API_KEY": request.app.state.config.IMAGES_EDIT_OPENAI_API_KEY,
        "IMAGES_EDIT_OPENAI_API_VERSION": request.app.state.config.IMAGES_EDIT_OPENAI_API_VERSION,
        "IMAGES_EDIT_GEMINI_API_BASE_URL": request.app.state.config.IMAGES_EDIT_GEMINI_API_BASE_URL,
        "IMAGES_EDIT_GEMINI_API_KEY": request.app.state.config.IMAGES_EDIT_GEMINI_API_KEY,
    }


@router.post('/config/update')
async def update_config(request: Request, form_data: ImagesConfig, user=Depends(get_admin_user)):
    request.app.state.config.ENABLE_IMAGE_GENERATION = form_data.ENABLE_IMAGE_GENERATION

    # Create Image
    request.app.state.config.ENABLE_IMAGE_PROMPT_GENERATION = form_data.ENABLE_IMAGE_PROMPT_GENERATION

    request.app.state.config.IMAGE_GENERATION_ENGINE = form_data.IMAGE_GENERATION_ENGINE
    await set_image_model(request, form_data.IMAGE_GENERATION_MODEL)
    if form_data.IMAGE_SIZE == 'auto' and not re.match(
        IMAGE_AUTO_SIZE_MODELS_REGEX_PATTERN, form_data.IMAGE_GENERATION_MODEL
    ):
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.INCORRECT_FORMAT(
                f'  (auto is only allowed with models matching {IMAGE_AUTO_SIZE_MODELS_REGEX_PATTERN}).'
            ),
        )

    pattern = r'^\d+x\d+$'
    if form_data.IMAGE_SIZE == 'auto' or form_data.IMAGE_SIZE == '' or re.match(pattern, form_data.IMAGE_SIZE):
        request.app.state.config.IMAGE_SIZE = form_data.IMAGE_SIZE
    else:
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.INCORRECT_FORMAT('  (e.g., 512x512).'),
        )

    if form_data.IMAGE_STEPS >= 0:
        request.app.state.config.IMAGE_STEPS = form_data.IMAGE_STEPS
    else:
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.INCORRECT_FORMAT('  (e.g., 50).'),
        )

    request.app.state.config.IMAGES_OPENAI_API_BASE_URL = form_data.IMAGES_OPENAI_API_BASE_URL
    request.app.state.config.IMAGES_OPENAI_API_KEY = form_data.IMAGES_OPENAI_API_KEY
    request.app.state.config.IMAGES_OPENAI_API_VERSION = form_data.IMAGES_OPENAI_API_VERSION
    request.app.state.config.IMAGES_OPENAI_API_PARAMS = form_data.IMAGES_OPENAI_API_PARAMS

    request.app.state.config.IMAGES_GEMINI_API_BASE_URL = (
        form_data.IMAGES_GEMINI_API_BASE_URL
    )
    request.app.state.config.IMAGES_GEMINI_API_KEY = form_data.IMAGES_GEMINI_API_KEY
    request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD = form_data.IMAGES_GEMINI_ENDPOINT_METHOD

    # Edit Image
    request.app.state.config.ENABLE_IMAGE_EDIT = form_data.ENABLE_IMAGE_EDIT
    request.app.state.config.IMAGE_EDIT_ENGINE = form_data.IMAGE_EDIT_ENGINE
    request.app.state.config.IMAGE_EDIT_MODEL = form_data.IMAGE_EDIT_MODEL
    request.app.state.config.IMAGE_EDIT_SIZE = form_data.IMAGE_EDIT_SIZE

    request.app.state.config.IMAGES_EDIT_OPENAI_API_BASE_URL = form_data.IMAGES_EDIT_OPENAI_API_BASE_URL
    request.app.state.config.IMAGES_EDIT_OPENAI_API_KEY = form_data.IMAGES_EDIT_OPENAI_API_KEY
    request.app.state.config.IMAGES_EDIT_OPENAI_API_VERSION = form_data.IMAGES_EDIT_OPENAI_API_VERSION

    request.app.state.config.IMAGES_EDIT_GEMINI_API_BASE_URL = form_data.IMAGES_EDIT_GEMINI_API_BASE_URL
    request.app.state.config.IMAGES_EDIT_GEMINI_API_KEY = form_data.IMAGES_EDIT_GEMINI_API_KEY

    return {
        "ENABLE_IMAGE_GENERATION": request.app.state.config.ENABLE_IMAGE_GENERATION,
        "ENABLE_IMAGE_PROMPT_GENERATION": request.app.state.config.ENABLE_IMAGE_PROMPT_GENERATION,
        "IMAGE_GENERATION_ENGINE": request.app.state.config.IMAGE_GENERATION_ENGINE,
        "IMAGE_GENERATION_MODEL": request.app.state.config.IMAGE_GENERATION_MODEL,
        "IMAGE_SIZE": request.app.state.config.IMAGE_SIZE,
        "IMAGE_STEPS": request.app.state.config.IMAGE_STEPS,
        "IMAGES_OPENAI_API_BASE_URL": request.app.state.config.IMAGES_OPENAI_API_BASE_URL,
        "IMAGES_OPENAI_API_KEY": request.app.state.config.IMAGES_OPENAI_API_KEY,
        "IMAGES_OPENAI_API_VERSION": request.app.state.config.IMAGES_OPENAI_API_VERSION,
        "IMAGES_OPENAI_API_PARAMS": request.app.state.config.IMAGES_OPENAI_API_PARAMS,
        "IMAGES_GEMINI_API_BASE_URL": request.app.state.config.IMAGES_GEMINI_API_BASE_URL,
        "IMAGES_GEMINI_API_KEY": request.app.state.config.IMAGES_GEMINI_API_KEY,
        "IMAGES_GEMINI_ENDPOINT_METHOD": request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD,
        "ENABLE_IMAGE_EDIT": request.app.state.config.ENABLE_IMAGE_EDIT,
        "IMAGE_EDIT_ENGINE": request.app.state.config.IMAGE_EDIT_ENGINE,
        "IMAGE_EDIT_MODEL": request.app.state.config.IMAGE_EDIT_MODEL,
        "IMAGE_EDIT_SIZE": request.app.state.config.IMAGE_EDIT_SIZE,
        "IMAGES_EDIT_OPENAI_API_BASE_URL": request.app.state.config.IMAGES_EDIT_OPENAI_API_BASE_URL,
        "IMAGES_EDIT_OPENAI_API_KEY": request.app.state.config.IMAGES_EDIT_OPENAI_API_KEY,
        "IMAGES_EDIT_OPENAI_API_VERSION": request.app.state.config.IMAGES_EDIT_OPENAI_API_VERSION,
        "IMAGES_EDIT_GEMINI_API_BASE_URL": request.app.state.config.IMAGES_EDIT_GEMINI_API_BASE_URL,
        "IMAGES_EDIT_GEMINI_API_KEY": request.app.state.config.IMAGES_EDIT_GEMINI_API_KEY,
    }


@router.get("/config/url/verify")
async def verify_url(request: Request, user=Depends(get_admin_user)):
    return True


@router.get('/models')
async def get_models(request: Request, user=Depends(get_verified_user)):
    try:
        if request.app.state.config.IMAGE_GENERATION_ENGINE == 'openai':
            return [
                {'id': 'dall-e-2', 'name': 'DALL·E 2'},
                {'id': 'dall-e-3', 'name': 'DALL·E 3'},
                {'id': 'gpt-image-1', 'name': 'GPT-IMAGE 1'},
                {'id': 'gpt-image-1.5', 'name': 'GPT-IMAGE 1.5'},
            ]
        elif request.app.state.config.IMAGE_GENERATION_ENGINE == 'gemini':
            return [
                {'id': 'imagen-3.0-generate-002', 'name': 'imagen-3.0 generate-002'},
            ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))


class CreateImageForm(BaseModel):
    model: str | None = None
    prompt: str
    size: str | None = None
    n: int = 1
    steps: int | None = None
    negative_prompt: str | None = None


GenerateImageForm = CreateImageForm  # Alias for backward compatibility


def _is_same_origin(url: str, base_url: str) -> bool:
    """Compare scheme + hostname + port of two URLs.

    Pure string-prefix matching (``startswith``) is vulnerable to
    userinfo injection (``http://host:port@evil.com/``) and suffix
    confusion (``http://host:portevil.com/``).  Parsing both URLs
    and comparing the three origin components eliminates those
    attack vectors.
    """

    def _default_port(scheme: str) -> int:
        return 443 if scheme == 'https' else 80

    parsed = urlparse(url)
    trusted = urlparse(base_url)
    return (
        parsed.scheme == trusted.scheme
        and parsed.hostname == trusted.hostname
        and (parsed.port or _default_port(parsed.scheme)) == (trusted.port or _default_port(trusted.scheme))
    )


async def get_image_data(data: str, headers=None, trusted_base_url: str | None = None):
    try:
        if data.startswith('http://') or data.startswith('https://'):
            # Defense-in-depth: gate before fetch (mirrors load_url_image).
            # For URLs originating from an admin-configured backend (e.g.
            # ComfyUI on a private network), skip SSRF validation only when
            # the URL shares the exact same origin (scheme + host + port)
            # as the admin-configured base.  This avoids both the global
            # ENABLE_RAG_LOCAL_WEB_FETCH hammer and a blanket trust flag
            # that would follow arbitrary redirects.
            if trusted_base_url and _is_same_origin(data, trusted_base_url):
                log.debug(f'Skipping URL validation for trusted backend: {data}')
            else:
                validate_url(data)
            session = await get_session()
            async with session.get(
                data,
                headers=headers,
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as r:
                r.raise_for_status()
                content_type = r.headers.get('content-type', '')
                if content_type.split('/')[0] == 'image':
                    return await r.read(), content_type
                else:
                    log.error('Url does not point to an image.')
                    return None, None
        else:
            if ',' in data:
                header, encoded = data.split(',', 1)
                mime_type = header.split(';')[0].lstrip('data:')
                img_data = base64.b64decode(encoded)
            else:
                mime_type = 'image/png'
                img_data = base64.b64decode(data)
            return img_data, mime_type
    except Exception as e:
        log.exception(f'Error loading image data: {e}')
        return None, None


async def upload_image(request, image_data, content_type, metadata, user, db=None):
    if image_data is None or content_type is None:
        raise ValueError('Failed to retrieve image data from the generation backend')
    image_format = mimetypes.guess_extension(content_type)
    file = UploadFile(
        file=io.BytesIO(image_data),
        filename=f'generated-image{image_format}',  # will be converted to a unique ID on upload_file
        headers={
            'content-type': content_type,
        },
    )
    file_item = await upload_file_handler(
        request,
        file=file,
        metadata=metadata,
        process=False,
        user=user,
    )

    if file_item and file_item.id:
        # If chat_id and message_id are provided in metadata, link the file to the chat message
        chat_id = metadata.get('chat_id')
        message_id = metadata.get('message_id')

        if chat_id and message_id:
            await Chats.insert_chat_files(
                chat_id=chat_id,
                message_id=message_id,
                file_ids=[file_item.id],
                user_id=user.id,
                db=db,
            )

    url = request.app.url_path_for('get_file_content_by_id', id=file_item.id)
    return file_item, url


@router.post('/generations')
async def generate_images(request: Request, form_data: CreateImageForm, user=Depends(get_verified_user)):
    if not request.app.state.config.ENABLE_IMAGE_GENERATION:
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if user.role != 'admin' and not await has_permission(
        user.id, 'features.image_generation', request.app.state.config.USER_PERMISSIONS
    ):
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    return await image_generations(request, form_data, user=user)


async def image_generations(
    request: Request,
    form_data: CreateImageForm,
    metadata: dict | None = None,
    user=None,
):
    # if IMAGE_SIZE = 'auto', default WidthxHeight to the 512x512 default
    # This is only relevant when the user has set IMAGE_SIZE to 'auto' with an
    # image model other than gpt-image-1, which is warned about on settings save

    size = '512x512'
    if request.app.state.config.IMAGE_SIZE and 'x' in request.app.state.config.IMAGE_SIZE:
        size = request.app.state.config.IMAGE_SIZE

    if form_data.size and 'x' in form_data.size:
        size = form_data.size

    width, height = tuple(map(int, size.split('x')))

    metadata = metadata or {}

    model = await get_image_model(request)

    try:
        if request.app.state.config.IMAGE_GENERATION_ENGINE == 'openai':
            headers = {
                'Authorization': f'Bearer {request.app.state.config.IMAGES_OPENAI_API_KEY}',
                'Content-Type': 'application/json',
            }

            if ENABLE_FORWARD_USER_INFO_HEADERS:
                headers = include_user_info_headers(headers, user)

            url = f'{request.app.state.config.IMAGES_OPENAI_API_BASE_URL}/images/generations'
            if request.app.state.config.IMAGES_OPENAI_API_VERSION:
                url = f'{url}?api-version={request.app.state.config.IMAGES_OPENAI_API_VERSION}'

            data = {
                'model': model,
                'prompt': form_data.prompt,
                'n': form_data.n,
                **(
                    {'size': form_data.size or request.app.state.config.IMAGE_SIZE}
                    if (form_data.size or request.app.state.config.IMAGE_SIZE)
                    else {}
                ),
                **(
                    {}
                    if re.match(
                        IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN,
                        request.app.state.config.IMAGE_GENERATION_MODEL,
                    )
                    else {'response_format': 'b64_json'}
                ),
                **(
                    {}
                    if not request.app.state.config.IMAGES_OPENAI_API_PARAMS
                    else request.app.state.config.IMAGES_OPENAI_API_PARAMS
                ),
            }

            session = await get_session()
            async with session.post(
                url=url,
                json=data,
                headers=headers,
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as r:
                r.raise_for_status()
                res = await r.json(content_type=None)

            images = []

            for image in res['data']:
                if image_url := image.get('url', None):
                    image_data, content_type = await get_image_data(
                        image_url,
                        {k: v for k, v in headers.items() if k != 'Content-Type'},
                    )
                else:
                    image_data, content_type = await get_image_data(image['b64_json'])

                _, url = await upload_image(request, image_data, content_type, {**data, **metadata}, user)
                images.append({'url': url})
            return images

        elif request.app.state.config.IMAGE_GENERATION_ENGINE == 'gemini':
            headers = {
                'Content-Type': 'application/json',
                'x-goog-api-key': request.app.state.config.IMAGES_GEMINI_API_KEY,
            }

            data = {}

            if (
                request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD == ''
                or request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD == 'predict'
            ):
                model = f'{model}:predict'
                data = {
                    'instances': {'prompt': form_data.prompt},
                    'parameters': {
                        'sampleCount': form_data.n,
                        'outputOptions': {'mimeType': 'image/png'},
                    },
                }

            elif request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD == 'generateContent':
                model = f'{model}:generateContent'
                data = {'contents': [{'parts': [{'text': form_data.prompt}]}]}

            session = await get_session()
            async with session.post(
                url=f'{request.app.state.config.IMAGES_GEMINI_API_BASE_URL}/models/{model}',
                json=data,
                headers=headers,
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as r:
                r.raise_for_status()
                res = await r.json(content_type=None)

            images = []

            if model.endswith(':predict'):
                for image in res['predictions']:
                    image_data, content_type = await get_image_data(image['bytesBase64Encoded'])
                    _, url = await upload_image(request, image_data, content_type, {**data, **metadata}, user)
                    images.append({'url': url})
            elif model.endswith(':generateContent'):
                for image in res['candidates']:
                    for part in image['content']['parts']:
                        if part.get('inlineData', {}).get('data'):
                            image_data, content_type = await get_image_data(part['inlineData']['data'])
                            _, url = await upload_image(
                                request,
                                image_data,
                                content_type,
                                {**data, **metadata},
                                user,
                            )
                            images.append({'url': url})

            return images
    except Exception as e:
        error = e
        if isinstance(e, aiohttp.ClientResponseError):
            error = e.message
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(error))


class EditImageForm(BaseModel):
    image: str | list[str]  # base64-encoded image(s) or URL(s)
    prompt: str
    model: str | None = None
    size: str | None = None
    n: int | None = None
    negative_prompt: str | None = None
    background: str | None = None


@router.post('/edit')
async def image_edits(
    request: Request,
    form_data: EditImageForm,
    metadata: dict | None = None,
    user=Depends(get_verified_user),
):
    size = None
    width, height = None, None
    metadata = metadata or {}

    if (request.app.state.config.IMAGE_EDIT_SIZE and 'x' in request.app.state.config.IMAGE_EDIT_SIZE) or (
        form_data.size and 'x' in form_data.size
    ):
        size = form_data.size if form_data.size else request.app.state.config.IMAGE_EDIT_SIZE
        width, height = tuple(map(int, size.split('x')))

    model = request.app.state.config.IMAGE_EDIT_MODEL if form_data.model is None else form_data.model

    try:

        async def load_url_image(data):
            if data.startswith('data:'):
                return data

            if data.startswith('http://') or data.startswith('https://'):
                # Validate URL to prevent SSRF attacks against local/private networks.
                # allow_redirects=False prevents redirect-based SSRF: validate_url() is
                # called only on the originally-submitted URL; following 3xx redirects
                # without re-validation would let an attacker reach private IPs via a
                # public host that redirects internally (e.g. cloud-metadata exfil).
                validate_url(data)
                session = await get_session()
                async with session.get(
                    data, ssl=AIOHTTP_CLIENT_SESSION_SSL, allow_redirects=AIOHTTP_CLIENT_ALLOW_REDIRECTS
                ) as r:
                    r.raise_for_status()

                    image_data = base64.b64encode(await r.read()).decode('utf-8')
                    return f'data:{r.headers["content-type"]};base64,{image_data}'

            else:
                file_id = None
                if data.startswith('/api/v1/files'):
                    file_id = data.split('/api/v1/files/')[1].split('/content')[0]
                else:
                    file_id = data

                file_response = await get_file_content_by_id(file_id, user)
                if isinstance(file_response, FileResponse):
                    file_path = file_response.path

                    with open(file_path, 'rb') as f:
                        file_bytes = f.read()
                        image_data = base64.b64encode(file_bytes).decode('utf-8')
                        mime_type, _ = mimetypes.guess_type(file_path)

                    return f'data:{mime_type};base64,{image_data}'
            return data

        # Load image(s) from URL(s) if necessary
        if isinstance(form_data.image, str):
            form_data.image = await load_url_image(form_data.image)
        elif isinstance(form_data.image, list):
            # Load all images in parallel for better performance
            form_data.image = list(await asyncio.gather(*[load_url_image(img) for img in form_data.image]))
    except Exception as e:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))

    def get_image_file_item(base64_string, param_name='image'):
        data = base64_string
        header, encoded = data.split(',', 1)
        mime_type = header.split(';')[0].lstrip('data:')
        image_data = base64.b64decode(encoded)
        return (
            param_name,
            (
                f'{uuid.uuid4()}.png',
                io.BytesIO(image_data),
                mime_type if mime_type else 'image/png',
            ),
        )

    try:
        if request.app.state.config.IMAGE_EDIT_ENGINE == 'openai':
            headers = {
                'Authorization': f'Bearer {request.app.state.config.IMAGES_EDIT_OPENAI_API_KEY}',
            }

            if ENABLE_FORWARD_USER_INFO_HEADERS:
                headers = include_user_info_headers(headers, user)

            data = {
                'model': model,
                'prompt': form_data.prompt,
                **({'n': form_data.n} if form_data.n else {}),
                **({'size': size} if size else {}),
                **({'background': form_data.background} if form_data.background else {}),
                **(
                    {}
                    if re.match(
                        IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN,
                        request.app.state.config.IMAGE_EDIT_MODEL,
                    )
                    else {'response_format': 'b64_json'}
                ),
            }

            files = []
            if isinstance(form_data.image, str):
                files = [get_image_file_item(form_data.image)]
            elif isinstance(form_data.image, list):
                for img in form_data.image:
                    files.append(get_image_file_item(img, 'image[]'))

            url_search_params = ''
            if request.app.state.config.IMAGES_EDIT_OPENAI_API_VERSION:
                url_search_params += f'?api-version={request.app.state.config.IMAGES_EDIT_OPENAI_API_VERSION}'

            # Build multipart form data for aiohttp
            form = aiohttp.FormData()
            for key, value in data.items():
                if isinstance(value, dict):
                    form.add_field(key, json.dumps(value))
                else:
                    form.add_field(key, str(value))
            for param_name, (filename, file_obj, content_type_val) in files:
                form.add_field(
                    param_name,
                    file_obj,
                    filename=filename,
                    content_type=content_type_val,
                )

            session = await get_session()
            async with session.post(
                url=f'{request.app.state.config.IMAGES_EDIT_OPENAI_API_BASE_URL}/images/edits{url_search_params}',
                headers=headers,
                data=form,
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as r:
                r.raise_for_status()
                res = await r.json(content_type=None)

            images = []
            for image in res['data']:
                if image_url := image.get('url', None):
                    image_data, content_type = await get_image_data(
                        image_url,
                        {k: v for k, v in headers.items() if k != 'Content-Type'},
                    )
                else:
                    image_data, content_type = await get_image_data(image['b64_json'])

                _, url = await upload_image(request, image_data, content_type, {**data, **metadata}, user)
                images.append({'url': url})
            return images

        elif request.app.state.config.IMAGE_EDIT_ENGINE == 'gemini':
            headers = {
                'Content-Type': 'application/json',
                'x-goog-api-key': request.app.state.config.IMAGES_EDIT_GEMINI_API_KEY,
            }

            model = f'{model}:generateContent'
            data = {'contents': [{'parts': [{'text': form_data.prompt}]}]}

            if isinstance(form_data.image, str):
                data['contents'][0]['parts'].append(
                    {
                        'inline_data': {
                            'mime_type': 'image/png',
                            'data': form_data.image.split(',', 1)[1],
                        }
                    }
                )
            elif isinstance(form_data.image, list):
                data['contents'][0]['parts'].extend(
                    [
                        {
                            'inline_data': {
                                'mime_type': 'image/png',
                                'data': image.split(',', 1)[1],
                            }
                        }
                        for image in form_data.image
                    ]
                )

            session = await get_session()
            async with session.post(
                url=f'{request.app.state.config.IMAGES_EDIT_GEMINI_API_BASE_URL}/models/{model}',
                json=data,
                headers=headers,
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as r:
                r.raise_for_status()
                res = await r.json(content_type=None)

            images = []
            for image in res['candidates']:
                for part in image['content']['parts']:
                    if part.get('inlineData', {}).get('data'):
                        image_data, content_type = await get_image_data(part['inlineData']['data'])
                        _, url = await upload_image(
                            request,
                            image_data,
                            content_type,
                            {**data, **metadata},
                            user,
                        )
                        images.append({'url': url})

            return images
    except Exception as e:
        error = e
        if isinstance(e, aiohttp.ClientResponseError):
            error = e.message

        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(error))
