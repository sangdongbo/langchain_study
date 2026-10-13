"""Agent 评估集校验和规则评分；执行器由独立评估脚本注入。"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_erp_rag_assistant.app.services.model_service import AgentPlan
from ai_erp_rag_assistant.app.services.rag_evaluation_service import (
    _citation_is_grounded,
    _extract_citations,
    _looks_like_abstention,
)


class EvalModel(BaseModel):
    """拒绝未知字段，避免评估配置拼错后被静默忽略。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class EvalToolCall(EvalModel):
    name: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)


class EvalCitation(EvalModel):
    source: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)


class AgentExpectation(EvalModel):
    route: Literal["knowledge", "erp_status", "approval_workflow", "customer_management", "general_chat"]
    workflow_status: str | None = None
    # 工具序列必须完全匹配；args 只校验声明的参数，便于聚焦业务边界。
    tools: list[EvalToolCall]
    model_calls: list[str] | None = None
    answer_contains: list[str] = Field(default_factory=list)
    answer_excludes: list[str] = Field(default_factory=list)
    should_answer: bool | None = None
    citations: list[EvalCitation] | None = None


class AgentFixtures(EvalModel):
    """模拟输入与期望输出分开，评分器不能用期望值生成实际结果。"""

    plan: AgentPlan
    answer: str = ""
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    customer_items: list[dict[str, Any]] = Field(default_factory=list)
    approval_status: dict[str, Any] = Field(default_factory=dict)
    write_mode: Literal["mock", "disabled"] = "mock"


class AgentEvalTurn(EvalModel):
    message: str = Field(min_length=1, max_length=10000)
    # 这些字段模拟不可信的请求输入，可信身份始终由执行器单独注入。
    user_id: str = "863"
    company_id: str = "16"
    department: str = "人事部"
    form_values: dict[str, Any] = Field(default_factory=dict)
    confirm: bool | None = None
    preview_confirmation: Literal["none", "current", "stale"] = "none"
    replay: bool = False
    fixtures: AgentFixtures
    expected: AgentExpectation


