"""读取模型配置；导入模块不会加载密钥或发出请求。"""

import os
from pathlib import Path

from browser_use import ChatOpenAI
from dotenv import load_dotenv

# 从文件位置寻找项目目录，避免切换终端工作目录后找不到配置。
PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_environment() -> None:
    # 按“当前示例 → 仓库根目录 → Deep Agents 示例”补齐缺失变量。
    for path in (
        PROJECT_DIR / ".env",
        PROJECT_DIR.parents[1] / ".env",
        PROJECT_DIR.parent / "deep_agent_examples" / ".env",
    ):
        # 已有的进程环境变量及前面加载的值不被后续文件覆盖。
        load_dotenv(path, override=False)


def build_llm() -> ChatOpenAI:
    # 只有显式创建模型时才加载 .env，静态检查无需读取密钥。
    load_environment()
    # 选取第一个有密钥的配置组：LLM_* 优先，其次 DEEPSEEK_*、OPENAI_*。
    for prefix, default_url, default_model in (
        ("LLM", "https://api.openai.com/v1", "gpt-4o-mini"),
        ("DEEPSEEK", "https://api.deepseek.com/v1", "deepseek-chat"),
        ("OPENAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ):
        key = os.getenv(f"{prefix}_API_KEY", "").strip()
        if key:
            # 使用 browser-use 的模型适配器，而不是 LangChain 的同名类。
            return ChatOpenAI(
                model=os.getenv(f"{prefix}_MODEL") or default_model,
                api_key=key,
                base_url=os.getenv(f"{prefix}_BASE_URL") or default_url,
                temperature=0,  # 减少输出随机性，但不保证每次规划完全一致。
                timeout=60,  # 单次模型请求超时，避免无限等待。
                max_retries=2,  # 请求失败时有限重试；它与 Agent 动作失败次数不同。
                # DeepSeek 等接口不支持 OpenAI 的严格 json_schema 响应格式。
                # 将 schema 放进提示词，并由适配器解析、校验返回的数据。
                add_schema_to_system_prompt=True,
                dont_force_structured_output=True,
            )
    # 缺少密钥时尽早报错，不输出密钥内容，也不发起无效请求。
    raise RuntimeError(
        "请在 .env 配置 LLM_API_KEY、DEEPSEEK_API_KEY 或 OPENAI_API_KEY。"
    )
