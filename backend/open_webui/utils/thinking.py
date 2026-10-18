"""统一的思考档位 thinking_level，发请求前按连接换成服务商自己的写法。

各家开关思考的字段互不相同（reasoning_effort、thinking.budget_tokens、enable_thinking……），
界面与教学配置只用一个档位：off / low / medium / high；不设就是模型默认。档位作为普通参数
随请求流到 OpenAI 兼容路由，在那里按连接的思考格式翻译后去掉，不会原样发给服务商。
只有在模型能力里勾了「思考控制」（capabilities.reasoning）的模型才翻译，其余直接丢弃。
"""

from typing import Literal, NamedTuple, Optional
from urllib.parse import urlparse

THINKING_LEVEL_PARAM = 'thinking_level'

ThinkingLevel = Literal['off', 'low', 'medium', 'high']
THINKING_LEVELS: tuple[str, ...] = ('off', 'low', 'medium', 'high')

ThinkingFormat = Literal[
    'openai', 'anthropic', 'deepseek', 'kimi', 'zhipu', 'doubao', 'qwen', 'chat_template', 'openrouter'
]
THINKING_FORMATS: tuple[str, ...] = (
    'openai',
    'anthropic',
    'deepseek',
    'kimi',
    'zhipu',
    'doubao',
    'qwen',
    'chat_template',
    'openrouter',
)

# 预算按 Anthropic 的最低 1024 起，逐档约 4 倍。
THINKING_BUDGET_TOKENS = {'low': 1024, 'medium': 4096, 'high': 16384}
# Anthropic 要求 max_tokens 大于思考预算，正文另留这么多。
ANTHROPIC_ANSWER_TOKENS = 8192

# 只有 low / high / max 三档的服务商（DeepSeek、Kimi K3、GLM-5.2+）：medium 落到 high，high 用满 max。
# 2026-10-18 实测见 docs/reference/thinking-params-test-results.md。
_THREE_LEVEL_EFFORT = {'low': 'low', 'medium': 'high', 'high': 'max'}

# 智谱：这些型号始终思考，传 thinking.type=disabled 会 400（code 1210）；关不掉时退到最低档。
_ZHIPU_ALWAYS_THINKING = ('glm-5.3', 'glm-4.7', 'glm-4.5v')
# 智谱：只有 GLM-5.2 及以上接受 reasoning_effort。
_ZHIPU_EFFORT_MODELS = ('glm-5.3', 'glm-5.2')

# 按主机名后缀认服务商（主机名等于它或以「.它」结尾）。
_FORMAT_BY_HOST = (
    ('anthropic.com', 'anthropic'),
    ('openrouter.ai', 'openrouter'),
    ('deepseek.com', 'deepseek'),
    ('moonshot.cn', 'kimi'),
    ('moonshot.ai', 'kimi'),
    ('bigmodel.cn', 'zhipu'),
    ('z.ai', 'zhipu'),
    ('volces.com', 'doubao'),
    ('dashscope.aliyuncs.com', 'qwen'),
    ('dashscope-intl.aliyuncs.com', 'qwen'),
    ('maas.aliyuncs.com', 'qwen'),
)


def detect_thinking_format(url: str, api_config: Optional[dict] = None) -> str:
    """连接上设了思考格式就用它；没设按地址认常见服务商，认不出按 OpenAI 的 reasoning_effort。"""
    configured = (api_config or {}).get('thinking_format')
    if configured in THINKING_FORMATS:
        return configured
    host = (urlparse(url or '').hostname or '').lower()
    for marker, thinking_format in _FORMAT_BY_HOST:
        if host == marker or host.endswith(f'.{marker}'):
            return thinking_format
    return 'openai'


def _model_matches(payload: dict, prefixes: tuple[str, ...]) -> bool:
    model = str(payload.get('model') or '').lower()
    return any(model.startswith(prefix) for prefix in prefixes)


