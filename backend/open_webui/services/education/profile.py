import difflib
import re
from typing import Optional

from sqlalchemy.orm import Session

from open_webui.models.education import (
    Education,
    StudentProfileAssignmentItem,
    StudentProfileInsight,
    StudentProfileMetricTrend,
    StudentProfileResponse,
    StudentProfileRoundProgress,
    StudentProfileTimelinePoint,
)
from open_webui.services.education.analysis import (
    build_version_diffs,
    get_or_build_submission_analyses,
)

# ---------------------------------------------------------------------------
# 学生成长画像
#
# 画像只由可解释的比率型指标构成:每一维的构成公式随响应一起返回(index_formula),
# 教师能逐项核对,也能向学生解释。教师给的 score 没有统一满分,所以产出维只呈现
# 原值与趋势,不参与任何合成指数。风险信号(突发插入、疑似未标注导入)照旧展示,
# 但不进成长指数 —— 防作弊和成长是两件事。
# ---------------------------------------------------------------------------

_ACTIVE_WRITING_GAP_SECONDS = 300
_ACTIVE_WRITING_MIN_BLOCK_SECONDS = 30
_END_LOADED_WINDOW_RATIO = 0.1
_DEADLINE_WINDOW_SECONDS = 24 * 3600
# 回头删改的字符量达到写入量的三成,就算把稿子认真打磨过一遍。
_PROCESS_TARGET_REVISION_RATIO = 0.3
_PROCESS_TARGET_SPAN_SECONDS = 3 * 24 * 3600
_COLLABORATION_TARGET_PROMPTS = 10
_REFLECTION_TARGET_CHARS = 150
_PROFILE_MAX_INSIGHTS = 5
_TREND_FLAT_TOLERANCE = 0.05
_TREND_MIN_SAMPLES = 3
_TREND_MAX_WINDOW = 3

# 学生自报的 AI 用途分两类:让 AI「生成」内容,和让 AI「打磨」自己的内容。
# 从前者迁移到后者是很强的成长信号。
_AI_HELP_GENERATIVE_TYPES = {
    "Understand Assignment",
    "Outline",
    "Examples",
    "Explain Concepts",
    "Help Break Through Writer's Block",
}
_AI_HELP_REFINING_TYPES = {
    "Revise Structure",
    "Polish",
    "Check Errors",
    "Strengthen Reasoning",
}

_PROFILE_TREND_KEYS = (
    "total_chars",
    "normalized_score",
    "process_index",
    "collaboration_index",
    "revision_depth",
    "active_writing_seconds",
    "end_loaded_ratio",
    "deadline_window_ratio",
    "ai_ratio",
    "digestion_ratio",
    "prompt_count",
    "reflection_quality",
)

# 反思质量的启发式:只看「有没有写出具体做了什么」,不做语义理解。
# 中英各一组模式,命中即得分,便于向学生解释为什么这条反思被判为空泛。
_REFLECTION_ACTION_PATTERNS = (
    r"删|改写|重写|补充|替换|调整|重组|拆分|合并|换成|加了|去掉|润色",
    r"\b(delete|rewrote|rewrite|revis|replac|restructur)",
    r"\b(added|removed|merged|split|polish)",
)
_REFLECTION_LOCATOR_PATTERNS = (
    r"第[一二三四五六七八九十\d]+(段|句|部分|章)|开头|结尾|结论|论点|论据|例子|标题",
    r"\b(paragraph|sentence|intro|conclusion|thesis|evidence|example|section|title)",
)
_REFLECTION_JUDGEMENT_PATTERNS = (
    r"但是|不过|其实|发现|意识到|不够|更好|不合适|不准确|不认同|没有采用|自己判断",
    r"\b(but|however|realiz|noticed|inaccurate|disagree|better|instead|rejected)",
)


