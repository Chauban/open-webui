"""提交前质疑环节的回合引擎。

这里的 AI 是「质疑读者」,与写作区左侧的辅导助手是两个相反的角色:辅导助手负责
帮学生写,质疑读者只负责问、绝不给可粘贴的文本。两者物理隔离,不共用对话。

回合数由本模块的代码控制,不由提示词控制。模型不会因为提示词里写了「只问三轮」
就真的停下,所以每一轮都是服务端显式发起的一次独立调用,到 planned_rounds 就转收尾。
"""

import difflib
import json
import logging
from typing import Optional

from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from open_webui.models.config import Config
from open_webui.models.education import (
    ChallengeClosing,
    ChallengeSessionModel,
    ChallengeTurnModel,
    Education,
    RubricCriterion,
    RubricSchema,
)
from open_webui.utils.chat import generate_chat_completion

log = logging.getLogger(__name__)

# 正文太短就没有可质疑的东西,空白页上来先被问三个问题只会让学生关掉页面。
CHALLENGE_MIN_DRAFT_CHARS = 100
# 传给模型的正文上限,超出部分截断,免得长文把上下文顶爆。
CHALLENGE_DRAFT_CHAR_LIMIT = 12000
# 收尾之后改动多少字才算「真的回去改了」。低于这个数基本是错别字和标点。
CHALLENGE_REVISION_MIN_CHARS = 20


class ChallengeError(Exception):
    """质疑流程的业务约束被违反,由路由层翻译成 4xx。"""


async def get_challenge_prompt(kind: str) -> str:
    """取质疑措辞。管理员把某段清空就返回空串,与辅导档位同一机制。"""

    prompts = await Config.get("education.challenge_prompts") or {}
    return (prompts.get(kind) or "").strip()


def resolve_focus_key(focus_keys: list[str], turn_no: int) -> str:
    """焦点按轮次轮转。只选了一个维度时三轮都打这一个,这是教师的选择,不做纠正。"""

    if not focus_keys:
        raise ChallengeError("Challenge focus keys are missing")
    return focus_keys[(turn_no - 1) % len(focus_keys)]


def find_criterion(assignment, focus_key: str) -> Optional[RubricCriterion]:
    rubric = RubricSchema.model_validate(assignment.rubric_schema)
    return next(
        (criterion for criterion in rubric.criteria if criterion.key == focus_key),
        None,
    )


def _truncate_draft(text: str) -> str:
    draft = (text or "").strip()
    if len(draft) <= CHALLENGE_DRAFT_CHAR_LIMIT:
        return draft
    return draft[:CHALLENGE_DRAFT_CHAR_LIMIT]


def _describe_focus(assignment, focus_key: str) -> str:
    criterion = find_criterion(assignment, focus_key)
    if criterion is None:
        return focus_key
    return f"{criterion.label}（该维度满分 {criterion.max_score} 分）"


def build_turn_messages(
    system_prompt: str,
    assignment,
    focus_key: str,
    draft_text: str,
    previous_turns: list[ChallengeTurnModel],
    turn_no: int,
    planned_rounds: int,
) -> list[dict]:
    lines = [
        f"【作业】{assignment.title}",
    ]
    description = (assignment.description or "").strip()
    if description:
        lines.append(f"【要求】{description}")
    lines.append(f"【本轮质疑聚焦的评分维度】{_describe_focus(assignment, focus_key)}")
    lines.append(f"【进度】这是第 {turn_no} 轮，共 {planned_rounds} 轮。")

    if previous_turns:
        history = []
        for turn in previous_turns:
            history.append(f"你的第 {turn.turn_no} 轮质疑：{turn.challenge_text}")
            response = (turn.response_text or "").strip()
            history.append(
                f"作者的回应：{response}" if response else "作者没有回应这一轮。"
            )
        lines.append("【此前的往来】\n" + "\n".join(history))
        lines.append(
            "请不要重复你已经问过的点。针对作者的回应，提出下一个仍然说服不了你的地方。"
        )

    lines.append(f"【作者的文章】\n{_truncate_draft(draft_text)}")

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(lines)},
    ]


