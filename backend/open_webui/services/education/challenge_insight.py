"""班级层面的质疑聚合。

平台此前对教师的全部回报都是个体的(提交详情、成长画像),班级层面只有来源占比和
改写程度分布——那些是监控指标,回答的是「有没有作弊」。质疑环节产生了第一批可聚合的
**学习指标**:每一轮质疑都带 focus_key(就是评分维度),收尾条目按轮次映射到维度,
修订判定给出被质疑处变没变。

这一层不调用模型,也不落表。数据在提交那一刻已经冻进 stats_json,看板本来就要把
submissions 全取回来,所以这里是纯内存聚合,不额外查库,也不进缓存。
"""

from typing import Iterable, Optional

from open_webui.models.education import RubricSchema

# 少于这个人数不出班级结论。几个人的比例没有意义,而教师会当真。
CHALLENGE_DISTRIBUTION_MIN_STUDENTS = 3


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

    for submission in submissions:
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

        for focus_key in stats.get("unresolved_focus_keys") or []:
            if focus_key not in challenged:
                continue
            unresolved.setdefault(focus_key, set()).add(student_id)
            if not focus_changed.get(focus_key, False):
                unchanged.setdefault(focus_key, set()).add(student_id)

    if completed == 0 and skipped == 0:
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
        }
        # 命中最多的排前面,教师那一屏第一眼看到的就是最该讲的那个维度。
        for focus_key, students in sorted(
            challenged.items(),
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
