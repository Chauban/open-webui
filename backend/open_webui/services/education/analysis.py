import difflib
import re
from typing import Optional

from sqlalchemy.orm import Session

from open_webui.models.chats import Chats
from open_webui.models.chat_messages import ChatMessages
from open_webui.models.education import Education

# Bump whenever the provenance/highlight analysis logic changes so cached
# results produced by older logic are recomputed instead of served stale.
_ANALYSIS_LOGIC_VERSION = "2"

SOURCE_MAP_TYPES = {
    "ai_inserted",
    "ai_pasted",
    "user_typed",
    "external_paste",
    "suspected_unmarked_import",
    "unknown",
}


def _empty_process_summary() -> dict:
    return {
        "prompt_sent_count": 0,
        "assistant_message_received_count": 0,
        "ai_copy_button_clicked_count": 0,
        "ai_reply_selection_copied_count": 0,
        "ai_insert_clicked_count": 0,
        "paste_detected_count": 0,
        "large_burst_detected_count": 0,
        "delete_text_count": 0,
        "replace_text_count": 0,
        "version_saved_count": 0,
        "assignment_submitted_count": 0,
    }


def _build_process_summary(operations: list, prompt_timeline: list[dict], versions: list, bursts: list) -> dict:
    summary = _empty_process_summary()
    summary["prompt_sent_count"] = len([item for item in prompt_timeline if item.get("role") == "user"])
    summary["assistant_message_received_count"] = len(
        [item for item in prompt_timeline if item.get("role") == "assistant"]
    )
    summary["version_saved_count"] = len(versions)
    summary["assignment_submitted_count"] = 1
    summary["large_burst_detected_count"] = len(bursts)

    op_type_counts = {
        "ai_copy_button_clicked": "ai_copy_button_clicked_count",
        "ai_reply_selection_copied": "ai_reply_selection_copied_count",
        "ai_insert_clicked": "ai_insert_clicked_count",
        "platform_ai_insert": "ai_insert_clicked_count",
        "paste_detected": "paste_detected_count",
        "paste": "paste_detected_count",
        "delete_text": "delete_text_count",
        "delete": "delete_text_count",
        "replace_text": "replace_text_count",
        "replace": "replace_text_count",
    }
    for operation in operations:
        key = op_type_counts.get(operation.op_type)
        if key:
            summary[key] += 1

    return summary


