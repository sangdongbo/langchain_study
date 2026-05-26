from __future__ import annotations

"""Prompt 加载工具。"""

from agent_demo.utils.path_tools import prompt_path


def load_prompt(filename: str) -> str:
    """读取 prompts/ 下的 prompt 文件。

    这里显式抛 FileNotFoundError，方便页面展示“缺少哪个 prompt”。
    """

    path = prompt_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"缺少 prompt 文件：{path}")
    return path.read_text(encoding="utf-8").strip()
