import asyncio
import base64
import uuid
import io
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Optional

from urllib.parse import quote
import requests
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from open_webui.config import (
    CACHE_DIR,
    IMAGE_AUTO_SIZE_MODELS_REGEX_PATTERN,
    IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN,
)
from open_webui.constants import ERROR_MESSAGES
from open_webui.retrieval.web.utils import validate_url
from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS

from open_webui.models.chats import Chats
from open_webui.routers.files import upload_file_handler, get_file_content_by_id
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_permission
from open_webui.utils.headers import include_user_info_headers
from open_webui.internal.db import get_session
from sqlalchemy.orm import Session
from pydantic import BaseModel

log = logging.getLogger(__name__)

IMAGE_CACHE_DIR = CACHE_DIR / "image" / "generations"
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()


def set_image_model(request: Request, model: str):
    log.info(f"Setting image model to {model}")
    request.app.state.config.IMAGE_GENERATION_MODEL = model
    return request.app.state.config.IMAGE_GENERATION_MODEL


def get_image_model(request):
    if request.app.state.config.IMAGE_GENERATION_ENGINE == "openai":
        return (
            request.app.state.config.IMAGE_GENERATION_MODEL
            if request.app.state.config.IMAGE_GENERATION_MODEL
            else "dall-e-2"
        )
    elif request.app.state.config.IMAGE_GENERATION_ENGINE == "gemini":
        return (
            request.app.state.config.IMAGE_GENERATION_MODEL
            if request.app.state.config.IMAGE_GENERATION_MODEL
            else "imagen-3.0-generate-002"
        )


class ImagesConfig(BaseModel):
    ENABLE_IMAGE_GENERATION: bool
    ENABLE_IMAGE_PROMPT_GENERATION: bool

    IMAGE_GENERATION_ENGINE: str
    IMAGE_GENERATION_MODEL: str
    IMAGE_SIZE: Optional[str]
    IMAGE_STEPS: Optional[int]

    IMAGES_OPENAI_API_BASE_URL: str
    IMAGES_OPENAI_API_KEY: str
    IMAGES_OPENAI_API_VERSION: str
    IMAGES_OPENAI_API_PARAMS: Optional[dict | str]

    IMAGES_GEMINI_API_BASE_URL: str
    IMAGES_GEMINI_API_KEY: str
    IMAGES_GEMINI_ENDPOINT_METHOD: str

    ENABLE_IMAGE_EDIT: bool
    IMAGE_EDIT_ENGINE: str
    IMAGE_EDIT_MODEL: str
    IMAGE_EDIT_SIZE: Optional[str]

    IMAGES_EDIT_OPENAI_API_BASE_URL: str
    IMAGES_EDIT_OPENAI_API_KEY: str
    IMAGES_EDIT_OPENAI_API_VERSION: str
    IMAGES_EDIT_GEMINI_API_BASE_URL: str
    IMAGES_EDIT_GEMINI_API_KEY: str


@router.get("/config", response_model=ImagesConfig)
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


