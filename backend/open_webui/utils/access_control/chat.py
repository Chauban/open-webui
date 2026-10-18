"""对话请求里用户能自己改的两样：模型参数与系统提示。

聊天控制面板和用户设置让用户覆盖模型参数、加自己的系统提示；chat.controls / chat.params /
chat.system_prompt 三个权限原先只是把面板藏起来，请求照样带着这些值生效。这里在服务端按同一组
权限把用户不能设的部分去掉，对话请求和保存的用户设置都照此执行。
"""

from dataclasses import dataclass

from fastapi import HTTPException, status
from open_webui.models.config import Config
from open_webui.utils.access_control import has_permission

# OpenAI 的 developer 消息与 system 一样充当系统提示。
SYSTEM_PROMPT_ROLES = frozenset({'system', 'developer'})

# 放在 params 里、却不是模型参数：输入框旁的工具审批开关，不归 chat.params 管。
NON_MODEL_PARAM_KEYS = frozenset({'tool_approval_mode'})

# 对话流水线自己读取的顶层字段。顶层其余字段会原样转给模型服务商（temperature、
# reasoning_effort、thinking……），不能设参数的用户只保留这些。
CHAT_PIPELINE_KEYS = frozenset(
    {
        'model',
        'messages',
        'stream',
        'stream_options',
        'params',
        'files',
        'tools',
        'tool_ids',
        'tool_servers',
        'skill_ids',
        'filter_ids',
        'terminal_id',
        'features',
        'variables',
        'chat_variables',
        'model_item',
        'session_id',
        'chat_id',
        'folder_id',
        'id',
        'message_ids',
        'parent_id',
        'parent_message',
        'user_message',
        'new_chat',
        'regeneration_prompt',
        'assistant_message_id',
        'previous_response_id',
        'background_tasks',
        'automation_id',
    }
)


@dataclass(frozen=True)
class ChatOverrides:
    params: bool
    system_prompt: bool


ALL_CHAT_OVERRIDES = ChatOverrides(params=True, system_prompt=True)
NO_CHAT_OVERRIDES = ChatOverrides(params=False, system_prompt=False)


async def get_chat_overrides(user) -> ChatOverrides:
    """与前端显示面板的条件一致：两样都在控制面板里，先要有 chat.controls。"""
    if user.role == 'admin':
        return ALL_CHAT_OVERRIDES

    default_permissions = await Config.get('user.permissions')
    if not await has_permission(user.id, 'chat.controls', default_permissions):
        return NO_CHAT_OVERRIDES
    return ChatOverrides(
        params=await has_permission(user.id, 'chat.params', default_permissions),
        system_prompt=await has_permission(user.id, 'chat.system_prompt', default_permissions),
    )


async def can_set_folder_system_prompt(user) -> bool:
    """项目文件夹的系统提示只看 chat.system_prompt，与文件夹编辑弹窗一致。"""
    return user.role == 'admin' or await has_permission(
        user.id, 'chat.system_prompt', await Config.get('user.permissions')
    )


async def ensure_raw_passthrough_allowed(user) -> None:
    """原样转发给服务商的接口没法逐项去掉参数与提示,两样都能设的用户才可用。"""
    if await get_chat_overrides(user) != ALL_CHAT_OVERRIDES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Raw provider passthrough requires permission to set model parameters and the system prompt.',
        )


def _allowed_params(params: dict, overrides: ChatOverrides) -> dict:
    if overrides.params:
        allowed = dict(params)
    else:
        allowed = {key: value for key, value in params.items() if key in NON_MODEL_PARAM_KEYS | {'system'}}
    if not overrides.system_prompt:
        allowed.pop('system', None)
    return allowed


def strip_chat_request_overrides(form_data: dict, overrides: ChatOverrides) -> dict:
    """去掉对话请求里用户不能设的参数与系统提示，返回新的请求体。"""
    if overrides == ALL_CHAT_OVERRIDES:
        return form_data

    if overrides.params:
        stripped = dict(form_data)
    else:
        stripped = {key: value for key, value in form_data.items() if key in CHAT_PIPELINE_KEYS}
    stripped['params'] = _allowed_params(form_data.get('params') or {}, overrides)
    if not overrides.system_prompt and 'messages' in stripped:
        stripped['messages'] = [
            message for message in stripped['messages'] or [] if message.get('role') not in SYSTEM_PROMPT_ROLES
        ]
    return stripped


def strip_settings_overrides(ui_settings: dict, overrides: ChatOverrides) -> dict:
    """保存用户设置前去掉不能设的默认参数与默认系统提示，返回新的界面设置。"""
    if overrides == ALL_CHAT_OVERRIDES:
        return ui_settings

    stripped = dict(ui_settings)
    if not overrides.system_prompt:
        stripped.pop('system', None)
    if isinstance(stripped.get('params'), dict):
        stripped['params'] = _allowed_params(stripped['params'], overrides)
    return stripped