def _profile_index_formula() -> dict:
    """把两个合成指数的构成如实返回,前端可展开查看,避免出现黑箱分数。"""
    return {
        "process_index": {
            "revision_depth": {
                "metric": "revised_chars / inserted_chars",
                "target": _PROCESS_TARGET_REVISION_RATIO,
                "weight": 1 / 3,
            },
            "span_effort": {
                "metric": "writing_span_seconds",
                "target": _PROCESS_TARGET_SPAN_SECONDS,
                "weight": 1 / 3,
            },
            "pacing": {
                "metric": "end_loaded_ratio",
                "inverted": True,
                "weight": 1 / 3,
            },
        },
        "collaboration_index": {
            "digestion": {"metric": "digestion_ratio", "weight": 1 / 3},
            "inquiry": {
                "metric": "prompt_count",
                "target": _COLLABORATION_TARGET_PROMPTS,
                "weight": 1 / 3,
            },
            "reflection": {"metric": "reflection_quality", "weight": 1 / 3},
            "note": "no_ai_usage_falls_back_to_reflection_only",
        },
        "reflection_quality": {
            "length": {"target_chars": _REFLECTION_TARGET_CHARS, "max": 40},
            "action": {"max": 20},
            "locator": {"max": 20},
            "judgement": {"max": 20},
        },
    }


def _estimate_active_writing_seconds(marks: list[int]) -> Optional[int]:
    """把编辑操作的时间戳聚成写作块,块内累计时长,块间空档不计。"""
    sorted_marks = sorted({mark for mark in marks if mark is not None})
    if not sorted_marks:
        return None

    total = 0
    block_start = sorted_marks[0]
    previous = sorted_marks[0]
    for mark in sorted_marks[1:]:
        if mark - previous > _ACTIVE_WRITING_GAP_SECONDS:
            total += max(previous - block_start, _ACTIVE_WRITING_MIN_BLOCK_SECONDS)
            block_start = mark
        previous = mark
    total += max(previous - block_start, _ACTIVE_WRITING_MIN_BLOCK_SECONDS)
    return total


def _compute_end_loaded_ratio(
    version_diffs: list[dict], start_at: int, end_at: int
) -> Optional[float]:
    """本轮写作窗口最后一成时间内的写入占比；它描述收尾集中度，不冒充截止压力。"""
    total_inserted = sum(diff.get("inserted_length", 0) for diff in version_diffs)
    if total_inserted <= 0 or end_at <= start_at:
        return None

    threshold = end_at - (end_at - start_at) * _END_LOADED_WINDOW_RATIO
    late_inserted = sum(
        diff.get("inserted_length", 0) for diff in version_diffs if (diff.get("created_at") or 0) >= threshold
    )
    return round(late_inserted / total_inserted, 4)


def _compute_deadline_window_ratio(
    version_diffs: list[dict], due_at: Optional[int]
) -> Optional[float]:
    """截止前 24 小时起写入的字符占本轮全部写入的比例；逾期后的写入也计入。"""
    total_inserted = sum(diff.get("inserted_length", 0) for diff in version_diffs)
    if total_inserted <= 0 or due_at is None:
        return None
    threshold = due_at - _DEADLINE_WINDOW_SECONDS
    deadline_window_inserted = sum(
        diff.get("inserted_length", 0)
        for diff in version_diffs
        if (diff.get("created_at") or 0) >= threshold
    )
    return round(deadline_window_inserted / total_inserted, 4)


def _score_reflection(text: str) -> dict:
    content = (text or "").strip()
    if not content:
        return {"char_count": 0, "score": 0}

    def _hits(patterns) -> bool:
        return any(re.search(pattern, content, re.IGNORECASE) for pattern in patterns)

    length_score = min(len(content) / _REFLECTION_TARGET_CHARS, 1.0) * 40
    action_score = 20 if _hits(_REFLECTION_ACTION_PATTERNS) else 0
    locator_score = 20 if _hits(_REFLECTION_LOCATOR_PATTERNS) else 0
    judgement_score = 20 if _hits(_REFLECTION_JUDGEMENT_PATTERNS) else 0
    return {
        "char_count": len(content),
        "score": int(round(length_score + action_score + locator_score + judgement_score)),
    }