@router.post("/config/update")
async def update_config(
    request: Request, form_data: ImagesConfig, user=Depends(get_admin_user)
):
    request.app.state.config.ENABLE_IMAGE_GENERATION = form_data.ENABLE_IMAGE_GENERATION

    # Create Image
    request.app.state.config.ENABLE_IMAGE_PROMPT_GENERATION = (
        form_data.ENABLE_IMAGE_PROMPT_GENERATION
    )

    request.app.state.config.IMAGE_GENERATION_ENGINE = form_data.IMAGE_GENERATION_ENGINE
    set_image_model(request, form_data.IMAGE_GENERATION_MODEL)
    if form_data.IMAGE_SIZE == "auto" and not re.match(
        IMAGE_AUTO_SIZE_MODELS_REGEX_PATTERN, form_data.IMAGE_GENERATION_MODEL
    ):
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.INCORRECT_FORMAT(
                f"  (auto is only allowed with models matching {IMAGE_AUTO_SIZE_MODELS_REGEX_PATTERN})."
            ),
        )

    pattern = r"^\d+x\d+$"
    if (
        form_data.IMAGE_SIZE == "auto"
        or form_data.IMAGE_SIZE == ""
        or re.match(pattern, form_data.IMAGE_SIZE)
    ):
        request.app.state.config.IMAGE_SIZE = form_data.IMAGE_SIZE
    else:
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.INCORRECT_FORMAT("  (e.g., 512x512)."),
        )

    if form_data.IMAGE_STEPS >= 0:
        request.app.state.config.IMAGE_STEPS = form_data.IMAGE_STEPS
    else:
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.INCORRECT_FORMAT("  (e.g., 50)."),
        )

    request.app.state.config.IMAGES_OPENAI_API_BASE_URL = (
        form_data.IMAGES_OPENAI_API_BASE_URL
    )
    request.app.state.config.IMAGES_OPENAI_API_KEY = form_data.IMAGES_OPENAI_API_KEY
    request.app.state.config.IMAGES_OPENAI_API_VERSION = (
        form_data.IMAGES_OPENAI_API_VERSION
    )
    request.app.state.config.IMAGES_OPENAI_API_PARAMS = (
        form_data.IMAGES_OPENAI_API_PARAMS
    )

    request.app.state.config.IMAGES_GEMINI_API_BASE_URL = (
        form_data.IMAGES_GEMINI_API_BASE_URL
    )
    request.app.state.config.IMAGES_GEMINI_API_KEY = form_data.IMAGES_GEMINI_API_KEY
    request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD = (
        form_data.IMAGES_GEMINI_ENDPOINT_METHOD
    )

    # Edit Image
    request.app.state.config.ENABLE_IMAGE_EDIT = form_data.ENABLE_IMAGE_EDIT
    request.app.state.config.IMAGE_EDIT_ENGINE = form_data.IMAGE_EDIT_ENGINE
    request.app.state.config.IMAGE_EDIT_MODEL = form_data.IMAGE_EDIT_MODEL
    request.app.state.config.IMAGE_EDIT_SIZE = form_data.IMAGE_EDIT_SIZE

    request.app.state.config.IMAGES_EDIT_OPENAI_API_BASE_URL = (
        form_data.IMAGES_EDIT_OPENAI_API_BASE_URL
    )
    request.app.state.config.IMAGES_EDIT_OPENAI_API_KEY = (
        form_data.IMAGES_EDIT_OPENAI_API_KEY
    )
    request.app.state.config.IMAGES_EDIT_OPENAI_API_VERSION = (
        form_data.IMAGES_EDIT_OPENAI_API_VERSION
    )

    request.app.state.config.IMAGES_EDIT_GEMINI_API_BASE_URL = (
        form_data.IMAGES_EDIT_GEMINI_API_BASE_URL
    )
    request.app.state.config.IMAGES_EDIT_GEMINI_API_KEY = (
        form_data.IMAGES_EDIT_GEMINI_API_KEY
    )

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


@router.get("/models")
def get_models(request: Request, user=Depends(get_verified_user)):
    try:
        if request.app.state.config.IMAGE_GENERATION_ENGINE == "openai":
            return [
                {"id": "dall-e-2", "name": "DALL·E 2"},
                {"id": "dall-e-3", "name": "DALL·E 3"},
                {"id": "gpt-image-1", "name": "GPT-IMAGE 1"},
                {"id": "gpt-image-1.5", "name": "GPT-IMAGE 1.5"},
            ]
        elif request.app.state.config.IMAGE_GENERATION_ENGINE == "gemini":
            return [
                {"id": "imagen-3.0-generate-002", "name": "imagen-3.0 generate-002"},
            ]
    except Exception as e:
        request.app.state.config.ENABLE_IMAGE_GENERATION = False
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))


class CreateImageForm(BaseModel):
    model: Optional[str] = None
    prompt: str
    size: Optional[str] = None
    n: int = 1
    steps: Optional[int] = None
    negative_prompt: Optional[str] = None


GenerateImageForm = CreateImageForm  # Alias for backward compatibility


def get_image_data(data: str, headers=None):
    try:
        if data.startswith("http://") or data.startswith("https://"):
            if headers:
                r = requests.get(data, headers=headers)
            else:
                r = requests.get(data)

            r.raise_for_status()
            if r.headers["content-type"].split("/")[0] == "image":
                mime_type = r.headers["content-type"]
                return r.content, mime_type
            else:
                log.error("Url does not point to an image.")
                return None
        else:
            if "," in data:
                header, encoded = data.split(",", 1)
                mime_type = header.split(";")[0].lstrip("data:")
                img_data = base64.b64decode(encoded)
            else:
                mime_type = "image/png"
                img_data = base64.b64decode(data)
            return img_data, mime_type
    except Exception as e:
        log.exception(f"Error loading image data: {e}")
        return None, None


