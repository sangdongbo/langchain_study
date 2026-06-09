from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


# LangSmith 版应用的基础配置集中放这里，避免 page/ui/agent 互相导入造成循环依赖。
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
ENV_PATH = PROJECT_ROOT / ".env"

# Streamlit 运行缓存放在本项目目录下，和原始 crm_ask 示例隔离。
CACHE_PATH = APP_DIR / ".cache" / "conversations.json"

# 新建会话时的默认助手资料；侧边栏里可以继续修改并保存到本地缓存。
DEFAULT_TITLE = "小黑"
DEFAULT_PERSONA = "性格火辣的四川姑娘，回答直接、亲切，偶尔带一点俏皮。"

# LangSmith tracing 配置。项目启动后会写入环境变量，让 LangChain 调用自动上报 trace。
DEFAULT_LANGSMITH_TRACING = "true"
DEFAULT_LANGSMITH_ENDPOINT = "https://api.smith.langchain.com"
DEFAULT_LANGSMITH_PROJECT = "crm-ask-langsmith"


def load_project_env(*, override: bool = False) -> bool:
    """加载项目根目录 .env，默认不覆盖 shell / IDE 已经注入的环境变量。"""

    return load_dotenv(ENV_PATH, override=override)


def configure_langsmith(*, override: bool = True) -> None:
    """把 LangSmith 配置注入环境变量，供 LangChain 自动读取。"""

    langsmith_tracing = os.getenv("LANGSMITH_TRACING", DEFAULT_LANGSMITH_TRACING)
    langsmith_api_key = os.getenv("LANGSMITH_API_KEY", "")
    langsmith_endpoint = os.getenv("LANGSMITH_ENDPOINT", DEFAULT_LANGSMITH_ENDPOINT)
    langsmith_project = os.getenv("LANGSMITH_PROJECT", DEFAULT_LANGSMITH_PROJECT)
    langsmith_values = {
        "LANGSMITH_TRACING": langsmith_tracing,
        "LANGSMITH_ENDPOINT": langsmith_endpoint,
        "LANGSMITH_PROJECT": langsmith_project,
        # 兼容仍读取 LANGCHAIN_* 的 LangChain / LangSmith 版本。
        "LANGCHAIN_TRACING_V2": langsmith_tracing,
        "LANGCHAIN_ENDPOINT": langsmith_endpoint,
        "LANGCHAIN_PROJECT": langsmith_project,
    }
    if langsmith_api_key:
        langsmith_values["LANGSMITH_API_KEY"] = langsmith_api_key
        langsmith_values["LANGCHAIN_API_KEY"] = langsmith_api_key
    for name, value in langsmith_values.items():
        if override or name not in os.environ:
            os.environ[name] = value
