import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypedDict

from dotenv import dotenv_values
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from openai import APIConnectionError, APITimeoutError


class GraphState(TypedDict, total=False):
    question: str
    answer: str


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str | None
    base_url: str | None
    model: str


def load_settings(env_file: Path | str = ".env") -> OpenAISettings:
    file_values = dotenv_values(env_file)

    def get_value(name: str, default: str | None = None) -> str | None:
        return file_values.get(name) or os.getenv(name) or default

    return OpenAISettings(
        api_key=get_value("OPENAI_API_KEY"),
        base_url=get_value("OPENAI_BASE_URL"),
        model=get_value("OPENAI_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini",
    )


def build_graph(llm_runner: Callable[[str], str]):
    graph = StateGraph(GraphState)

    def call_llm(state: GraphState) -> GraphState:
        question = state["question"]
        return {"answer": llm_runner(question)}

    graph.add_node("call_llm", call_llm)
    graph.add_edge(START, "call_llm")
    graph.add_edge("call_llm", END)
    return graph.compile()


def invoke_llm(llm: Any, question: str) -> str:
    try:
        response = llm.invoke(question)
    except APITimeoutError as exc:
        raise RuntimeError(
            "连接 OpenAI API 超时。请检查网络、代理，或在 .env 中配置可访问的 OPENAI_BASE_URL。"
        ) from exc
    except APIConnectionError as exc:
        raise RuntimeError(
            "无法连接 OpenAI API。请检查网络、代理，或在 .env 中配置可访问的 OPENAI_BASE_URL。"
        ) from exc

    return str(response.content)


def create_openai_runner() -> Callable[[str], str]:
    settings = load_settings()

    if not settings.api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Create a .env file or set the environment variable."
        )

    llm = ChatOpenAI(
        api_key=settings.api_key,
        model=settings.model,
        temperature=0.2,
        base_url=settings.base_url,
        timeout=20,
        max_retries=1,
    )

    def run(question: str) -> str:
        return invoke_llm(llm, question)

    return run


def main() -> None:
    question = "用一句话解释 LangGraph 和 LangChain 的关系。"
    settings = load_settings()
    print("Base URL:", settings.base_url or "https://api.openai.com/v1")
    print("Model:", settings.model)
    graph = build_graph(create_openai_runner())
    result = graph.invoke({"question": question})

    print("Question:", question)
    print("Answer:", result["answer"])


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Error: {exc}")
