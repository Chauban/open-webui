"""Read-only summaries of historical frozen revision checklists.

New revision coaching uses revision_reading.py. Historical decisions remain facts,
never regenerated or converted into new reading records.
"""
from typing import Optional
from open_webui.models.education import RevisionItemModel


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


def _snapshot_items(stats_json: Optional[dict]) -> Optional[list[dict]]:
    block = (stats_json or {}).get("revision_items") or {}
    if block.get("status") != "ready":
        return None
    return list(block.get("items") or [])


def is_same_as_draft(final_text: Optional[str], baseline_text: Optional[str]) -> bool:
    """终稿与初稿逐字相同(只忽略空白)。只回答改没改,不回答改得好不好。"""
    return "".join((final_text or "").split()) == "".join((baseline_text or "").split())


def summarize_revision_snapshot(
    stats_json: Optional[dict], unchanged_from_draft: bool
) -> Optional[dict]:
    """提交列表上一行的修改清单概况。数据是提交时冻存的那一轮,不重算。

    claimed_untouched:学生说「改了」、第一次通读引用的那句却原样还在——
    给老师的是「去看一眼」的提示,不是判定(学生可能在别处改了同一个问题)。
    """
    if stats_json is not None and 'revision_readings' in stats_json:
        return {'reading_count': len(stats_json['revision_readings']), 'unchanged_from_draft': unchanged_from_draft}
    items = _snapshot_items(stats_json)
    if items is None:
        return None
    problems = [item for item in items if item.get("status") == "problem"]
    decisions = {"revised": 0, "partly": 0, "kept": 0}
    for item in problems:
        if item.get("decision") in decisions:
            decisions[item["decision"]] += 1
    return {
        "problem_count": len(problems),
        "minor_count": len([item for item in items if item.get("status") == "minor"]),
        "decisions": decisions,
        "claimed_untouched": len(
            [
                item
                for item in problems
                if item.get("decision") == "revised" and item.get("quote_unchanged")
            ]
        ),
        "unchanged_from_draft": unchanged_from_draft,
    }


def build_first_read_distribution(
    assignment, submissions, unchanged_by_submission: dict[str, bool]
) -> Optional[dict]:
    """全班的第一次通读汇总:每个评分维度多少人要改、学生怎么处理的。

    回答的是「这个班普遍卡在哪一项、改了没有」,按人数算;每个学生只取最新一轮。
    没有任何一份带修改清单的提交就返回 None,看板不摆空区块。
    """
    if assignment.task_mode != "revise_draft":
        return None
    latest: dict[str, object] = {}
    for submission in submissions:
        current = latest.get(submission.student_id)
        if current is None or submission.round_no > current.round_no:
            latest[submission.student_id] = submission

    labels = {
        criterion.key: criterion.label for criterion in assignment.rubric_schema.criteria
    }
    rows = {
        key: {
            "criterion_key": key,
            "label": label,
            "statuses": {"problem": 0, "minor": 0, "ok": 0, "deferred": 0},
            "decisions": {"revised": 0, "partly": 0, "kept": 0},
            "claimed_untouched": 0,
        }
        for key, label in labels.items()
    }
    counted = 0
    for submission in latest.values():
        items = _snapshot_items(submission.stats_json)
        if items is None:
            continue
        counted += 1
        for item in items:
            row = rows.get(item.get("criterion_key"))
            if row is None:
                continue
            status = item.get("status")
            if status in row["statuses"]:
                row["statuses"][status] += 1
            if status == "problem":
                decision = item.get("decision")
                if decision in row["decisions"]:
                    row["decisions"][decision] += 1
                if decision == "revised" and item.get("quote_unchanged"):
                    row["claimed_untouched"] += 1
    if counted == 0:
        return None
    return {
        "submission_count": counted,
        "unchanged_from_draft_count": len(
            [
                submission
                for submission in latest.values()
                if unchanged_by_submission.get(submission.id)
            ]
        ),
        # 要改的人多的维度排前面:老师第一眼看到的就是这个班最该讲的那一项。
        "criteria": sorted(
            rows.values(), key=lambda row: -row["statuses"]["problem"]
        ),
    }
