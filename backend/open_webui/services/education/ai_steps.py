"""教学模块的每一处模型调用都登记为一个「AI 步骤」，思考档位由步骤决定。

管理员「写作辅导」里的 AI 思考设置表、教师作业页的 AI 设置卡都按这里的登记生成，说明不会和
实际行为脱节。除辅导对话走聊天流水线外，每处调用都经 call_step_model 并写明步骤；测试逐一
核对教学代码里的模型调用，新加一处调用就得先在这里登记。

只有辅导对话的思考档位可以交给教师（及学生）；通读与补看、读者试读、图片识别、班级论证归纳
始终按管理员的设定，各班结果才可比——试跑里关掉通读的思考，漏判误判明显增多。
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from open_webui.models.config import Config
from open_webui.models.education import (
    AssignmentModelParams,
    ThinkingControl,
    ThinkingSetting,
)
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.thinking import THINKING_LEVEL_PARAM

StepKey = Literal["coaching_chat", "first_read", "reader_check", "image_parsing", "class_insight"]
# 步骤用哪个模型：学生在写作区选的对话模型 / 管理员指定的初稿图片识别模型 / 教师触发时选的模型。
ModelSource = Literal["student_chat_model", "draft_image_model", "teacher_chat_model"]


class AiStep(BaseModel):
    key: StepKey
    model_source: ModelSource
    teacher_controllable: bool


AI_STEPS: tuple[AiStep, ...] = (
    AiStep(key="coaching_chat", model_source="student_chat_model", teacher_controllable=True),
    # 修订初稿的第一次通读，以及暂缓项的补看：补看按通读的结论复核，两者必须同一种想法。
    AiStep(key="first_read", model_source="student_chat_model", teacher_controllable=False),
    AiStep(key="reader_check", model_source="student_chat_model", teacher_controllable=False),
    AiStep(key="image_parsing", model_source="draft_image_model", teacher_controllable=False),
    AiStep(key="class_insight", model_source="teacher_chat_model", teacher_controllable=False),
)


class CoachingChatThinkingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control: ThinkingControl
    default: ThinkingSetting


class EducationThinkingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coaching_chat: CoachingChatThinkingPolicy
    first_read: ThinkingSetting
    reader_check: ThinkingSetting
    image_parsing: ThinkingSetting
    class_insight: ThinkingSetting


async def get_thinking_policy() -> EducationThinkingPolicy:
    return EducationThinkingPolicy.model_validate(await Config.get("education.thinking"))


def thinking_params(setting: ThinkingSetting) -> dict:
    return {} if setting == "model_default" else {THINKING_LEVEL_PARAM: setting}


PlatformStepKey = Literal["first_read", "reader_check", "image_parsing", "class_insight"]


async def call_step_model(
    request,
    user,
    step: PlatformStepKey,
    model_id: str,
    messages: list[dict],
    *,
    bypass_filter: bool = False,
):
    """平台步骤的单次非流式模型调用，按管理员给该步骤设的思考档位发出。"""

    policy = await get_thinking_policy()
    payload = {
        "model": model_id,
        "messages": messages,
        "stream": False,
        **thinking_params(getattr(policy, step)),
    }
    return await generate_chat_completion(request, form_data=payload, user=user, bypass_filter=bypass_filter)


class ModelParamsNotAllowed(ValueError):
    pass


def ensure_model_params_allowed(params: AssignmentModelParams, policy: EducationThinkingPolicy) -> None:
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
    policy: EducationThinkingPolicy,
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


class StepThinkingView(BaseModel):
    """管理员表与教师卡的一行：步骤、模型来源、由谁定、当前生效的档位。"""

    key: StepKey
    model_source: ModelSource
    control: ThinkingControl
    thinking: ThinkingSetting


def describe_steps(policy: EducationThinkingPolicy, coaching: Optional[CoachingThinking] = None):
    """按登记顺序列出各步骤；给出 coaching 时辅导对话那一行用作业的实际生效值。"""

    rows = []
    for step in AI_STEPS:
        if step.key == "coaching_chat":
            control = coaching.control if coaching else policy.coaching_chat.control
            thinking = coaching.level if coaching else policy.coaching_chat.default
        else:
            control, thinking = "admin", getattr(policy, step.key)
        rows.append(
            StepThinkingView(key=step.key, model_source=step.model_source, control=control, thinking=thinking)
        )
    return rows
