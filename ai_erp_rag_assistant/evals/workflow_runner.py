"""在独立评估进程中执行真实 LangGraph，替换模型及外部业务边界。"""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from typing import Any
from unittest.mock import patch

from langsmith import tracing_context

from ai_erp_rag_assistant.app.graph import workflow
from ai_erp_rag_assistant.app.graph.state import initial_state
from ai_erp_rag_assistant.app.services.agent_evaluation_service import (
    AgentEvalCase,
    AgentObservation,
    EvalToolCall,
)
from ai_erp_rag_assistant.app.services.execution_repository import StepStart
from ai_erp_rag_assistant.app.services.execution_runtime import DurableExecutionContext
from ai_erp_rag_assistant.app.services.model_service import (
    AgentPlan,
    ApprovalFieldExtraction,
    ModelService,
)


def _deny_external(*args, **kwargs):
    raise RuntimeError("评估禁止访问真实数据库、ERP 或 Milvus")


class _MemorySteps:
    """只模拟步骤存储，复用生产 DurableExecutionContext 的重放规则。"""

    def __init__(self):
        self.outputs: dict[str, dict[str, Any]] = {}

    def begin_step(self, *, step_name, replay_completed, **kwargs):
        cached = replay_completed and step_name in self.outputs
        return StepStart(cached, deepcopy(self.outputs.get(step_name, {})) if cached else {})

    def complete_step(self, *, step_name, output, **kwargs):
        self.outputs[step_name] = deepcopy(output)

    def fail_step(self, **kwargs):
        pass


