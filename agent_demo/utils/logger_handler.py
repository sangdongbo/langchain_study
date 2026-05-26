from __future__ import annotations

"""运行日志工具。

日志是这个学习项目的重要部分：它让用户看到 Agent 的执行过程，
例如用户输入、prompt 切换、工具调用、入库结果和错误信息。
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from agent_demo.utils.path_tools import logs_dir


@dataclass(frozen=True)
class LogEntry:
    """一条日志。"""

    stage: str
    message: str
    timestamp: str
    date: str

    def render(self) -> str:
        """转成页面上显示的一行文本。"""

        return f"[{self.timestamp}] {self.stage}：{self.message}"


@dataclass
class LogStore:
    """内存日志容器。

    Streamlit 会把这个对象放进 session_state。
    max_entries 用来限制日志数量，避免长时间演示后页面越来越慢。
    log_dir 指向落盘目录；每次 add 都会追加写入当天日志文件。
    """

    max_entries: int = 80
    log_dir: Path | str = field(default_factory=logs_dir)
    entries: list[LogEntry] = field(default_factory=list)

    def add(self, entry: LogEntry) -> None:
        """追加日志、裁剪内存列表，并写入当天日志文件。"""

        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries :]
        self._append_to_file(entry)

    def render_lines(self) -> list[str]:
        """返回所有日志的渲染文本。"""

        return [entry.render() for entry in self.entries]

    def clear(self) -> None:
        """清空页面内存日志。

        注意：这里不删除磁盘日志。磁盘日志是运行审计记录，按天保存在 logs/ 下。
        """

        self.entries.clear()

    def _append_to_file(self, entry: LogEntry) -> None:
        """把日志追加到 agent_demo/logs/YYYY-MM-DD.log。"""

        directory = Path(self.log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{entry.date}.log"
        with path.open("a", encoding="utf-8") as file:
            file.write(entry.render() + "\n")


def make_log(stage: str, message: str) -> LogEntry:
    """创建带当前时间的日志。"""

    now = datetime.now()
    return LogEntry(
        stage=stage,
        message=message,
        timestamp=now.strftime("%H:%M:%S"),
        date=now.strftime("%Y-%m-%d"),
    )
