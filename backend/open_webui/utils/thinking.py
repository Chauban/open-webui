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


class ThinkingSupport(NamedTuple):
    """一个模型在思考上能做什么。

    can_turn_off 为假：始终思考，「关」退到最低档；graded 为假：只有开 / 关，low / medium / high 都只是开着。
    两样都没有的（始终思考、没有档位）没什么可调，各档都按模型默认，什么也不发。
    """

    can_turn_off: bool = True
    graded: bool = True


# 各格式里与默认（能关、能分档）不同的模型，按模型 id 前缀先匹配先用，空前缀兜住该格式其余型号。
# 发送时的翻译（apply_thinking_level）和界面（模型列表里每个模型带的 thinking_support）都读这张表。
MODEL_THINKING_SUPPORT: dict[str, tuple[tuple[str, ThinkingSupport], ...]] = {
    'kimi': (
        # 实测：收到 reasoning_effort 不报错，但看不出有没有生效（同档推理 token 41–92 之间波动），只当开 / 关。
        ('kimi-k2.6', ThinkingSupport(graded=False)),
        # 参考文档：始终思考、没有档位；不用传，显式传只能 {type: enabled, keep: all}，传 disabled 报错（现网没有，未实测）。
        ('kimi-k2.7-code', ThinkingSupport(can_turn_off=False, graded=False)),
    ),
    'zhipu': (
        # 实测：传 thinking.type=disabled 返回 400（code 1210）；reasoning_effort 收 low / high / max。
        ('glm-5.3', ThinkingSupport(can_turn_off=False)),
        ('glm-5.2', ThinkingSupport()),
        # 参考文档：始终思考，不收 reasoning_effort（现网没有，未实测）。
        ('glm-4.7', ThinkingSupport(can_turn_off=False, graded=False)),
        ('glm-4.5v', ThinkingSupport(can_turn_off=False, graded=False)),
        # 更早的型号不收 reasoning_effort，只认 thinking.type 开 / 关。
        ('', ThinkingSupport(graded=False)),
    ),
    # 只有 enable_thinking 一个开关。
    'chat_template': (('', ThinkingSupport(graded=False)),),
}


def thinking_support(thinking_format: str, model_id: Optional[str]) -> ThinkingSupport:
    model = (model_id or '').lower()
    for prefix, support in MODEL_THINKING_SUPPORT.get(thinking_format, ()):
        if model.startswith(prefix):
            return support
    return ThinkingSupport()


def effective_thinking_level(level: str, support: ThinkingSupport) -> str:
    """这个模型上实际生效的档位：关不掉的「关」退到最低档；始终思考又没有档位的一律按模型默认。"""
    if support.can_turn_off:
        return level
    if not support.graded:
        return 'model_default'
    return 'low' if level == 'off' else level


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


def apply_thinking_level(payload: dict, level: str, thinking_format: str, *, responses_api: bool = False) -> dict:
    """把档位写成该格式的请求字段，返回新的请求体。个别服务商的写法按 payload 里的模型 id 区分。"""
    if level not in THINKING_LEVELS:
        raise ValueError(f'Unknown thinking level: {level}')
    payload = dict(payload)
    support = thinking_support(thinking_format, payload.get('model'))
    # 关不掉思考的模型从不发会 400 的「关」：退到最低档，没有档位的什么也不发。
    level = effective_thinking_level(level, support)
    if level == 'model_default':
        return payload
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
        # K2.6 与 K3 都认 thinking.type=disabled。K3 按 reasoning_effort 分档，不发 thinking.type=enabled
        # （按文档 K3 不接受它）；K2.6 只有开 / 关，各档都发 thinking.type=enabled（实测 200）。
        if not enabled:
            payload['thinking'] = {'type': 'disabled'}
        elif support.graded:
            payload['reasoning_effort'] = _THREE_LEVEL_EFFORT[level]
        else:
            payload['thinking'] = {'type': 'enabled'}
    elif thinking_format == 'zhipu':
        payload['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
        if enabled and support.graded:
            payload['reasoning_effort'] = _THREE_LEVEL_EFFORT[level]
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
    """服务商固定死的采样参数:只接受一个值,传别的直接 400。

    allowed_without_thinking:关掉思考时只接受的值与开着时不同的写在这里。
    """

    param: str
    allowed: float
    allowed_without_thinking: Optional[float] = None


# 只收实测返回 400 的(2026-10-18、10-19,见 docs/reference/thinking-params-test-results.md)。
# 发送前按这张表去掉;管理员页的提示也读这张表(/openai/sampling-rules),两边不会说法不一。
FIXED_SAMPLING_PARAMS: dict[str, tuple[FixedSamplingParam, ...]] = {
    'kimi': (
        # K2.6、K3:开着思考「only 1 is allowed」,关掉思考「only 0.6 is allowed」
        FixedSamplingParam('temperature', 1.0, allowed_without_thinking=0.6),
        # 以下 K2.6、K3 都是「only <值> is allowed for this model」
        FixedSamplingParam('top_p', 0.95),
        FixedSamplingParam('n', 1),
        FixedSamplingParam('presence_penalty', 0),
        FixedSamplingParam('frequency_penalty', 0),
    ),
}


def fixed_sampling_params(thinking_format: str) -> list[FixedSamplingParam]:
    """该格式下固定死的采样参数(实测 K2.6、K3 一样,不分模型)。"""
    return list(FIXED_SAMPLING_PARAMS.get(thinking_format, ()))


def strip_fixed_sampling_params(payload: dict, thinking_format: str) -> tuple[dict, list[str]]:
    """去掉服务商固定死的采样参数,返回新的请求体和去掉的参数名。

    值固定,传了也改不了什么;而 temperature 能接受的值还随思考开关变,恰好等于某个值的也不发,由服务商取它自己的。
    """
    dropped = [rule.param for rule in fixed_sampling_params(thinking_format) if rule.param in payload]
    if not dropped:
        return payload, []
    return {key: value for key, value in payload.items() if key not in dropped}, dropped


def model_supports_thinking_control(model_info) -> bool:
    meta = getattr(model_info, 'meta', None)
    capabilities = getattr(meta, 'capabilities', None) or {}
    return bool(capabilities.get('reasoning'))
