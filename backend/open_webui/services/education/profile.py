from typing import Optional

from open_webui.models.education import (
    StudentProfileCollaborationFormula,
    StudentProfileFormulaTerm,
    StudentProfileHelpTypeShift,
    StudentProfileHelpTypeSummary,
    StudentProfileIndexFormula,
    StudentProfileInsight,
    StudentProfileMetricTrend,
    StudentProfileProcessFormula,
    StudentProfileReflectionQuality,
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
# 教师给的 1—5 分折算到 0—100,好让它和其他比率型指标同尺度参与合成。
_REFLECTION_TEACHER_SCORE_MIN = 1
_REFLECTION_TEACHER_SCORE_MAX = 5
_PROFILE_MAX_INSIGHTS = 5
_TREND_FLAT_TOLERANCE = 0.05
_TREND_MIN_SAMPLES = 3
_TREND_MAX_WINDOW = 3
PROFILE_METRIC_VERSION = "2026-09-07.1"
PROFILE_INSIGHT_VERSION = "2026-09-03.1"

_INSIGHT_META = {
    "not_enough_data": ("low", 5, "all"),
    "digestion_up": ("low", 4, "source"),
    "digestion_low": ("high", 5, "source"),
    "ai_share_changed": ("low", 3, "source"),
    "round_improvement": ("low", 5, "round"),
    "round_revision_thin": ("high", 5, "round"),
    "help_type_shift_refining": ("low", 4, "source"),
    "deadline_rush": ("high", 5, "version"),
    "process_up": ("low", 4, "process"),
    "reflection_thin": ("medium", 5, "reflection"),
    "ai_revision_productive": ("low", 5, "combined"),
    "ai_use_needs_review": ("high", 5, "combined"),
}
_INSIGHT_SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

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

def _profile_index_formula() -> StudentProfileIndexFormula:
    """把两个合成指数的构成如实返回。

    只发给教师端 —— 教师要能逐项核对、向学生解释这个分怎么来的。学生端不给,
    阈值一旦公开就是一份刷分说明书(改够三成、写满三天、问够十条),学生看到的
    是自己的指标值与趋势。
    """
    return StudentProfileIndexFormula(
        process_index=StudentProfileProcessFormula(
            revision_depth=StudentProfileFormulaTerm(
                metric="revised_chars / inserted_chars",
                target=_PROCESS_TARGET_REVISION_RATIO,
                weight=1 / 3,
            ),
            span_effort=StudentProfileFormulaTerm(
                metric="writing_span_seconds",
                target=_PROCESS_TARGET_SPAN_SECONDS,
                weight=1 / 3,
            ),
            pacing=StudentProfileFormulaTerm(
                metric="end_loaded_ratio", inverted=True, weight=1 / 3
            ),
        ),
        collaboration_index=StudentProfileCollaborationFormula(
            digestion=StudentProfileFormulaTerm(
                metric="digestion_ratio", weight=1 / 3
            ),
            inquiry=StudentProfileFormulaTerm(
                metric="prompt_count",
                target=_COLLABORATION_TARGET_PROMPTS,
                weight=1 / 3,
            ),
            reflection=StudentProfileFormulaTerm(
                metric="reflection_quality", weight=1 / 3
            ),
        ),
    )


def _reflection_quality_from_review(reflection_score: Optional[int]) -> Optional[int]:
    """教师给的 1—5 分折算成 0—100;没批改就是空,不折算成 0。"""
    if reflection_score is None:
        return None
    span = _REFLECTION_TEACHER_SCORE_MAX - _REFLECTION_TEACHER_SCORE_MIN
    ratio = (reflection_score - _REFLECTION_TEACHER_SCORE_MIN) / span
    return int(round(min(max(ratio, 0.0), 1.0) * 100))


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
    digestion_ratio: Optional[int],
    prompt_count: Optional[int],
    reflection_quality: Optional[int],
    ai_ratio: Optional[float],
    ai_used: bool,
) -> Optional[int]:
    # 反思质量来自教师批改,批改之前这一维就是空的 —— 未批改的提交本来也还没有
    # 完整评价,留空比先给个假分诚实。
    if reflection_quality is None:
        return None

    # 没用 AI 的提交不该被「消化度 0」拖成低分,这一维退化为只看反思质量。
    if not ai_used:
        return int(round(reflection_quality))

    if digestion_ratio is None or prompt_count is None or ai_ratio is None:
        return None

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


def _summarize_help_types(points: list) -> StudentProfileHelpTypeSummary:
    generative = 0
    refining = 0
    for point in points:
        for help_type in point.ai_help_types:
            if help_type in _AI_HELP_GENERATIVE_TYPES:
                generative += 1
            elif help_type in _AI_HELP_REFINING_TYPES:
                refining += 1
    total = generative + refining
    return StudentProfileHelpTypeSummary(
        generative=generative,
        refining=refining,
        refining_ratio=round(refining / total, 4) if total else None,
    )


