"""班级层面的质疑聚合。

平台此前对教师的全部回报都是个体的(提交详情、成长画像),班级层面只有来源占比和
改写程度分布——那些是监控指标,回答的是「有没有作弊」。质疑环节产生了第一批可聚合的
**学习指标**:每一轮质疑都带 focus_key(就是评分维度),收尾条目按轮次映射到维度,
修订判定给出被质疑处变没变。

这一层不调用模型,也不落表。数据在提交那一刻已经冻进 stats_json,看板本来就要把
submissions 全取回来,所以这里是纯内存聚合,不额外查库,也不进缓存。
"""

import hashlib
import json
import logging
from typing import Iterable, Optional

from open_webui.models.education import (
    ChallengeInsightCategory,
    ChallengeInsightResponse,
    Education,
    RubricSchema,
)
# 走模块引用而不是 from ... import generate_completion：模型调用出口只有
# challenge.generate_completion 一个，测试靠替换它来隔离模型。直接把名字绑过来
# 会绕开那个出口，这里就成了第二个出口。
from open_webui.services.education import challenge as challenge_module
from open_webui.services.education.challenge import (
    ChallengeError,
    get_challenge_prompt,
)

log = logging.getLogger(__name__)

# 少于这个人数不出班级结论。几个人的比例没有意义,而教师会当真。
CHALLENGE_DISTRIBUTION_MIN_STUDENTS = 3
# 归纳的门槛更高:少数几条文本归纳出来的「类型」是噪声,而教师会拿它上讲台。
CHALLENGE_INSIGHT_MIN_STUDENTS = 5
# 一次最多送这么多条,防止大班把上下文顶爆。
CHALLENGE_INSIGHT_MAX_ITEMS = 200


def _challenge_stats(submission) -> dict:
    return (submission.stats_json or {}).get("challenge") or {}


def _criterion_labels(assignment) -> dict[str, str]:
    """维度 key -> 名称。教师那一屏要读的是「论据支撑」,不是 evidence。"""

    rubric = RubricSchema.model_validate(assignment.rubric_schema)
    return {criterion.key: criterion.label for criterion in rubric.criteria}


def build_challenge_distribution(assignment, submissions: Iterable) -> Optional[dict]:
    """按评分维度算这次作业的质疑命中率。

    每个维度三个数,凑成一句教师能直接拿去讲评的话:
    「本次『论据支撑』28 人被质疑,21 人没答住,其中 15 人被质疑处一字未动。」

    没有任何人做过质疑就返回 None——看板不显示空区块,不摆空状态占位。
    """

    completed = 0
    skipped = 0
    # 维度 -> 三个集合,存 student_id 而不是计数:同一个学生在一个维度上可能被问
    # 到不止一轮(焦点轮转会绕回来),按人数算才是教师要的口径。
    challenged: dict[str, set[str]] = {}
    unresolved: dict[str, set[str]] = {}
    unchanged: dict[str, set[str]] = {}
    # 写作前的评析：这个维度上预设的漏洞，有几人次找出来 / 一共几人次。
    critique_hits: dict[str, int] = {}
    critique_total: dict[str, int] = {}

    for submission in submissions:
        for entry in ((submission.stats_json or {}).get("critique") or {}).get(
            "focus_hits"
        ) or []:
            focus_key = entry.get("focus_key")
            if not focus_key:
                continue
            critique_total[focus_key] = critique_total.get(focus_key, 0) + 1
            if entry.get("hit"):
                critique_hits[focus_key] = critique_hits.get(focus_key, 0) + 1

        stats = _challenge_stats(submission)
        status = stats.get("status")
        if status == "skipped":
            skipped += 1
            continue
        if status != "completed":
            continue
        completed += 1

        student_id = submission.student_id
        revision_turns = (stats.get("revision") or {}).get("turns") or []
        # 该学生在每个维度上被质疑的那几处,是不是一处都没动。
        focus_changed: dict[str, bool] = {}
        for turn in revision_turns:
            focus_key = turn.get("focus_key")
            if not focus_key:
                continue
            challenged.setdefault(focus_key, set()).add(student_id)
            focus_changed[focus_key] = focus_changed.get(focus_key, False) or bool(
                turn.get("changed")
            )

        for item in stats.get("unresolved_items") or []:
            focus_key = item.get("focus_key")
            # 归属不上的条目照样给学生看，只是不进这张按维度统计的表。
            if not focus_key or focus_key not in challenged:
                continue
            unresolved.setdefault(focus_key, set()).add(student_id)
            if not focus_changed.get(focus_key, False):
                unchanged.setdefault(focus_key, set()).add(student_id)

    if completed == 0 and skipped == 0 and not critique_total:
        return None

    labels = _criterion_labels(assignment)
    criteria = [
        {
            "focus_key": focus_key,
            # 维度可能在作业更新时被改名或删掉，取不到就退回 key，不让这一行消失。
            "label": labels.get(focus_key, focus_key),
            "challenged": len(students),
            "unresolved": len(unresolved.get(focus_key, set())),
            "unresolved_unchanged": len(unchanged.get(focus_key, set())),
            # 写前认得出这个毛病的人次 / 总人次。认得出别人的、写自己时照样犯，
            # 这个对照才是这两个环节合起来的价值。
            "critique_hits": critique_hits.get(focus_key, 0),
            "critique_total": critique_total.get(focus_key, 0),
        }
        # 命中最多的排前面,教师那一屏第一眼看到的就是最该讲的那个维度。
        for focus_key, students in sorted(
            # 只被评析、没被质疑的维度也要出现，否则那一行整个消失。
            {
                **{key: set() for key in critique_total},
                **challenged,
            }.items(),
            key=lambda item: (-len(unresolved.get(item[0], set())), item[0]),
        )
    ]

    return {
        "completed_students": completed,
        # 「已跳过」和「压根没开始」对教师是同一件事,合并呈现(PRD 12.9.10)。
        "skipped_students": skipped,
        "criteria": criteria,
        # 样本太少时前端只报数字、不下结论。门槛放在这里而不是前端,是为了让
        # 「少于几人不出结论」这条规则只有一个出处。
        "below_sample_threshold": completed < CHALLENGE_DISTRIBUTION_MIN_STUDENTS,
        "sample_threshold": CHALLENGE_DISTRIBUTION_MIN_STUDENTS,
    }


