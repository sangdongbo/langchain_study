"""在一次性 LangSmith 云沙箱中运行 Deep Agent 的示例入口。

云沙箱与本机文件系统隔离，适合演示 Agent 创建文件和执行命令。上下文管理器
退出后会停止沙箱，并按配置在一段时间后删除资源。
"""

from __future__ import annotations

import os

from deepagents import create_deep_agent
from deepagents.backends import LangSmithSandbox
from langsmith import tracing_context
from langsmith.sandbox import SandboxClient

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    load_environment,
    tracing_enabled,
    tracing_project,
)


def run_langsmith_sandbox(prompt: str, thread_id: str = "cloud-sandbox-demo") -> dict:
    """创建临时 LangSmith 云沙箱，在其中运行 Agent 并返回最终 Graph State。"""
    load_environment()

    # SandboxClient 调用 LangSmith 服务，必须使用真实 API Key。
    if not os.getenv("LANGSMITH_API_KEY"):
        raise RuntimeError("LANGSMITH_API_KEY is required for LangSmith Sandbox.")

    # 空闲 10 分钟停止；停止 10 分钟后删除，避免示例资源长期占用配额。
    sandbox_kwargs = {
        # 连续 600 秒没有活动后自动停止实例，停止后仍可在保留期内查看。
        "idle_ttl_seconds": 600,
        # 实例停止 600 秒后彻底删除；这是远程资源生命周期配置。
        "delete_after_stop_seconds": 600,
    }
    # 配置快照时从预制环境启动，否则使用 LangSmith 默认沙箱环境。
    if snapshot_name := os.getenv("LANGSMITH_SANDBOX_SNAPSHOT"):
        # snapshot_name：远程预制环境名称，可包含提前安装的依赖和基础文件。
        sandbox_kwargs["snapshot_name"] = snapshot_name

    client = SandboxClient()
    # 上下文管理器负责创建和停止沙箱，即使 Agent 运行报错也会执行清理。
    with client.sandbox(**sandbox_kwargs) as sandbox:
        # LangSmithSandbox 把 Deep Agent 的文件和 shell 工具定向到这个远程沙箱。
        agent = create_deep_agent(
            # 模型在本机调用，但它生成的文件/命令操作由远程 Backend 执行。
            model=build_model(),
            # backend：将 Deep Agent 的文件和 shell 工具绑定到当前 sandbox 实例。
            backend=LangSmithSandbox(sandbox),
            # Graph/Trace 中显示的名称。
            name="langsmith-sandbox-agent",
            # 约束模型只在一次性沙箱内工作并回报可验证结果。
            system_prompt=(
                "Work only inside the disposable cloud sandbox. Create files under "
                "/workspace and report command exit codes and artifact paths."
            ),
        )
        # tracing_context 只控制本次调用的追踪开关、项目归属和检索标签。
        with tracing_context(
            # enabled：是否上传 Trace，不决定沙箱是否创建。
            enabled=tracing_enabled(),
            # project_name：Trace 在 LangSmith 中归属的项目。
            project_name=tracing_project(),
            # tags：用于筛选本示例，不进入模型上下文。
            tags=["deep-agent-example", "langsmith-sandbox"],
            # metadata：Trace 的结构化检索字段，不是 Graph State。
            metadata={"example": "langsmith-sandbox"},
        ):
            # thread_id 写入调用配置，便于在 LangSmith 中关联同一会话的多次运行。
            return agent.invoke(
                # 第一个参数是 Graph 输入 State，messages 会发送给模型。
                {"messages": [{"role": "user", "content": prompt}]},
                # config 提供 thread_id、run_name 和追踪字段，不是模型消息。
                config=invoke_config("langsmith-sandbox", thread_id),
            )