def _point_completeness_ratio(point) -> float:
    statuses = [
        point.data_completeness.version_data,
        point.data_completeness.editor_operations,
        point.data_completeness.source_tracking,
    ]
    if point.data_completeness.scoring not in {"pending", "not_applicable"}:
        statuses.append(point.data_completeness.scoring)
    return sum(status == "complete" for status in statuses) / len(statuses)


def _insight_evidence_codes(evidence_kind: str) -> list[str]:
    codes = {
        "all": ["sample_size"],
        "source": ["sample_size", "source_evidence"],
        "version": ["sample_size", "version_evidence"],
        "process": ["sample_size", "version_evidence", "editor_evidence"],
        "reflection": ["sample_size", "reflection_evidence"],
        "round": ["round_evidence", "scoring_evidence"],
        "combined": [
            "sample_size",
            "version_evidence",
            "source_evidence",
            "scoring_evidence",
            "reflection_evidence",
        ],
    }
    return codes[evidence_kind]


def _build_profile_insights(
    timeline: list,
    round_progress: list,
    trends: dict,
    help_shift: StudentProfileHelpTypeShift,
    reflection_quality: StudentProfileReflectionQuality,
) -> list[StudentProfileInsight]:
    candidates: list[StudentProfileInsight] = []
    assignment_sample_count = len(
        {point.assignment_id for point in timeline if point.is_current}
    )
    if assignment_sample_count < _TREND_MIN_SAMPLES:
        candidates.append(
            StudentProfileInsight(
                code="not_enough_data",
                tone="neutral",
                action_code="complete_more_submissions",
                confidence=1,
                sample_count=assignment_sample_count,
                data_completeness=0,
                teaching_value=5,
                priority_score=15,
                evidence_codes=["sample_size"],
            )
        )
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
                action_code="keep_rewriting_ai_text",
            )
        )
    elif (
        latest.ai_ratio is not None
        and latest.digestion_ratio is not None
        and latest.ai_ratio >= 0.3
        and latest.digestion_ratio < 20
    ):
        candidates.append(
            StudentProfileInsight(
                code="digestion_low",
                tone="warning",
                params={
                    "digestion_ratio": latest.digestion_ratio,
                    "ai_ratio": latest.ai_ratio,
                },
                action_code="rewrite_one_ai_section",
                submission_id=latest.submission_id,
            )
        )

    ai_ratio = trends.get("ai_ratio")
    if ai_ratio is not None and abs(ai_ratio.delta) >= 0.15:
        candidates.append(
            StudentProfileInsight(
                code="ai_share_changed",
                tone="neutral",
                params={"delta": ai_ratio.delta, "last": ai_ratio.last},
                action_code="review_ai_use_pattern",
                submission_id=latest.submission_id,
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
                action_code="reuse_successful_revision",
            )
        )
    elif round_progress and all(item.revision_ratio < 10 for item in round_progress):
        candidates.append(
            StudentProfileInsight(
                code="round_revision_thin",
                tone="warning",
                params={"revision_ratio": max(item.revision_ratio for item in round_progress)},
                action_code="revise_feedback_deeply",
                submission_id=latest.submission_id,
            )
        )

    if (
        help_shift.refining_ratio_delta is not None
        and help_shift.refining_ratio_delta >= 0.2
    ):
        candidates.append(
            StudentProfileInsight(
                code="help_type_shift_refining",
                tone="positive",
                params={"delta": help_shift.refining_ratio_delta},
                action_code="continue_refining_own_writing",
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
                action_code="start_next_assignment_earlier",
                submission_id=latest.submission_id,
            )
        )

    process = trends.get("process_index")
    if process is not None and process.direction == "up":
        candidates.append(
            StudentProfileInsight(
                code="process_up",
                tone="positive",
                params={"delta": process.delta, "last": process.last},
                action_code="keep_current_process",
            )
        )

    if (
        reflection_quality.average_score is not None
        and reflection_quality.average_score < 40
    ):
        candidates.append(
            StudentProfileInsight(
                code="reflection_thin",
                tone="warning",
                params={"average_score": reflection_quality.average_score},
                action_code="add_specific_reflection_evidence",
                submission_id=latest.submission_id,
            )
        )

    score_trend = trends.get("normalized_score")
    latest_round = round_progress[-1] if round_progress else None
    score_improved = bool(
        (score_trend is not None and score_trend.direction == "up")
        or (latest_round and latest_round.score_delta is not None and latest_round.score_delta > 0)
    )
    score_not_improved = bool(
        (score_trend is not None and score_trend.direction in {"flat", "down"})
        or (latest_round and latest_round.score_delta is not None and latest_round.score_delta <= 0)
    )
    if (
        latest.ai_ratio is not None
        and latest.ai_ratio >= 0.1
        and latest.digestion_ratio is not None
        and latest.digestion_ratio >= 50
        and latest.reflection_quality is not None
        and latest.reflection_quality >= 60
        and latest.revision_depth is not None
        and latest.revision_depth >= 40
        and score_improved
    ):
        candidates.append(
            StudentProfileInsight(
                code="ai_revision_productive",
                tone="positive",
                params={
                    "ai_ratio": latest.ai_ratio,
                    "digestion_ratio": latest.digestion_ratio,
                    "revision_depth": latest.revision_depth,
                    "reflection_quality": latest.reflection_quality,
                    "normalized_score": latest.normalized_score,
                    "score_delta": latest_round.score_delta if latest_round else None,
                },
                action_code="repeat_productive_ai_revision",
                submission_id=latest.submission_id,
            )
        )
    elif (
        latest.ai_ratio is not None
        and latest.ai_ratio >= 0.3
        and latest.digestion_ratio is not None
        and latest.digestion_ratio < 30
        and latest.reflection_quality is not None
        and latest.reflection_quality < 50
        and latest.revision_depth is not None
        and latest.revision_depth < 20
        and score_not_improved
    ):
        candidates.append(
            StudentProfileInsight(
                code="ai_use_needs_review",
                tone="warning",
                params={
                    "ai_ratio": latest.ai_ratio,
                    "digestion_ratio": latest.digestion_ratio,
                    "revision_depth": latest.revision_depth,
                    "reflection_quality": latest.reflection_quality,
                    "normalized_score": latest.normalized_score,
                    "score_delta": latest_round.score_delta if latest_round else None,
                },
                action_code="reduce_ai_share_and_deepen_revision",
                submission_id=latest.submission_id,
            )
        )

    def evidence_for(insight):
        _, _, evidence_kind = _INSIGHT_META[insight.code]
        if insight.code == "not_enough_data":
            relevant = [point for point in timeline if point.is_current]
            completeness = (
                sum(_point_completeness_ratio(point) for point in relevant)
                / len(relevant)
                if relevant
                else 0
            )
            return insight.model_copy(
                update={
                    "severity": "low",
                    "confidence": 1,
                    "sample_count": assignment_sample_count,
                    "data_completeness": round(completeness, 2),
                    "teaching_value": 5,
                    "priority_score": 15,
                    "evidence_codes": ["sample_size"],
                }
            )
        if evidence_kind == "round":
            count = len(round_progress)
            completeness = (
                sum(
                    int(item.score_delta is not None) + int(item.revision_ratio >= 0)
                    for item in round_progress
                )
                / (count * 2)
                if count
                else 0
            )
        else:
            if evidence_kind == "combined":
                relevant = [
                    point
                    for point in timeline
                    if point.data_completeness.source_tracking == "complete"
                    and point.data_completeness.version_data == "complete"
                    and point.data_completeness.scoring == "complete"
                ]
            elif evidence_kind == "source":
                relevant = [
                    point
                    for point in timeline
                    if point.data_completeness.source_tracking == "complete"
                ]
            elif evidence_kind == "version":
                relevant = [
                    point
                    for point in timeline
                    if point.data_completeness.version_data == "complete"
                ]
            elif evidence_kind == "process":
                relevant = [
                    point
                    for point in timeline
                    if point.data_completeness.version_data == "complete"
                    and point.data_completeness.editor_operations == "complete"
                ]
            else:
                relevant = timeline
            count = len(relevant)
            completeness = (
                sum(_point_completeness_ratio(point) for point in relevant)
                / count
                if count
                else 0
            )
        confidence = min(count / _TREND_MIN_SAMPLES, 1.0) * completeness
        severity, teaching_value, _ = _INSIGHT_META[insight.code]
        priority_score = (
            _INSIGHT_SEVERITY_WEIGHT[severity] * 10
            + teaching_value * 2
            + confidence
        )
        return insight.model_copy(
            update={
                "severity": severity,
                "confidence": round(confidence, 2),
                "sample_count": count,
                "data_completeness": round(completeness, 2),
                "teaching_value": teaching_value,
                "priority_score": round(priority_score, 2),
                "evidence_codes": _insight_evidence_codes(evidence_kind),
            }
        )

    enriched = [evidence_for(insight) for insight in candidates]
    enriched.sort(
        key=lambda insight: insight.priority_score,
        reverse=True,
    )
    return enriched[:_PROFILE_MAX_INSIGHTS]
