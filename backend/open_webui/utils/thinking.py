"""统一的思考档位 thinking_level，发请求前按连接换成服务商自己的写法。

各家开关思考的字段互不相同（reasoning_effort、thinking.budget_tokens、enable_thinking……），
界面与教学配置只用一个档位：off / low / medium / high；不设就是模型默认。档位作为普通参数
随请求流到 OpenAI 兼容路由，在那里按连接的思考格式翻译后去掉，不会原样发给服务商。
只有在模型能力里勾了「思考控制」（capabilities.reasoning）的模型才翻译，其余直接丢弃。
"""

from typing import Literal, Optional
from urllib.parse import urlparse

THINKING_LEVEL_PARAM = 'thinking_level'

ThinkingLevel = Literal['off', 'low', 'medium', 'high']
THINKING_LEVELS: tuple[str, ...] = ('off', 'low', 'medium', 'high')

ThinkingFormat = Literal['openai', 'anthropic', 'qwen', 'chat_template', 'thinking_type', 'openrouter']
THINKING_FORMATS: tuple[str, ...] = ('openai', 'anthropic', 'qwen', 'chat_template', 'thinking_type', 'openrouter')

# 预算按 Anthropic 的最低 1024 起，逐档约 4 倍。
THINKING_BUDGET_TOKENS = {'low': 1024, 'medium': 4096, 'high': 16384}
# Anthropic 要求 max_tokens 大于思考预算，正文另留这么多。
ANTHROPIC_ANSWER_TOKENS = 8192

_FORMAT_BY_HOST = (
    ('anthropic.com', 'anthropic'),
    ('openrouter.ai', 'openrouter'),
    ('dashscope', 'qwen'),
    ('deepseek.com', 'thinking_type'),
    ('volces.com', 'thinking_type'),
    ('bigmodel.cn', 'thinking_type'),
)


def detect_thinking_format(url: str, api_config: Optional[dict] = None) -> str:
    """连接上设了思考格式就用它；没设按地址认常见服务商，认不出按 OpenAI 的 reasoning_effort。"""
    configured = (api_config or {}).get('thinking_format')
    if configured in THINKING_FORMATS:
        return configured
    host = urlparse(url or '').hostname or ''
    for marker, thinking_format in _FORMAT_BY_HOST:
        if marker in host:
            return thinking_format
    return 'openai'


def apply_thinking_level(payload: dict, level: str, thinking_format: str, *, responses_api: bool = False) -> dict:
    """把档位写成该格式的请求字段，返回新的请求体。"""
    if level not in THINKING_LEVELS:
        raise ValueError(f'Unknown thinking level: {level}')
    payload = dict(payload)
    enabled = level != 'off'

    if thinking_format == 'openai':
        # 推理模型关不掉思考，最低一档是 minimal。
        effort = level if enabled else 'minimal'
        if responses_api:
            payload['reasoning'] = {**(payload.get('reasoning') or {}), 'effort': effort}
        else:
            payload['reasoning_effort'] = effort
    elif thinking_format == 'anthropic':
        if enabled:
            budget = THINKING_BUDGET_TOKENS[level]
            payload['thinking'] = {'type': 'enabled', 'budget_tokens': budget}
            if (payload.get('max_tokens') or 0) <= budget:
                payload['max_tokens'] = budget + ANTHROPIC_ANSWER_TOKENS
            # 开着思考时 Anthropic 不接受改采样参数。
            for key in ('temperature', 'top_p', 'top_k'):
                payload.pop(key, None)
        else:
            payload['thinking'] = {'type': 'disabled'}
    elif thinking_format == 'qwen':
        payload['enable_thinking'] = enabled
        if enabled:
            payload['thinking_budget'] = THINKING_BUDGET_TOKENS[level]
    elif thinking_format == 'chat_template':
        payload['chat_template_kwargs'] = {**(payload.get('chat_template_kwargs') or {}), 'enable_thinking': enabled}
    elif thinking_format == 'thinking_type':
        payload['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
    elif thinking_format == 'openrouter':
        payload['reasoning'] = {'effort': level} if enabled else {'enabled': False}
    else:
        raise ValueError(f'Unknown thinking format: {thinking_format}')
    return payload


def model_supports_thinking_control(model_info) -> bool:
    meta = getattr(model_info, 'meta', None)
    capabilities = getattr(meta, 'capabilities', None) or {}
    return bool(capabilities.get('reasoning'))
