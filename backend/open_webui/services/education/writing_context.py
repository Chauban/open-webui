"""写作会话的初稿基线与左侧对话上下文。

修订初稿作业(task_mode=revise_draft)里,学生先显式提交课外写好的初稿,冻结为
基线后才能编辑正文、和 AI 对话。左侧对话每一轮都带上右侧编辑器最近一次保存的正文:
文件夹的 system_prompt 是建作业时一次性生成的静态内容,装不下实时正文;
靠模型自己调 view_note 工具去读,国产模型又调不可靠。
"""

import html
import io
import os
import zipfile

from open_webui.models.chat_messages import ChatMessages
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


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class DraftFileError(ValueError):
    """文件读不出初稿正文;消息是给学生看的 i18n 键。"""


def extract_draft_text(filename: str, data: bytes) -> str:
    """从学生上传的初稿文件里取出纯文本,一段一行。

    只解析不存档:文件内容不落盘、不进文件库,学生核对后照常走「确认初稿」。
    收 .docx、旧版 .doc 和纯文本。PDF 不收,中文 PDF 抽出来每个视觉行都断成
    一段,学生得逐段拼回去。
    """

    if len(data) > DRAFT_FILE_MAX_BYTES:
        raise DraftFileError("The file is too large")
    suffix = os.path.splitext(filename or "")[1].lower()
    if suffix in (".docx", ".doc"):
        # 按内容而不是扩展名分派:学生常把 .doc 改名成 .docx(或反过来),
        # 设了密码的 .docx 也是 OLE 容器。
        if data.startswith(_OLE_MAGIC):
            text = _extract_doc_text(data)
        else:
            text = _extract_docx_text(data)
    elif suffix in (".txt", ".md"):
        text = _decode_plain_text(data)
    else:
        raise DraftFileError("Only .docx, .doc, .txt and .md files are supported")
    text = "\n".join(normalize_draft_paragraphs(text))
    if not text:
        raise DraftFileError("No text found in this file")
    return text


def _extract_docx_text(data: bytes) -> str:
    from docx import Document
    from docx.text.paragraph import Paragraph

    try:
        document = Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as err:
        raise DraftFileError("Could not read this file") from err
    # 按文档顺序取正文段落和表格(每个单元格一行),与 .doc 的主文档一致;
    # 页眉页脚、脚注、文本框不取。段内软回车 python-docx 给的是 \n,随后按行切段。
    lines = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            lines.append(block.text)
            continue
        seen = set()
        for row in block.rows:
            for cell in row.cells:
                # 合并单元格在 row.cells 里会重复出现
                if cell._tc in seen:
                    continue
                seen.add(cell._tc)
                lines.append(cell.text)
    return "\n".join(lines)


def _extract_doc_text(data: bytes) -> str:
    """Word 97-2003 的 .doc:OLE 复合文件里的 WordDocument 流。

    正文不是连续存放的,要按表流里的 piece table 逐段拼回来([MS-DOC] 2.4.1)。
    只取主文档(前 ccpText 个字符):页眉页脚、脚注、文本框排在它后面,
    与 .docx 只取正文段落一致。
    """
    # olefile 由上游直接依赖 msoffcrypto-tool 带进来。
    import olefile

    # 不用 olefile.isOleFile:传入的 bytes 短于 1536 字节时它会当成文件路径去打开。
    if len(data) < olefile.MINIMAL_OLEFILE_SIZE:
        raise DraftFileError("Could not read this file")
    try:
        with olefile.OleFileIO(data) as ole:
            # 设了打开密码的 .docx/.xlsx 等:加密包装在 OLE 容器里
            if ole.exists("EncryptedPackage"):
                raise DraftFileError("This file is password protected")
            if not ole.exists("WordDocument"):
                raise DraftFileError("Could not read this file")
            word = ole.openstream("WordDocument").read()
            flags = int.from_bytes(word[0x0A:0x0C], "little")
            if flags & 0x0100:
                raise DraftFileError("This file is password protected")
            table_name = "1Table" if flags & 0x0200 else "0Table"
            if not ole.exists(table_name):
                raise DraftFileError("Could not read this file")
            table = ole.openstream(table_name).read()
        return _doc_main_text(word, table)
    except DraftFileError:
        raise
    except Exception as err:
        # 截断、损坏的文件在 olefile 和下标运算里抛什么都有,一律当读不出。
        raise DraftFileError("Could not read this file") from err


