from __future__ import annotations

"""规则路由版 ReactAgent。

这里的 ReactAgent 不是完整论文意义上的 ReAct 循环，而是学习用的“可读版 Agent”：
先根据用户输入做简单意图判断，再调用对应工具或 RAG 服务。

这样设计的好处是：
- 初学者能清楚看到“问题 -> 路由 -> 工具/RAG -> 回答”的完整路径。
- 每条分支都容易打断点、写测试、讲解日志。
- 后续如果要升级 LangGraph 或真正 tool-calling Agent，可以保持外部接口不变。
"""

import re
from dataclasses import dataclass, field
from typing import Any

from agent_demo.middleware import monitor_tool, report_prompt_switch
from agent_demo.rag.rag_service import RagSummarizeService
from agent_demo.tools.agent_tools import run_tool
from agent_demo.utils.logger_handler import LogStore, make_log


@dataclass(frozen=True)
class AgentResponse:
    """Agent 对页面层返回的统一结果。

    answer 是最终给用户看的文本。
    route 表示本次走了哪条分支，页面会把它显示在回答标题里。
    sources 是 RAG 检索片段，只有 RAG 问答/总结时通常有值。
    tool_result 保留结构化工具结果，方便调试或后续做更丰富的过程展示。
    """

    answer: str
    route: str
    sources: list[dict[str, str]] = field(default_factory=list)
    tool_result: dict[str, Any] | None = None


class ReactAgent:
    """智能体编排层。

    构造函数允许注入 rag_service 和 logs：
    - 页面运行时使用真实 RagSummarizeService。
    - 单元测试时注入 FakeRagService，避免触碰 ChromaDB 或真实模型。
    """

    def __init__(self, rag_service: Any | None = None, logs: LogStore | None = None, retrieval_k: int = 4) -> None:
        self.rag_service = rag_service or RagSummarizeService()
        self.logs = logs or LogStore()
        self.retrieval_k = retrieval_k

    def execute(self, message: str) -> AgentResponse:
        """执行一轮用户输入。

        第一版使用关键词规则做路由。规则越靠前优先级越高，例如“总结北京天气”
        会先命中总结分支。真实生产项目可以把这层替换成模型意图识别或 LangGraph。
        """

        text = message.strip()
        self.logs.add(make_log("用户", text))

        # 总结类问题走 RAG 总结 prompt。
        if any(keyword in text for keyword in ("总结", "概括", "摘要")):
            return self._summarize(text)

        # 工具类问题走 tools。这里故意用简单关键词，方便本地学习演示。
        if "天气" in text:
            return self._weather(text)
        if any(keyword in text for keyword in ("位置", "在哪", "哪里")):
            return self._location()
        if any(keyword in text.lower() for keyword in ("用户", "user_id", "userid")):
            return self._user_id()
        if any(keyword in text for keyword in ("月份", "当前月")):
            return self._current_month()
        if any(keyword in text for keyword in ("外部数据", "生成数据", "模拟数据")):
            return self._external_data(text)

        # 没命中任何工具时，默认走知识库问答。
        return self._rag_answer(text)

    def execute_stream(self, message: str) -> list[str]:
        """预留的流式输出入口。

        目前返回单段文本列表，让页面可以用统一接口渲染。
        后续如果接入真正的 streaming model，可以把这里改成生成器。
        """

        response = self.execute(message)
        return [response.answer]

    def _summarize(self, text: str) -> AgentResponse:
        """RAG 总结分支：先切换 prompt，再调用总结链路。"""

        report_prompt_switch(self.logs, "rag_summary")
        answer = self.rag_service.rag_summarize(text, k=self.retrieval_k)
        docs = self.rag_service.retrieve_docs(text, k=self.retrieval_k)
        return AgentResponse(answer=answer, route="rag:summarize", sources=self._sources(docs))

    def _rag_answer(self, text: str) -> AgentResponse:
        """普通知识库问答分支。"""

        report_prompt_switch(self.logs, "agent_system")
        answer = self.rag_service.answer(text, k=self.retrieval_k)
        docs = self.rag_service.retrieve_docs(text, k=self.retrieval_k)
        return AgentResponse(answer=answer, route="rag:answer", sources=self._sources(docs))

    def _weather(self, text: str) -> AgentResponse:
        """天气工具分支。

        这里不接真实天气 API，只返回 mock 数据。学习重点是展示：
        Agent 如何从问题中抽取参数、如何通过 middleware 记录工具调用、
        如何把结构化工具结果转成自然语言回答。
        """

        location = self._extract_location(text) or "上海"
        result = monitor_tool(
            self.logs,
            "get_weather",
            {"location": location},
            lambda: run_tool("get_weather", {"location": location}),
        )
        data = result["data"]
        answer = f"{data['location']}天气：{data['condition']}，温度 {data['temperature']}。{data['suggestion']}"
        return AgentResponse(answer=answer, route="tool:get_weather", tool_result=result)

    def _location(self) -> AgentResponse:
        """用户位置工具分支。"""

        result = monitor_tool(self.logs, "get_user_location", {}, lambda: run_tool("get_user_location"))
        data = result["data"]
        answer = f"当前演示用户位置：{data['city']} {data['district']}。"
        return AgentResponse(answer=answer, route="tool:get_user_location", tool_result=result)

    def _user_id(self) -> AgentResponse:
        """用户 ID 工具分支。"""

        result = monitor_tool(self.logs, "get_user_id", {}, lambda: run_tool("get_user_id"))
        data = result["data"]
        answer = f"当前用户：{data['name']}，用户 ID：{data['user_id']}。"
        return AgentResponse(answer=answer, route="tool:get_user_id", tool_result=result)

    def _current_month(self) -> AgentResponse:
        """当前月份工具分支。"""

        result = monitor_tool(self.logs, "get_current_month", {}, lambda: run_tool("get_current_month"))
        data = result["data"]
        answer = f"当前月份是 {data['month']}，月份数字为 {data['month_number']}。"
        return AgentResponse(answer=answer, route="tool:get_current_month", tool_result=result)

    def _external_data(self, text: str) -> AgentResponse:
        """模拟外部数据工具分支。"""

        result = monitor_tool(
            self.logs,
            "generate_external_data",
            {"topic": text},
            lambda: run_tool("generate_external_data", {"topic": text}),
        )
        data = result["data"]
        answer = "已生成模拟外部数据：" + "、".join(data["items"])
        return AgentResponse(answer=answer, route="tool:generate_external_data", tool_result=result)

    @staticmethod
    def _extract_location(text: str) -> str | None:
        """从“北京天气”这类表达中抽取地点。

        这是一个演示用轻量解析器，不追求覆盖所有自然语言表达。
        真实项目可替换成正则集合、实体识别模型或 LLM 参数抽取。
        """

        match = re.search(r"([\u4e00-\u9fff]{2,8})天气", text)
        if match:
            raw = match.group(1)
            for prefix in ("帮我查一下", "查一下", "查询", "查看", "帮我查", "我想查"):
                raw = raw.replace(prefix, "")
            return raw[-4:]
        return None

    @staticmethod
    def _sources(documents) -> list[dict[str, str]]:
        """把 LangChain Document 转成页面更容易展示的 dict。"""

        return [
            {
                "source": str(doc.metadata.get("source", "未知来源")),
                "content": doc.page_content.strip(),
            }
            for doc in documents
        ]
