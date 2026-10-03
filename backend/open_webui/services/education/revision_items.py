"""修订初稿作业的第一次通读(逐项诊断)与修改清单。

学生交了初稿后、和 AI 说第一句话之前,服务端先让模型把初稿在作业的每一个评分维度上
都看一遍,逐项下结论;再把这张结论表附进对话的系统提示,首轮回复只按表写。

为什么先下结论再写:让模型直接写首轮回复,它谈哪几项是它自己定的(「定位出问题只谈
这一条」「最多五条」「没问题的不说」),没被提到的维度分不清是达标、没看还是被截掉,
修改清单和老师的评分也就对不上。先逐项下结论,每个维度都有明确结论,首轮回复、
修改清单、老师批改用的是同一张表。

- 四档:problem 要改(提交时必须交代)、minor 可改进(可以交代)、ok 达标、
  deferred 暂缓(任务说明规定了「某项出问题时哪几项先不谈」且这一项确实出了问题,
  这一项记 is_blocking)。只分有问题/达标时,写得好的稿子也会被判七八项有问题
  (2026-10-03 用 8 份样稿试跑),所以分出可改进。
- 补看:学生改好那一项后点「接着看」,平台按他当前的正文先确认那一项改到位了,
  再给暂缓的几项补上结论,修改清单随之补全。只补暂缓的格子、不重看整张表:
  允许随时重看全表的话,学生可以反复点到「要改」变少(同一份稿子两次诊断约 1/8 的项
  会在要改和可改进之间跳),清单就失去了交代的意义。
- 诊断用学生接下来对话的那个模型,按模型默认的思考设置调;试跑里关掉思考的一组
  漏判、误判明显多。
- 结论只在初稿上做一次,之后的对话不改这张表。
- 引用的原句一律对回初稿原文(`locate_quoted_span`),对不回去就留空——条目照样给,
  只是提交时判不了「原句动没动」。
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from open_webui.models.education import Education, RevisionItemModel
from open_webui.models.notes import Notes
from open_webui.services.education import challenge as challenge_service
from open_webui.services.education.challenge import (
    ChallengeError,
    _extract_json_object,
    locate_quoted_span,
)

log = logging.getLogger(__name__)

REVISION_STATUSES = ("problem", "minor", "ok", "deferred")
REVISION_FINDING_MAX_CHARS = 160
REVISION_REASON_MAX_CHARS = 500
# 通读中的占位多久算过期:开思考的诊断一次要二三十秒到一分多钟,失败还会当场重试一次。
REVISION_CLAIM_STALE_SECONDS = 300

DIAGNOSIS_PROMPT = """你在帮一门写作课做学生初稿的第一次通读。下面有这份作业的任务说明（那是写给对话助手的，你只用其中的批改标准和判定规则）、作业的评分维度和学生的初稿。请对照标准，把初稿在每一个评分维度上都看一遍，逐项给出结论。结论会原样给学生和老师看：学生据此修改，老师据此核对学生改了什么。

【怎么下结论】
- 每个评分维度给一个 status：
  · problem（要改）：这一项明显没做到，会让文章不成立或明显失分，这一轮必须处理；
  · minor（可改进）：基本做到了，只有个别小瑕疵，改了更好，不改也不影响这一项成立；
  · ok（达标）：做到了；
  · deferred（暂缓）：这一轮先不看。只在任务说明规定了「某一项出问题时哪几项先不谈」、并且那一项确实出了问题时使用：那一项填 problem，并在 JSON 顶层用 blocking 写出它的 key；任务说明点名先不谈的那几项填 deferred，其余照常下结论。任务说明没有这种规定，就不要用 deferred，blocking 填空字符串。
- 分清轻重：批改时只在明显没做到的地方动笔，一份写得好的稿子通常只有一两项要改。拿不准是 problem 还是 minor 时，选 minor。
- problem 和 minor：finding 用一句话说清问题在哪，不超过 60 字，写给学生看，不加修改建议；quote 抄一句最能说明问题的初稿原文，一字不改；问题是整体性的、找不到合适的单句时填空字符串。
- ok：finding 用一句话说做到了什么，可以为空；quote 填空字符串。
- deferred：finding 和 quote 都填空字符串。
- 每一项都要对照原文看过再下结论。不要为了凑数把达标的判成 problem，也不要因为问题多就省略某一项。
- 严格输出一个 JSON 对象，不要输出任何其他文字：
{"blocking": "", "items": [{"key": "评分维度的 key", "status": "problem", "finding": "...", "quote": "..."}]}
items 按评分维度的顺序，每个维度各一条，不多不少。"""

FOLLOW_UP_PROMPT = """你在帮一门写作课做学生稿子的补看。第一次通读时，下面标出的「出问题的那一项」没做到，按任务说明，「暂缓的几项」当时先没看。学生说他已经把那一项改好了，请按他现在的正文：
1. 先判断那一项是否已经改到位。按任务说明里这一项的判定规则看，不要比第一次通读更严或更松。resolved 填 true 或 false；note 用一句话写给学生：改到位了就说明哪里看得出来，没改到位就说清还差在哪，最好引用一句正文原文。
2. 只有改到位了，才对暂缓的几项逐项下结论；没改到位时 items 填空数组。
  · status 只能是 problem（要改：明显没做到，这一轮必须处理）、minor（可改进：基本做到了，只有个别小瑕疵）、ok（达标）。拿不准是 problem 还是 minor 时，选 minor。
  · problem 和 minor：finding 用一句话说清问题在哪，不超过 60 字，写给学生看，不加修改建议；quote 抄一句最能说明问题的正文原文，一字不改，找不到合适的单句时填空字符串。
  · ok：finding 用一句话说做到了什么，可以为空；quote 填空字符串。
