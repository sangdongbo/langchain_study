from __future__ import annotations

"""项目路径工具。

把路径集中放在这里有两个好处：
- 其它模块不需要反复写 `Path(__file__).resolve()`。
- 后续移动 chroma_db、prompts、sample_docs 目录时，只改这里即可。
"""

from pathlib import Path


# agent_demo 包根目录，例如 D:/PythonProject/LearnOne/agent_demo。
AGENT_DEMO_ROOT = Path(__file__).resolve().parents[1]


def chroma_dir() -> Path:
    """本 demo 独立的 ChromaDB 持久化目录。"""

    return AGENT_DEMO_ROOT / "chroma_db"


def sample_docs_dir() -> Path:
    """示例文档目录。"""

    return AGENT_DEMO_ROOT / "data" / "sample_docs"


def logs_dir() -> Path:
    """按天保存运行日志的目录。"""

    return AGENT_DEMO_ROOT / "logs"


def prompt_path(filename: str) -> Path:
    """根据 prompt 文件名返回完整路径。"""

    return AGENT_DEMO_ROOT / "prompts" / filename
