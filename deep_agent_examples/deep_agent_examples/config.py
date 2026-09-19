"""项目共享配置。

本模块集中处理三类配置：读取 ``.env``、创建聊天模型，以及生成
LangGraph/LangSmith 每次运行需要的 thread、标签和追踪元数据。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


# 当前示例项目目录和它的上级仓库目录，用于按优先级查找两层 .env。
PROJECT_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = PROJECT_DIR.parent

# 只有配置了 DEEPSEEK_API_KEY、但没有显式指定地址或模型时才使用这两个默认值。
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


def load_environment() -> None:
    """加载环境变量，项目级配置优先，仓库根目录配置作为补充。

    ``override=False`` 保证操作系统中已经存在的环境变量不会被 .env 覆盖；
    第二次加载也只补充第一份 .env 中没有提供的变量。
    """
    load_dotenv(PROJECT_DIR / ".env", override=False)
    load_dotenv(REPOSITORY_DIR / ".env", override=False)


@dataclass(frozen=True)
class ModelSettings:
    """创建聊天模型所需的不可变配置快照。"""

    # api_key：发送给 OpenAI 兼容接口的凭据，不应写入日志或 Trace。
    api_key: str
    # base_url：模型服务根地址；None 表示使用 OpenAI SDK 默认官方地址。
    base_url: str | None
    # model：供应商侧模型标识，例如 deepseek-chat。
    model: str
    # temperature：采样随机度；0 更适合可重复的工具调用示例。
    temperature: float
    # timeout：单次模型 HTTP 请求的超时秒数。
    timeout: float


def model_settings() -> ModelSettings:
    """按照“通用 LLM > DeepSeek > OpenAI”的顺序解析模型配置。

    每套密钥只读取同一供应商对应的地址和模型名，避免出现使用 A 供应商
    密钥却误配 B 供应商地址的情况。
    """
    load_environment()
    llm_api_key = os.getenv("LLM_API_KEY")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    # LLM_* 是显式的通用 OpenAI 兼容配置，优先级最高。
    if llm_api_key:
        api_key = llm_api_key
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL") or "gpt-4o-mini"
    # DeepSeek 密钥存在时自动补齐官方兼容地址和默认模型。
    elif deepseek_api_key:
        api_key = deepseek_api_key
        base_url = os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL
        model = os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL
    # OpenAI 配置最后兜底；base_url 为空时由 SDK 使用官方地址。
    elif openai_api_key:
        api_key = openai_api_key
        base_url = os.getenv("OPENAI_BASE_URL")
        model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    else:
        raise RuntimeError(
            "Missing model credential. Copy .env.example to .env and set "
            "LLM_API_KEY, DEEPSEEK_API_KEY, or OPENAI_API_KEY."
        )
    return ModelSettings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        timeout=float(os.getenv("LLM_TIMEOUT", "120")),
    )


def build_model() -> ChatOpenAI:
    """根据环境配置创建可供所有 Agent 共用的 ChatOpenAI 实例。

    ``ChatOpenAI`` 同时支持 OpenAI 官方接口和兼容接口，因此 DeepSeek 或
    其他供应商只需提供对应的 ``base_url``，无需更换 Agent 代码。
    """
    settings = model_settings()
    return ChatOpenAI(
        # model：传给供应商 API 的模型名称。
        model=settings.model,
        # api_key：请求鉴权凭据；ChatOpenAI 会放入 HTTP 鉴权头。
        api_key=settings.api_key,
        # base_url：把同一 OpenAI 兼容客户端指向 DeepSeek 或其他供应商。
        base_url=settings.base_url,
        # temperature：控制模型输出随机性，不影响工具本身的确定性。
        temperature=settings.temperature,
        # timeout：每次模型网络请求最多等待的秒数。
        timeout=settings.timeout,
        # max_retries：SDK 遇到可重试的网络/限流错误时最多额外尝试两次。
        max_retries=2,
    )


def tracing_enabled() -> bool:
    """判断是否启用 LangSmith 链路追踪，兼容常见的真值写法。"""
    load_environment()
    return os.getenv("LANGSMITH_TRACING", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def tracing_project() -> str:
    """返回 LangSmith 项目名，未配置时归入示例项目默认空间。"""
    load_environment()
    return os.getenv("LANGSMITH_PROJECT") or "deep-agent-examples"


def invoke_config(example: str, thread_id: str) -> dict:
    """构造一次 Graph 调用的运行配置。

    ``thread_id`` 决定 checkpoint/state 属于哪个会话；tags 和 metadata 用于
    LangSmith 检索，``run_name`` 则让单次运行在追踪页面中容易辨认。
    """
    return {
        # configurable.thread_id：Checkpointer 查找会话 State 的主键。
        "configurable": {"thread_id": thread_id},
        # tags：LangSmith 中可筛选的一组标签，不参与 Agent 推理。
        "tags": ["deep-agent-example", example],
        # metadata：随 Trace 保存的结构化检索信息，不会自动进入模型上下文。
        "metadata": {
            "example": example,
            "project_kind": "deep-agent-learning",
        },
        # run_name：当前顶层运行在 LangSmith 时间线中的显示名称。
        "run_name": f"deep-agent-example:{example}",
    }
