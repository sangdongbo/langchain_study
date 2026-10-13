"""运行配置检查和全部专题的离线检查；无真实模型、无数据库。"""

# subprocess 逐课启动独立进程；patch 用占位环境验证配置，不读取真实密钥。
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import call, patch

from pydantic_ai import models

from pydantic_examples.config import PROJECT_DIR as CONFIG_DIR, build_model, load_environment

# 当前进程禁止真实模型请求；每个子进程的 test.py 也会独立设置此开关。
models.ALLOW_MODEL_REQUESTS = False
PROJECT_DIR = Path(__file__).resolve().parent


def check_config() -> None:
    # 替换 load_dotenv，只检查加载顺序和参数，不实际打开本地 .env。
    with patch("pydantic_examples.config.load_dotenv") as load:
        load_environment()
    assert load.call_args_list == [
        call(CONFIG_DIR / ".env", override=False),
        call(CONFIG_DIR.parents[1] / ".env", override=False),
        call(CONFIG_DIR.parent / "deep_agent_examples" / ".env", override=False),
    ]
    # 分别验证供应商前缀不混用、LLM 优先、空 LLM Key 跳过后选择 OpenAI。
    cases = [
        ({"DEEPSEEK_API_KEY": "test-key", "OPENAI_BASE_URL": "https://wrong.example/v1", "OPENAI_MODEL": "wrong"}, "deepseek-chat", "https://api.deepseek.com/v1/"),
        ({"LLM_API_KEY": "test-key", "LLM_BASE_URL": "https://llm.example/v1", "LLM_MODEL": "custom-model", "DEEPSEEK_API_KEY": "other-test-key"}, "custom-model", "https://llm.example/v1/"),
        ({"LLM_API_KEY": "", "OPENAI_API_KEY": "test-key"}, "gpt-4o-mini", "https://api.openai.com/v1/"),
    ]
    for env, name, url in cases:
        # clear=True 隔离机器原有变量；关闭文件加载，保证所有凭据都只是测试占位值。
        with patch("pydantic_examples.config.load_environment"), patch.dict(os.environ, env, clear=True):
            model = build_model()
            assert model.model_name == name
            assert str(model.provider.client.base_url) == url
    with patch("pydantic_examples.config.load_environment"), patch.dict(os.environ, {}, clear=True):
        # 没有凭据时应在客户端构建阶段明确报错，而不是等到发出网络请求才失败。
        try:
            build_model()
        except RuntimeError:
            pass
        else:
            raise AssertionError("缺少密钥应在入口报错。")
    print("CONFIG PASS：文件顺序、不覆盖环境、供应商匹配与缺少密钥", flush=True)


def main() -> None:
    check_config()
    # 每课都必须具备说明、真实入口与离线入口；排序保证按 01 到 08 展示教学结果。
    tests = sorted((PROJECT_DIR / "examples").glob("*/test.py"))
    assert len(tests) == 8
    # 编码变量必须在启动子进程前设置；在 Python 启动后加载 .env 无法替代这一步。
    env = os.environ | {
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYDANTIC_AI_NO_BANNER": "1",
    }
    for script in tests:
        assert script.with_name("run.py").is_file()
        assert script.with_name("README.md").is_file()
        # sys.executable 复用当前独立环境；进程隔离各课同名 run 模块及模型请求开关。
        # check=True 使任一专题失败立即停止；timeout 防止单课意外卡住整个演示。
        subprocess.run([sys.executable, str(script)], cwd=PROJECT_DIR, env=env, check=True, timeout=60)
    print("ALL PASS：8 个离线专题，无模型网络请求、无数据库访问")


# 直接运行脚本才启动检查，导入时不启动子进程。
if __name__ == "__main__":
    main()
