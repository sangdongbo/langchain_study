import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypedDict

from dotenv import dotenv_values
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from openai import APIConnectionError, APITimeoutError


"""最小 LangGraph 示例。

这个文件演示了三件事：
1. 从 `.env` 或系统环境变量读取 OpenAI-compatible 配置。
2. 把一次 LLM 调用包进 LangGraph 的节点。
3. 运行图并打印结果。

它不是 Streamlit 页面，而是可以直接 `python main.py` 运行的命令行示例。
"""


class GraphState(TypedDict, total=False):
    """LangGraph 节点之间传递的状态。

    TypedDict 像一个带类型提示的 dict。这里 question 是输入，answer 是输出。
    total=False 表示字段可以不一次性全部存在。
    """

    question: str
    answer: str


@dataclass(frozen=True)
class OpenAISettings:
    """LLM 连接配置。

    frozen=True 表示创建后不再修改，适合保存配置这种只读数据。
    """

    api_key: str | None
    base_url: str | None
    model: str


def load_settings(env_file: Path | str = ".env") -> OpenAISettings:
    """从 `.env` 和系统环境变量读取模型配置。"""

    file_values = dotenv_values(env_file)

    def get_value(name: str, default: str | None = None) -> str | None:
        # 优先级：.env 文件 > 系统环境变量 > 默认值。
        return file_values.get(name) or os.getenv(name) or default

    return OpenAISettings(
        api_key=get_value("OPENAI_API_KEY"),
        base_url=get_value("OPENAI_BASE_URL"),
        model=get_value("OPENAI_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini",
    )


def build_graph(llm_runner: Callable[[str], str]):
    """创建一个只有一个节点的 LangGraph。

    llm_runner 是一个普通 Python 函数：输入问题字符串，返回回答字符串。
    这样图本身不关心具体模型是哪家厂商，便于测试和替换。
    """

    graph = StateGraph(GraphState)

    def call_llm(state: GraphState) -> GraphState:
        question = state["question"]
        return {"answer": llm_runner(question)}

    # START -> call_llm -> END 是最简单的图结构。
    graph.add_node("call_llm", call_llm)
    graph.add_edge(START, "call_llm")
    graph.add_edge("call_llm", END)
    return graph.compile()


def invoke_llm(llm: Any, question: str) -> str:
    """调用 LangChain 模型对象，并把常见网络错误转成更友好的提示。"""

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
    """构造一个可传给 LangGraph 节点的 LLM 调用函数。"""

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
        # 闭包：run 会记住外层创建好的 llm 对象。
        return invoke_llm(llm, question)

    return run


def main() -> None:
    """命令行入口函数。"""

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
