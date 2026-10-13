"""Agent Evals 纯单测；业务边界和网络在执行器内封闭，不连接数据库。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ai_erp_rag_assistant.app.graph import workflow
from ai_erp_rag_assistant.app.services.agent_evaluation_service import (
    AgentEvalCase,
    AgentEvaluationService,
    AgentObservation,
    EvalToolCall,
    score_turn,
)
from ai_erp_rag_assistant.app.services.model_service import AgentPlan, ModelService
from ai_erp_rag_assistant.evals.workflow_runner import WorkflowEvalRunner


CASES = Path(__file__).resolve().parents[1] / "evals" / "agent_cases.example.jsonl"


def test_example_agent_evals_execute_real_graph_without_external_services():
    original_model = workflow.model_service
    original_submit = workflow.submit_approval
    cases = AgentEvaluationService.load_jsonl(CASES)

    report = AgentEvaluationService.evaluate(cases, WorkflowEvalRunner())

    assert report["failed_cases"] == 0, report["results"]
    assert report["total_cases"] >= 15
    assert report["total_turns"] > report["total_cases"]
    assert report["metrics"]["identity"]["rate"] == 1
    assert report["metrics"]["replay"]["total"] == 1
    # 评估完成后必须恢复全局绑定，不污染已有单测和服务函数。
    assert workflow.model_service is original_model
    assert workflow.submit_approval is original_submit


def test_scoring_detects_wrong_route_tools_identity_answer_and_citation():
    turn = AgentEvaluationService.load_jsonl(CASES)[0].turns[0]
    actual = AgentObservation(
        route="general_chat", workflow_status="idle", answer="未知",
        evidence=[], model_calls=[],
        tools=[EvalToolCall(name="rag.search", args={"company_id": "999"})],
    )

    checks = score_turn(turn, actual)

    assert not any(checks.values())


def test_tool_trace_detects_extra_call_and_wrong_parameter():
    case = AgentEvaluationService.load_jsonl(CASES)[7]
    actual = WorkflowEvalRunner()(case)[0]
    assert score_turn(case.turns[0], actual)["tools"] is True
    actual.tools[0].args["date_range"] = ["2026-10-01", "2026-10-31"]
    assert score_turn(case.turns[0], actual)["tools"] is False
    actual.tools.append(EvalToolCall(name="erp.approval_submit"))
    assert score_turn(case.turns[0], actual)["tools"] is False


def test_runtime_errors_count_in_metrics_and_report_omits_sensitive_content():
    cases = AgentEvaluationService.load_jsonl(CASES)

    def broken(case):
        raise RuntimeError("包含凭据的上游错误不能输出 secret-authorization")

    report = AgentEvaluationService.evaluate([cases[0], cases[1]], broken)

    assert report["failed_cases"] == report["error_cases"] == 2
    assert report["metrics"]["route"] == {"passed": 0, "total": 2, "rate": 0}
    assert report["metrics"]["no_answer"] == {"passed": 0, "total": 1, "rate": 0}
    assert "secret-authorization" not in str(report)
    assert "text" not in report["results"][0]["turns"][0]


def test_runner_restores_patches_after_failure():
    import socket

    case = AgentEvaluationService.load_jsonl(CASES)[0]
    original_search = workflow.search_knowledge
    original_model = workflow.model_service
    original_connect = socket.socket.connect
    runner = WorkflowEvalRunner()

    class ProbeGraph:
        @staticmethod
        def invoke(state, config):
            assert workflow.search_knowledge is not original_search
            # 失败发生在保护桩生效后，才能验证异常退出时也会恢复绑定。
            with socket.socket() as client:
                client.connect(("127.0.0.1", 1))

    runner.graph = ProbeGraph()
    with pytest.raises(RuntimeError, match="评估禁止"):
        runner(case)
    assert workflow.search_knowledge is original_search
    assert workflow.model_service is original_model
    assert socket.socket.connect is original_connect


@pytest.mark.parametrize("supports_structured", [False, True])
def test_llm_mode_uses_model_boundary_instead_of_fixture_outputs(monkeypatch, supports_structured):
    case = AgentEvaluationService.load_jsonl(CASES)[0]
    assert case.turns[0].fixtures.plan.route == "knowledge"
    calls = []

    class StructuredModel:
        def invoke(self, messages):
            calls.append("structured")
            return {"parsed": AgentPlan(route="general_chat")}

    class FakeModel:
        def with_structured_output(self, schema, **kwargs):
            if not supports_structured:
                raise NotImplementedError("模拟不支持结构化输出的供应商")
            return StructuredModel()

        def invoke(self, messages):
            payload = json.loads(messages[-1].content)
            is_plan = "output_schema" in payload
            calls.append("json_plan" if is_plan else "answer")
            return SimpleNamespace(content='{"route":"general_chat"}' if is_plan else "模型边界返回的独立回答")

    # 只替换模型客户端，保留真实结构化/JSON 兼容逻辑，防止观测包装影响模型模式。
    monkeypatch.setattr(ModelService, "_model", lambda self, *args, **kwargs: FakeModel())

    actual = WorkflowEvalRunner(with_llm=True)(case)[0]

    assert actual.route == "general_chat"
    assert actual.answer == "模型边界返回的独立回答"
    assert actual.tools == []
    assert actual.model_calls == ["plan", "answer"]
    assert calls == ["structured" if supports_structured else "json_plan", "answer"]
    assert score_turn(case.turns[0], actual)["route"] is False


@pytest.mark.parametrize("with_llm", [False, True])
def test_runner_blocks_database_and_erp_even_in_llm_mode(with_llm):
    import pymysql
    from ai_erp_rag_assistant.app.services.erp_client import ErpClient

    runner = WorkflowEvalRunner(with_llm=with_llm)
    case = AgentEvaluationService.load_jsonl(CASES)[0]

    class ProbeGraph:
        @staticmethod
        def invoke(state, config):
            with pytest.raises(RuntimeError, match="评估禁止"):
                pymysql.connect(host="127.0.0.1", user="unused")
            with pytest.raises(RuntimeError, match="评估禁止"):
                ErpClient()._post("/api/approval/add", {}, {})
            raise RuntimeError("安全边界探测结束")

    runner.graph = ProbeGraph()
    with pytest.raises(RuntimeError, match="安全边界探测结束"):
        runner(case)


def test_case_validation_rejects_unknown_fields_and_invalid_types():
    value = AgentEvaluationService.load_jsonl(CASES)[0].model_dump()
    value["turns"][0]["confirm"] = "true"
    with pytest.raises(ValidationError):
        AgentEvalCase.model_validate(value)
    value["turns"][0]["confirm"] = None
    value["turns"][0]["authorization"] = "禁止在评估集添加真实凭据"
    with pytest.raises(ValidationError):
        AgentEvalCase.model_validate(value)


def test_dataset_loader_rejects_empty_invalid_and_duplicate_cases(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text("# 空数据集\n", encoding="utf-8")
    with pytest.raises(ValueError, match="不能为空"):
        AgentEvaluationService.load_jsonl(path)
    path.write_text('{"id":"broken"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="第 1 行"):
        AgentEvaluationService.load_jsonl(path)
    case = AgentEvaluationService.load_jsonl(CASES)[0].model_dump_json()
    path.write_text(f"\ufeff# 支持 Windows BOM\n{case}\n{case}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="重复"):
        AgentEvaluationService.load_jsonl(path)