def upload_image(request, image_data, content_type, metadata, user, db=None):
    image_format = mimetypes.guess_extension(content_type)
    file = UploadFile(
        file=io.BytesIO(image_data),
        filename=f"generated-image{image_format}",  # will be converted to a unique ID on upload_file
        headers={
            "content-type": content_type,
        },
    )
    file_item = upload_file_handler(
        request,
        file=file,
        metadata=metadata,
        process=False,
        user=user,
    )

    if file_item and file_item.id:
        # If chat_id and message_id are provided in metadata, link the file to the chat message
        chat_id = metadata.get("chat_id")
        message_id = metadata.get("message_id")

        if chat_id and message_id:
            Chats.insert_chat_files(
                chat_id=chat_id,
                message_id=message_id,
                file_ids=[file_item.id],
                user_id=user.id,
                db=db,
            )

    url = request.app.url_path_for("get_file_content_by_id", id=file_item.id)
    return file_item, url


@router.post("/generations")
async def generate_images(
    request: Request, form_data: CreateImageForm, user=Depends(get_verified_user)
):
    if not request.app.state.config.ENABLE_IMAGE_GENERATION:
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if user.role != "admin" and not has_permission(
        user.id, "features.image_generation", request.app.state.config.USER_PERMISSIONS
    ):
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    return await image_generations(request, form_data, user=user)


async def image_generations(
    request: Request,
    form_data: CreateImageForm,
    metadata: Optional[dict] = None,
    user=None,
):
    # if IMAGE_SIZE = 'auto', default WidthxHeight to the 512x512 default
    # This is only relevant when the user has set IMAGE_SIZE to 'auto' with an
    # image model other than gpt-image-1, which is warned about on settings save

    size = "512x512"
    if (
        request.app.state.config.IMAGE_SIZE
        and "x" in request.app.state.config.IMAGE_SIZE
    ):
        size = request.app.state.config.IMAGE_SIZE

    if form_data.size and "x" in form_data.size:
        size = form_data.size

    width, height = tuple(map(int, size.split("x")))

    metadata = metadata or {}

    model = get_image_model(request)

    r = None
    try:
        if request.app.state.config.IMAGE_GENERATION_ENGINE == "openai":

            headers = {
                "Authorization": f"Bearer {request.app.state.config.IMAGES_OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }

            if ENABLE_FORWARD_USER_INFO_HEADERS:
                headers = include_user_info_headers(headers, user)

            url = f"{request.app.state.config.IMAGES_OPENAI_API_BASE_URL}/images/generations"
            if request.app.state.config.IMAGES_OPENAI_API_VERSION:
                url = f"{url}?api-version={request.app.state.config.IMAGES_OPENAI_API_VERSION}"

            data = {
                "model": model,
                "prompt": form_data.prompt,
                "n": form_data.n,
                "size": (
                    form_data.size
                    if form_data.size
                    else request.app.state.config.IMAGE_SIZE
                ),
                **(
                    {}
                    if re.match(
                        IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN,
                        request.app.state.config.IMAGE_GENERATION_MODEL,
                    )
                    else {"response_format": "b64_json"}
                ),
                **(
                    {}
                    if not request.app.state.config.IMAGES_OPENAI_API_PARAMS
                    else request.app.state.config.IMAGES_OPENAI_API_PARAMS
                ),
            }

            # Use asyncio.to_thread for the requests.post call
            r = await asyncio.to_thread(
                requests.post,
                url=url,
                json=data,
                headers=headers,
            )

            r.raise_for_status()
            res = r.json()

            images = []

            for image in res["data"]:
                if image_url := image.get("url", None):
                    image_data, content_type = get_image_data(
                        image_url,
                        {k: v for k, v in headers.items() if k != "Content-Type"},
                    )
                else:
                    image_data, content_type = get_image_data(image["b64_json"])

                _, url = upload_image(
                    request, image_data, content_type, {**data, **metadata}, user
                )
                images.append({"url": url})
            return images

        elif request.app.state.config.IMAGE_GENERATION_ENGINE == "gemini":
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": request.app.state.config.IMAGES_GEMINI_API_KEY,
            }

            data = {}

            if (
                request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD == ""
                or request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD == "predict"
            ):
                model = f"{model}:predict"
                data = {
                    "instances": {"prompt": form_data.prompt},
                    "parameters": {
                        "sampleCount": form_data.n,
                        "outputOptions": {"mimeType": "image/png"},
                    },
                }

            elif (
                request.app.state.config.IMAGES_GEMINI_ENDPOINT_METHOD
                == "generateContent"
            ):
                model = f"{model}:generateContent"
                data = {"contents": [{"parts": [{"text": form_data.prompt}]}]}

            # Use asyncio.to_thread for the requests.post call
            r = await asyncio.to_thread(
                requests.post,
                url=f"{request.app.state.config.IMAGES_GEMINI_API_BASE_URL}/models/{model}",
                json=data,
                headers=headers,
            )

            r.raise_for_status()
            res = r.json()

            images = []

            if model.endswith(":predict"):
                for image in res["predictions"]:
                    image_data, content_type = get_image_data(
                        image["bytesBase64Encoded"]
                    )
                    _, url = upload_image(
                        request, image_data, content_type, {**data, **metadata}, user
                    )
                    images.append({"url": url})
            elif model.endswith(":generateContent"):
                for image in res["candidates"]:
                    for part in image["content"]["parts"]:
                        if part.get("inlineData", {}).get("data"):
                            image_data, content_type = get_image_data(
                                part["inlineData"]["data"]
                            )
                            _, url = upload_image(
                                request,
                                image_data,
                                content_type,
                                {**data, **metadata},
                                user,
                            )
                            images.append({"url": url})

            return images
    except Exception as e:
        error = e
        if r != None:
            data = r.json()
            if "error" in data:
                error = data["error"]["message"]
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(error))


