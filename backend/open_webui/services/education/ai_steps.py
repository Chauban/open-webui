"""教学模块的每一处模型调用都登记为一个「AI 步骤」，用哪个模型、思考多少都由步骤决定。

管理员「写作辅导」里的 AI 步骤设置表、教师作业页的 AI 设置卡都按这里的登记生成，说明不会和
实际行为脱节。除辅导对话走聊天流水线外，每处调用都先经 resolve_step_model 解析模型、再经
call_step_model 发出并写明步骤；测试逐一核对教学代码里的模型调用，新加一处调用就得先在这里登记。

只有辅导对话的思考档位可以交给教师（及学生）；通读与补看、读者试读、图片识别、班级论证归纳
始终按管理员的设定，各班结果才可比——试跑里关掉通读的思考，漏判误判明显增多。
辅导对话的模型始终是学生在写作区选的：学生能选哪些由模型访问控制决定，不另设固定模型。
"""

import logging
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from open_webui.models.config import Config
from open_webui.models.education import (
    AssignmentModelParams,
    ThinkingControl,
    ThinkingSetting,
)
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.models import get_all_models
from open_webui.utils.retry import RETRY_TRANSIENT_FLAG
from open_webui.utils.thinking import THINKING_LEVEL_PARAM

log = logging.getLogger(__name__)

StepKey = Literal["coaching_chat", "first_read", "reader_check", "image_parsing", "class_insight"]
PlatformStepKey = Literal["first_read", "reader_check", "image_parsing", "class_insight"]
# 管理员没给这一步指定模型时用谁的：学生在写作区选的 / 教师触发时选的 / 没有可回落的（必须指定）。
ModelSource = Literal["student_chat_model", "teacher_chat_model", "admin_model"]


class AiStep(BaseModel):
    key: StepKey
    model_source: ModelSource
    # 管理员能否给这一步指定固定模型；辅导对话不能（见模块说明）。
    model_configurable: bool
    teacher_controllable: bool


AI_STEPS: tuple[AiStep, ...] = (
    AiStep(
        key="coaching_chat",
        model_source="student_chat_model",
        model_configurable=False,
        teacher_controllable=True,
    ),
    # 修订初稿的第一次通读，以及暂缓项的补看：补看按通读的结论复核，两者必须同一个模型、同一种想法。
    AiStep(key="first_read", model_source="student_chat_model", model_configurable=True, teacher_controllable=False),
    AiStep(key="reader_check", model_source="student_chat_model", model_configurable=True, teacher_controllable=False),
    # 图片识别没有可回落的模型：没指定就不提供图片导入。
    AiStep(key="image_parsing", model_source="admin_model", model_configurable=True, teacher_controllable=False),
    AiStep(key="class_insight", model_source="teacher_chat_model", model_configurable=True, teacher_controllable=False),
)
AI_STEPS_BY_KEY = {step.key: step for step in AI_STEPS}


class CoachingChatPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: ThinkingControl
    default: ThinkingSetting


class PlatformStepPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 空：按登记的 model_source 用学生 / 教师选的模型；图片识别为空即不提供图片导入。
    model: Optional[str] = Field(default=None, min_length=1, max_length=256)
    thinking: ThinkingSetting


class EducationAiStepPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coaching_chat: CoachingChatPolicy
    first_read: PlatformStepPolicy
    reader_check: PlatformStepPolicy
    image_parsing: PlatformStepPolicy
    class_insight: PlatformStepPolicy


async def get_ai_step_policy() -> EducationAiStepPolicy:
    return EducationAiStepPolicy.model_validate(await Config.get("education.ai_steps"))


def thinking_params(setting: ThinkingSetting) -> dict:
    return {} if setting == "model_default" else {THINKING_LEVEL_PARAM: setting}


class StepModel(BaseModel):
    """一个平台步骤这次实际用的模型。fixed：管理员为这一步指定的，学生 / 教师未必有权在聊天里用它。"""

    model_id: str
    fixed: bool


async def available_models(request, user) -> dict:
    # 模型列表是进程内缓存，重启后要等有人请求过才会填上，与对话接口一样先补一次。
    if not request.app.state.MODELS:
        await get_all_models(request, user=user)
    return request.app.state.MODELS


async def resolve_step_model(
    request,
    user,
    step: PlatformStepKey,
    requested_model_id: Optional[str] = None,
    policy: Optional[EducationAiStepPolicy] = None,
) -> Optional[StepModel]:
    """这一步此刻用哪个模型；None 表示没有可用的。

    管理员指定的模型还在就用它（fixed）；指定的已被删掉时记一条告警，回落到学生 / 教师选的模型
    （管理员页同时标红提示）。图片识别没有回落，指定的不在了就是 None。
    """

    policy = policy or await get_ai_step_policy()
    configured = getattr(policy, step).model
    if configured:
        if configured in await available_models(request, user):
            return StepModel(model_id=configured, fixed=True)
        log.warning("AI step %s: configured model %s is not available", step, configured)
    if AI_STEPS_BY_KEY[step].model_source == "admin_model" or not requested_model_id:
        return None
    return StepModel(model_id=requested_model_id, fixed=False)


