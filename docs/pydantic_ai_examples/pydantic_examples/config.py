"""读取现有模型配置；导入模块不会加载密钥或发出请求。"""

# os 读取进程环境；Path 根据代码位置寻找配置，不依赖终端当前所在目录。
import os
from pathlib import Path

# python-dotenv 加载 .env；OpenAIProvider 连接支持 Chat Completions 的兼容接口。
from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

# config.py 位于共享包内，上两级就是独立示例项目根目录。
PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_environment() -> None:
    # 按项目自身、仓库根目录、参考项目的顺序补齐变量，缺少某个文件也可以继续。
    for path in (
        PROJECT_DIR / ".env",
        PROJECT_DIR.parents[1] / ".env",
        PROJECT_DIR.parent / "deep_agent_examples" / ".env",
    ):
        # override=False 保留进程已有值和先加载的同名值；空值也不会被后续文件覆盖。
        load_dotenv(path, override=False)


def build_model() -> OpenAIChatModel:
    # 导入本模块不会执行这里；仅真实演示入口需要读取密钥并创建客户端。
    load_environment()
    # 供应商优先级与配置文件优先级分别处理；选择第一个非空 Key 所在的供应商组。
    for prefix, default_url, default_model in (
        ("LLM", "https://api.openai.com/v1", "gpt-4o-mini"),
        ("DEEPSEEK", "https://api.deepseek.com/v1", "deepseek-chat"),
        ("OPENAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ):
        key = os.getenv(f"{prefix}_API_KEY", "").strip()
        if key:
            # Key、模型名、地址始终取同一前缀，避免将 DeepSeek Key 拼到其他服务地址。
            # 创建客户端尚未发出模型请求；请求发生在 Agent.run / run_sync / run_stream。
            return OpenAIChatModel(
                os.getenv(f"{prefix}_MODEL") or default_model,
                provider=OpenAIProvider(
                    api_key=key,
                    base_url=os.getenv(f"{prefix}_BASE_URL") or default_url,
                ),
                settings={"temperature": 0, "timeout": 60},  # 降低输出随机性，并设单次请求超时。
            )
    # 错误仅列出配置变量名，不附带任何密钥或完整环境内容。
    raise RuntimeError("请在 .env 配置 LLM_API_KEY、DEEPSEEK_API_KEY 或 OPENAI_API_KEY。")
