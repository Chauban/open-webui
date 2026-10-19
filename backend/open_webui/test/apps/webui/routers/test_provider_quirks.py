"""服务商注意事项:从发送时实际读的表生成,一条不漏;代码管不了的事实另列。"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[5]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from open_webui.utils.provider_quirks import provider_quirks, step_quirks
from open_webui.utils.retry import ONE_SHOT_RETRY
from open_webui.utils.thinking import FIXED_SAMPLING_PARAMS, ThinkingSupport, thinking_support


def _by_kind(quirks):
    return {quirk['kind']: quirk for quirk in quirks}


def test_kimi_connection_lists_every_fixed_value_and_model_limit():
    quirks = _by_kind(provider_quirks('kimi'))
    params = {rule['param']: rule for rule in quirks['fixed_sampling']['params']}
    assert set(params) == {rule.param for rule in FIXED_SAMPLING_PARAMS['kimi']}
    assert (params['temperature']['allowed'], params['temperature']['allowed_without_thinking']) == (1.0, 0.6)
    assert (params['n']['allowed'], params['top_p']['allowed'], params['presence_penalty']['allowed']) == (1, 0.95, 0)
    assert quirks['on_off_only']['models'] == ['kimi-k2.6']
    assert quirks['always_thinking']['models'] == ['kimi-k2.7-code']
    # K3 等其余型号分三档:中按 high、高按 max
    assert quirks['effort_mapping'] == {
        'kind': 'effort_mapping',
        'models': [],
        'mapping': {'medium': 'high', 'high': 'max'},
    }
    assert 'thinks_by_default' in quirks


def test_zhipu_connection_names_the_models_that_cannot_turn_thinking_off():
    quirks = _by_kind(provider_quirks('zhipu'))
    assert quirks['cannot_turn_off']['models'] == ['glm-5.3']
    assert quirks['always_thinking']['models'] == ['glm-4.7', 'glm-4.5v']
    # 其余型号只有开 / 关;GLM 不收 medium,能分档的型号按 high 发
    assert quirks['on_off_only']['models'] == ['*']
    assert quirks['effort_mapping'] == {
        'kind': 'effort_mapping',
        'models': ['glm-5.3', 'glm-5.2'],
        'mapping': {'medium': 'high', 'high': 'max'},
    }


def test_facts_the_code_cannot_enforce():
    assert 'peak_pricing' in _by_kind(provider_quirks('deepseek'))
    assert 'summary_billing' in _by_kind(provider_quirks('doubao'))
    assert 'json_mode' in _by_kind(provider_quirks('qwen'))
    # 豆包按档位原样发,不算映射;也不默认开着思考
    assert {'effort_mapping', 'thinks_by_default'}.isdisjoint(_by_kind(provider_quirks('doubao')))
    assert provider_quirks('openai') == []


def test_one_model_gets_only_its_own_limits():
    glm = [quirk['kind'] for quirk in provider_quirks('zhipu', thinking_support('zhipu', 'glm-5.3-flash'))]
    assert glm == ['cannot_turn_off', 'effort_mapping', 'thinks_by_default']
    old = [quirk['kind'] for quirk in provider_quirks('zhipu', thinking_support('zhipu', 'glm-4.7'))]
    assert old == ['always_thinking', 'thinks_by_default']
    assert [quirk['kind'] for quirk in provider_quirks('deepseek', ThinkingSupport())] == [
        'effort_mapping',
        'thinks_by_default',
        'peak_pricing',
    ]


def test_step_notes_follow_the_chosen_model_and_level():
    # 没指定模型、按模型默认:笼统说明这几家默认开着思考;通读另提醒可能超过读超时
    notes = _by_kind(step_quirks('first_read', 'model_default', None, None))
    assert notes['model_default_thinks']['formats'] == ['deepseek', 'kimi', 'zhipu']
    assert notes['slow_step']['seconds'] == ONE_SHOT_RETRY.timeout.sock_read == 90
    assert 'slow_step' in _by_kind(step_quirks('first_read', 'high', None, None))
    assert step_quirks('first_read', 'low', None, None) == []
    # 别的步骤不提读超时
    assert 'slow_step' not in _by_kind(step_quirks('reader_check', 'high', None, None))
    # 指定了模型:列这个模型的注意事项,「模型默认」由它自己的 thinks_by_default 说明
    chosen = _by_kind(step_quirks('reader_check', 'model_default', 'kimi', thinking_support('kimi', 'kimi-k2.6')))
    assert {'fixed_sampling', 'on_off_only', 'thinks_by_default'} <= set(chosen)
    assert 'model_default_thinks' not in chosen
