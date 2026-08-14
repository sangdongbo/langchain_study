from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from ai_erp_rag_assistant.app.config import get_settings

logger = logging.getLogger("ai_erp_rag_assistant.model")


class AgentPlan(BaseModel):
    route: Literal["knowledge", "erp_status", "approval_workflow", "general_chat"]
    query: str = ""
    approval_type: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    decision: Literal["continue", "confirm", "cancel"] = "continue"


class ModelService:
    """One boundary for planner and answer generation.

    The graph never decides business intent with keyword branches. The model
    returns a bounded JSON plan, while ERP and RAG services remain deterministic
    and auditable tools.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(self.settings.llm_api_key)

    def _model(self):
        if not self.settings.llm_api_key:
            raise RuntimeError("未配置 LLM_API_KEY/DEEPSEEK_API_KEY，无法执行 Agent。")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("缺少 langchain-openai，请执行 uv sync。") from exc
        return ChatOpenAI(
            model=self.settings.llm_model,
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            temperature=0,
            timeout=self.settings.llm_timeout,
            max_retries=1,
        )

    def plan(self, message: str, *, context: dict[str, Any] | None = None) -> AgentPlan:
        context = context or {}
        system = """你是企业 ERP 聊天助手的 Agent Planner。只返回一个 JSON 对象，不要 Markdown。
route 只能是 knowledge、erp_status、approval_workflow、general_chat。
knowledge：询问制度、员工手册、政策、流程规则；query 写检索问题。
erp_status：查询实时审批、当前审批人、审批状态；不要把制度问题归为此类。
approval_workflow：用户要发起/提交审批。approval_type 用用户说的业务类型，fields 只填从当前消息明确提取的值；不确定的值留空。用户确认提交时 decision=confirm，取消时 decision=cancel。
general_chat：问候、解释技术或与 ERP/RAG 无关的问题。
不要编造字段值、公司信息、审批状态。"""
        payload = {
            "user_message": message,
            "known_context": context,
            "output_schema": {
                "route": "knowledge|erp_status|approval_workflow|general_chat",
                "query": "string",
                "approval_type": "string",
                "fields": "object",
                "reason": "string",
                "decision": "continue|confirm|cancel",
            },
        }
        try:
            raw = self._invoke(system, payload)
            return AgentPlan.model_validate(raw)
        except (ValidationError, ValueError, RuntimeError) as exc:
            logger.warning("Agent planner failed: %s", exc)
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"LLM Planner 返回了无法识别的计划：{exc}") from exc

    def answer(
        self,
        question: str,
        *,
        route: str,
        evidence: list[dict[str, Any]] | None = None,
        erp_data: dict[str, Any] | None = None,
    ) -> str:
        evidence = evidence or []
        erp_data = erp_data or {}
        system = """你是企业级 ERP 助手。用中文简洁回答，只使用输入的 evidence 或 erp_data。
制度问答必须引用来源文件和页码；证据为空时明确说没有检索到依据，不得凭常识补充。
实时审批问题只能使用 erp_data，并说明这是 ERP 实时数据。不要把 ERP 状态和制度文档混淆。"""
        payload = {
            "question": question,
            "route": route,
            "evidence": evidence,
            "erp_data": erp_data,
        }
        try:
            return self._text(self._invoke(system, payload, parse_json=False))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"LLM 回答生成失败：{exc}") from exc

    def _invoke(self, system: str, payload: dict[str, Any], *, parse_json: bool = True) -> Any:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = self._model().invoke(
            [SystemMessage(content=system), HumanMessage(content=json.dumps(payload, ensure_ascii=False))]
        )
        content = self._text(response.content)
        if not parse_json:
            return content
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"LLM response is not JSON: {content[:160]}")
        return json.loads(content[start : end + 1])

    @staticmethod
    def _text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item))
            return "".join(parts).strip()
        return str(content).strip()


model_service = ModelService()
