"""The assignment type registry. No database or instance configuration side effects."""

from typing import Literal

TaskMode = Literal['from_scratch', 'revise_draft', 'revise_argument']
TASK_TYPES = {
    'from_scratch': {'label': '从零写作', 'requires_baseline': False, 'revision_coaching': False, 'reader_check': True},
    'revise_draft': {
        'label': '修订初稿（文献综述）',
        'requires_baseline': True,
        'revision_coaching': True,
        'reader_check': False,
    },
    'revise_argument': {
        'label': '修订初稿（段落论证）',
        'requires_baseline': True,
        'revision_coaching': True,
        'reader_check': False,
    },
}
TASK_MODES = tuple(TASK_TYPES)


def is_revision(task_mode: str | None) -> bool:
    return bool(task_mode in TASK_TYPES and TASK_TYPES[task_mode]['revision_coaching'])
