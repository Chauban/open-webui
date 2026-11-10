"""Materials carry document facts; they do not add a second coaching prompt."""

import asyncio
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import pytest
from open_webui.services.education import materials, teaching_runtime
from open_webui.services.education.revision_reading import FORMAT, PURPOSES
from open_webui.services.education.writing_context import build_current_text_context

MATERIALS = [
    {
        'id': 'source-file',
        'filename': '课堂材料.docx',
        'blocks': [
            {
                'id': 'm1',
                'kind': 'image',
                'location': '正文第三段后',
                'text': '截图原文：材料甲',
                'extracted_text': '截图原文：材料甲',
                'status': 'read',
                'detail': '',
                'image': True,
            }
        ],
    }
]


@pytest.mark.parametrize('stage', ['first_read', 'coaching_chat', 'revision_review', 'whole_review'])
@pytest.mark.parametrize('prompt', ['只讨论推理关系。', '教师自行设置：请核对出处，再说明你的判断。'])
def test_materials_do_not_change_the_authored_system_prompt(stage, prompt):
    config = {'ai': {'prompt': prompt}, 'title': '课堂论证', 'description': '作业说明'}
    baseline = prompt + '\n\n【本次作业信息】\n\n标题：课堂论证\n作业说明'
    assert teaching_runtime.system_context(config) == baseline
    before = copy.deepcopy(config)
    dialogue = [{'role': 'user', 'content': '看看这段'}]
    with_materials = teaching_runtime.build_messages(config, stage, '当前稿', dialogue, MATERIALS, True)
    without_materials = teaching_runtime.build_messages(config, stage, '当前稿', dialogue, [], True)
    expected = baseline + ('\n' + PURPOSES[stage] + '\n' + FORMAT if stage == 'first_read' else '')
    assert with_materials[0] == without_materials[0] == {'role': 'system', 'content': expected}
    assert with_materials[-1]['content'].endswith(materials.material_context(MATERIALS))
    assert '截图原文：材料甲' in with_materials[-1]['content']
    assert materials.EVIDENCE_PROMPT not in json.dumps(with_materials, ensure_ascii=False)
    assert config == before


@pytest.mark.parametrize('supplied', [[], MATERIALS])
def test_actual_markdown_reading_adapter_adds_no_material_coaching_rules(monkeypatch, supplied):
    captured = []

    async def capture(request, user, config, context, messages):
        captured.append(copy.deepcopy(messages))
        return {'choices': [{'message': {'content': '教师要求下的反馈'}, 'finish_reason': 'stop'}]}

    monkeypatch.setattr(teaching_runtime, 'execute', capture)
    config = {'ai': {'prompt': '只用我的辅导方式。'}, 'title': '作业', 'description': '说明'}
    context = {'purpose': 'first_read', 'source_text': '当前稿', 'materials': supplied}
    asyncio.run(teaching_runtime.execute_first_read(None, None, config, context, []))
    expected = (
        '只用我的辅导方式。\n\n【本次作业信息】\n\n标题：作业\n说明\n'
        + PURPOSES['first_read']
        + '\n直接输出面向学生的反馈正文，可使用 Markdown 排版；无需为平台包裹 JSON 字段。'
    )
    assert captured[0][0]['content'] == expected
    assert captured[0][-1]['content'].endswith(materials.material_context(supplied))


def test_from_scratch_context_contains_only_existing_draft_wrapper_and_material_facts():
    session = SimpleNamespace(id='session', draft_baseline_text=None)
    expected = (
        '【学生当前正文】以下是右侧编辑器最近一次保存的全文，作为本轮稿件材料。'
        '下列改动说明来自已保存版本的比较；历史回复中的引文可能属于旧稿。\n<<<\n当前稿\n>>>'
    )
    for supplied in ([], MATERIALS):
        result = asyncio.run(build_current_text_context(session, captured_text='当前稿', captured_materials=supplied))
        assert result == expected + materials.material_context(supplied)


def test_material_payload_is_descriptive_data():
    content = materials.material_context(MATERIALS)
    prefix = '\n【本轮随附材料】\n'
    assert content.startswith(prefix)
    payload = json.loads(content.removeprefix(prefix))
    assert payload[0]['文件'] == '课堂材料.docx'
    assert payload[0]['内容'][0]['text'] == '截图原文：材料甲'
    assert payload[0]['内容'][0]['status'] == 'read'
    assert set(payload[0]['内容'][0]) == {'id', 'kind', 'location', 'text', 'status', 'detail', '文字性质'}
