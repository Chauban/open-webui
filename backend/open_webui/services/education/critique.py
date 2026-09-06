"""写作前的评析环节。

提交前质疑的对偶。质疑受时机所限——正文为空时没有可质疑的东西;但空白页阶段可以
评析别人的文章。两个环节因此在时间轴上互补,构成一个对称结构:

    写作前：评析靶文（建立判断标准） -> 写作 -> 提交前：接受质疑（把标准用于自己）

AI 在这里不与学生对话,只做一次匹配判定,所以它不是第三个 AI 角色。这也是教学环节
里唯一有标准答案、因而唯一可自动判定的一环——唯一不增加教师批改负担的一环。
"""

import json
import logging
from typing import Optional

from open_webui.models.config import Config
from open_webui.models.education import CritiqueFlaw, CritiqueMatch
from open_webui.services.education import challenge as challenge_module
from open_webui.services.education.challenge import ChallengeError

log = logging.getLogger(__name__)


async def get_critique_prompt() -> str:
    prompts = await Config.get("education.challenge_prompts") or {}
    return (prompts.get("critique") or "").strip()


def build_match_messages(
    system_prompt: str, target_text: str, flaws: list[CritiqueFlaw], items: list[str]
) -> list[dict]:
    lines = ["【靶文】", target_text, "", "【预设的问题】"]
    for flaw in flaws:
        lines.append(f"- {flaw.key}：{flaw.description}")
    lines.append("")
    lines.append("【学生指出的地方】")
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item}")
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(lines)},
    ]


def parse_matches(raw: str, flaws: list[CritiqueFlaw]) -> Optional[list[CritiqueMatch]]:
    """解析命中结果。

    解析不出来返回 None 而不是「全部未命中」:判不出来和「他一条都没找到」是两回事,
    后者会冤枉学生。返回 None 时上层记为待判定,不阻塞学生进写作区。
    """

    text = (raw or "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        log.warning("critique match output was not a JSON object")
        return None
    try:
        payload = json.loads(text[start:end])
    except json.JSONDecodeError:
        log.warning("critique match output was not valid JSON")
        return None

    hit_keys = {
        str(key).strip()
        for key in (payload.get("hits") or [])
        if str(key).strip()
    }
    return [
        CritiqueMatch(key=flaw.key, focus_key=flaw.focus_key, hit=flaw.key in hit_keys)
        for flaw in flaws
    ]


async def match_critique_items(
    request, user, assignment, items: list[str], model_id: str
) -> list[CritiqueMatch]:
    """学生写的条目对上了哪几处预设漏洞。

    只报命中与未命中,**不给分、不给等级**——一旦给分,学生就会去猜系统想要的答案,
    这个环节训练的东西当场变质。

    判定失败不抛错:靶文这道门拦在写作之前,模型抽风不该把学生挡在门外。
    """

    flaws = [CritiqueFlaw.model_validate(flaw) for flaw in (assignment.critique_flaws or [])]
    if not flaws:
        raise ChallengeError("Critique is not configured for this assignment")

    cleaned = [item.strip() for item in items if item.strip()]
    if not cleaned:
        raise ChallengeError("Write at least one thing you find unconvincing")

    system_prompt = await get_critique_prompt()
    if not system_prompt:
        raise ChallengeError("Critique prompt is not configured")

    try:
        raw = await challenge_module.generate_completion(
            request,
            user,
            model_id,
            build_match_messages(
                system_prompt, assignment.critique_text or "", flaws, cleaned
            ),
        )
    except ChallengeError:
        log.warning("critique match generation failed; recording as undetermined")
        return []

    matches = parse_matches(raw, flaws)
    # 判不出来就记为待判定（空列表），不等同于「一条都没找到」。
    return matches if matches is not None else []