def _compute_revision_depth(revised_chars: int, inserted_chars: int) -> Optional[int]:
    """回头删改的字符量占写入量的比例,折算成 0-100。

    刻意不用版本数:一个版本 = 编辑器停顿 1.2 秒后的一次自动保存,数量只反映打字
    时长(实测一篇稿子能有 200 多个版本),拿它当「改了几版」会被打字速度带偏。
    删改字符量才真正区分「一路往下写」和「回头反复打磨」。
    """
    if inserted_chars <= 0:
        return None
    ratio = revised_chars / inserted_chars
    return int(round(min(ratio / _PROCESS_TARGET_REVISION_RATIO, 1.0) * 100))


def _compute_process_index(
    revision_depth: Optional[int],
    writing_span_seconds: int,
    end_loaded_ratio: Optional[float],
) -> Optional[int]:
    if revision_depth is None or end_loaded_ratio is None:
        return None
    span_effort = min(writing_span_seconds / _PROCESS_TARGET_SPAN_SECONDS, 1.0) * 100
    pacing = (1 - min(max(end_loaded_ratio, 0.0), 1.0)) * 100
    return int(round((revision_depth + span_effort + pacing) / 3))


def _compute_collaboration_index(
    digestion_ratio: int,
    prompt_count: int,
    reflection_quality: int,
    ai_ratio: float,
) -> int:
    # 没用 AI 的提交不该被「消化度 0」拖成低分,这一维退化为只看反思质量。
    if ai_ratio <= 0 and prompt_count <= 0:
        return int(round(reflection_quality))

    inquiry = min(prompt_count / _COLLABORATION_TARGET_PROMPTS, 1.0) * 100
    return int(round((digestion_ratio + inquiry + reflection_quality) / 3))


def _slice_round_versions(versions, previous_final_version_id, final_version_id):
    """截出本轮写作窗口内的版本:上一轮定稿之后 → 本轮定稿。"""
    version_ids = [version.id for version in versions]
    try:
        end_index = version_ids.index(final_version_id)
    except ValueError:
        end_index = len(versions) - 1
    start_index = 0
    if previous_final_version_id in version_ids:
        start_index = version_ids.index(previous_final_version_id) + 1
    if start_index > end_index:
        start_index = end_index
    return versions[start_index : end_index + 1]