def build_closing_messages(
    system_prompt: str, assignment, turns: list[ChallengeTurnModel]
) -> list[dict]:
    history = []
    for turn in turns:
        history.append(f"你的第 {turn.turn_no} 轮质疑：{turn.challenge_text}")
        response = (turn.response_text or "").strip()
        history.append(f"作者的回应：{response}" if response else "作者没有回应这一轮。")

    content = "\n\n".join(
        [
            f"【作业】{assignment.title}",
            "【往来记录】\n" + "\n".join(history),
        ]
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


async def generate_completion(request, user, model_id: str, messages: list[dict]) -> str:
    """单次非流式生成。

    这是本模块唯一的模型调用出口,测试通过替换它来隔离模型。质疑是核心教学交互,
    不走 task model 降级,直接用学生写作区当前选的模型;模型可见性与访问控制由
    generate_chat_completion 自己校验。
    """

    payload = {"model": model_id, "messages": messages, "stream": False}
    response = await generate_chat_completion(request, form_data=payload, user=user)

    if isinstance(response, JSONResponse):
        raise ChallengeError("Challenge generation failed")

    try:
        return (response["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as error:
        log.error("challenge generation returned an unexpected payload: %s", error)
        raise ChallengeError("Challenge generation failed") from error


def parse_closing(raw: str) -> ChallengeClosing:
    """把收尾输出解析成清单。

    解析不出来时返回空清单而不是抛错:收尾失败不该把学生卡在质疑里出不来,
    但也不能编造「你都答住了」这种结论。
    """

    text = (raw or "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        log.warning("challenge closing output had no JSON object")
        return ChallengeClosing()

    try:
        payload = json.loads(text[start:end])
    except json.JSONDecodeError:
        log.warning("challenge closing output was not valid JSON")
        return ChallengeClosing()

    def _clean(items) -> list[str]:
        if not isinstance(items, list):
            return []
        return [str(item).strip() for item in items if str(item).strip()]

    return ChallengeClosing(
        stood=_clean(payload.get("stood")),
        unresolved=_clean(payload.get("unresolved")),
    )


def summarize_post_challenge_revision(source_text: str, final_text: str) -> dict:
    """被质疑的那一稿和最终交上来的稿子差多少。

    这是教师最想知道的那件事:他被问住之后到底改了没有。刻意不用 editor_operation
    的时间戳来判断——那既依赖客户端时钟(和服务端时间没有可比性),又只统计上报成功
    的编辑。改成直接比两份服务端快照:source_version 是发起质疑时冻住的那一稿,
    final_text 是这次提交的正文,两头都是服务端权威数据,不需要信任客户端。
    """

    source = (source_text or "").strip()
    final = (final_text or "").strip()
    matcher = difflib.SequenceMatcher(None, source, final)
    changed_chars = sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    )
    return {
        "revised": changed_chars >= CHALLENGE_REVISION_MIN_CHARS,
        "changed_chars": changed_chars,
    }


async def start_challenge(
    request,
    user,
    assignment,
    writing_session,
    model_id: str,
    db: Session,
) -> tuple[ChallengeSessionModel, ChallengeTurnModel]:
    """发起一次质疑,落库并生成第 1 轮。"""

    if not assignment.challenge_enabled:
        raise ChallengeError("Challenge is not enabled for this assignment")

    round_no = Education.resolve_next_submission_round_no(
        assignment.id, writing_session.owner_user_id, db=db
    )
    existing = Education.get_challenge_session_for_round(
        writing_session.id, round_no, db=db
    )
    if existing is not None:
        raise ChallengeError("Challenge for this round already exists")

    version = Education.get_latest_version(writing_session.id, db=db)
    draft_text = (version.note_snapshot_text or "").strip() if version else ""
    if version is None or len(draft_text) < CHALLENGE_MIN_DRAFT_CHARS:
        raise ChallengeError("Draft is too short to be challenged")

    system_prompt = await get_challenge_prompt("turn")
    if not system_prompt:
        raise ChallengeError("Challenge prompt is not configured")

    focus_keys = list(assignment.challenge_focus_keys or [])
    focus_key = resolve_focus_key(focus_keys, 1)
    challenge_text = await generate_completion(
        request,
        user,
        model_id,
        build_turn_messages(
            system_prompt,
            assignment,
            focus_key,
            draft_text,
            [],
            1,
            assignment.challenge_rounds,
        ),
    )
    if not challenge_text:
        raise ChallengeError("Challenge generation returned empty text")

    session = Education.insert_challenge_session(
        writing_session.id,
        assignment.id,
        writing_session.owner_user_id,
        round_no,
        version.id,
        focus_keys,
        assignment.challenge_rounds,
        commit=False,
        db=db,
    )
    turn = Education.insert_challenge_turn(
        session.id,
        1,
        focus_key,
        challenge_text,
        commit=False,
        db=db,
    )
    db.commit()
    return session, turn


async def submit_challenge_response(
    request,
    user,
    assignment,
    challenge_session,
    turn_no: int,
    response_text: str,
    model_id: str,
    db: Session,
) -> dict:
    """记录回应,然后要么发下一轮,要么收尾。

    回合上限在这里兜死:已经答满 planned_rounds 还想继续,直接拒绝。
    """

    if challenge_session.status != "in_progress":
        raise ChallengeError("Challenge is already finished")

    turns = Education.get_challenge_turns(challenge_session.id, db=db)
    current = next((turn for turn in turns if turn.turn_no == turn_no), None)
    if current is None:
        raise ChallengeError("Challenge turn not found")
    if current.response_text is not None:
        raise ChallengeError("Challenge turn already answered")
    if turn_no != len(turns):
        raise ChallengeError("Challenge turns must be answered in order")

    Education.record_challenge_response(
        challenge_session.id, turn_no, response_text, commit=False, db=db
    )
    turns = Education.get_challenge_turns(challenge_session.id, db=db)

    if turn_no < challenge_session.planned_rounds:
        system_prompt = await get_challenge_prompt("turn")
        if not system_prompt:
            raise ChallengeError("Challenge prompt is not configured")
        version = Education.get_version_by_id(
            challenge_session.source_version_id, db=db
        )
        draft_text = (version.note_snapshot_text or "") if version else ""
        next_turn_no = turn_no + 1
        focus_key = resolve_focus_key(
            list(challenge_session.focus_keys or []), next_turn_no
        )
        challenge_text = await generate_completion(
            request,
            user,
            model_id,
            build_turn_messages(
                system_prompt,
                assignment,
                focus_key,
                draft_text,
                turns,
                next_turn_no,
                challenge_session.planned_rounds,
            ),
        )
        if not challenge_text:
            raise ChallengeError("Challenge generation returned empty text")
        next_turn = Education.insert_challenge_turn(
            challenge_session.id,
            next_turn_no,
            focus_key,
            challenge_text,
            commit=False,
            db=db,
        )
        db.commit()
        return {"session": challenge_session, "turn": next_turn, "closing": None}

    closing_prompt = await get_challenge_prompt("closing")
    closing = ChallengeClosing()
    if closing_prompt:
        raw = await generate_completion(
            request,
            user,
            model_id,
            build_closing_messages(closing_prompt, assignment, turns),
        )
        closing = parse_closing(raw)

    session = Education.complete_challenge_session(
        challenge_session.id, closing, commit=False, db=db
    )
    db.commit()
    return {"session": session, "turn": None, "closing": closing}
