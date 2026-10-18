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
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.thinking import THINKING_LEVEL_PARAM

# model_default：不发档位，按模型自己的参数（含管理员在模型上保存的思考档位）。
ThinkingSetting = Literal["model_default", "off", "low", "medium", "high"]
# 辅导对话的思考档位由谁定：管理员 / 教师按作业 / 教师按作业并可交给学生开关。
ThinkingControl = Literal["admin", "teacher", "student"]
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


class StepThinkingView(BaseModel):
    """管理员表与教师卡的一行：步骤、模型来源、由谁定、当前生效的档位。"""

    key: StepKey
    model_source: ModelSource
    control: ThinkingControl
    thinking: ThinkingSetting


def describe_steps(policy: EducationThinkingPolicy, coaching: Optional[tuple[ThinkingControl, ThinkingSetting]] = None):
    """按登记顺序列出各步骤；coaching 给出时用它替换辅导对话那一行（作业的实际生效值）。"""

    rows = []
    for step in AI_STEPS:
        if step.key == "coaching_chat":
            control, thinking = coaching or (policy.coaching_chat.control, policy.coaching_chat.default)
        else:
            control, thinking = "admin", getattr(policy, step.key)
        rows.append(
            StepThinkingView(key=step.key, model_source=step.model_source, control=control, thinking=thinking)
        )
    return rows
