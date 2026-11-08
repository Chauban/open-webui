"""Administrator-authorized, single-hop transport fallback. Never carries credentials."""

import hashlib
import json
import logging
from urllib.parse import urlsplit

from fastapi import HTTPException
from open_webui.models.models import Models

log = logging.getLogger(__name__)


def connection_fingerprint(url, config):
    return hashlib.sha256(
        json.dumps(
            {
                'url': url,
                **{
                    k: config.get(k)
                    for k in ('prefix_id', 'api_type', 'api_version', 'provider', 'thinking_format', 'auth_type')
                },
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


async def provider_route(request, model_id):
    from open_webui.routers.openai import get_all_models, get_openai_connection

    models = request.app.state.OPENAI_MODELS
    if model_id not in models:
        await get_all_models(request)
        models = request.app.state.OPENAI_MODELS
    model = models.get(model_id)
    info = await Models.get_model_by_id(model_id)
    if (
        not model
        or model.get('urlIdx') is None
        or model.get('pipe')
        or model.get('pipeline')
        or model.get('direct')
        or (info and (not info.is_active or info.base_model_id))
    ):
        raise HTTPException(400, '备用模型必须是已启用的服务端直连模型。')
    url, _, config = await get_openai_connection(model['urlIdx'])
    if not config.get('enable', True):
        raise HTTPException(400, '备用模型连接已停用。')
    # These routes use OpenAI chat/responses adapters, not native Anthropic or pipelines.
    from open_webui.utils.anthropic import is_anthropic_url

    if is_anthropic_url(url):
        raise HTTPException(400, '备用线路暂不支持原生 Anthropic 接口。')
    route = {
        'model_id': model_id,
        'capabilities': {
            k: v for k, v in ((info.meta.capabilities if info else None) or {}).items() if k in ('reasoning', 'vision')
        },
        'connection_hash': connection_fingerprint(url, config),
    }
    return route, model, info, url


async def resolve_fallback(request, source_info):
    target = source_info.meta.fallback_model_id if source_info else None
    if not target:
        return None
    route, _, _, _ = await provider_route(request, target)
    return route


async def validate_model_fallback(request, user, form, previous=None, db=None):
    target = form.meta.fallback_model_id
    old = previous.meta.fallback_model_id if previous else None
    if user.role != 'admin':
        if target != old or (target and previous and form.base_model_id != previous.base_model_id):
            raise HTTPException(403, '只有管理员可以配置备用模型。')
        return
    if not target:
        return
    primary = form.base_model_id or form.id
    if target in (form.id, primary):
        raise HTTPException(400, '备用模型不能是当前模型。')
    _, _, _, primary_url = await provider_route(request, primary)
    _, _, _, backup_url = await provider_route(request, target)
    if primary_url.rstrip('/') == backup_url.rstrip('/'):
        raise HTTPException(400, '请选择另一家供应商的模型作为备用。')
    seen = {form.id, primary}
    cursor = target
    while cursor:
        if cursor in seen:
            raise HTTPException(400, '备用模型配置不能形成循环。')
        seen.add(cursor)
        item = await Models.get_model_by_id(cursor, db=db)
        cursor = item.meta.fallback_model_id if item else None


async def fallback_options(request):
    from open_webui.routers.openai import get_all_models, get_openai_connection

    await get_all_models(request)
    saved = {m.id: m for m in await Models.get_base_models()}
    options = []
    connections = {}
    for model_id, model in request.app.state.OPENAI_MODELS.items():
        info = saved.get(model_id)
        if model.get('urlIdx') is None or model.get('pipe') or model.get('pipeline') or model.get('direct'):
            continue
        if info and (not info.is_active or info.base_model_id):
            continue
        index = model['urlIdx']
        if index not in connections:
            connections[index] = await get_openai_connection(index)
        url, _, config = connections[index]
        from open_webui.utils.anthropic import is_anthropic_url

        if not config.get('enable', True) or is_anthropic_url(url):
            continue
        options.append(
            {
                'id': model_id,
                'name': info.name if info else model.get('name') or model_id,
                'provider': urlsplit(url).hostname or '',
                'connection': model['urlIdx'],
            }
        )
    return options


async def notify_retry(request, metadata, *, done=False):
    callback = getattr(request.state, 'reading_retry_callback', None)
    if callback and not done:
        await callback()
    if metadata and all(metadata.get(k) for k in ('user_id', 'chat_id', 'message_id')):
        from open_webui.socket.main import get_event_emitter

        try:
            emitter = await get_event_emitter(metadata)
            await emitter(
                {
                    'type': 'status',
                    'data': {
                        'action': 'model_fallback',
                        'description': '响应较慢，正在自动重试……',
                        'done': done,
                        'hidden': done,
                    },
                }
            )
        except Exception as error:
            log.warning('Could not publish fallback progress: %s', type(error).__name__)