def _clean_provenance_text(text: str) -> str:
    """Recover the visible text a segment actually contributed to the document.

    Stored AI segment text can still contain reasoning/<details> blocks and HTML
    that never reach the final note, so strip them and decode entities before
    matching or counting. Plain typed text is returned effectively unchanged.
    """
    if not text:
        return ""
    from html import unescape

    text = re.sub(r"<details[^>]*>.*?</details>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(
        r"<(think|thinking|reasoning)\b[^>]*>.*?</\1>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


class NormalizedSegment:
    """Read-only view over a provenance segment exposing cleaned visible text."""

    __slots__ = (
        "segment_id",
        "segment_text",
        "source_type",
        "source_message_id",
        "start_offset",
        "end_offset",
        "version_id",
        "metadata_json",
    )

    def __init__(self, segment):
        original = segment.segment_text or ""
        cleaned = _clean_provenance_text(original)
        self.segment_id = segment.segment_id
        self.segment_text = cleaned
        self.source_type = segment.source_type
        self.source_message_id = getattr(segment, "source_message_id", None)
        # Stored offsets refer to the original text; drop them when cleaning
        # changed the content so matching falls back to whitespace-tolerant search.
        changed = cleaned != original
        self.start_offset = None if changed else getattr(segment, "start_offset", None)
        self.end_offset = None if changed else getattr(segment, "end_offset", None)
        self.version_id = getattr(segment, "version_id", None)
        self.metadata_json = getattr(segment, "metadata_json", None)


def filter_segments_for_final_text(final_text: str, segments):
    remaining_text = final_text or ""
    filtered_segments = []

    def segment_priority(segment):
        source_priority = {
            "ai_inserted": 0,
            "ai_pasted": 1,
            "suspected_unmarked_import": 2,
            "user_typed": 3,
        }.get(segment.source_type, 4)
        return (source_priority, -len(segment.segment_text or ""))

    for segment in sorted(segments, key=segment_priority):
        if _is_low_signal_manual_segment(segment):
            continue
        segment_text = segment.segment_text or ""
        if not segment_text:
            continue
        # Whitespace-tolerant match: the snapshot text (from editor.getText) and
        # the stored segment_text can differ in block separators / line breaks
        # after the editor re-parses inserted HTML, so an exact find() drops
        # legitimate AI-inserted/pasted segments. Match ignoring whitespace.
        start, end = _find_ignoring_whitespace(remaining_text, segment_text)
        if start == -1:
            continue
        filtered_segments.append(segment)
        remaining_text = remaining_text[:start] + (" " * (end - start)) + remaining_text[end:]
    return filtered_segments


def _is_source_map_segment(segment) -> bool:
    metadata = segment.metadata_json or {}
    return metadata.get("provenance_kind") == "source_map"


def _make_highlight_segment(segment, final_text: str, start: int, end: int) -> dict:
    return {
        "segment_id": segment.segment_id,
        "segment_text": final_text[start:end],
        "source_type": segment.source_type,
        "start_offset": start,
        "end_offset": end,
        "metadata_json": segment.metadata_json,
    }


def _make_unknown_highlight(final_text: str, start: int, end: int) -> dict:
    return {
        "segment_id": f"unknown-{start}-{end}",
        "segment_text": final_text[start:end],
        "source_type": "unknown",
        "start_offset": start,
        "end_offset": end,
        "metadata_json": {"provenance_kind": "source_map"},
    }


def build_source_map_highlights(final_text: str, segments) -> Optional[list[dict]]:
    source_map_segments = []
    for segment in segments:
        if not _is_source_map_segment(segment):
            continue
        if segment.source_type not in SOURCE_MAP_TYPES:
            continue
        start = segment.start_offset
        end = segment.end_offset
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start < 0 or end <= start or end > len(final_text):
            continue
        if final_text[start:end] != (segment.segment_text or ""):
            continue
        source_map_segments.append(segment)

    if not source_map_segments:
        return None

    highlights: list[dict] = []
    cursor = 0
    for segment in sorted(source_map_segments, key=lambda item: (item.start_offset, item.end_offset)):
        start = segment.start_offset
        end = segment.end_offset
        if start < cursor:
            continue
        if cursor < start:
            highlights.append(_make_unknown_highlight(final_text, cursor, start))
        highlights.append(_make_highlight_segment(segment, final_text, start, end))
        cursor = end

    if cursor < len(final_text):
        highlights.append(_make_unknown_highlight(final_text, cursor, len(final_text)))

    return highlights


def _find_ignoring_whitespace(haystack: str, needle: str) -> tuple[int, int]:
    """Find ``needle`` inside ``haystack`` ignoring all whitespace differences.

    Returns the ``(start, end)`` span in the original ``haystack`` coordinates,
    or ``(-1, -1)`` when there is no match.
    """
    stripped_needle = re.sub(r"\s+", "", needle)
    if not stripped_needle:
        return (-1, -1)

    stripped = []
    index_map = []
    for index, char in enumerate(haystack):
        if not char.isspace():
            stripped.append(char)
            index_map.append(index)

    hit = "".join(stripped).find(stripped_needle)
    if hit == -1:
        return (-1, -1)

    start = index_map[hit]
    end = index_map[hit + len(stripped_needle) - 1] + 1
    return (start, end)


_MIN_MATCH_BLOCK = 8


def _match_segment_blocks(segment_text: str, final_text: str, consumed: list) -> list:
    """Locate the parts of ``final_text`` that originated from ``segment_text``.

    Uses sequence alignment (difflib) instead of exact search so that AI or
    typed content which was lightly edited after insertion is still attributed.
    Positions already claimed by higher-priority segments (``consumed``) are
    skipped to avoid double counting overlapping segments.
    """
    if not segment_text or not final_text:
        return []
    matcher = difflib.SequenceMatcher(None, segment_text, final_text, autojunk=False)
    blocks: list = []
    for match in matcher.get_matching_blocks():
        if match.size < _MIN_MATCH_BLOCK:
            continue
        run_start = None
        for position in range(match.b, match.b + match.size):
            if consumed[position]:
                if run_start is not None and position - run_start >= _MIN_MATCH_BLOCK:
                    blocks.append((run_start, position))
                run_start = None
            elif run_start is None:
                run_start = position
        block_end = match.b + match.size
        if run_start is not None and block_end - run_start >= _MIN_MATCH_BLOCK:
            blocks.append((run_start, block_end))
    return blocks


def _is_low_signal_manual_segment(segment) -> bool:
    if segment.source_type != "user_typed":
        return False

    text = (segment.segment_text or "").strip()
    if not text:
        return True
    if re.fullmatch(r"[A-Za-z]{1,3}", text):
        return True
    return len(text) < 2


def compute_stats(final_text: str, segments, prompt_count: int, version_count: int) -> dict:
    stats = {
        "total_chars": len(final_text or ""),
        "user_typed_chars": 0,
        "ai_inserted_chars": 0,
        "ai_pasted_chars": 0,
        "external_paste_chars": 0,
        "suspected_unmarked_import_chars": 0,
        "unknown_chars": 0,
        "prompt_count": prompt_count,
        "version_count": version_count,
    }
    for segment in segments:
        key = f"{segment.source_type}_chars"
        if key in stats:
            stats[key] += len(segment.segment_text or "")
    return stats


def compute_stats_from_highlights(
    final_text: str,
    highlights: list[dict],
    prompt_count: int,
    version_count: int,
) -> dict:
    stats = {
        "total_chars": len(final_text or ""),
        "user_typed_chars": 0,
        "ai_inserted_chars": 0,
        "ai_pasted_chars": 0,
        "external_paste_chars": 0,
        "suspected_unmarked_import_chars": 0,
        "unknown_chars": 0,
        "prompt_count": prompt_count,
        "version_count": version_count,
    }
    for segment in highlights:
        source_type = segment.get("source_type")
        segment_length = len(segment.get("segment_text") or "")
        if source_type == "user_typed":
            stats["user_typed_chars"] += segment_length
        else:
            key = f"{source_type}_chars"
            if key in stats:
                stats[key] += segment_length
    return stats


def _diff_text(previous_text: str, current_text: str) -> Optional[dict]:
    previous_text = previous_text or ""
    current_text = current_text or ""
    if previous_text == current_text:
        return None

    start = 0
    while start < len(previous_text) and start < len(current_text) and previous_text[start] == current_text[start]:
        start += 1

    previous_end = len(previous_text) - 1
    current_end = len(current_text) - 1
    while previous_end >= start and current_end >= start:
        if previous_text[previous_end] != current_text[current_end]:
            break
        previous_end -= 1
        current_end -= 1

    deleted_text = previous_text[start : previous_end + 1]
    inserted_text = current_text[start : current_end + 1]
    if inserted_text and deleted_text:
        change_type = "replace"
    elif inserted_text:
        change_type = "insert"
    else:
        change_type = "delete"

    return {
        "change_type": change_type,
        "start_offset": start,
        "end_offset": start + len(inserted_text),
        "inserted_text": inserted_text,
        "deleted_text": deleted_text,
        "inserted_length": len(inserted_text),
        "deleted_length": len(deleted_text),
        "net_growth": len(current_text) - len(previous_text),
    }


def build_version_diffs(versions, baseline_text: str = "") -> list[dict]:
    diffs: list[dict] = []
    previous_text = baseline_text
    for version in versions:
        diff = _diff_text(previous_text, version.note_snapshot_text or "")
        if diff is not None:
            diffs.append(
                {
                    "version_id": version.id,
                    "version_no": version.version_no,
                    "trigger_type": version.trigger_type,
                    "created_at": version.created_at,
                    **diff,
                }
            )
        previous_text = version.note_snapshot_text or ""
    return diffs


def _classify_rewrite_level(rewrite_ratio: int) -> str:
    if rewrite_ratio <= 10:
        return "unchanged"
    if rewrite_ratio <= 35:
        return "lightly_edited"
    if rewrite_ratio <= 65:
        return "moderately_rewritten"
    return "deeply_rewritten"


def _estimate_segment_retention(segment_text: str, final_text: str) -> dict:
    source_text = (segment_text or "").strip()
    final_text = final_text or ""
    if not source_text:
        return {
            "content_current": "",
            "final_retained_length": 0,
            "retained_ratio": 0,
            "rewrite_ratio": 100,
            "rewrite_level": "deeply_rewritten",
        }

    exact_index = final_text.find(source_text)
    if exact_index != -1:
        return {
            "content_current": source_text,
            "final_retained_length": len(source_text),
            "retained_ratio": 100,
            "rewrite_ratio": 0,
            "rewrite_level": "unchanged",
        }

    candidates = [final_text]
    candidates.extend([part.strip() for part in final_text.splitlines() if part.strip()])
    best_candidate = ""
    best_ratio = 0.0
    for candidate in candidates:
        ratio = difflib.SequenceMatcher(None, source_text, candidate).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_candidate = candidate

    match = difflib.SequenceMatcher(None, source_text, final_text).find_longest_match(
        0, len(source_text), 0, len(final_text)
    )
    final_retained_length = match.size
    retained_ratio = int(round((final_retained_length / max(len(source_text), 1)) * 100))
    rewrite_ratio = int(round((1 - best_ratio) * 100))
    return {
        "content_current": best_candidate if best_ratio >= 0.2 else "",
        "final_retained_length": final_retained_length,
        "retained_ratio": retained_ratio,
        "rewrite_ratio": rewrite_ratio,
        "rewrite_level": _classify_rewrite_level(rewrite_ratio),
    }


def _detect_large_bursts(version_diffs: list[dict], final_text: str, operations: list) -> list[dict]:
    bursts: list[dict] = []
    total_chars = max(len(final_text or ""), 1)
    for diff in version_diffs:
        inserted_length = diff.get("inserted_length", 0)
        inserted_ratio = inserted_length / total_chars
        if inserted_length < 120 and diff.get("net_growth", 0) < 80:
            continue

        nearby_operation = next(
            (
                operation
                for operation in operations
                if abs((operation.created_at or 0) - (diff.get("created_at") or 0)) <= 20
                and (operation.inserted_text or "")
            ),
            None,
        )
        bursts.append(
            {
                "event_type": "large_burst",
                "created_at": diff.get("created_at"),
                "version_id": diff.get("version_id"),
                "version_no": diff.get("version_no"),
                "operation_id": nearby_operation.id if nearby_operation else None,
                "inserted_length": inserted_length,
                "net_growth": diff.get("net_growth", 0),
                "inserted_ratio": round(inserted_ratio, 4),
                "source_inference": (nearby_operation.source_type if nearby_operation else "unknown"),
                "message": f"Large burst detected: +{inserted_length} chars in version {diff.get('version_no')}.",
            }
        )
    return bursts


def build_submission_analysis(submission, session, versions, provenance_segments, operations, prompt_timeline):
    final_text = (versions[-1].note_snapshot_text if versions else "") or ""
    provenance_segments = [NormalizedSegment(segment) for segment in provenance_segments]
    filtered_segments = filter_segments_for_final_text(final_text, provenance_segments)
    source_map_highlights = build_source_map_highlights(final_text, provenance_segments)
    version_diffs = build_version_diffs(versions)
    bursts = _detect_large_bursts(version_diffs, final_text, operations)

    operation_by_source: dict[str, object] = {}
    for operation in operations:
        operation_by_source[(operation.inserted_text or "").strip()] = operation

    analyzed_segments: list[dict] = []
    for segment in filtered_segments:
        if segment.source_type not in {"ai_inserted", "ai_pasted"}:
            continue
        retention = _estimate_segment_retention(segment.segment_text or "", final_text)
        source_operation = operation_by_source.get((segment.segment_text or "").strip())
        analyzed_segments.append(
            {
                "segment_id": segment.segment_id,
                "source_operation_id": (source_operation.id if source_operation else None),
                "origin_type": segment.source_type,
                "content_initial": segment.segment_text or "",
                "content_current": retention["content_current"],
                "first_seen_version_id": segment.version_id,
                "last_seen_version_id": submission.final_version_id,
                "initial_length": len(segment.segment_text or ""),
                "final_length": retention["final_retained_length"],
                "retained_ratio": retention["retained_ratio"],
                "rewrite_ratio": retention["rewrite_ratio"],
                "rewrite_level": retention["rewrite_level"],
                "suspicion_score": 0,
                "is_suspected_unmarked_import": False,
                "suspicion_reason": None,
                "metadata_json": segment.metadata_json or {},
            }
        )

    suspected_segments: list[dict] = []
    if source_map_highlights is None:
        for operation in operations:
            inserted_text = (operation.inserted_text or "").strip()
            if operation.source_type != "user_typed" or len(inserted_text) < 80:
                continue
            if operation.op_type not in {"keyboard_input", "replace", "paste"}:
                continue
            retention = _estimate_segment_retention(inserted_text, final_text)
            suspicion_score = min(
                100,
                int(
                    len(inserted_text) / 8
                    + retention["retained_ratio"] * 0.4
                    + (20 if operation.op_type != "keyboard_input" else 0)
                ),
            )
            if suspicion_score < 45:
                continue
            suspected_segments.append(
                {
                    "segment_id": f"suspected-{operation.id}",
                    "source_operation_id": operation.id,
                    "origin_type": "suspected_unmarked_import",
                    "content_initial": inserted_text,
                    "content_current": retention["content_current"] or inserted_text,
                    "first_seen_version_id": None,
                    "last_seen_version_id": submission.final_version_id,
                    "initial_length": len(inserted_text),
                    "final_length": retention["final_retained_length"],
                    "retained_ratio": retention["retained_ratio"],
                    "rewrite_ratio": retention["rewrite_ratio"],
                    "rewrite_level": retention["rewrite_level"],
                    "suspicion_score": suspicion_score,
                    "is_suspected_unmarked_import": True,
                    "suspicion_reason": "Large typed burst without explicit paste/AI source and with high final retention.",
                    "metadata_json": {
                        "batch_id": operation.batch_id,
                        "start_offset": operation.start_offset,
                        "end_offset": operation.end_offset,
                    },
                }
            )

    if source_map_highlights is not None:
        highlight_segments = source_map_highlights
    else:
        consumed = [False] * len(final_text)
        highlight_priority = {"ai_inserted": 0, "ai_pasted": 1, "user_typed": 2}
        highlight_segments = []
        for segment in sorted(
            (
                s
                for s in provenance_segments
                if s.source_type in highlight_priority
                and (s.segment_text or "")
                and not _is_low_signal_manual_segment(s)
            ),
            key=lambda s: (
                highlight_priority[s.source_type],
                -len(s.segment_text or ""),
            ),
        ):
            for block_start, block_end in _match_segment_blocks(segment.segment_text or "", final_text, consumed):
                for position in range(block_start, block_end):
                    consumed[position] = True
                highlight_segments.append(
                    {
                        "segment_id": segment.segment_id,
                        "segment_text": final_text[block_start:block_end],
                        "source_type": segment.source_type,
                        "start_offset": block_start,
                        "end_offset": block_end,
                        "metadata_json": segment.metadata_json,
                    }
                )
        highlight_segments.extend(
            [
                {
                    "segment_id": segment["segment_id"],
                    "segment_text": segment["content_current"] or segment["content_initial"],
                    "source_type": "suspected_unmarked_import",
                    "start_offset": None,
                    "end_offset": None,
                    "metadata_json": {
                        "suspicion_score": segment["suspicion_score"],
                        "suspicion_reason": segment["suspicion_reason"],
                    },
                }
                for segment in suspected_segments
            ]
        )

    typed_chars = 0
    ai_inserted_chars = 0
    ai_pasted_chars = 0
    external_paste_chars = 0
    suspected_chars = 0
    unknown_chars = 0
    source_mapped_chars = 0
    for segment in highlight_segments:
        segment_length = len(segment.get("segment_text") or "")
        source_mapped_chars += segment_length
        if segment["source_type"] == "user_typed":
            typed_chars += segment_length
        elif segment["source_type"] == "ai_inserted":
            ai_inserted_chars += segment_length
        elif segment["source_type"] == "ai_pasted":
            ai_pasted_chars += segment_length
        elif segment["source_type"] == "external_paste":
            external_paste_chars += segment_length
            suspected_chars += segment_length
        elif segment["source_type"] == "suspected_unmarked_import":
            suspected_chars += segment_length
        elif segment["source_type"] == "unknown":
            unknown_chars += segment_length

    if source_map_highlights is None:
        typed_chars = max(
            len(final_text) - ai_inserted_chars - ai_pasted_chars - suspected_chars,
            0,
        )
        source_mapped_chars = min(source_mapped_chars + typed_chars, len(final_text))

    imported_segments = analyzed_segments + suspected_segments
    average_rewrite_ratio = (
        int(round(sum(segment["rewrite_ratio"] for segment in imported_segments) / len(imported_segments)))
        if imported_segments
        else 0
    )
    process_summary = _build_process_summary(operations, prompt_timeline, versions, bursts)

    timeline = [
        {
            "event_type": "version",
            "created_at": version.created_at,
            "version_id": version.id,
            "version_no": version.version_no,
            "label": f"Version {version.version_no}",
            "trigger_type": version.trigger_type,
        }
        for version in versions
    ]
    timeline.extend(
        [
            {
                "event_type": "source_operation",
                "created_at": operation.created_at,
                "operation_id": operation.id,
                "op_type": operation.op_type,
                "source_type": operation.source_type,
                "inserted_length": len((operation.inserted_text or "").strip()),
                "label": f"{operation.source_type}:{operation.op_type}",
            }
            for operation in operations
            if operation.op_type
        ]
    )
    timeline.extend(bursts)
    timeline.append(
        {
            "event_type": "submit",
            "created_at": submission.submitted_at,
            "version_id": submission.final_version_id,
            "label": "Submission",
        }
    )
    timeline.sort(key=lambda item: item.get("created_at") or 0)

    return {
        "summary": {
            "total_chars": len(final_text),
            "typed_chars": typed_chars,
            "typed_ratio": round(typed_chars / max(len(final_text), 1), 4),
            "ai_inserted_chars": ai_inserted_chars,
            "ai_inserted_ratio": round(ai_inserted_chars / max(len(final_text), 1), 4),
            "ai_pasted_chars": ai_pasted_chars,
            "ai_pasted_ratio": round(ai_pasted_chars / max(len(final_text), 1), 4),
            "external_paste_chars": external_paste_chars,
            "external_paste_ratio": round(external_paste_chars / max(len(final_text), 1), 4),
            "suspected_unmarked_import_chars": suspected_chars,
            "suspected_unmarked_import_count": (
                len(
                    [
                        segment
                        for segment in highlight_segments
                        if segment["source_type"] in {"external_paste", "suspected_unmarked_import"}
                    ]
                )
                if source_map_highlights is not None
                else len(suspected_segments)
            ),
            "unknown_chars": unknown_chars,
            "unknown_ratio": round(unknown_chars / max(len(final_text), 1), 4),
            "source_mapped_chars": source_mapped_chars,
            "source_mapped_ratio": round(source_mapped_chars / max(len(final_text), 1), 4),
            "burst_count": len(bursts),
            "average_rewrite_ratio": average_rewrite_ratio,
            "prompt_count": process_summary["prompt_sent_count"],
            "version_count": len(versions),
            "process_summary": process_summary,
        },
        "logic_version": _ANALYSIS_LOGIC_VERSION,
        "highlights": highlight_segments,
        "segments": analyzed_segments + suspected_segments,
        "timeline": timeline,
        "version_diffs": version_diffs,
    }


def _versions_up_to(versions, final_version_id: Optional[str]) -> list:
    for index, version in enumerate(versions):
        if version.id == final_version_id:
            return versions[: index + 1]
    return versions


def _is_analysis_payload_usable(submission, payload: Optional[dict]) -> bool:
    """存档的分析结果还能不能直接用。

    历史轮是一条记录,不是一个派生视图:它依赖的 provenance(source map 按会话
    整体覆盖)已经被后续轮次改写,重算只会算错。所以只要历史轮有存档就一律直接
    返回,哪怕 logic_version 已经升级 —— payload 里带着 logic_version,调用方
    自己知道这份结果由哪一版逻辑算出。当前轮才跟着 logic_version 走。

    (真要对历史轮做追溯重算,payload 里的 highlights 已经是那一轮终稿的完整
    分段来源,不需要再回头找 provenance_segment 表。)
    """
    if not payload:
        return False
    if submission.is_current != 1:
        return True
    return payload.get("logic_version") == _ANALYSIS_LOGIC_VERSION


async def get_or_build_submission_analysis(
    submission,
    session,
    db: Session,
    cached_payloads: Optional[dict] = None,
) -> dict:
    """取一份提交的分析结果。

    ``cached_payloads`` 由调用方批量预取(见 ``get_or_build_submission_analyses``);
    传 None 表示这里自己查一次。
    """
    if cached_payloads is None:
        cached = Education.get_analysis_result(session.id, "submission_analysis", submission_id=submission.id, db=db)
        payload = cached.payload_json if cached is not None else None
    else:
        payload = cached_payloads.get(submission.id)

    if _is_analysis_payload_usable(submission, payload):
        return payload

    # 分析的终稿必须停在本轮的定稿版本上:重交会往同一个会话继续追加版本,
    # 拿 versions[-1] 会让历史轮的分析读到后面几轮的正文。
    versions = _versions_up_to(Education.get_versions(session.id, db=db), submission.final_version_id)
    provenance_segments = Education.get_provenance_segments(session.id, db=db)
    operations = Education.get_editor_operations(session.id, db=db)
    prompt_timeline = await get_prompt_timeline(session, db)
    payload = build_submission_analysis(
        submission,
        session,
        versions,
        provenance_segments,
        operations,
        prompt_timeline,
    )
    Education.upsert_analysis_result(
        session.id,
        "submission_analysis",
        payload,
        submission_id=submission.id,
        db=db,
    )
    return payload


async def get_or_build_submission_analyses(submissions: list, sessions: dict, db: Session) -> dict[str, dict]:
    """批量版本:存档一次查完,只有缺失/过期的那几份才真正重算。

    看板、班级进度、学生画像都要对几十份提交取分析,逐份查缓存就是 N 次查询。
    """
    cached_payloads = Education.get_analysis_results_by_submission_ids(
        [submission.id for submission in submissions],
        "submission_analysis",
        db=db,
    )
    analyses: dict[str, dict] = {}
    for submission in submissions:
        session = sessions.get(submission.writing_session_id)
        if session is None:
            continue
        analyses[submission.id] = await get_or_build_submission_analysis(
            submission, session, db, cached_payloads=cached_payloads
        )
    return analyses


def empty_risk_summary() -> dict:
    return {
        "submission_count": 0,
        "ai_inserted_chars": 0,
        "ai_pasted_chars": 0,
        "suspected_unmarked_import_count": 0,
        "burst_count": 0,
        "average_rewrite_ratio": 0,
    }


def accumulate_risk_summary(summary: dict, analysis_summary: Optional[dict]) -> dict:
    if not analysis_summary:
        return summary
    summary["submission_count"] += 1
    summary["ai_inserted_chars"] += analysis_summary.get("ai_inserted_chars", 0)
    summary["ai_pasted_chars"] += analysis_summary.get("ai_pasted_chars", 0)
    summary["suspected_unmarked_import_count"] += analysis_summary.get("suspected_unmarked_import_count", 0)
    summary["burst_count"] += analysis_summary.get("burst_count", 0)
    summary["average_rewrite_ratio"] += analysis_summary.get("average_rewrite_ratio", 0)
    return summary


def finalize_risk_summary(summary: dict) -> dict:
    submission_count = max(summary.get("submission_count", 0), 0)
    average_rewrite_ratio = (
        int(round(summary.get("average_rewrite_ratio", 0) / submission_count)) if submission_count else 0
    )
    return {
        **summary,
        "average_rewrite_ratio": average_rewrite_ratio,
    }


def _get_chat_history_messages(chat) -> list[dict]:
    if chat is None:
        return []

    chat_payload = getattr(chat, "chat", None) or {}
    history = chat_payload.get("history") or {}
    messages = history.get("messages") or {}
    current_id = history.get("currentId")
    ordered_messages = []
    visited = set()

    while current_id and current_id in messages and current_id not in visited:
        message = messages[current_id]
        ordered_messages.append(message)
        visited.add(current_id)
        current_id = message.get("parentId")

    ordered_messages.reverse()
    return ordered_messages


async def get_prompt_timeline(session, db: Session) -> list[dict]:
    chat_ids: list[str] = []

    if session.folder_id:
        folder_chats = await Chats.get_chats_by_folder_id_and_user_id(session.folder_id, session.owner_user_id, db=db)
        chat_ids = [chat.id for chat in folder_chats]
    elif session.chat_id:
        chat_ids = [session.chat_id]

    prompt_timeline = []
    for chat_id in chat_ids:
        chat_messages = await ChatMessages.get_messages_by_chat_id(chat_id, db=db)
        if chat_messages:
            prompt_timeline.extend(
                [
                    {
                        "id": message.id,
                        "role": message.role,
                        "content": message.content,
                        "created_at": message.created_at,
                    }
                    for message in chat_messages
                ]
            )
            continue

        chat = await Chats.get_chat_by_id(chat_id, db=db)
        prompt_timeline.extend(
            [
                {
                    "id": message.get("id"),
                    "role": message.get("role"),
                    "content": message.get("content"),
                    "created_at": message.get("timestamp"),
                }
                for message in _get_chat_history_messages(chat)
            ]
        )

    prompt_timeline.sort(key=lambda item: item.get("created_at") or 0)
    return prompt_timeline
