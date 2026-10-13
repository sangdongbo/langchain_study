"""运行配置检查和全部专题的离线检查；无真实模型、无数据库。"""

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import call, patch

from pydantic_ai import models

from pydantic_examples.config import PROJECT_DIR as CONFIG_DIR, build_model, load_environment

models.ALLOW_MODEL_REQUESTS = False
PROJECT_DIR = Path(__file__).resolve().parent


def check_config() -> None:
    with patch("pydantic_examples.config.load_dotenv") as load:
        load_environment()
    assert load.call_args_list == [
        call(CONFIG_DIR / ".env", override=False),
        call(CONFIG_DIR.parents[1] / ".env", override=False),
        call(CONFIG_DIR.parent / "deep_agent_examples" / ".env", override=False),
    ]
    cases = [
        ({"DEEPSEEK_API_KEY": "test-key", "OPENAI_BASE_URL": "https://wrong.example/v1", "OPENAI_MODEL": "wrong"}, "deepseek-chat", "https://api.deepseek.com/v1/"),
        ({"LLM_API_KEY": "test-key", "LLM_BASE_URL": "https://llm.example/v1", "LLM_MODEL": "custom-model", "DEEPSEEK_API_KEY": "other-test-key"}, "custom-model", "https://llm.example/v1/"),
        ({"LLM_API_KEY": "", "OPENAI_API_KEY": "test-key"}, "gpt-4o-mini", "https://api.openai.com/v1/"),
    ]
    for env, name, url in cases:
        with patch("pydantic_examples.config.load_environment"), patch.dict(os.environ, env, clear=True):
            model = build_model()
            assert model.model_name == name
            assert str(model.provider.client.base_url) == url
    with patch("pydantic_examples.config.load_environment"), patch.dict(os.environ, {}, clear=True):
        try:
            build_model()
        except RuntimeError:
            pass
        else:
            raise AssertionError("缺少密钥应在入口报错。")
    print("CONFIG PASS：文件顺序、不覆盖环境、供应商匹配与缺少密钥", flush=True)


def main() -> None:
    check_config()
    tests = sorted((PROJECT_DIR / "examples").glob("*/test.py"))
    assert len(tests) == 8
    env = os.environ | {
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYDANTIC_AI_NO_BANNER": "1",
    }
    for script in tests:
        assert script.with_name("run.py").is_file()
        assert script.with_name("README.md").is_file()
        subprocess.run([sys.executable, str(script)], cwd=PROJECT_DIR, env=env, check=True, timeout=60)
    print("ALL PASS：8 个离线专题，无模型网络请求、无数据库访问")


if __name__ == "__main__":
    main()
