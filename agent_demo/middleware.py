from __future__ import annotations

"""学习用中间件。

中间件放在 Agent 和工具/模型之间，用来记录过程信息。
它不改变业务结果，只负责可观测性：什么时候切换 prompt、调用了哪个工具、
参数是什么、结果大概是什么。
"""

from collections.abc import Callable
from typing import Any

from agent_demo.utils.logger_handler import LogStore, make_log


def monitor_tool(logs: LogStore, tool_name: str, arguments: dict[str, Any], call: Callable[[], Any]) -> Any:
    """包装一次工具调用，并把调用前后写入日志。"""

    logs.add(make_log("工具", f"工具 {tool_name} 参数：{arguments}"))
    try:
        result = call()
    except Exception as exc:
        logs.add(make_log("工具", f"工具 {tool_name} 失败：{exc}"))
        raise
    logs.add(make_log("工具", f"工具 {tool_name} 完成：{_summarize_result(result)}"))
    return result


def log_before_model(logs: LogStore, prompt_name: str, context: str) -> None:
    """记录模型调用前的上下文信息。

    当前第一版页面还没有把它接进所有模型调用点，但保留这个函数可以展示
    “模型前中间件”的典型职责。
    """

    logs.add(make_log("模型", f"调用模型前：prompt={prompt_name}，上下文长度={len(context)}"))


def report_prompt_switch(logs: LogStore, prompt_name: str) -> None:
    """记录本轮 Agent 选择了哪个 prompt。"""

    logs.add(make_log("Prompt", f"切换到 {prompt_name}"))


def _summarize_result(result: Any) -> str:
    """把工具结果压缩成适合日志显示的短文本。"""

    text = str(result)
    if len(text) <= 120:
        return text
    return text[:117] + "..."
