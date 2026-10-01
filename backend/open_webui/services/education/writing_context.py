"""写作会话的初稿基线与左侧对话上下文。

修订初稿作业(task_mode=revise_draft)里,学生先显式提交课外写好的初稿,冻结为
基线后才能编辑正文、和 AI 对话。左侧对话每一轮都带上右侧编辑器里此刻的正文:
文件夹的 system_prompt 是建作业时一次性生成的静态内容,装不下实时正文;
靠模型自己调 view_note 工具去读,国产模型又调不可靠。
"""

import html
import io
import os
import zipfile

from open_webui.models.education import Education
from open_webui.models.notes import Notes

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


# 初稿文件上限。几千字的论文 docx 通常不到 100KB,大的多半是嵌了图片。
DRAFT_FILE_MAX_BYTES = 10 * 1024 * 1024


class DraftFileError(ValueError):
    """文件读不出初稿正文;消息是给学生看的 i18n 键。"""


def extract_draft_text(filename: str, data: bytes) -> str:
    """从学生上传的初稿文件里取出纯文本,一段一行。

    只解析不存档:文件内容不落盘、不进文件库,学生核对后照常走「确认初稿」。
    只收 .docx 和纯文本。旧版 .doc 是二进制格式,让学生另存为 .docx;
    PDF 不收,中文 PDF 抽出来每个视觉行都断成一段,学生得逐段拼回去。
    """

    if len(data) > DRAFT_FILE_MAX_BYTES:
        raise DraftFileError("The file is too large")
    suffix = os.path.splitext(filename or "")[1].lower()
    if suffix == ".docx":
        text = _extract_docx_text(data)
    elif suffix in (".txt", ".md"):
        text = _decode_plain_text(data)
    elif suffix == ".doc":
        raise DraftFileError("Old .doc files are not supported, save it as .docx")
    else:
        raise DraftFileError("Only .docx, .txt and .md files are supported")
    text = "\n".join(normalize_draft_paragraphs(text))
    if not text:
        raise DraftFileError("No text found in this file")
    return text


def _extract_docx_text(data: bytes) -> str:
    from docx import Document

    try:
        document = Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as err:
        raise DraftFileError("Could not read this file") from err
    # 只取正文段落:页眉页脚、文本框、表格不是论文正文。
    # 段内软回车(Shift+Enter)python-docx 给的是 \n,随后按行切段。
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _decode_plain_text(data: bytes) -> str:
    # Windows 记事本存的中文 txt 常是 GBK。
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DraftFileError("Could not read this file")


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


async def build_current_text_context(session) -> str:
    """要追加到系统提示末尾的学生当前正文。

    笔记用自己的短会话读取,读完即释放,不把数据库事务带进之后的模型调用。
    """

    note = await Notes.get_note_by_id(session.note_id)
    content = ((note.data or {}).get("content") or {}) if note else {}
    text = (content.get("md") or "").strip()
    if not text:
        return "【学生当前正文】右侧编辑器里还没有内容。"
    return (
        "【学生当前正文】以下是学生右侧编辑器里此刻的全文，每轮对话都会更新。"
        "学生会边聊边改稿，所以它可能和你之前回复里引用过的句子不一样："
        "那是改动前的旧版本，不是你记错了。谈论正文时一律以这一版为准，"
        "学生说改过了，就对照这一版看他改了什么。\n"
        f"<<<\n{text}\n>>>"
    )
