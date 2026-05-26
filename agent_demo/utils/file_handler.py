from __future__ import annotations

"""上传文件处理工具。

Streamlit 上传文件给到的是 bytes。RAG 入库需要普通字符串，所以这里负责：
1. 按常见编码解码。
2. 清理多余空白。
3. 保留文件名和编码信息，方便后续写入 Document metadata。
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UploadedText:
    """解码后的上传文本。"""

    name: str
    text: str
    encoding: str


def clean_text(text: str) -> str:
    """清理文本头尾空白，并把连续空行压缩成一个空行。"""

    stripped = text.strip()
    return re.sub(r"\n{3,}", "\n\n", stripped)


def decode_uploaded_bytes(name: str, raw: bytes) -> UploadedText:
    """把上传文件 bytes 解码成 UploadedText。

    优先 UTF-8；如果失败，回退到 gb18030。gb18030 能覆盖很多中文 Windows
    环境里常见的 txt 文件编码。
    """

    try:
        return UploadedText(name=name, text=clean_text(raw.decode("utf-8")), encoding="utf-8")
    except UnicodeDecodeError:
        return UploadedText(
            name=name,
            text=clean_text(raw.decode("gb18030", errors="ignore")),
            encoding="gb18030",
        )
