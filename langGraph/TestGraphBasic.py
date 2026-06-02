from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


"""LangGraph 底层 Graph API 的基础例子。

运行方式：
    python langGraph/TestGraphBasic.py

这个文件对应图片里的两个演示：
1. 一个节点通过 state 接收 messages，并追加一条 AIMessage。
2. 多个节点按边顺序执行，并把上一个节点写入的 state 传给下一个节点。
3. 使用 reducer 汇总多个节点写入的列表。
4. 使用条件边和 recursion_limit 控制循环。
5. 在节点中读取图运行时配置。

整个例子不调用大模型，不需要 DeepSeek API Key，可以直接本地运行。
"""


class MessageState(TypedDict, total=False):
    """节点之间通信的消息状态。

    TypedDict 只负责静态类型提示；LangGraph 会按这里声明的字段保留状态。
    如果节点返回了没有声明的字段，默认不会出现在最终结果里。
    """

    messages: list[AnyMessage]
    extra_field: int


def message_node(state: MessageState) -> MessageState:
    """读取已有 messages，追加一条 AIMessage，并写入额外字段。"""

    messages = state["messages"]
    new_message = AIMessage(content="你好！我是节点1")

    return {
        "messages": messages + [new_message],
        "extra_field": 1,
    }


def build_single_node_graph() -> Any:
    """创建一个只有一个节点的图。"""

    graph_builder = StateGraph(MessageState)
    graph_builder.add_node("node", message_node)
    graph_builder.add_edge(START, "node")
    graph_builder.add_edge("node", END)
    return graph_builder.compile()


class ValueState(TypedDict, total=False):
    """多节点示例使用的状态。"""

    value_1: str
    value_2: int


def step_1(state: ValueState) -> ValueState:
    return {"value_1": "a"}


def step_2(state: ValueState) -> ValueState:
    current_value_1 = state["value_1"]
    return {"value_1": f"{current_value_1}b"}


def step_3(state: ValueState) -> ValueState:
    return {"value_2": 10}


def build_multi_node_graph() -> Any:
    """创建一个串行多节点图：step_1 -> step_2 -> step_3。"""

    graph_builder = StateGraph(ValueState)
    graph_builder.add_node("step_1", step_1)
    graph_builder.add_node("step_2", step_2)
    graph_builder.add_node("step_3", step_3)

    graph_builder.add_edge(START, "step_1")
    graph_builder.add_edge("step_1", "step_2")
    graph_builder.add_edge("step_2", "step_3")
    graph_builder.add_edge("step_3", END)

    return graph_builder.compile()


class AggregateState(TypedDict):
    """reducer 示例。

    Annotated[list[str], operator.add] 表示多个节点都返回 aggregate 时，
    不覆盖旧值，而是用 list + list 的方式追加。
    """

    aggregate: Annotated[list[str], operator.add]


def node_a(state: AggregateState) -> AggregateState:
    print(f"Node A sees {state['aggregate']}")
    return {"aggregate": ["A"]}


def node_b(state: AggregateState) -> AggregateState:
    print(f"Node B sees {state['aggregate']}")
    return {"aggregate": ["B"]}


def node_c(state: AggregateState) -> AggregateState:
    print(f"添加 C 到 {state['aggregate']}")
    return {"aggregate": ["C"]}


def node_d(state: AggregateState) -> AggregateState:
    print(f"添加 D 到 {state['aggregate']}")
    return {"aggregate": ["D"]}


def build_reducer_parallel_graph() -> Any:
    """创建一个并行分支汇总图：a -> b/c -> d。"""

    builder = StateGraph(AggregateState)
    builder.add_node("a", node_a)
    builder.add_node("b", node_b)
    builder.add_node("c", node_c)
    builder.add_node("d", node_d)

    builder.add_edge(START, "a")
    builder.add_edge("a", "b")
    builder.add_edge("a", "c")
    builder.add_edge("b", "d")
    builder.add_edge("c", "d")
    builder.add_edge("d", END)

    return builder.compile()


def route_loop(state: AggregateState) -> Literal["b", "__end__"]:
    """如果 aggregate 长度小于 7，就继续走 b，否则结束。"""

    if len(state["aggregate"]) < 7:
        return "b"
    return END


def build_conditional_loop_graph() -> Any:
    """创建一个 a <-> b 的条件循环图。"""

    builder = StateGraph(AggregateState)
    builder.add_node("a", node_a)
    builder.add_node("b", node_b)

    builder.add_edge(START, "a")
    builder.add_conditional_edges("a", route_loop)
    builder.add_edge("b", "a")

    return builder.compile()


