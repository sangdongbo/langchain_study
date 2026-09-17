from __future__ import annotations

import argparse
import asyncio
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langsmith import tracing_context

from deep_agent_examples.config import invoke_config, tracing_enabled, tracing_project


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
    messages = result.get("messages") or []
    if not messages:
        return ""
    content = getattr(messages[-1], "content", "")
    return content if isinstance(content, str) else str(content)


def _print_result(result: dict[str, Any]) -> None:
    print(_last_content(result) or "(no final assistant message)")
    files = result.get("files") or {}
    if files:
        print("\nfiles:")
        for path in sorted(files):
            print(f"- {path}")
    interrupts = result.get("__interrupt__") or result.get("interrupts")
    if interrupts:
        print("\ninterrupt:")
        print(interrupts)


def _approval_count(result: dict[str, Any]) -> int:
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
    payload: dict[str, Any] = {"messages": [{"role": "user", "content": prompt}]}
    if name == "skill":
        from deep_agent_examples.graphs import DYNAMIC_SKILL_FILES

        payload["files"] = DYNAMIC_SKILL_FILES
    return payload


async def _ainvoke(graph, payload: dict, config: dict) -> dict:
    return await graph.ainvoke(payload, config=config)


def main() -> None:
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

    if args.example == "langsmith-sandbox":
        from deep_agent_examples.cloud_sandbox import run_langsmith_sandbox

        _print_result(run_langsmith_sandbox(prompt, args.thread_id))
        return

    graph, requires_async = _load_example(args.example)
    config = invoke_config(args.example, args.thread_id)
    payload = _payload(args.example, prompt)
    with tracing_context(
        enabled=tracing_enabled(),
        project_name=tracing_project(),
        tags=["deep-agent-example", args.example],
        metadata={"example": args.example, "entrypoint": "cli"},
    ):
        result = (
            asyncio.run(_ainvoke(graph, payload, config))
            if requires_async
            else graph.invoke(payload, config=config)
        )
        _print_result(result)
        approval_round = 0
        while args.approve and (decision_count := _approval_count(result)):
            approval_round += 1
            if approval_round > 5:
                raise RuntimeError("Stopped after 5 approval rounds to avoid an approval loop.")
            result = graph.invoke(
                Command(
                    resume={
                        "decisions": [
                            {"type": "approve"} for _ in range(decision_count)
                        ]
                    }
                ),
                config=config,
            )
            print(f"\nresumed after approval round {approval_round}:")
            _print_result(result)


if __name__ == "__main__":
    main()