class AgentEvalCase(EvalModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[\w.-]+$")
    assistant_type: Literal["rag", "approval", "customer"]
    turns: list[AgentEvalTurn] = Field(min_length=1, max_length=20)


class AgentObservation(EvalModel):
    """执行器返回内部观测；公开报告不包含答案、表单或凭据。"""

    route: str
    workflow_status: str
    answer: str
    evidence: list[dict[str, Any]]
    tools: list[EvalToolCall]
    model_calls: list[str]
    replay_pass: bool | None = None


def score_turn(turn: AgentEvalTurn, actual: AgentObservation) -> dict[str, bool]:
    """按独立期望评分，不用另一轮 LLM 充当裁判。"""
    expected = turn.expected
    checks = {
        "route": actual.route == expected.route,
        "tools": len(actual.tools) == len(expected.tools) and all(
            observed.name == wanted.name
            and all(observed.args.get(key) == value for key, value in wanted.args.items())
            for observed, wanted in zip(actual.tools, expected.tools)
        ),
        "answer": bool(actual.answer.strip())
        and all(text in actual.answer for text in expected.answer_contains)
        and all(text not in actual.answer for text in expected.answer_excludes),
    }
    # 每个业务工具都必须沿用模拟登录身份；调用次数为零时不虚增隔离指标。
    if actual.tools:
        checks["identity"] = all(
            call.args.get("company_id") == "16"
            and (call.args.get("uid") == "863" if call.name != "rag.search" else (
                call.args.get("department") == "人事部"
                and call.args.get("permission_tags") == ["employee"]
            ))
            for call in actual.tools
        )
    if expected.workflow_status is not None:
        checks["workflow"] = actual.workflow_status == expected.workflow_status
    if expected.model_calls is not None:
        checks["model_calls"] = actual.model_calls == expected.model_calls
    if expected.should_answer is False:
        checks["no_answer"] = _looks_like_abstention(actual.answer) or "未查询到" in actual.answer
    if expected.citations is not None:
        citations = _extract_citations(actual.answer)
        wanted = [(item.source, item.page) for item in expected.citations]
        checks["citations"] = sorted(citations, key=str) == sorted(wanted, key=str) and all(
            _citation_is_grounded(item, actual.evidence) for item in citations
        )
    if turn.replay:
        checks["replay"] = actual.replay_pass is True
    return checks


class AgentEvaluationService:
    """加载 JSONL 并汇总逐轮指标，异常样例仍计入失败分母。"""

    @staticmethod
    def load_jsonl(path: str | Path) -> list[AgentEvalCase]:
        cases: list[AgentEvalCase] = []
        seen: set[str] = set()
        with Path(path).open(encoding="utf-8-sig") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                try:
                    case = AgentEvalCase.model_validate(json.loads(line))
                except (ValueError, TypeError) as exc:
                    # 不回显原始输入，避免公司案例中的敏感内容进入控制台。
                    raise ValueError(f"第 {number} 行评估配置无效，请检查字段和类型") from exc
                if case.id in seen:
                    raise ValueError(f"第 {number} 行存在重复样例 ID")
                seen.add(case.id)
                cases.append(case)
        if not cases:
            raise ValueError("评估集不能为空")
        return cases

    @staticmethod
    def evaluate(
        cases: list[AgentEvalCase],
        runner: Callable[[AgentEvalCase], list[AgentObservation]],
        *,
        mode: Literal["offline", "llm"] = "offline",
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        totals: dict[str, list[bool]] = {}
        for case in cases:
            started = perf_counter()
            checks_by_turn: list[dict[str, bool]] = []
            observations: list[AgentObservation] = []
            error = ""
            try:
                observations = runner(case)
                if len(observations) != len(case.turns):
                    raise ValueError("执行器返回的轮数不匹配")
                checks_by_turn = [score_turn(turn, actual) for turn, actual in zip(case.turns, observations)]
            except Exception as exc:
                error = type(exc).__name__
                # 运行失败不能只从准确率分母中移除，否则模型故障会让评分变好。
                for turn in case.turns:
                    failed = {"route": False, "tools": False, "answer": False}
                    for name, enabled in (
                        ("workflow", turn.expected.workflow_status is not None),
                        ("model_calls", turn.expected.model_calls is not None),
                        ("no_answer", turn.expected.should_answer is False),
                        ("citations", turn.expected.citations is not None),
                        ("identity", bool(turn.expected.tools)),
                        ("replay", turn.replay),
                    ):
                        if enabled:
                            failed[name] = False
                    checks_by_turn.append(failed)
            for checks in checks_by_turn:
                for name, passed in checks.items():
                    totals.setdefault(name, []).append(passed)
            results.append({
                "id": case.id,
                "passed": not error and all(all(checks.values()) for checks in checks_by_turn),
                "error": error,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "turns": [
                    {
                        "turn": index + 1,
                        "checks": checks,
                        "failed_checks": [name for name, passed in checks.items() if not passed],
                        "route": observations[index].route if not error else "",
                        "tool_names": [item.name for item in observations[index].tools] if not error else [],
                    }
                    for index, checks in enumerate(checks_by_turn)
                ],
            })
        passed = sum(item["passed"] for item in results)
        return {
            "mode": mode,
            "orchestrator": "langgraph",
            "total_cases": len(cases),
            "total_turns": sum(len(case.turns) for case in cases),
            "passed_cases": passed,
            "failed_cases": len(cases) - passed,
            "error_cases": sum(bool(item["error"]) for item in results),
            "metrics": {
                name: {"passed": sum(values), "total": len(values), "rate": round(sum(values) / len(values), 6)}
                for name, values in totals.items()
            },
            "results": results,
        }
