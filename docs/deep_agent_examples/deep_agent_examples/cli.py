"""统一运行各个 Deep Agents 示例的命令行入口。

该模块负责选择 Graph、组装输入 State、配置 LangSmith 追踪并打印结果；
具体 Agent 结构在 ``graphs.py`` 中定义，业务工具在 ``tools.py`` 中定义。
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langsmith import tracing_context

from deep_agent_examples.config import invoke_config, tracing_enabled, tracing_project


# 每个示例的默认中文任务；命令行传入 --prompt 时会覆盖对应内容。
DEFAULT_PROMPTS = {
    "tool": "研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件，请评审。",
    "lifecycle": "计算采购 4 台、单价 68000 元的总额，并展示本次 Agent 生命周期。",
    "subagent-lifecycle": "让 lifecycle-reviewer 检查采购 4 台 AI 推理服务器的库存，并总结结果。",
    "subagent": "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件，并让风险专家独立复核。",
    "compiled": "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件，并让财务图复核。",
    "remote": "调查北辰智能硬件的供应商风险和 AI 推理服务器库存。",
    "async": "请在后台调查北辰智能硬件和 AI 推理服务器库存，先返回 task_id。",
    "backend": "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件，并把证据和报告写入文件。",
    "skill": "按本会话的采购评审技能，评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件。",
    "hitl": "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件，生成草稿并发布。",
    "local-shell": "创建 /artifacts/hello.py，让它打印 hello deep agents，然后申请执行。",
    "langsmith-sandbox": "在 /workspace 创建 hello.py，运行它并返回退出码。",
}


def _last_content(result: dict[str, Any]) -> str:
    """从 Graph 最终 State 中提取最后一条助手消息文本。"""
    messages = result.get("messages") or []
    if not messages:
        return ""
    content = getattr(messages[-1], "content", "")
    return content if isinstance(content, str) else str(content)


def _print_result(result: dict[str, Any]) -> None:
    """打印最终回答，并附带虚拟文件路径或待人工处理的中断信息。"""
    print(_last_content(result) or "(no final assistant message)")

    # StateBackend/沙箱示例会在 files 中留下 Agent 创建或修改的文件。
    files = result.get("files") or {}
    if files:
        print("\nfiles:")
        for path in sorted(files):
            print(f"- {path}")
    # 不同 LangGraph 版本可能使用两个字段名之一表示 HITL 中断。
    interrupts = result.get("__interrupt__") or result.get("interrupts")
    if interrupts:
        print("\ninterrupt:")
        print(interrupts)


def _approval_count(result: dict[str, Any]) -> int:
    """计算当前 HITL 中断包含的待审批动作数量。"""
    interrupts = result.get("__interrupt__") or result.get("interrupts") or []
    if not interrupts:
        return 0
    interrupt = interrupts[0]
    value = getattr(interrupt, "value", interrupt)
    if isinstance(value, dict):
        actions = value.get("action_requests") or []
        return max(len(actions), 1)
    return 1


def _load_example(name: str):
    """根据命令行名称返回目标 Graph 及其是否必须异步调用。"""
    # 延迟导入避免仅查看 --help 时就创建全部模型和 Agent。
    from deep_agent_examples import graphs

    if name == "tool":
        return graphs.tool_agent, False
    if name == "lifecycle":
        return graphs.lifecycle_agent, False
    if name == "subagent-lifecycle":
        return graphs.subagent_lifecycle_agent, False
    if name == "subagent":
        return graphs.subagent_agent, False
    if name == "compiled":
        return graphs.compiled_subagent_agent, False
    if name == "remote":
        return graphs.remote_research_agent, False
    if name == "async":
        return graphs.async_subagent_agent, True
    if name == "backend":
        return graphs.backend_agent, False
    if name == "skill":
        return graphs.dynamic_skill_agent, False
    if name == "hitl":
        return graphs.build_hitl_harness_agent(InMemorySaver()), False
    if name == "local-shell":
        return graphs.build_local_shell_agent(InMemorySaver()), False
    raise ValueError(f"Unknown example: {name}")


def _payload(name: str, prompt: str) -> dict:
    """构造 Graph 输入 State；动态 Skill 示例额外注入虚拟技能文件。"""
    payload: dict[str, Any] = {"messages": [{"role": "user", "content": prompt}]}
    if name == "skill":
        from deep_agent_examples.graphs import DYNAMIC_SKILL_FILES

        # StateBackend 从 state["files"] 读取文件；常量本身不会自动进入 State。
        payload["files"] = DYNAMIC_SKILL_FILES
    return payload


async def _ainvoke(graph, payload: dict, config: dict) -> dict:
    """为必须运行在异步事件循环中的 Graph 提供统一调用包装。"""
    # payload 是 Graph 输入 State；config 是 thread_id/Trace 等运行配置。
    return await graph.ainvoke(payload, config=config)


def main() -> None:
    """解析命令行、运行选中的示例，并按需处理最多五轮人工批准。"""
    parser = argparse.ArgumentParser(description="Run one observable Deep Agents example.")
    parser.add_argument("example", choices=sorted(DEFAULT_PROMPTS))
    parser.add_argument("--prompt", help="Override the example prompt.")
    parser.add_argument("--thread-id", default="deep-agent-example-cli")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Approve HITL requests in hitl/local-shell examples (max 5 rounds).",
    )
    args = parser.parse_args()
    prompt = args.prompt or DEFAULT_PROMPTS[args.example]

    # 云沙箱需要独立创建/销毁远程资源，不从 graphs.py 的常驻 Graph 中选择。
    if args.example == "langsmith-sandbox":
        from deep_agent_examples.cloud_sandbox import run_langsmith_sandbox

        _print_result(run_langsmith_sandbox(prompt, args.thread_id))
        return

    graph, requires_async = _load_example(args.example)
    config = invoke_config(args.example, args.thread_id)
    payload = _payload(args.example, prompt)

    # 给当前示例添加统一追踪元数据，便于在 LangSmith 中按示例筛选调用链。
    with tracing_context(
        # enabled：只控制是否上传 LangSmith Trace，不影响 Graph 执行。
        enabled=tracing_enabled(),
        # project_name：Trace 在 LangSmith 中归属的项目。
        project_name=tracing_project(),
        # tags：检索标签，不会作为消息发送给模型。
        tags=["deep-agent-example", args.example],
        # metadata：结构化追踪信息，不会自动合并进 Graph State。
        metadata={"example": args.example, "entrypoint": "cli"},
    ):
        # 远程异步子 Agent 示例必须使用 ainvoke，其余示例直接同步执行。
        result = (
            asyncio.run(_ainvoke(graph, payload, config))
            if requires_async
            else graph.invoke(payload, config=config)
        )
        _print_result(result)

        # --approve 会把当前中断中的所有动作批准后恢复同一个 thread。
        # 五轮上限用于防止错误配置导致 Agent 在“批准 -> 再次中断”之间无限循环。
        approval_round = 0
        while args.approve and (decision_count := _approval_count(result)):
            approval_round += 1
            if approval_round > 5:
                raise RuntimeError("Stopped after 5 approval rounds to avoid an approval loop.")
            result = graph.invoke(
                Command(
                    # resume：把与 action_requests 一一对应的人工决定送回暂停点。
                    resume={
                        "decisions": [
                            {"type": "approve"} for _ in range(decision_count)
                        ]
                    }
                ),
                # 复用同一个 config/thread_id，Checkpointer 才能找到原中断状态。
                config=config,
            )
            print(f"\nresumed after approval round {approval_round}:")
            _print_result(result)


if __name__ == "__main__":
    main()