- 严格输出一个 JSON 对象，不要输出任何其他文字：
{"resolved": true, "note": "...", "items": [{"key": "暂缓那一项的 key", "status": "problem", "finding": "...", "quote": "..."}]}
改到位时 items 里暂缓的每一项各一条，不多不少。"""


class RevisionItemsError(Exception):
    pass


def build_diagnosis_messages(task_prompt: str, criteria, baseline_text: str) -> list[dict]:
    rubric = "\n".join(f"{criterion.key}：{criterion.label}" for criterion in criteria)
    system = (
        f"{DIAGNOSIS_PROMPT}\n\n【任务说明】\n{task_prompt or '（无）'}"
        f"\n\n【评分维度】（key：名称）\n{rubric}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"【初稿】\n<<<\n{baseline_text}\n>>>"},
    ]


def parse_diagnosis(raw: str, baseline_text: str, criteria) -> list[dict]:
    """把模型输出整理成按评分维度排好的结论。缺维度、档位不合法都算失败,整轮重来。"""
    payload = _extract_json_object(raw)
    if payload is None or not isinstance(payload.get("items"), list):
        raise RevisionItemsError("Diagnosis output was not valid JSON")

    by_key: dict[str, dict] = {}
    for entry in payload["items"]:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        status = str(entry.get("status") or "").strip()
        if key and status in REVISION_STATUSES and key not in by_key:
            by_key[key] = entry

    keys = [criterion.key for criterion in criteria]
    if any(key not in by_key for key in keys):
        raise RevisionItemsError("Diagnosis is missing criteria")
    statuses = [by_key[key]["status"] for key in keys]
    # 暂缓必须说明是被哪一项挡住的,且那一项确实要改;补看时要先确认的就是它。
    blocking = str(payload.get("blocking") or "").strip()
    if "deferred" in statuses:
        if blocking not in by_key or by_key[blocking]["status"] != "problem":
            raise RevisionItemsError("Diagnosis deferred criteria without a blocking problem")
    else:
        blocking = ""

    items = []
    for key in keys:
        entry = by_key[key]
        status = entry["status"]
        finding = str(entry.get("finding") or "").strip()[:REVISION_FINDING_MAX_CHARS]
        flagged = status in ("problem", "minor")
        items.append(
            {
                "criterion_key": key,
                "status": status,
                "finding": (finding or None) if status != "deferred" else None,
                "quoted_span": (
                    locate_quoted_span(baseline_text, str(entry.get("quote") or ""))
                    if flagged
                    else None
                ),
                "is_blocking": key == blocking,
            }
        )
    return items


async def ensure_revision_items(
    request, user, session, assignment, model_id: Optional[str], task_prompt: str, db: Session
) -> tuple[str, list[RevisionItemModel]]:
    """取第一次通读的结论,还没通读就现在通读。返回 (status, items)。

    status:ready 已有结论;pending 别的请求正在通读;failed 这次没成功,再调一次会重试。
    """
    if session.revision_items_generated_at is not None:
        return "ready", Education.get_revision_items(session.id, db=db)
    if not model_id:
        return "failed", []

    if not Education.claim_revision_items(
        session.id, REVISION_CLAIM_STALE_SECONDS, db=db
    ):
        refreshed = Education.get_writing_session_by_id(session.id, db=db)
        if refreshed is not None and refreshed.revision_items_generated_at is not None:
            return "ready", Education.get_revision_items(session.id, db=db)
        return "pending", []

    # 占位已单独提交,下面的模型调用不夹在任何没提交的事务里。
    # 占位之后出任何错都要放掉占位,否则这个会话要干等到占位过期才能再通读。
    try:
        criteria = assignment.rubric_schema.criteria
        baseline = session.draft_baseline_text or ""
        messages = build_diagnosis_messages(task_prompt, criteria, baseline)
        items = None
        for _ in range(2):
            try:
                raw = await challenge_service.generate_completion(
                    request, user, model_id, messages
                )
                items = parse_diagnosis(raw, baseline, criteria)
                break
            except (ChallengeError, RevisionItemsError) as error:
                log.warning("first read-through failed: %s", error)
        if items is not None:
            stored = Education.store_revision_items(session.id, baseline, items, db=db)
            if stored is None:
                # 通读期间初稿被撤回(可能又交了新的一份):占位已随撤回清掉,现在可能是新初稿的通读
                # 在占着,不能放。
                return "failed", []
            return "ready", stored
    except Exception:
        log.exception("first read-through crashed")
    Education.release_revision_items_claim(session.id, db=db)
    return "failed", []


async def _current_text(session) -> str:
    """学生右侧编辑器最近一次保存的正文。笔记用自己的短会话读取,不带进之后的模型调用。"""
    note = await Notes.get_note_by_id(session.note_id)
    content = ((note.data or {}).get("content") or {}) if note else {}
    return (content.get("md") or "").strip()


def build_follow_up_messages(
    task_prompt: str, criteria, items: list[RevisionItemModel], current_text: str
) -> list[dict]:
    labels = {criterion.key: criterion.label for criterion in criteria}
    blocking = next(item for item in items if item.is_blocking)
    deferred = "\n".join(
        f"{item.criterion_key}：{labels.get(item.criterion_key, item.criterion_key)}"
        for item in items
        if item.status == "deferred"
    )
    system = (
        f"{FOLLOW_UP_PROMPT}\n\n【任务说明】\n{task_prompt or '（无）'}"
        f"\n\n【出问题的那一项】{labels.get(blocking.criterion_key, blocking.criterion_key)}"
        f"（第一次通读的结论：{blocking.finding or '无'}）"
        f"\n\n【暂缓的几项】（key：名称）\n{deferred}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"【学生现在的正文】\n<<<\n{current_text}\n>>>"},
    ]


def parse_follow_up(
    raw: str, current_text: str, deferred_keys: list[str]
) -> tuple[bool, Optional[str], list[dict]]:
    """返回 (那一项改到位没有, 给学生的一句话, 暂缓项的结论)。不合格式就算失败重来。"""
    payload = _extract_json_object(raw)
    if payload is None or not isinstance(payload.get("resolved"), bool):
        raise RevisionItemsError("Follow-up output was not valid JSON")
    note = str(payload.get("note") or "").strip()[:REVISION_FINDING_MAX_CHARS] or None
    if not payload["resolved"]:
        return False, note, []

    by_key: dict[str, dict] = {}
    for entry in payload.get("items") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        status = str(entry.get("status") or "").strip()
        if key in deferred_keys and status in ("problem", "minor", "ok") and key not in by_key:
            by_key[key] = entry
    if any(key not in by_key for key in deferred_keys):
        raise RevisionItemsError("Follow-up is missing deferred criteria")

    items = []
    for key in deferred_keys:
        entry = by_key[key]
        status = entry["status"]
        finding = str(entry.get("finding") or "").strip()[:REVISION_FINDING_MAX_CHARS]
        items.append(
            {
                "criterion_key": key,
                "status": status,
                "finding": finding or None,
                "quoted_span": (
                    locate_quoted_span(current_text, str(entry.get("quote") or ""))
                    if status != "ok"
                    else None
                ),
            }
        )
    return True, note, items


async def ensure_follow_up(
    request, user, session, assignment, model_id: Optional[str], task_prompt: str, db: Session
) -> tuple[str, Optional[str], list[RevisionItemModel]]:
    """补看:学生说出问题的那一项改好了,确认之后给暂缓的几项补上结论。

    返回 (status, note, items)。status:ready 补完了;not_ready 那一项还没改到位,
    note 说还差在哪,暂缓项不动;pending 别的请求正在通读或补看;failed 这次没成功。
    """
    items = Education.get_revision_items(session.id, db=db)
    deferred_keys = [item.criterion_key for item in items if item.status == "deferred"]
    if not deferred_keys:
        return "ready", None, items
    if not model_id:
        return "failed", None, items
    if not Education.claim_revision_follow_up(
        session.id, REVISION_CLAIM_STALE_SECONDS, db=db
    ):
        return "pending", None, items

    # 占位已单独提交,模型调用不夹在没提交的事务里;出任何错都放掉占位。
    try:
        current_text = await _current_text(session)
        messages = build_follow_up_messages(
            task_prompt, assignment.rubric_schema.criteria, items, current_text
        )
        for _ in range(2):
            try:
                raw = await challenge_service.generate_completion(
                    request, user, model_id, messages
                )
                resolved, note, filled = parse_follow_up(raw, current_text, deferred_keys)
            except (ChallengeError, RevisionItemsError) as error:
                log.warning("follow-up read failed: %s", error)
                continue
            if not resolved:
                Education.release_revision_follow_up_claim(session.id, db=db)
                return "not_ready", note, items
            return "ready", note, Education.apply_revision_follow_up(
                session.id, filled, db=db
            )
    except Exception:
        log.exception("follow-up read crashed")
    Education.release_revision_follow_up_claim(session.id, db=db)
    return "failed", None, items


def build_conclusion_context(items: list[RevisionItemModel], criteria) -> str:
    """附进对话系统提示的结论表。首轮回复按它写,之后的对话也知道第一次通读说过什么。"""
    labels = {criterion.key: criterion.label for criterion in criteria}
    label = lambda item: labels.get(item.criterion_key, item.criterion_key)  # noqa: E731

    # 补看补上的几条前面标「补看」;出问题的那一项补看时确认改到位了,也写明。
    tag = lambda item: "补看 · " if item.follow_up_at and not item.is_blocking else ""  # noqa: E731
    blocking = next((item for item in items if item.is_blocking), None)

    lines = [
        "【第一次通读结论】学生交初稿后，平台已按评分维度把初稿逐项看过。"
        "首轮回复以这张表为准；之后的对话以学生当前正文为准，不必重复整张表。"
    ]
    for item in items:
        if item.status == "problem":
            quote = f"（原句：「{item.quoted_span}」）" if item.quoted_span else ""
            fixed = (
                "（学生改过后补看时已确认改到位）"
                if item.is_blocking and item.follow_up_at
                else ""
            )
            lines.append(f"- {tag(item)}要改 · {label(item)}：{item.finding or ''}{quote}{fixed}")
    for item in items:
        if item.status == "minor":
            lines.append(f"- {tag(item)}可改进 · {label(item)}：{item.finding or ''}")
    passed = [f"{label(item)}{'（补看）' if tag(item) else ''}" for item in items if item.status == "ok"]
    if passed:
        lines.append("- 达标：" + "、".join(passed))
    deferred = [label(item) for item in items if item.status == "deferred"]
    if deferred and blocking is not None:
        lines.append(
            f"- 暂缓（等「{label(blocking)}」改好后再看）：" + "、".join(deferred)
            + f"。学生说「{label(blocking)}」改好了时，提醒他点右侧的「改好了，接着看」，"
            "平台会先确认，再补看这几项。"
        )
    if blocking is not None and blocking.follow_up_at:
        lines.append(
            f"- 学生已经改好「{label(blocking)}」，平台补看了原先暂缓的几项（标「补看」的几条）。"
            "学生请你接着看时，先确认这一项已改到位，再按首轮的写法展开补看出的「要改」，"
            "「可改进」合起来一两句话带过，最后问他先改哪一个。"
        )
    return "\n".join(lines)


def build_first_read_context(session, db: Optional[Session] = None) -> Optional[str]:
    """写作区对话要附的第一次通读结论;不是修订初稿作业或还没通读时返回 None。"""
    if (
        session.scope != "assignment"
        or not session.assignment_id
        or session.revision_items_generated_at is None
    ):
        return None
    assignment = Education.get_assignment_by_id(session.assignment_id, db=db)
    if assignment is None or assignment.task_mode != "revise_draft":
        return None
    items = Education.get_revision_items(session.id, db=db)
    return build_conclusion_context(items, assignment.rubric_schema.criteria)


def normalize_revision_decision(
    decision: Optional[str], reason: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    text = (reason or "").strip()
    if len(text) > REVISION_REASON_MAX_CHARS:
        raise ValueError("Reason is too long")
    return decision, (text or None)


def build_revision_snapshot(items: list[RevisionItemModel], final_text: str) -> list[dict]:
    """提交时冻进本轮记录。quote_unchanged:初稿原句在终稿里原样还在。

    和质疑的「被质疑那句动没动」同一个判法:原句是从初稿里原样截下来的,
    学生动了任何一个字,它就找不到了。只回答动没动,不回答改得好不好。
    """
    final = final_text or ""
    return [
        {
            "item_no": item.item_no,
            "criterion_key": item.criterion_key,
            "status": item.status,
            "finding": item.finding,
            "quoted_span": item.quoted_span,
            "decision": item.decision,
            "reason": item.reason,
            "is_blocking": item.is_blocking,
            "follow_up_at": item.follow_up_at,
            "quote_unchanged": bool(item.quoted_span) and item.quoted_span in final,
        }
        for item in items
    ]
