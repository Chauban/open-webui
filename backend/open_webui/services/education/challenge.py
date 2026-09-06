"""提交前质疑环节的回合引擎。

这里的 AI 是「质疑读者」,与写作区左侧的辅导助手是两个相反的角色:辅导助手负责
帮学生写,质疑读者只负责问、绝不给可粘贴的文本。两者物理隔离,不共用对话。

回合数由本模块的代码控制,不由提示词控制。模型不会因为提示词里写了「只问三轮」
就真的停下,所以每一轮都是服务端显式发起的一次独立调用,到 planned_rounds 就转收尾。

每一轮质疑必须引用它所质疑的原文片段。引用要求写在本模块拼的 user message 里,
不写在管理员可编辑的那段提示词里——格式是判定的地基,不能被改掉。
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
    ChallengeClosingItem,
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
# 短于这个长度的引用锚不住:一个逗号在全文里到处都是,判不出改没改。
CHALLENGE_QUOTE_MIN_CHARS = 8
# 模型改写过引用时的模糊定位阈值。低于它就认为它引的不是原文里的东西。
CHALLENGE_QUOTE_MATCH_RATIO = 0.75
# 在最终稿里找「这句被改成了什么」用更松的阈值——学生正是把它改了才要看。
# 低于它就认为这句已经被整段删掉,而不是硬凑一段不相干的话给教师看。
CHALLENGE_FINAL_SPAN_MATCH_RATIO = 0.45


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


# 输出格式的契约。放在 user message 里由代码下发,管理员改不掉——quote 是修订判定
# 的锚点,格式一旦被改坏,整条证据链就断了。
TURN_OUTPUT_CONTRACT = (
    "【输出格式】严格输出一个 JSON 对象，不要输出任何其他文字：\n"
    '{"quote": "...", "challenge": "..."}\n'
    "- quote 必须原样抄录你所质疑的那一句或那一小段原文，一字不改，"
    f"不少于 {CHALLENGE_QUOTE_MIN_CHARS} 个字。不要抄整段，只抄你要问的那一句。\n"
    "- challenge 是你对这句话的质疑，先说清你为什么不信服，再提一个具体问题。\n"
    "- 只输出 JSON。"
)


def build_turn_messages(
    system_prompt: str,
    assignment,
    focus_key: str,
    draft_text: str,
    previous_turns: list[ChallengeTurnModel],
    turn_no: int,
    planned_rounds: int,
    followup_comment: Optional[str] = None,
) -> list[dict]:
    lines = [
        f"【作业】{assignment.title}",
    ]
    description = (assignment.description or "").strip()
    if description:
        lines.append(f"【要求】{description}")
    lines.append(f"【本轮质疑聚焦的评分维度】{_describe_focus(assignment, focus_key)}")
    lines.append(f"【进度】这是第 {turn_no} 轮，共 {planned_rounds} 轮。")

    # 教师退回时点名要追问的那条。焦点维度照旧轮转（班级聚合要靠它），教师的话
    # 叠在上面当作本轮的首要指向——退回意见此前写完就没下文，这是它第一次有抓手。
    if followup_comment:
        lines.append(
            "【教师退回这篇时点名的问题】"
            + followup_comment
            + "\n本轮优先追问这一条。作者如果已经把它解决了，就说明它已经解决，"
            "再问上面那个维度里其它仍然说服不了你的地方。"
        )

    if previous_turns:
        history = []
        for turn in previous_turns:
            history.append(
                f"你的第 {turn.turn_no} 轮质疑（针对「{turn.quoted_span}」）："
                f"{turn.challenge_text}"
            )
            response = (turn.response_text or "").strip()
            history.append(
                f"作者的回应：{response}" if response else "作者没有回应这一轮。"
            )
        lines.append("【此前的往来】\n" + "\n".join(history))
        lines.append(
            "请不要重复你已经问过的点，也不要再引用你已经引用过的句子。"
            "针对作者的回应，提出下一个仍然说服不了你的地方。"
        )

    lines.append(f"【作者的文章】\n{_truncate_draft(draft_text)}")
    lines.append(TURN_OUTPUT_CONTRACT)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(lines)},
    ]


def build_closing_messages(
    system_prompt: str, assignment, turns: list[ChallengeTurnModel]
) -> list[dict]:
    history = []
    for turn in turns:
        history.append(
            f"你的第 {turn.turn_no} 轮质疑（针对「{turn.quoted_span}」）："
            f"{turn.challenge_text}"
        )
        response = (turn.response_text or "").strip()
        history.append(f"作者的回应：{response}" if response else "作者没有回应这一轮。")

    content = "\n\n".join(
        [
            f"【作业】{assignment.title}",
            "【往来记录】\n" + "\n".join(history),
            "unresolved 里的每一条都要写清它来自第几轮（turn_no），"
            f"轮次范围是 1 到 {len(turns)}。",
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


def _extract_json_object(raw: str) -> Optional[dict]:
    text = (raw or "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start:end])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


# 句子边界。按句切而不是按定长窗口取:窗口起点是估出来的,引用与原文长度一有出入
# 就会错位,切出半个词——那种片段既锚不住,摆给教师看也是乱码。
_SENTENCE_ENDINGS = "。！？!?；;\n"


def split_sentences(text: str) -> list[str]:
    """按句切分。保留句末标点,切出来的每一段都是原文的连续子串。"""

    sentences = []
    buffer: list[str] = []
    for char in text or "":
        buffer.append(char)
        if char in _SENTENCE_ENDINGS:
            sentence = "".join(buffer).strip()
            if sentence:
                sentences.append(sentence)
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        sentences.append(tail)
    return sentences


def _best_matching_sentence(text: str, needle: str) -> tuple[Optional[str], float]:
    best: Optional[str] = None
    best_ratio = 0.0
    for sentence in split_sentences(text):
        ratio = difflib.SequenceMatcher(None, sentence, needle, autojunk=False).ratio()
        if ratio > best_ratio:
            best, best_ratio = sentence, ratio
    return best, best_ratio


def locate_quoted_span(draft_text: str, quote: str) -> Optional[str]:
    """把模型给的引用对回原文,返回原文中的那一段。

    返回的是**原文里的字符串**而不是模型给的字符串:模型常会顺手改标点或吞字,
    存下改过的版本就再也对不回正文了。锚不住就返回 None——锚不住的引用对后面的
    修订判定毫无价值,宁可判这一轮生成失败重来。
    """

    draft = draft_text or ""
    needle = (quote or "").strip()
    if len(needle) < CHALLENGE_QUOTE_MIN_CHARS or not draft:
        return None

    if needle in draft:
        return needle

    # 模型改写过引用:回退到「原文里最像它的那一句」,整句返回,仍然是连续子串。
    candidate, ratio = _best_matching_sentence(draft, needle)
    if candidate is None or ratio < CHALLENGE_QUOTE_MATCH_RATIO:
        return None
    if len(candidate) < CHALLENGE_QUOTE_MIN_CHARS:
        return None
    return candidate


def parse_turn(raw: str, draft_text: str) -> tuple[str, str]:
    """把一轮输出解析成（质疑正文, 原文片段）。

    解析不出来或片段锚不住都抛错,由调用方重试一次。这里刻意不做「拿整段输出当质疑、
    片段留空」的降级:留空的片段会让这一轮永远判不出改没改,是把坏数据写进证据链。
    """

    payload = _extract_json_object(raw)
    if payload is None:
        raise ChallengeError("Challenge output was not valid JSON")

    challenge_text = str(payload.get("challenge") or "").strip()
    quote = str(payload.get("quote") or "").strip()
    if not challenge_text:
        raise ChallengeError("Challenge output had no challenge text")

    span = locate_quoted_span(draft_text, quote)
    if span is None:
        raise ChallengeError("Challenge quote could not be located in the draft")
    return challenge_text, span


async def generate_turn(
    request,
    user,
    model_id: str,
    messages: list[dict],
    draft_text: str,
) -> tuple[str, str]:
    """生成一轮质疑,解析失败重试一次。

    重试一次而不是多次:每次重试都是一次真实的模型调用,学生在界面上是干等着的。
    """

    last_error: Optional[ChallengeError] = None
    for attempt in range(2):
        raw = await generate_completion(request, user, model_id, messages)
        try:
            return parse_turn(raw, draft_text)
        except ChallengeError as error:
            last_error = error
            log.warning("challenge turn parse failed (attempt %d): %s", attempt + 1, error)
    raise last_error or ChallengeError("Challenge generation failed")


def parse_closing(raw: str, turns: list[ChallengeTurnModel]) -> ChallengeClosing:
    """把收尾输出解析成清单。

    解析不出来时返回空清单而不是抛错:收尾失败不该把学生卡在质疑里出不来,
    但也不能编造「你都答住了」这种结论。

    unresolved 的每一条按模型报的 turn_no 映射到那一轮的维度。模型报错轮次或不报,
    focus_key 就留空——这条照样给学生看,只是不进班级那张按维度统计的表。宁可少统计
    一条,也不把它硬塞给某个维度。
    """

    payload = _extract_json_object(raw)
    if payload is None:
        log.warning("challenge closing output was not a JSON object")
        return ChallengeClosing()

    focus_by_turn = {turn.turn_no: turn.focus_key for turn in turns}

    def _clean_stood(items) -> list[str]:
        if not isinstance(items, list):
            return []
        return [str(item).strip() for item in items if str(item).strip()]

    def _clean_unresolved(items) -> list[ChallengeClosingItem]:
        if not isinstance(items, list):
            return []
        cleaned = []
        for item in items:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                raw_turn = item.get("turn_no")
            else:
                text = str(item).strip()
                raw_turn = None
            if not text:
                continue
            try:
                turn_no = int(raw_turn) if raw_turn is not None else None
            except (TypeError, ValueError):
                turn_no = None
            if turn_no not in focus_by_turn:
                turn_no = None
            cleaned.append(
                ChallengeClosingItem(
                    text=text,
                    turn_no=turn_no,
                    focus_key=focus_by_turn.get(turn_no) if turn_no else None,
                )
            )
        return cleaned

    return ChallengeClosing(
        stood=_clean_stood(payload.get("stood")),
        unresolved=_clean_unresolved(payload.get("unresolved")),
    )


def _find_final_span(final_text: str, span: str) -> Optional[str]:
    """这句在最终稿里变成了什么样。找不到就是被整段删了,返回 None。

    同样按句匹配。教师那一栏要能直接读,给半句话不如不给。
    """

    needle = (span or "").strip()
    if not needle or not (final_text or ""):
        return None

    candidate, ratio = _best_matching_sentence(final_text, needle)
    if candidate is None or ratio < CHALLENGE_FINAL_SPAN_MATCH_RATIO:
        return None
    return candidate


def summarize_post_challenge_revision(
    turns: list[ChallengeTurnModel], final_text: str
) -> dict:
    """被质疑的那几处,在最终交上来的稿子里变了没有。

    判的是位置,不是字数。用全文改动量加最小字符阈值的老口径方向是反的:被质疑之后
    最理想的修改往往最小(删掉一个站不住的例子、把「所有人都认为」限缩为「我采访的
    12 个同学里有 9 个」),那些都过不了阈值;而在结尾补一句无关的套话稳过。

    做法很直白:quoted_span 是发起质疑时从那一稿里原样截下来的,只要学生没动那句话,
    它就会原样出现在最终正文里;动了任何一个字,它就找不到了。不需要阈值,也不依赖
    客户端——两头都是服务端快照。

    这里只回答「那处变没变」,不回答「改得对不对、是不是真回应了质疑」。后者要不要
    交给 AI 判是个待定问题(PRD 16.4),本期不做,由教师看三栏证据自己下结论。
    """

    final = (final_text or "").strip()
    items = []
    for turn in turns:
        span = (turn.quoted_span or "").strip()
        changed = bool(span) and span not in final
        items.append(
            {
                "turn_no": turn.turn_no,
                "focus_key": turn.focus_key,
                "quoted_span": span,
                "changed": changed,
                # 教师那一屏要三栏并排,最终稿的样子在提交这一刻就冻好,
                # 免得教师端每次打开都重算一遍 diff。
                "final_span": _find_final_span(final, span) if changed else span,
            }
        )

    return {
        "revised": any(item["changed"] for item in items),
        "changed_spans": sum(1 for item in items if item["changed"]),
        "total_spans": len(items),
        "turns": items,
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
    followup_comment = resolve_followup_comment(assignment, writing_session, db)
    challenge_text, quoted_span = await generate_turn(
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
            followup_comment,
        ),
        draft_text,
    )

    session = Education.insert_challenge_session(
        writing_session.id,
        assignment.id,
        writing_session.owner_user_id,
        round_no,
        version.id,
        focus_keys,
        assignment.challenge_rounds,
        followup_comment=followup_comment,
        commit=False,
        db=db,
    )
    turn = Education.insert_challenge_turn(
        session.id,
        1,
        focus_key,
        challenge_text,
        quoted_span,
        commit=False,
        db=db,
    )
    db.commit()
    return session, turn


def resolve_followup_comment(assignment, writing_session, db: Session) -> Optional[str]:
    """上一轮教师退回时勾了「让质疑读者追问」的话，取出那条意见。

    只认当前这一轮之前那次退回：教师没勾就没有，勾了但没写意见也没有——没有内容
    可追问的时候不该硬造一轮。
    """

    submission = Education.get_current_submission(
        assignment.id, writing_session.owner_user_id, db=db
    )
    if submission is None:
        return None
    review = Education.get_submission_review_by_submission_id(submission.id, db=db)
    if review is None or review.review_status != "returned":
        return None
    if not review.challenge_followup:
        return None
    return (review.returned_comment or "").strip() or None


def skip_challenge_before_start(
    assignment, writing_session, db: Session
) -> ChallengeSessionModel:
    """学生在契约页没点「开始」就跳过。

    这种回避同样要留痕。不落库的话,最该被教师看到的那批学生——连开都不开的——
    反而是唯一在质疑维度上完全空白的,而这正是这个环节最有教学意义的信号。
    """

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

    # 没开始就跳过时不存在「被质疑的那一稿」,source_version_id 留空是语义正确的。
    version = Education.get_latest_version(writing_session.id, db=db)
    return Education.insert_challenge_session(
        writing_session.id,
        assignment.id,
        writing_session.owner_user_id,
        round_no,
        version.id if version else None,
        list(assignment.challenge_focus_keys or []),
        assignment.challenge_rounds,
        status="skipped",
        db=db,
    )


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
        challenge_text, quoted_span = await generate_turn(
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
                challenge_session.followup_comment,
            ),
            draft_text,
        )
        next_turn = Education.insert_challenge_turn(
            challenge_session.id,
            next_turn_no,
            focus_key,
            challenge_text,
            quoted_span,
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
        closing = parse_closing(raw, turns)

    session = Education.complete_challenge_session(
        challenge_session.id, closing, commit=False, db=db
    )
    db.commit()
    return {"session": session, "turn": None, "closing": closing}