class EditImageForm(BaseModel):
    image: str | list[str]  # base64-encoded image(s) or URL(s)
    prompt: str
    model: Optional[str] = None
    size: Optional[str] = None
    n: Optional[int] = None
    negative_prompt: Optional[str] = None
    background: Optional[str] = None


@router.post("/edit")
async def image_edits(
    request: Request,
    form_data: EditImageForm,
    metadata: Optional[dict] = None,
    user=Depends(get_verified_user),
):
    size = None
    width, height = None, None
    metadata = metadata or {}

    if (
        request.app.state.config.IMAGE_EDIT_SIZE
        and "x" in request.app.state.config.IMAGE_EDIT_SIZE
    ) or (form_data.size and "x" in form_data.size):
        size = (
            form_data.size
            if form_data.size
            else request.app.state.config.IMAGE_EDIT_SIZE
        )
        width, height = tuple(map(int, size.split("x")))

    model = (
        request.app.state.config.IMAGE_EDIT_MODEL
        if form_data.model is None
        else form_data.model
    )

    try:

        async def load_url_image(data):
            if data.startswith("data:"):
                return data

            if data.startswith("http://") or data.startswith("https://"):
                # Validate URL to prevent SSRF attacks against local/private networks
                validate_url(data)
                r = await asyncio.to_thread(requests.get, data)
                r.raise_for_status()

                image_data = base64.b64encode(r.content).decode("utf-8")
                return f"data:{r.headers['content-type']};base64,{image_data}"

            else:
                file_id = None
                if data.startswith("/api/v1/files"):
                    file_id = data.split("/api/v1/files/")[1].split("/content")[0]
                else:
                    file_id = data

                file_response = await get_file_content_by_id(file_id, user)
                if isinstance(file_response, FileResponse):
                    file_path = file_response.path

                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                        image_data = base64.b64encode(file_bytes).decode("utf-8")
                        mime_type, _ = mimetypes.guess_type(file_path)

                    return f"data:{mime_type};base64,{image_data}"
            return data

        # Load image(s) from URL(s) if necessary
        if isinstance(form_data.image, str):
            form_data.image = await load_url_image(form_data.image)
        elif isinstance(form_data.image, list):
            # Load all images in parallel for better performance
            form_data.image = list(
                await asyncio.gather(*[load_url_image(img) for img in form_data.image])
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))

    def get_image_file_item(base64_string, param_name="image"):
        data = base64_string
        header, encoded = data.split(",", 1)
        mime_type = header.split(";")[0].lstrip("data:")
        image_data = base64.b64decode(encoded)
        return (
            param_name,
            (
                f"{uuid.uuid4()}.png",
                io.BytesIO(image_data),
                mime_type if mime_type else "image/png",
            ),
        )

    r = None
    try:
        if request.app.state.config.IMAGE_EDIT_ENGINE == "openai":
            headers = {
                "Authorization": f"Bearer {request.app.state.config.IMAGES_EDIT_OPENAI_API_KEY}",
            }

            if ENABLE_FORWARD_USER_INFO_HEADERS:
                headers = include_user_info_headers(headers, user)

            data = {
                "model": model,
                "prompt": form_data.prompt,
                **({"n": form_data.n} if form_data.n else {}),
                **({"size": size} if size else {}),
                **(
                    {"background": form_data.background} if form_data.background else {}
                ),
                **(
                    {}
                    if re.match(
                        IMAGE_URL_RESPONSE_MODELS_REGEX_PATTERN,
                        request.app.state.config.IMAGE_EDIT_MODEL,
                    )
                    else {"response_format": "b64_json"}
                ),
            }

            files = []
            if isinstance(form_data.image, str):
                files = [get_image_file_item(form_data.image)]
            elif isinstance(form_data.image, list):
                for img in form_data.image:
                    files.append(get_image_file_item(img, "image[]"))

            url_search_params = ""
            if request.app.state.config.IMAGES_EDIT_OPENAI_API_VERSION:
                url_search_params += f"?api-version={request.app.state.config.IMAGES_EDIT_OPENAI_API_VERSION}"

            # Use asyncio.to_thread for the requests.post call
            r = await asyncio.to_thread(
                requests.post,
                url=f"{request.app.state.config.IMAGES_EDIT_OPENAI_API_BASE_URL}/images/edits{url_search_params}",
                headers=headers,
                files=files,
                data=data,
            )

            r.raise_for_status()
            res = r.json()

            images = []
            for image in res["data"]:
                if image_url := image.get("url", None):
                    image_data, content_type = get_image_data(
                        image_url,
                        {k: v for k, v in headers.items() if k != "Content-Type"},
                    )
                else:
                    image_data, content_type = get_image_data(image["b64_json"])

                _, url = upload_image(
                    request, image_data, content_type, {**data, **metadata}, user
                )
                images.append({"url": url})
            return images

        elif request.app.state.config.IMAGE_EDIT_ENGINE == "gemini":
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": request.app.state.config.IMAGES_EDIT_GEMINI_API_KEY,
            }

            model = f"{model}:generateContent"
            data = {"contents": [{"parts": [{"text": form_data.prompt}]}]}

            if isinstance(form_data.image, str):
                data["contents"][0]["parts"].append(
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": form_data.image.split(",", 1)[1],
                        }
                    }
                )
            elif isinstance(form_data.image, list):
                data["contents"][0]["parts"].extend(
                    [
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": image.split(",", 1)[1],
                            }
                        }
                        for image in form_data.image
                    ]
                )

            # Use asyncio.to_thread for the requests.post call
            r = await asyncio.to_thread(
                requests.post,
                url=f"{request.app.state.config.IMAGES_EDIT_GEMINI_API_BASE_URL}/models/{model}",
                json=data,
                headers=headers,
            )

            r.raise_for_status()
            res = r.json()

            images = []
            for image in res["candidates"]:
                for part in image["content"]["parts"]:
                    if part.get("inlineData", {}).get("data"):
                        image_data, content_type = get_image_data(
                            part["inlineData"]["data"]
                        )
                        _, url = upload_image(
                            request,
                            image_data,
                            content_type,
                            {**data, **metadata},
                            user,
                        )
                        images.append({"url": url})

            return images
    except Exception as e:
        error = e
        if r != None:
            data = r.text
            try:
                data = json.loads(data)
                if "error" in data:
                    error = data["error"]["message"]
            except Exception:
                error = data

        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(error))
