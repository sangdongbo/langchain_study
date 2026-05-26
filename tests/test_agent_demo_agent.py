from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.tools import BaseTool

from agent_demo.middleware import monitor_tool, report_prompt_switch
from agent_demo.react_agent import ReactAgent
from agent_demo.tools.agent_tools import (
    generate_external_data,
    get_current_month,
    get_user_id,
    get_user_location,
    get_weather,
    list_tools,
    run_tool,
)
from agent_demo.utils.logger_handler import LogStore


class FakeRagService:
    def __init__(self) -> None:
        self.last_question = ""

    def retrieve_docs(self, question: str, k: int = 4) -> list[Document]:
        self.last_question = question
        return [Document(page_content="片段内容", metadata={"source": "fake.md"})]

    def answer(self, question: str, k: int = 4) -> str:
        self.last_question = question
        return f"RAG回答：{question}"

    def rag_summarize(self, query: str, k: int = 4) -> str:
        self.last_question = query
        return f"总结：{query}"


def test_mock_tools_return_structured_results() -> None:
    assert isinstance(get_user_id, BaseTool)
    assert isinstance(get_user_location, BaseTool)
    assert isinstance(get_current_month, BaseTool)
    assert isinstance(get_weather, BaseTool)
    assert isinstance(generate_external_data, BaseTool)
    assert get_user_id.invoke({})["data"]["user_id"] == "U1001"
    assert get_user_location.invoke({})["data"]["city"] == "上海"
    assert "month" in get_current_month.invoke({})["data"]
    assert get_weather.invoke({"location": "北京"})["data"]["location"] == "北京"
    assert generate_external_data.invoke({"topic": "销售"})["data"]["topic"] == "销售"


def test_tools_are_registered_and_invokable() -> None:
    tool_names = {tool.name for tool in list_tools()}

    assert {"get_user_id", "get_user_location", "get_weather"}.issubset(tool_names)
    assert run_tool("get_weather", {"location": "杭州"})["data"]["location"] == "杭州"


def test_middleware_records_tool_call(tmp_path) -> None:
    logs = LogStore(log_dir=tmp_path)

    result = monitor_tool(logs, "demo_tool", {"a": 1}, lambda: {"ok": True})

    assert result == {"ok": True}
    assert "工具 demo_tool 参数" in logs.render_lines()[0]
    assert "工具 demo_tool 完成" in logs.render_lines()[1]


def test_report_prompt_switch_records_prompt(tmp_path) -> None:
    logs = LogStore(log_dir=tmp_path)

    report_prompt_switch(logs, "rag_summary")

    assert "切换到 rag_summary" in logs.render_lines()[0]


def test_agent_routes_weather_to_tool(tmp_path) -> None:
    logs = LogStore(log_dir=tmp_path)
    agent = ReactAgent(rag_service=FakeRagService(), logs=logs)

    response = agent.execute("帮我查一下北京天气")

    assert response.answer.startswith("北京天气")
    assert response.route == "tool:get_weather"


def test_agent_routes_summary_to_rag_summary(tmp_path) -> None:
    agent = ReactAgent(rag_service=FakeRagService(), logs=LogStore(log_dir=tmp_path))

    response = agent.execute("总结一下智能体项目")

    assert response.answer == "总结：总结一下智能体项目"
    assert response.route == "rag:summarize"


def test_agent_routes_default_to_rag_answer(tmp_path) -> None:
    agent = ReactAgent(rag_service=FakeRagService(), logs=LogStore(log_dir=tmp_path))

    response = agent.execute("智能体是什么？")

    assert response.answer == "RAG回答：智能体是什么？"
    assert response.route == "rag:answer"
    assert response.sources[0]["source"] == "fake.md"