def _doc_main_text(word: bytes, table: bytes) -> str:
    def u16(buf, pos):
        return int.from_bytes(buf[pos : pos + 2], "little")

    def u32(buf, pos):
        return int.from_bytes(buf[pos : pos + 4], "little")

    if u16(word, 0) != 0xA5EC:
        raise DraftFileError("Could not read this file")
    # FIB:32 字节 FibBase,随后 csw 个 u16、cslw 个 u32、cbRgFcLcb 对 (fc, lcb)。
    pos = 32
    pos += 2 + u16(word, pos) * 2
    rg_lw = pos + 2
    ccp_text = u32(word, rg_lw + 3 * 4)
    pos += 2 + u16(word, pos) * 4
    rg_fc_lcb = pos + 2
    fc_clx = u32(word, rg_fc_lcb + 33 * 8)
    lcb_clx = u32(word, rg_fc_lcb + 33 * 8 + 4)

    # Clx:若干 Prc(0x01)之后是 Pcdt(0x02),里面是 PlcPcd。
    pos, end = fc_clx, fc_clx + lcb_clx
    while pos < end and table[pos] == 0x01:
        pos += 3 + u16(table, pos + 1)
    if pos >= end or table[pos] != 0x02:
        raise DraftFileError("Could not read this file")
    lcb = u32(table, pos + 1)
    plc = pos + 5
    count = (lcb - 4) // 12
    # 损坏文件的 lcb 可能是天文数字,先核对表流装得下,免得按它分配几亿个元素。
    if count <= 0 or plc + lcb > len(table):
        raise DraftFileError("Could not read this file")
    cps = [u32(table, plc + i * 4) for i in range(count + 1)]
    pcds = plc + (count + 1) * 4

    chars = []
    for i in range(count):
        start, stop = cps[i], min(cps[i + 1], ccp_text)
        if start >= stop:
            break
        fc = u32(table, pcds + i * 8 + 2)
        length = stop - start
        if fc & 0x40000000:
            # 压缩片段:一字节一字符,cp1252;中文都在非压缩的 UTF-16 片段里。
            offset = (fc & ~0x40000000) // 2
            chars.append(word[offset : offset + length].decode("cp1252", "replace"))
        else:
            chars.append(word[fc : fc + length * 2].decode("utf-16-le", "replace"))
    return _clean_doc_text("".join(chars))


def _clean_doc_text(raw: str) -> str:
    # 域:\x13 域代码 \x14 域结果 \x15,可嵌套;只留结果(如超链接的显示文字)。
    out = []
    fields = []
    for ch in raw:
        if ch == "\x13":
            fields.append("code")
        elif ch == "\x14":
            if fields:
                fields[-1] = "result"
        elif ch == "\x15":
            if fields:
                fields.pop()
        elif "code" in fields:
            continue
        elif ch in "\r\x0b\x0c\x07":
            # 段落标记、手动换行、分页符、表格单元格/行结束
            out.append("\n")
        elif ch == "\t" or ch >= " ":
            out.append(ch)
        # 其余控制字符是图片、脚注引用之类的占位符,丢掉
    return "".join(out)


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


async def build_current_text_context(
    session,
    chat_id: str | None = None,
    previous_reply_id: str | None = None,
    db=None,
) -> str:
    """要追加到系统提示末尾的学生当前正文,连同它改没改过的状态。

    正文取的是最近一次保存的版本;学生不一定每轮都改,改没改由这里算好告诉模型,
    不让它拿自己回复里引用过的句子去猜。previous_reply_id 是本轮之前模型的那条回复
    (当前提问的父消息),它的时间戳由后端在发起请求时写入,与版本时间同一个时钟。
    笔记用自己的短会话读取,读完即释放,不把数据库事务带进之后的模型调用。
    """

    note = await Notes.get_note_by_id(session.note_id)
    content = ((note.data or {}).get("content") or {}) if note else {}
    text = (content.get("md") or "").strip()
    if not text:
        return "【学生当前正文】右侧编辑器里还没有内容。"

    paragraphs = normalize_draft_paragraphs(text)
    status = []
    baseline = session.draft_baseline_text
    if baseline is not None:
        unchanged = paragraphs == normalize_draft_paragraphs(baseline)
        status.append("与初稿相比：" + ("还没有改动。" if unchanged else "已有改动。"))

    previous_reply = (
        await ChatMessages.get_message_by_id(f"{chat_id}-{previous_reply_id}")
        if chat_id and previous_reply_id
        else None
    )
    if previous_reply is not None and previous_reply.role == "assistant":
        version = Education.get_latest_version_until(
            session.id, previous_reply.created_at, db=db
        )
        # 初稿确认时不存版本;那之前没有版本,模型上次看到的就是初稿(从零写作则是空稿)。
        seen_text = (
            version.note_snapshot_text if version else (baseline or "")
        )
        unchanged = paragraphs == normalize_draft_paragraphs(seen_text)
        status.append(
            "自你上一次回复以来：" + ("没有新的改动。" if unchanged else "有新的改动。")
        )

    return (
        "【学生当前正文】以下是学生右侧编辑器里最近一次保存的全文。"
        "学生会边聊边改稿，但不一定每轮都改，改没改以下面的状态为准，不要自己推测。"
        "它和你之前回复里引用过的句子不一样时，那是改动前的旧版本，不是你记错了；"
        "谈论正文时一律以这一版为准。学生说改好了、状态却显示没有新的改动，"
        "多半是还没保存，请他等编辑器显示已保存后再发。\n"
        + "".join(f"{line}\n" for line in status)
        + f"<<<\n{text}\n>>>"
    )