def _build_trend(key: str, values: list[float]) -> Optional[StudentProfileMetricTrend]:
    samples = [value for value in values if value is not None]
    if len(samples) < _TREND_MIN_SAMPLES:
        return None

    window_size = min(_TREND_MAX_WINDOW, len(samples) // 2)
    early = samples[:window_size]
    recent = samples[-window_size:]
    first = sum(float(value) for value in early) / len(early)
    last = sum(float(value) for value in recent) / len(recent)
    delta = last - first
    tolerance = max(abs(first), 1.0) * _TREND_FLAT_TOLERANCE
    if delta > tolerance:
        direction = "up"
    elif delta < -tolerance:
        direction = "down"
    else:
        direction = "flat"
    return StudentProfileMetricTrend(
        key=key,
        first=round(first, 4),
        last=round(last, 4),
        delta=round(delta, 4),
        direction=direction,
        sample_count=len(samples),
    )


def _summarize_help_types(points: list) -> dict:
    generative = 0
    refining = 0
    for point in points:
        for help_type in point.ai_help_types:
            if help_type in _AI_HELP_GENERATIVE_TYPES:
                generative += 1
            elif help_type in _AI_HELP_REFINING_TYPES:
                refining += 1
    total = generative + refining
    return {
        "generative": generative,
        "refining": refining,
        "refining_ratio": round(refining / total, 4) if total else 0.0,
    }


def _build_profile_insights(
    timeline: list,
    round_progress: list,
    trends: dict,
    help_shift: dict,
    reflection_quality: dict,
) -> list[StudentProfileInsight]:
    candidates: list[StudentProfileInsight] = []
    if len(timeline) < _TREND_MIN_SAMPLES:
        candidates.append(StudentProfileInsight(code="not_enough_data", tone="neutral"))
    if not timeline:
        return candidates

    latest = timeline[-1]

    digestion = trends.get("digestion_ratio")
    if digestion is not None and digestion.direction == "up":
        candidates.append(
            StudentProfileInsight(
                code="digestion_up",
                tone="positive",
                params={"delta": digestion.delta, "last": digestion.last},
            )
        )
    elif latest.ai_ratio >= 0.3 and latest.digestion_ratio < 20:
        candidates.append(
            StudentProfileInsight(
                code="digestion_low",
                tone="warning",
                params={
                    "digestion_ratio": latest.digestion_ratio,
                    "ai_ratio": latest.ai_ratio,
                },
            )
        )

    ai_ratio = trends.get("ai_ratio")
    if ai_ratio is not None and abs(ai_ratio.delta) >= 0.15:
        candidates.append(
            StudentProfileInsight(
                code="ai_share_changed",
                tone="neutral",
                params={"delta": ai_ratio.delta, "last": ai_ratio.last},
            )
        )

    improved_rounds = [item for item in round_progress if item.score_delta is not None and item.score_delta > 0]
    if improved_rounds:
        candidates.append(
            StudentProfileInsight(
                code="round_improvement",
                tone="positive",
                params={
                    "count": len(improved_rounds),
                    "best_delta": max(item.score_delta for item in improved_rounds),
                },
            )
        )
    elif round_progress and all(item.revision_ratio < 10 for item in round_progress):
        candidates.append(
            StudentProfileInsight(
                code="round_revision_thin",
                tone="warning",
                params={"revision_ratio": max(item.revision_ratio for item in round_progress)},
            )
        )

    if help_shift.get("refining_ratio_delta", 0) >= 0.2:
        candidates.append(
            StudentProfileInsight(
                code="help_type_shift_refining",
                tone="positive",
                params={"delta": help_shift.get("refining_ratio_delta", 0)},
            )
        )

    if (
        latest.deadline_window_ratio is not None
        and latest.deadline_window_ratio >= 0.6
    ):
        candidates.append(
            StudentProfileInsight(
                code="deadline_rush",
                tone="warning",
                params={"ratio": latest.deadline_window_ratio},
            )
        )

    process = trends.get("process_index")
    if process is not None and process.direction == "up":
        candidates.append(
            StudentProfileInsight(
                code="process_up",
                tone="positive",
                params={"delta": process.delta, "last": process.last},
            )
        )

    if reflection_quality.get("average_score", 0) < 40:
        candidates.append(
            StudentProfileInsight(
                code="reflection_thin",
                tone="warning",
                params={"average_score": reflection_quality.get("average_score", 0)},
            )
        )

    return candidates[:_PROFILE_MAX_INSIGHTS]


async def build_student_profile(
    student,
    student_id: str,
    classroom,
    assignments: list,
    db: Session,
) -> StudentProfileResponse:
    assignment_by_id = {assignment.id: assignment for assignment in assignments}
    submissions = Education.get_submissions_by_student(student_id, list(assignment_by_id.keys()), db=db)
    reviews = Education.get_submission_reviews_by_submission_ids([submission.id for submission in submissions], db=db)
    sessions = Education.get_writing_sessions_by_ids(
        [submission.writing_session_id for submission in submissions], db=db
    )
    versions_by_session = Education.get_versions_by_session_ids(list(sessions.keys()), db=db)
    operation_marks = Education.get_editor_operation_marks_by_session_ids(list(sessions.keys()), db=db)
    reflections = Education.get_micro_reflections_by_ids(
        [submission.micro_reflection_id for submission in submissions], db=db
    )
    analyses = await get_or_build_submission_analyses(submissions, sessions, db)

    rounds_by_assignment: dict[str, list] = {}
    for submission in submissions:
        rounds_by_assignment.setdefault(submission.assignment_id, []).append(submission)
    for assignment_rounds in rounds_by_assignment.values():
        assignment_rounds.sort(key=lambda item: item.round_no)

    timeline: list[StudentProfileTimelinePoint] = []
    round_progress: list[StudentProfileRoundProgress] = []

    for assignment_id, assignment_rounds in rounds_by_assignment.items():
        assignment = assignment_by_id.get(assignment_id)
        if assignment is None:
            continue

        previous_submission = None
        previous_final_text = ""
        for submission in assignment_rounds:
            session = sessions.get(submission.writing_session_id)
            if session is None:
                continue

            previous_review = reviews.get(previous_submission.id) if previous_submission else None
            # 第 2 轮起的截止时间是退回时设的重交截止,拿作业原始截止算提前量会失真。
            round_due_at = (
                previous_review.resubmit_due_at
                if previous_review and previous_review.resubmit_due_at
                else assignment.due_at
            )

            summary = (analyses.get(submission.id) or {}).get("summary") or {}
            review = reviews.get(submission.id)
            reflection = reflections.get(submission.micro_reflection_id)
            reflection_score = _score_reflection(reflection.reflection_text if reflection else "")

            all_versions = versions_by_session.get(submission.writing_session_id, [])
            round_versions = _slice_round_versions(
                all_versions,
                previous_submission.final_version_id if previous_submission else None,
                submission.final_version_id,
            )
            window_start_at = round_versions[0].created_at if round_versions else submission.submitted_at
            version_diffs = build_version_diffs(round_versions, previous_final_text)
            inserted_chars = sum(diff.get("inserted_length", 0) for diff in version_diffs)
            revised_chars = sum(diff.get("deleted_length", 0) for diff in version_diffs)
            revision_depth = _compute_revision_depth(revised_chars, inserted_chars)
            writing_span_seconds = max(submission.submitted_at - window_start_at, 0)
            active_writing_seconds = _estimate_active_writing_seconds(
                [
                    mark
                    for mark in operation_marks.get(submission.writing_session_id, [])
                    if window_start_at <= mark <= submission.submitted_at
                ]
            )
            end_loaded_ratio = _compute_end_loaded_ratio(
                version_diffs, window_start_at, submission.submitted_at
            )
            deadline_window_ratio = _compute_deadline_window_ratio(
                version_diffs, round_due_at
            )

            ai_ratio = round(
                summary.get("ai_inserted_ratio", 0) + summary.get("ai_pasted_ratio", 0),
                4,
            )
            digestion_ratio = summary.get("average_rewrite_ratio", 0)
            prompt_count = summary.get("prompt_count", 0)

            timeline.append(
                StudentProfileTimelinePoint(
                    submission_id=submission.id,
                    assignment_id=assignment.id,
                    assignment_title=assignment.title,
                    round_no=submission.round_no,
                    is_current=submission.is_current == 1,
                    submitted_at=submission.submitted_at,
                    total_chars=summary.get("total_chars", 0),
                    score=review.score if review else None,
                    score_max=assignment.score_max,
                    normalized_score=(
                        round(review.score / assignment.score_max * 100, 2)
                        if review and review.score is not None
                        else None
                    ),
                    rubric=review.rubric_json if review else None,
                    review_status=review.review_status if review else "pending",
                    inserted_chars=inserted_chars,
                    revised_chars=revised_chars,
                    revision_depth=revision_depth,
                    writing_span_seconds=writing_span_seconds,
                    active_writing_seconds=active_writing_seconds,
                    lead_time_seconds=(round_due_at - window_start_at if round_due_at is not None else None),
                    end_loaded_ratio=end_loaded_ratio,
                    deadline_window_ratio=deadline_window_ratio,
                    process_index=_compute_process_index(
                        revision_depth, writing_span_seconds, end_loaded_ratio
                    ),
                    typed_ratio=summary.get("typed_ratio", 0),
                    ai_ratio=ai_ratio,
                    unknown_ratio=summary.get("unknown_ratio", 0),
                    prompt_count=prompt_count,
                    digestion_ratio=digestion_ratio,
                    reflection_char_count=reflection_score["char_count"],
                    reflection_quality=reflection_score["score"],
                    ai_help_types=list(reflection.ai_help_types) if reflection else [],
                    collaboration_index=_compute_collaboration_index(
                        digestion_ratio,
                        prompt_count,
                        reflection_score["score"],
                        ai_ratio,
                    ),
                    burst_count=summary.get("burst_count", 0),
                    suspected_unmarked_import_count=summary.get("suspected_unmarked_import_count", 0),
                )
            )

            final_version = next(
                (version for version in all_versions if version.id == submission.final_version_id),
                None,
            )
            final_text = (final_version.note_snapshot_text if final_version else "") or ""

            if previous_submission is not None:
                similarity = difflib.SequenceMatcher(None, previous_final_text, final_text).ratio()
                round_progress.append(
                    StudentProfileRoundProgress(
                        assignment_id=assignment.id,
                        assignment_title=assignment.title,
                        from_round=previous_submission.round_no,
                        to_round=submission.round_no,
                        char_delta=len(final_text) - len(previous_final_text),
                        revision_ratio=int(round((1 - similarity) * 100)),
                        score_delta=(
                            review.score - previous_review.score
                            if review
                            and review.score is not None
                            and previous_review
                            and previous_review.score is not None
                            else None
                        ),
                        turnaround_seconds=(
                            submission.submitted_at - previous_review.reviewed_at
                            if previous_review and previous_review.reviewed_at
                            else None
                        ),
                    )
                )

            previous_submission = submission
            previous_final_text = final_text

    timeline.sort(key=lambda point: (point.submitted_at, point.round_no))
    round_progress.sort(key=lambda item: (item.assignment_title, item.to_round))

    trends = {}
    for key in _PROFILE_TREND_KEYS:
        trend = _build_trend(key, [getattr(point, key) for point in timeline])
        if trend is not None:
            trends[key] = trend

    half = len(timeline) // 2
    early_points = timeline[:half] if half else []
    recent_points = timeline[half:] if half else timeline
    early_help = _summarize_help_types(early_points)
    recent_help = _summarize_help_types(recent_points)
    help_shift = {
        "early": early_help,
        "recent": recent_help,
        "refining_ratio_delta": round(recent_help["refining_ratio"] - early_help["refining_ratio"], 4),
    }

    help_distribution: dict[str, int] = {}
    for point in timeline:
        for help_type in point.ai_help_types:
            help_distribution[help_type] = help_distribution.get(help_type, 0) + 1

    reflection_scores = [point.reflection_quality for point in timeline]
    reflection_quality = {
        "count": len(reflection_scores),
        "average_score": (int(round(sum(reflection_scores) / len(reflection_scores))) if reflection_scores else 0),
        "average_chars": (
            int(round(sum(point.reflection_char_count for point in timeline) / len(timeline))) if timeline else 0
        ),
    }

    profile_assignments: list[StudentProfileAssignmentItem] = []
    submitted_count = 0
    reviewed_count = 0
    returned_count = 0
    normalized_scores: list[float] = []
    for assignment in assignments:
        assignment_rounds = rounds_by_assignment.get(assignment.id, [])
        current = next((item for item in reversed(assignment_rounds) if item.is_current == 1), None)
        if current is None:
            profile_assignments.append(StudentProfileAssignmentItem(assignment=assignment))
            continue

        review = reviews.get(current.id)
        review_status = review.review_status if review else "pending"
        submitted_count += 1
        if review_status == "reviewed":
            reviewed_count += 1
        elif review_status == "returned":
            returned_count += 1
        if review and review.score is not None:
            normalized_scores.append(review.score / assignment.score_max * 100)
        profile_assignments.append(
            StudentProfileAssignmentItem(
                assignment=assignment,
                submission_id=current.id,
                submitted_at=current.submitted_at,
                round_no=current.round_no,
                review_status=review_status,
                score=review.score if review else None,
            )
        )

    return StudentProfileResponse(
        student_id=student_id,
        student_name=student.name if student else student_id,
        student_email=student.email if student else None,
        classroom=classroom,
        assignment_count=len(assignments),
        submitted_count=submitted_count,
        unsubmitted_count=len(assignments) - submitted_count,
        reviewed_count=reviewed_count,
        returned_count=returned_count,
        average_score_percent=(
            round(sum(normalized_scores) / len(normalized_scores), 1)
            if normalized_scores
            else None
        ),
        assignments=profile_assignments,
        timeline=timeline,
        round_progress=round_progress,
        trends=list(trends.values()),
        ai_help_type_distribution=help_distribution,
        ai_help_type_shift=help_shift,
        reflection_quality=reflection_quality,
        index_formula=_profile_index_formula(),
        insights=_build_profile_insights(timeline, round_progress, trends, help_shift, reflection_quality),
    )
