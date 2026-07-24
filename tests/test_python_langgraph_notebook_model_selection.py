from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import dotenv
import pytest


NOTEBOOK_PATH = Path(__file__).parents[1] / "docs" / "python_langgraph_notes.ipynb"


class FakeChatOpenAI:
    def __init__(self, **kwargs: object) -> None:
        self.kind = "dashscope" if "dashscope.aliyuncs.com" in str(kwargs["base_url"]) else "openai"
        self.kwargs = kwargs


class FakeChatDeepSeek:
    def __init__(self, **kwargs: object) -> None:
        self.kind = "deepseek"
        self.kwargs = kwargs


def notebook_code_cell_source(marker: str) -> str:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    return next(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code" and marker in "".join(cell["source"])
    )


def load_connection_check_namespace(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    source = notebook_code_cell_source("def build_chat_model_for_check")

    monkeypatch.setattr(dotenv, "load_dotenv", lambda: False)
    monkeypatch.setitem(sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI))
    monkeypatch.setitem(sys.modules, "langchain_deepseek", types.SimpleNamespace(ChatDeepSeek=FakeChatDeepSeek))

    namespace: dict[str, object] = {"__name__": "not_main"}
    exec(source, namespace)
    return namespace


def test_auto_selects_dashscope_before_deepseek_compatible_openai_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "auto")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-test-key")
    monkeypatch.setenv("DASHSCOPE_OPENAI_MODEL", "qwen-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "inherited-openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/anthropic")

    namespace = load_connection_check_namespace(monkeypatch)
    models = namespace["build_chat_models"]()

    assert [model.kind for model in models] == ["dashscope", "deepseek"]
    assert models[0].kwargs["model"] == "qwen-test"


def test_model_error_message_separates_provider_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "auto")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-test-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "inherited-openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/anthropic")

    namespace = load_connection_check_namespace(monkeypatch)
    namespace["print_model_error"](RuntimeError("authentication failed"), "连接失败。")
    output = capsys.readouterr().out

    assert "实际调用链： DashScope -> DeepSeek" in output
    assert "DashScope 配置：DASHSCOPE_API_KEY / DASHSCOPE_BASE_URL / DASHSCOPE_OPENAI_MODEL" in output
    assert "DeepSeek 配置：DEEPSEEK_API_KEY / DEEPSEEK_API_BASE / DEEPSEEK_MODEL" in output
    assert "auto 模式忽略 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL" in output


def test_agent_cell_uses_ordered_models_and_provider_specific_error_output() -> None:
    source = notebook_code_cell_source("def build_chat_model()")

    assert "models = build_chat_models()" in source
    assert "ModelFallbackMiddleware(*models)" in source
    assert "print_model_error(exc, \"真实模型请求失败。\")" in source
    assert "os.getenv(\"DASHSCOPE_API_KEY\") or os.getenv(\"OPENAI_API_KEY\")" not in source


def test_connection_check_reloads_the_discovered_project_env() -> None:
    source = notebook_code_cell_source("def build_chat_model_for_check")

    assert "load_dotenv(env_path, override=True)" in source