async def call_step_model(request, user, step: PlatformStepKey, model: StepModel, messages: list[dict]):
    """平台步骤的单次非流式模型调用：按该步骤的思考档位发出；管理员指定的模型跳过模型访问控制。"""

    policy = await get_ai_step_policy()
    payload = {
        "model": model.model_id,
        "messages": messages,
        "stream": False,
        **thinking_params(getattr(policy, step).thinking),
        # 服务商一时出错时由 OpenAI 兼容路由自动重发;图片识别逐页自己重发(draft_import),这里不叠加。
        "metadata": {RETRY_TRANSIENT_FLAG: step != "image_parsing"},
    }
    return await generate_chat_completion(request, form_data=payload, user=user, bypass_filter=model.fixed)


class StepModelNotAllowed(ValueError):
    pass


def ensure_step_models_valid(
    policy: EducationAiStepPolicy, previous: EducationAiStepPolicy, models: dict
) -> None:
    """保存设置时：新选的模型必须存在，图片识别的还得能看图。

    没改动的不再校验——已被删掉的模型照旧留着，由管理员页标红提示，不挡住保存别的设置。
    """

    for step in (step for step in AI_STEPS if step.model_configurable):
        model_id = getattr(policy, step.key).model
        if not model_id or model_id == getattr(previous, step.key).model:
            continue
        model = models.get(model_id)
        if model is None:
            raise StepModelNotAllowed(f"Model {model_id} is not available")
        capabilities = ((model.get("info") or {}).get("meta") or {}).get("capabilities") or {}
        if step.key == "image_parsing" and capabilities.get("vision") is False:
            raise StepModelNotAllowed(f"Model {model_id} cannot read images")


class ModelParamsNotAllowed(ValueError):
    pass


def ensure_model_params_allowed(params: AssignmentModelParams, policy: EducationAiStepPolicy) -> None:
    """教师只能设管理员下放了的部分：仅管理员时什么都不能设，交给学生开关要管理员允许。"""

    control = policy.coaching_chat.control
    if control == "admin" and params != AssignmentModelParams():
        raise ModelParamsNotAllowed("Thinking for the coaching chat is set by the administrator")
    if control == "teacher" and params.students_choose_thinking:
        raise ModelParamsNotAllowed("The administrator has not allowed students to switch thinking")


class CoachingThinking(BaseModel):
    """一次辅导对话实际用的思考档位，以及它从哪来。"""

    control: ThinkingControl
    level: ThinkingSetting
    # admin：管理员默认；teacher：本作业设的；student：学生这轮关掉了。
    source: Literal["admin", "teacher", "student"]
    students_choose: bool


def resolve_coaching_thinking(
    policy: EducationAiStepPolicy,
    params: AssignmentModelParams,
    student_choice: Optional[str] = None,
) -> CoachingThinking:
    """辅导对话的思考档位：按管理员此刻的下放方式解读作业设置。

    管理员事后收回下放时，作业里存的设置不再生效，直接回到管理员默认。学生只能在允许时
    把这一轮关掉（student_choice == "off"），其余值一律按作业设的档位。
    """

    control = policy.coaching_chat.control
    default = policy.coaching_chat.default
    if control == "admin":
        return CoachingThinking(control=control, level=default, source="admin", students_choose=False)

    level, source = (params.thinking, "teacher") if params.thinking else (default, "admin")
    students_choose = control == "student" and params.students_choose_thinking
    if students_choose and student_choice == "off":
        return CoachingThinking(control=control, level="off", source="student", students_choose=True)
    return CoachingThinking(control=control, level=level, source=source, students_choose=students_choose)


class StepView(BaseModel):
    """管理员表与教师卡的一行：步骤、模型从哪来、由谁定、当前生效的档位。

    model_id 是管理员为这一步指定的模型（没指定为空）；model_available 为假时它已被删掉，
    这一步回落到 model_source（图片识别则不可用）。
    """

    key: StepKey
    model_source: ModelSource
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    model_available: bool = True
    control: ThinkingControl
    thinking: ThinkingSetting


def describe_steps(
    policy: EducationAiStepPolicy, models: dict, coaching: Optional[CoachingThinking] = None
) -> list[StepView]:
    """按登记顺序列出各步骤；给出 coaching 时辅导对话那一行用作业的实际生效值。"""

    rows = []
    for step in AI_STEPS:
        if step.key == "coaching_chat":
            control = coaching.control if coaching else policy.coaching_chat.control
            thinking = coaching.level if coaching else policy.coaching_chat.default
            model_id = None
        else:
            step_policy = getattr(policy, step.key)
            control, thinking, model_id = "admin", step_policy.thinking, step_policy.model
        model = models.get(model_id) if model_id else None
        rows.append(
            StepView(
                key=step.key,
                model_source=step.model_source,
                model_id=model_id,
                model_name=(model or {}).get("name") or model_id,
                model_available=model_id is None or model is not None,
                control=control,
                thinking=thinking,
            )
        )
    return rows