class WorkflowEvalRunner:
    """串行评估真实根图；不得作为 HTTP 服务中的并发运行器使用。"""

    def __init__(self, *, with_llm: bool = False):
        self.with_llm = with_llm
        self.graph = workflow.create_workflow(with_checkpointer=False)

    def __call__(self, case: AgentEvalCase) -> list[AgentObservation]:
        observations: list[AgentObservation] = []
        prior = None
        user = {
            "company_id": "16", "uid": "863", "user_id": "863",
            "department": "人事部", "rag_access_tags": ["employee"], "erp_mode": "mock",
        }
        template = {
            "template_id": "eval-leave", "title": "请假审批", "erp_mode": "mock",
            "fields": [{"name": "reason", "label": "请假原因", "type": "text", "required": True}],
        }
        # 单独的模型实例避免修改在线服务单例；全局工具 patch 仅供独立进程串行使用。
        model = ModelService()
        invoke_structured = model._invoke_structured
        invoke_answer = model._invoke
        for turn in case.turns:
            fixtures = turn.fixtures
            calls: list[EvalToolCall] = []
            model_calls: list[str] = []

            def record(name, args, result):
                calls.append(EvalToolCall(name=name, args=deepcopy(args)))
                return deepcopy(result)

            def identity(actual_user):
                return {key: actual_user.get(key) for key in ("company_id", "uid")}

            def structured(system, payload, schema, **kwargs):
                name = "plan" if schema is AgentPlan else "extract_fields"
                model_calls.append(name)
                if self.with_llm:
                    return invoke_structured(system, payload, schema, **kwargs)
                if schema is AgentPlan:
                    return fixtures.plan.model_copy(deep=True)
                if schema is ApprovalFieldExtraction:
                    return ApprovalFieldExtraction(fields=deepcopy(fixtures.extracted_fields))
                raise ValueError("未提供此结构化模型输出的评估 Fixture")

            def answer(system, payload, **kwargs):
                # 结构化调用的 JSON 回退仍属于 plan/extract_fields，不是新增一次回答。
                if kwargs.get("parse_json", True) is False:
                    model_calls.append("answer")
                return invoke_answer(system, payload, **kwargs) if self.with_llm else fixtures.answer

            def search(query, **kwargs):
                return record("rag.search", {"query": query, **{
                    key: kwargs.get(key) for key in ("company_id", "department", "permission_tags", "top_k")
                }}, fixtures.evidence)

            def customer(query, date_range, *, user):
                return record("erp.customer_activity", {"query": query, "date_range": date_range, **identity(user)}, {
                    "items": fixtures.customer_items, "count": len(fixtures.customer_items),
                    "date_range": date_range, "erp_mode": "mock",
                })

            def templates(query, company_id, *, user):
                return record("erp.approval_list", {"query": query, "company_id": company_id, "uid": user.get("uid")}, [template])

            def get_template(template_id, company_id, *, title, user):
                return record("erp.approval_template", {"template_id": template_id, "company_id": company_id, "uid": user.get("uid")}, template)

            def status(user_id, *, user):
                return record("erp.approval_status", {"user_id": user_id, **identity(user)}, fixtures.approval_status)

            def submit(preview, *, user):
                return record("erp.approval_submit", {
                    "fields": preview.get("submission_fields"),
                    "has_idempotency_key": bool(preview.get("idempotency_key")), **identity(user),
                }, {"approval_id": "EVAL-A-1", "erp_mode": "mock", "erp_write_mode": fixtures.write_mode})

            state = initial_state(
                f"eval-{case.id}", turn.user_id, turn.message, assistant_type=case.assistant_type,
                uid=turn.user_id, company_id=turn.company_id, department=turn.department,
                form_values=deepcopy(turn.form_values), confirm=turn.confirm, prior=prior,
            )
            # 模拟服务端已校验的身份，不读取登录接口或检查点中的真实凭据。
            state["user_context"] = deepcopy(user)
            if turn.preview_confirmation != "none":
                preview = state.get("preview") or {}
                if not preview:
                    raise ValueError("确认轮之前必须先生成预览")
                state.update(
                    confirm_preview_id=preview["preview_id"],
                    confirm_preview_version=preview["preview_version"],
                    confirm_preview_hash=preview["preview_hash"] if turn.preview_confirmation == "current" else "stale-hash",
                )
            with ExitStack() as stack:
                stack.enter_context(tracing_context(enabled=False))
                for target in (
                    "pymysql.connect", "pymysql.connections.Connection.connect",
                    "sqlalchemy.engine.Engine.connect",
                    "ai_erp_rag_assistant.app.services.erp_client.ErpClient._post",
                    "ai_erp_rag_assistant.app.services.erp_client.ErpClient._get",
                    "ai_erp_rag_assistant.app.services.milvus_service.MilvusService._client",
                ):
                    stack.enter_context(patch(target, side_effect=_deny_external))
                if not self.with_llm:
                    stack.enter_context(patch("socket.socket.connect", side_effect=_deny_external))
                # 显式保留模型工厂，避免生产兼容逻辑将观测包装误判为离线 invoker。
                stack.enter_context(patch.object(model, "_model", model._model if self.with_llm else _deny_external))
                for name, replacement in {
                    "model_service": model, "write_audit_event": lambda *args, **kwargs: None,
                    "get_current_user": _deny_external, "search_knowledge": search,
                    "list_approval_templates": templates, "get_approval_template": get_template,
                    "get_approval_nodes": _deny_external, "query_approval_status": status,
                    "submit_approval": submit,
                }.items():
                    stack.enter_context(patch.object(workflow, name, replacement))
                stack.enter_context(patch("ai_erp_rag_assistant.app.tools.customer.state_tools.get_customer_activity", customer))
                stack.enter_context(patch.object(model, "_invoke_structured", structured))
                stack.enter_context(patch.object(model, "_invoke", answer))
                config = {"configurable": {}}
                if turn.replay:
                    config["configurable"]["durable_execution"] = DurableExecutionContext(_MemorySteps(), case.id, "eval-owner")
                output = self.graph.invoke(deepcopy(state), config=config)
                replay_pass = None
                if turn.replay:
                    count_before = (len(calls), len(model_calls))
                    replayed = self.graph.invoke(deepcopy(state), config=config)
                    replay_pass = count_before == (len(calls), len(model_calls)) and all(
                        output.get(key) == replayed.get(key)
                        for key in ("route", "workflow_status", "fields", "preview", "erp_data", "assistant_message")
                    )
            observations.append(AgentObservation(
                route=output.get("route", "unknown"), workflow_status=output.get("workflow_status", ""),
                answer=output.get("assistant_message", ""), evidence=output.get("evidence", []),
                tools=calls, model_calls=model_calls, replay_pass=replay_pass,
            ))
            prior = output
        return observations
