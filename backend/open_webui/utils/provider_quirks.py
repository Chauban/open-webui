"""管理员页的「服务商注意事项」：每家服务商、每个模型不寻常的地方，一条不漏地写给管理员看。

能由代码执行的（固定死的采样参数、能不能关思考 / 分档、档位映射、读超时）都从发送时实际读的表生成，
说法不会和行为脱节；代码管不了、但会影响效果或账单的事实（计费、价格、兼容性）记在 PROVIDER_FACTS。
每条是一个结构化条目，界面按 kind 写成中文。
"""

from typing import Optional

from open_webui.utils.retry import ONE_SHOT_RETRY
from open_webui.utils.thinking import (
    EFFORT_BY_LEVEL,
    FIXED_SAMPLING_PARAMS,
    MODEL_THINKING_SUPPORT,
    THINKS_BY_DEFAULT,
    ThinkingSupport,
)

# 代码不执行、管理员要知道的事实，按格式各列几条。依据见 docs/reference/llm-thinking-params-pricing.md。
PROVIDER_FACTS: dict[str, tuple[str, ...]] = {
    # 北京时间工作日 9:00–12:00、14:00–18:00 是高峰价，空闲价的 2 倍，正好和上课、写作业的时间重叠。
    'deepseek': ('peak_pricing',),
    # seed-2.1 系列等默认只返回思考摘要，计费却按原始思考 token 算。
    'doubao': ('summary_billing',),
    # 开着思考时不支持 JSON mode / 结构化输出。
    'qwen': ('json_mode',),
}

# 「模型默认」或「高」时第一次通读可能超过一次性回复的读超时。
SLOW_STEPS = ('first_read',)


def _thinking_quirk(support: ThinkingSupport) -> Optional[str]:
    if not support.can_turn_off:
        return 'cannot_turn_off' if support.graded else 'always_thinking'
    return None if support.graded else 'on_off_only'


def _effort_mapping(thinking_format: str) -> dict:
    return {level: effort for level, effort in EFFORT_BY_LEVEL.get(thinking_format, {}).items() if effort != level}


def provider_quirks(thinking_format: str, support: Optional[ThinkingSupport] = None) -> list[dict]:
    """这个格式（给出 support 时只针对这一个模型）要提醒管理员的事。

    models：针对哪些模型（id 前缀）；空表示整家服务商，'*' 表示表里没单列的其余型号，'this' 表示当前这个模型。
    """
    quirks = []
    fixed = FIXED_SAMPLING_PARAMS.get(thinking_format)
    if fixed:
        quirks.append({'kind': 'fixed_sampling', 'models': [], 'params': [rule._asdict() for rule in fixed]})

    rows = MODEL_THINKING_SUPPORT.get(thinking_format, ())
    mapping = _effort_mapping(thinking_format)
    if support is None:
        by_kind: dict[str, list[str]] = {}
        for prefix, row in rows:
            kind = _thinking_quirk(row)
            if kind:
                by_kind.setdefault(kind, []).append(prefix or '*')
        for kind, models in by_kind.items():
            quirks.append({'kind': kind, 'models': [] if models == ['*'] and len(rows) == 1 else models})
        if mapping:
            # 有不分档的兜底型号时，映射只对单列出来、能分档的型号成立。
            graded = [prefix for prefix, row in rows if prefix and row.graded]
            fallback_flat = any(not prefix and not row.graded for prefix, row in rows)
            quirks.append({'kind': 'effort_mapping', 'models': graded if fallback_flat else [], 'mapping': mapping})
    else:
        kind = _thinking_quirk(support)
        if kind:
            quirks.append({'kind': kind, 'models': ['this']})
        if mapping and support.graded:
            quirks.append({'kind': 'effort_mapping', 'models': ['this'], 'mapping': mapping})

    if thinking_format in THINKS_BY_DEFAULT:
        quirks.append({'kind': 'thinks_by_default', 'models': []})
    quirks.extend({'kind': fact, 'models': []} for fact in PROVIDER_FACTS.get(thinking_format, ()))
    return quirks


def step_quirks(
    step: str, thinking: str, thinking_format: Optional[str], support: Optional[ThinkingSupport]
) -> list[dict]:
    """AI 步骤设置里一行要提醒的：所选模型的注意事项，加上与所选档位有关的几条。

    thinking_format 为空表示没指定模型（跟学生 / 老师选的），只能按可能接入的服务商笼统提醒。
    """
    quirks = provider_quirks(thinking_format, support) if thinking_format else []
    if thinking == 'model_default':
        if thinking_format is None:
            quirks.append({'kind': 'model_default_thinks', 'models': [], 'formats': list(THINKS_BY_DEFAULT)})
    if step in SLOW_STEPS and thinking in ('model_default', 'high'):
        quirks.append({'kind': 'slow_step', 'models': [], 'seconds': int(ONE_SHOT_RETRY.timeout.sock_read)})
    return quirks