def collect_unresolved_items(assignment, submissions: Iterable) -> list[tuple[str, str]]:
    """把全班的未解决条目收成 (维度名, 文本)。

    **只收这两样。** 不带姓名、学号、提交 id,也不带任何能回指到人的东西——这份东西
    是要送进模型、再摆到课堂上讲的,学生不能在讲评时被全班认出来。脱敏做在收集这一步
    而不是展示那一步,是为了让「送出去的载荷里根本没有标识」这件事只有一个出处。
    """

    labels = _criterion_labels(assignment)
    items: list[tuple[str, str]] = []
    for submission in submissions:
        stats = _challenge_stats(submission)
        if stats.get("status") != "completed":
            continue
        for item in stats.get("unresolved_items") or []:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            focus_key = item.get("focus_key")
            items.append((labels.get(focus_key, "") if focus_key else "", text))
    # 排序让同一批内容无论提交顺序如何都算出同一个哈希。
    items.sort()
    return items[:CHALLENGE_INSIGHT_MAX_ITEMS]


def insight_input_hash(items: list[tuple[str, str]]) -> str:
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def count_completed_students(submissions: Iterable) -> int:
    return sum(
        1
        for submission in submissions
        if _challenge_stats(submission).get("status") == "completed"
    )


def build_insight_messages(
    system_prompt: str, assignment, items: list[tuple[str, str]]
) -> list[dict]:
    lines = [f"【作业】{assignment.title}", "【全班仍未答住的点】"]
    for label, text in items:
        lines.append(f"- （{label}）{text}" if label else f"- {text}")
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(lines)},
    ]


def parse_insight(raw: str) -> list[ChallengeInsightCategory]:
    """解析归纳结果。解析不出来就返回空,不编造类型。"""

    text = (raw or "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        log.warning("challenge insight output was not a JSON object")
        return []
    try:
        payload = json.loads(text[start:end])
    except json.JSONDecodeError:
        log.warning("challenge insight output was not valid JSON")
        return []

    categories = []
    for entry in payload.get("categories") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        samples = [
            str(sample).strip()
            for sample in (entry.get("samples") or [])
            if str(sample).strip()
        ]
        try:
            hits = max(0, int(entry.get("hits") or 0))
        except (TypeError, ValueError):
            hits = 0
        categories.append(
            ChallengeInsightCategory(
                name=name,
                hits=hits,
                samples=samples[:2],
                advice=str(entry.get("advice") or "").strip(),
            )
        )
    return categories[:5]


async def build_challenge_insight(
    request,
    user,
    assignment,
    submissions: Iterable,
    model_id: str,
    db,
) -> ChallengeInsightResponse:
    """把全班的未解决条目归纳成几类「普遍站不住的论证」。

    四条约束,缺一条这个功能就不能用:

    - **缓存**:输入哈希不变就直接返回上次的结果,不重算。
    - **样本门槛**:完成质疑的人少于门槛就明说样本不足,不勉强归纳。
    - **脱敏**:送进模型的载荷里只有维度名和条目文本,见 collect_unresolved_items。
    - **只报频次**:措辞里写死了不许给班级下评价性结论。
    """

    submissions = list(submissions)
    completed = count_completed_students(submissions)
    if completed < CHALLENGE_INSIGHT_MIN_STUDENTS:
        return ChallengeInsightResponse(
            sample_size=completed,
            below_threshold=True,
            threshold=CHALLENGE_INSIGHT_MIN_STUDENTS,
        )

    items = collect_unresolved_items(assignment, submissions)
    if not items:
        return ChallengeInsightResponse(
            sample_size=completed, threshold=CHALLENGE_INSIGHT_MIN_STUDENTS
        )

    input_hash = insight_input_hash(items)
    cached = Education.get_challenge_insight(assignment.id, db=db)
    if cached is not None and cached.input_hash == input_hash:
        return ChallengeInsightResponse(
            categories=[
                ChallengeInsightCategory.model_validate(category)
                for category in cached.categories_json.get("categories") or []
            ],
            sample_size=cached.sample_size,
            threshold=CHALLENGE_INSIGHT_MIN_STUDENTS,
            generated_at=cached.created_at,
        )

    system_prompt = await get_challenge_prompt("insight")
    if not system_prompt:
        raise ChallengeError("Challenge insight prompt is not configured")

    raw = await challenge_module.generate_completion(
        request,
        user,
        model_id,
        build_insight_messages(system_prompt, assignment, items),
    )
    categories = parse_insight(raw)

    stored = Education.upsert_challenge_insight(
        assignment.id,
        input_hash,
        {"categories": [category.model_dump() for category in categories]},
        completed,
        db=db,
    )
    return ChallengeInsightResponse(
        categories=categories,
        sample_size=completed,
        threshold=CHALLENGE_INSIGHT_MIN_STUDENTS,
        generated_at=stored.created_at,
    )
