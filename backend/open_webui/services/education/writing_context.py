"""写作会话的初稿基线与左侧对话上下文。

修订初稿作业(task_mode=revise_draft)里,学生先显式提交课外写好的初稿,冻结为
基线后才能编辑正文、和 AI 对话。左侧对话每一轮都带上右侧编辑器里此刻的正文:
文件夹的 system_prompt 是建作业时一次性生成的静态内容,装不下实时正文;
靠模型自己调 view_note 工具去读,国产模型又调不可靠。
"""

import html

from open_webui.models.education import Education

# 与 routers/education.py 的 PROJECT_MODE_* 取值一致。
_WRITING_FOLDER_MODES = ("assignment_writing", "personal_writing")


def is_draft_baseline_missing(session, db=None) -> bool:
    """修订初稿作业还没交初稿:不能编辑正文,也不能和 AI 对话。"""
    if session.scope != "assignment" or session.draft_baseline_at is not None:
        return False
    assignment = Education.get_assignment_by_id(session.assignment_id, db=db)
    return assignment is not None and assignment.task_mode == "revise_draft"


def normalize_draft_paragraphs(text: str) -> list[str]:
    """按行切段,去掉首尾空白(含全角空格)和空行。

    编辑器的纯文本是 getText({blockSeparator: '\\n'}),纯段落文档里就是各段用
    一个换行相连;基线、笔记 md 与 source map 都用这个形式,前端载入后逐字对得上。
    """

    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def build_draft_note_content(paragraphs: list[str]) -> dict:
    return {
        "json": {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": line}]}
                for line in paragraphs
            ],
        },
        "html": "".join(f"<p>{html.escape(line)}</p>" for line in paragraphs),
        "md": "\n".join(paragraphs),
    }


def get_folder_writing_session(folder, user_id: str):
    """写作区文件夹对应的写作会话;不是写作区文件夹或会话不属于该用户时返回 None。"""

    meta = folder.meta or {}
    if meta.get("mode") not in _WRITING_FOLDER_MODES:
        return None
    session_id = meta.get("writing_session_id")
    if not session_id:
        return None
    session = Education.get_writing_session_by_id(session_id)
    if session is None or session.owner_user_id != user_id:
        return None
    return session
