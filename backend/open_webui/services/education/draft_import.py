"""把学生拍的初稿照片转成纯文本:作业写作区「导入图片」。

修订初稿作业交初稿时、从零写作作业在编辑器里导入时共用这一条路。图片交给管理员在
「设置 → 写作辅导」里选定的识图模型逐张转录,只转录不改写;结果与导入 Word 文件一样
填回给学生核对,不落盘、不进文件库。模型是平台功能指定的,不看学生能不能在聊天里用它。
"""

import asyncio
import base64
import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

from open_webui.models.config import Config
from open_webui.services.education.writing_context import normalize_draft_paragraphs
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.models import get_all_models

log = logging.getLogger(__name__)

# 一次最多几张、单张和合计多大。照片转码后再发给模型,这里限的是上传的原文件。
DRAFT_IMAGE_MAX_COUNT = 8
DRAFT_IMAGE_MAX_BYTES = 10 * 1024 * 1024
DRAFT_IMAGE_TOTAL_MAX_BYTES = 30 * 1024 * 1024
# 发给模型前把长边缩到这个尺寸:一页手写稿 2048 像素足够认字,原图动辄四五千像素只多花钱。
_MAX_EDGE = 2048
# 再大的多半不是照片;Pillow 自己到 1.8 亿像素才报解压炸弹。
_MAX_PIXELS = 100_000_000
_ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
# 同时转录几张。逐张发而不是一次全塞进去:一张认不出不至于拖垮整份,也不会撞上单次输出上限。
_CONCURRENCY = 3
_NO_TEXT = "<<NO_TEXT>>"

TRANSCRIBE_PROMPT = f"""你是文字转录工具。图片是学生写作初稿的照片或扫描件，可能是手写，也可能是打印稿。请把图片里的正文逐字转录成纯文本。
- 只转录，不改写：不纠正错别字、语病和标点，不润色、不补全、不翻译，保持原文的语言。
- 按原文分段：每个自然段输出为一行，段与段之间空一行；同一段里因为纸张宽度换的行要接起来，不要断开。
- 标题、小标题各占一行。
- 忽略页码、页眉页脚、纸张格线和与正文无关的涂画；被划掉的字不要转录。
- 实在认不出的字用「□」代替，不要猜。
- 只输出转录出的正文，不加任何说明、引号或 Markdown 格式。图片里没有可读的正文时，只输出：{_NO_TEXT}"""


class DraftImageError(ValueError):
    """图片导入失败;消息是给学生看的 i18n 键。"""


class DraftImageModelError(DraftImageError):
    """识图模型这次没调通(而不是图片本身有问题),学生可以重试。"""


async def resolve_draft_image_model(request, user) -> str:
    """管理员选定的识图模型;没设、平台上已没有、或标明不能看图时报错。"""
    model_id = ((await Config.get("education.draft_image_model")) or "").strip()
    if not model_id:
        raise DraftImageError(
            "Image import is not set up. Ask your administrator to choose an image parsing model."
        )
    # 模型列表是进程内缓存,重启后要等有人请求过才会填上,与对话接口一样先补一次。
    if not request.app.state.MODELS:
        await get_all_models(request, user=user)
    model = request.app.state.MODELS.get(model_id)
    if model is None:
        raise DraftImageError(
            "The image parsing model is not available. Ask your administrator to check the setting."
        )
    capabilities = (model.get("info") or {}).get("meta", {}).get("capabilities") or {}
    if capabilities.get("vision") is False:
        raise DraftImageError(
            "The image parsing model cannot read images. Ask your administrator to choose another model."
        )
    return model_id


def prepare_draft_image(data: bytes) -> str:
    """校验图片并转成发给模型的 data URL:按 EXIF 摆正、透明底铺白、缩到长边 2048 的 JPEG。

    按内容判断格式,不看扩展名。手机竖拍的照片像素是横的,方向只记在 EXIF 里,
    不摆正的话模型看到的是躺倒的字。
    """
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in _ACCEPTED_FORMATS:
                raise DraftImageError("Only JPG, PNG and WebP images are supported")
            if source.width * source.height > _MAX_PIXELS:
                raise DraftImageError("This image is too large")
            # 只对 JPEG 生效:按目标尺寸降采样解码,大照片省内存。
            source.draft("RGB", (_MAX_EDGE, _MAX_EDGE))
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            ):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            image.thumbnail((_MAX_EDGE, _MAX_EDGE))
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=90)
    except DraftImageError:
        raise
    except Image.DecompressionBombError as error:
        raise DraftImageError("This image is too large") from error
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise DraftImageError("Could not read this image") from error
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


async def generate_transcription(request, user, model_id: str, messages: list[dict]) -> str:
    """单次非流式生成。图片导入唯一的模型调用出口,测试通过替换它来隔离模型。

    识图模型是管理员为这项平台功能指定的,学生在聊天里未必有权用它,所以跳过模型访问控制。
    """
    payload = {"model": model_id, "messages": messages, "stream": False}
    response = await generate_chat_completion(
        request, form_data=payload, user=user, bypass_filter=True
    )
    # 出错时 generate_chat_completion 返回 JSONResponse,流式模型返回 StreamingResponse。
    if not isinstance(response, dict):
        raise DraftImageModelError("Could not read the images. Please try again.")
    try:
        return response["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as error:
        log.error("draft image transcription returned an unexpected payload: %s", error)
        raise DraftImageModelError("Could not read the images. Please try again.") from error


def clean_transcription(raw: str) -> list[str]:
    """模型输出 → 段落列表。去掉偶尔包上的代码围栏;「没有正文」记为空。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text or text == _NO_TEXT:
        return []
    return normalize_draft_paragraphs(text.replace(_NO_TEXT, ""))


def build_transcription_messages(image_url: str) -> list[dict]:
    return [
        {"role": "system", "content": TRANSCRIBE_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请转录这张图片里的正文。"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]


async def transcribe_draft_images(request, user, model_id: str, image_urls: list[str]) -> str:
    """按上传顺序逐张转录,拼成一段一行的纯文本(与导入 Word 文件的结果同一形式)。

    任何一张失败整份作废:悄悄少一页比报错更糟,学生不一定发现。
    """
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def transcribe(image_url: str) -> list[str]:
        async with semaphore:
            raw = await generate_transcription(
                request, user, model_id, build_transcription_messages(image_url)
            )
            return clean_transcription(raw)

    try:
        pages = await asyncio.gather(*(transcribe(url) for url in image_urls))
    except DraftImageError:
        raise
    except Exception as error:
        log.exception("draft image transcription failed")
        raise DraftImageModelError("Could not read the images. Please try again.") from error
    paragraphs = [line for page in pages for line in page]
    if not paragraphs:
        raise DraftImageError("No text found in these images")
    return "\n".join(paragraphs)
