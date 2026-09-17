"""把 LangGraph 业务节点接入 ERP Durable Execution 仓储。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.runnables import RunnableConfig

from ai_erp_rag_assistant.app.services.execution_repository import ExecutionRepository


@dataclass
class DurableExecutionContext:
    """随 LangGraph RunnableConfig 传递的单次运行控制器。"""

    repository: ExecutionRepository
    run_key: str
    owner_token: str
    retry_count: int = 0
    current_step: str = ""

    def execute_step(
        self,
        step_name: str,
        state: dict[str, Any],
        call: Callable[[], dict[str, Any]],
        *,
        replay_completed: bool,
    ) -> dict[str, Any]:
        """围绕业务节点建立 before/after/failed 三类持久化边界。"""
        self.current_step = step_name
        started = self.repository.begin_step(
            run_key=self.run_key,
            owner_token=self.owner_token,
            step_name=step_name,
            state=state,
            replay_completed=replay_completed,
        )
        if started.cached:
            return started.output
        try:
            output = call()
        except Exception as exc:
            try:
                self.repository.fail_step(
                    run_key=self.run_key,
                    owner_token=self.owner_token,
                    step_name=step_name,
                    state=state,
                    error=exc,
                )
            except Exception:
                # 数据库同时不可用时仍抛出原业务异常，路由层会再次尝试标记 Run 失败。
                pass
            raise
        self.repository.complete_step(
            run_key=self.run_key,
            owner_token=self.owner_token,
            step_name=step_name,
            state=state,
            output=output,
        )
        return output

    def complete(self, state: dict[str, Any], response: dict[str, Any]) -> None:
        self.repository.complete_run(
            run_key=self.run_key,
            owner_token=self.owner_token,
            state=state,
            response=response,
        )

    def fail(self, state: dict[str, Any], error: Exception) -> None:
        self.repository.fail_run(
            run_key=self.run_key,
            owner_token=self.owner_token,
            state=state,
            error=error,
        )


def durable_node(
    step_name: str,
    node: Callable[..., dict[str, Any]],
    *,
    pass_config: bool = False,
    replay_completed: bool = True,
) -> Callable[[dict[str, Any], RunnableConfig], dict[str, Any]]:
    """把普通 LangGraph 节点转换为可检查点、可重放的节点。"""

    def wrapped(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
        context = config.get("configurable", {}).get("durable_execution")

        def call() -> dict[str, Any]:
            return node(state, config) if pass_config else node(state)

        if not isinstance(context, DurableExecutionContext):
            return call()
        return context.execute_step(
            step_name,
            state,
            call,
            replay_completed=replay_completed,
        )

    return wrapped