def apply_thinking_level(payload: dict, level: str, thinking_format: str, *, responses_api: bool = False) -> dict:
    """把档位写成该格式的请求字段，返回新的请求体。个别服务商的写法按 payload 里的模型 id 区分。"""
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
    elif thinking_format == 'deepseek':
        payload['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
        if enabled:
            payload['reasoning_effort'] = _THREE_LEVEL_EFFORT[level]
    elif thinking_format == 'kimi':
        # K2.6 与 K3 都认 thinking.type=disabled；K3 按 reasoning_effort 分档，K2.6 不分档、忽略这个字段。
        # 不发 thinking.type=enabled：思考本来就默认开着，K3 按文档不接受它。
        if enabled:
            payload['reasoning_effort'] = _THREE_LEVEL_EFFORT[level]
        else:
            payload['thinking'] = {'type': 'disabled'}
    elif thinking_format == 'zhipu':
        always_thinking = _model_matches(payload, _ZHIPU_ALWAYS_THINKING)
        takes_effort = _model_matches(payload, _ZHIPU_EFFORT_MODELS)
        payload['thinking'] = {'type': 'enabled' if enabled or always_thinking else 'disabled'}
        if takes_effort and (enabled or always_thinking):
            payload['reasoning_effort'] = _THREE_LEVEL_EFFORT['low' if not enabled else level]
    elif thinking_format == 'doubao':
        # 关思考时 reasoning_effort 只能是 minimal，干脆不发。
        payload['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
        if enabled:
            payload['reasoning_effort'] = level
    elif thinking_format == 'qwen':
        payload['enable_thinking'] = enabled
        # 高档不设预算，用模型自己的思维链上限。
        if enabled and level != 'high':
            payload['thinking_budget'] = THINKING_BUDGET_TOKENS[level]
    elif thinking_format == 'chat_template':
        payload['chat_template_kwargs'] = {**(payload.get('chat_template_kwargs') or {}), 'enable_thinking': enabled}
    elif thinking_format == 'openrouter':
        payload['reasoning'] = {'effort': level} if enabled else {'enabled': False}
    else:
        raise ValueError(f'Unknown thinking format: {thinking_format}')
    return payload


class FixedSamplingParam(NamedTuple):
    """服务商固定死的采样参数:传别的值直接 400。models 为空表示该格式下所有模型。"""

    param: str
    allowed: float
    models: tuple[str, ...] = ()


# 只收实测返回 400 的(2026-10-18,见 docs/reference/thinking-params-test-results.md)。
# 发送前按这张表去掉;管理员页的提示也读这张表(/openai/sampling-rules),两边不会说法不一。
FIXED_SAMPLING_PARAMS: dict[str, tuple[FixedSamplingParam, ...]] = {
    'kimi': (
        # K2.6 与 K3:「invalid temperature: only 1 is allowed for this model」
        FixedSamplingParam('temperature', 1.0),
        # K2.6:「invalid top_p: only 0.95 is allowed for this model」;K3 未实测,不动
        FixedSamplingParam('top_p', 0.95, ('kimi-k2.6',)),
    ),
}


def fixed_sampling_params(thinking_format: str, model_id: Optional[str] = None) -> list[FixedSamplingParam]:
    """该格式下固定死的采样参数;给出 model_id 时只留适用于这个模型的。"""
    rules = FIXED_SAMPLING_PARAMS.get(thinking_format, ())
    if model_id is None:
        return list(rules)
    model = model_id.lower()
    return [rule for rule in rules if not rule.models or any(model.startswith(prefix) for prefix in rule.models)]


def _is_allowed(value, allowed: float) -> bool:
    try:
        return float(value) == allowed
    except (TypeError, ValueError):
        return False


def strip_fixed_sampling_params(payload: dict, thinking_format: str) -> tuple[dict, list[str]]:
    """去掉服务商不接受的采样参数(值不等于它固定的那个),返回新的请求体和去掉的参数名。"""
    dropped = [
        rule.param
        for rule in fixed_sampling_params(thinking_format, str(payload.get('model') or ''))
        if rule.param in payload and not _is_allowed(payload[rule.param], rule.allowed)
    ]
    if not dropped:
        return payload, []
    return {key: value for key, value in payload.items() if key not in dropped}, dropped


def model_supports_thinking_control(model_info) -> bool:
    meta = getattr(model_info, 'meta', None)
    capabilities = getattr(meta, 'capabilities', None) or {}
    return bool(capabilities.get('reasoning'))