def build_complex_loop_graph() -> Any:
    """创建一个更复杂的循环图。

    流程是：
    START -> a
    a 根据 route_loop 决定继续到 b 或结束
    b 同时走向 c 和 d
    c、d 都回到 a

    因为 c 和 d 同时返回 aggregate，AggregateState 的 reducer 会把它们合并。
    """

    builder = StateGraph(AggregateState)
    builder.add_node("a", node_a)
    builder.add_node("b", node_b)
    builder.add_node("c", node_c)
    builder.add_node("d", node_d)

    builder.add_edge(START, "a")
    builder.add_conditional_edges("a", route_loop)
    builder.add_edge("b", "c")
    builder.add_edge("b", "d")
    builder.add_edge(["c", "d"], "a")

    return builder.compile()


class ConfigState(TypedDict, total=False):
    """运行时配置示例使用的状态。"""

    answer: str


def config_node(state: ConfigState, config: RunnableConfig) -> ConfigState:
    """节点读取 graph.invoke 第二个参数里的 configurable 配置。"""

    configurable = config.get("configurable", {})
    user_name = configurable.get("user_name", "匿名用户")
    language = configurable.get("language", "中文")

    return {
        "answer": f"当前用户是 {user_name}，回答语言是 {language}。"
    }


def build_runtime_config_graph() -> Any:
    """创建一个读取运行时配置的图。"""

    builder = StateGraph(ConfigState)
    builder.add_node("config_node", config_node)
    builder.add_edge(START, "config_node")
    builder.add_edge("config_node", END)
    return builder.compile()


def save_graph_png(graph: Any, filename: str) -> None:
    """把图保存成 PNG；如果当前环境不支持渲染，只打印 Mermaid 文本。"""

    output_path = Path(__file__).with_name(filename)
    try:
        output_path.write_bytes(graph.get_graph().draw_mermaid_png())
        print(f"图结构 PNG 已保存：{output_path}")
    except Exception as exc:
        print(f"PNG 渲染失败：{exc}")
        print("可以复制下面的 Mermaid 文本到支持 Mermaid 的编辑器查看：")
        print(graph.get_graph().draw_mermaid())


def print_messages(messages: list[AnyMessage]) -> None:
    """类似 notebook 里的 pretty_print，格式化显示消息。"""

    for message in messages:
        message.pretty_print()


def run_single_node_demo() -> None:
    print("\n===== 单节点 messages 通信示例 =====")
    graph = build_single_node_graph()

    result = graph.invoke(
        {"messages": [HumanMessage(content="你好啊！我是 tomie！")]}
    )

    print("原始返回：")
    print(result)

    print("\npretty_print 格式化显示：")
    print_messages(result["messages"])

    print("\nMermaid 文本：")
    print(graph.get_graph().draw_mermaid())
    save_graph_png(graph, "single_node_graph.png")


def run_multi_node_demo() -> None:
    print("\n===== 多节点串行控制示例 =====")
    graph = build_multi_node_graph()

    result = graph.invoke({})
    print("最终 state：")
    print(result)

    print("\nMermaid 文本：")
    print(graph.get_graph().draw_mermaid())
    save_graph_png(graph, "multi_node_graph.png")


def run_reducer_parallel_demo() -> None:
    print("\n===== reducer 并行分支汇总示例 =====")
    graph = build_reducer_parallel_graph()

    result = graph.invoke({"aggregate": []})
    print("最终 state：")
    print(result)

    print("\nMermaid 文本：")
    print(graph.get_graph().draw_mermaid())
    save_graph_png(graph, "reducer_parallel_graph.png")


def run_conditional_loop_demo() -> None:
    print("\n===== 条件边循环示例 =====")
    graph = build_conditional_loop_graph()

    result = graph.invoke({"aggregate": []})
    print("最终 state：")
    print(result)

    print("\n使用 recursion_limit 限制异常循环：")
    try:
        graph.invoke({"aggregate": []}, {"recursion_limit": 4})
    except GraphRecursionError:
        print("Recursion Error")

    print("\nMermaid 文本：")
    print(graph.get_graph().draw_mermaid())
    save_graph_png(graph, "conditional_loop_graph.png")


def run_complex_loop_demo() -> None:
    print("\n===== 复杂条件循环示例 =====")
    graph = build_complex_loop_graph()

    result = graph.invoke({"aggregate": []})
    print("最终 state：")
    print(result)

    print("\nMermaid 文本：")
    print(graph.get_graph().draw_mermaid())
    save_graph_png(graph, "complex_loop_graph.png")


def run_runtime_config_demo() -> None:
    print("\n===== 图的运行时配置示例 =====")
    graph = build_runtime_config_graph()

    result = graph.invoke(
        {},
        {"configurable": {"user_name": "tomie", "language": "中文"}},
    )
    print("最终 state：")
    print(result)

    print("\nMermaid 文本：")
    print(graph.get_graph().draw_mermaid())
    save_graph_png(graph, "runtime_config_graph.png")


def main() -> None:
    run_single_node_demo()
    run_multi_node_demo()
    run_reducer_parallel_demo()
    run_conditional_loop_demo()
    run_complex_loop_demo()
    run_runtime_config_demo()


if __name__ == "__main__":
    main()
