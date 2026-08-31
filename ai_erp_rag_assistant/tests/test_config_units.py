import ai_erp_rag_assistant.app.config as config_module


def _clear_model_environment(monkeypatch):
    for key in (
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_BASE_URL",
        "DASHSCOPE_OPENAI_MODEL",
        "DASHSCOPE_EMBEDDING_MODEL",
        "DASHSCOPE_EMBEDDING_DIMENSIONS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
    ):
        monkeypatch.delenv(key, raising=False)


def test_erp_base_url_accepts_approval_project_alias(monkeypatch):
    monkeypatch.delenv("ERP_BASE_URL", raising=False)
    monkeypatch.delenv("AI_APPROVAL_CRM_BASE_URL", raising=False)
    monkeypatch.setattr(
        config_module,
        "dotenv_values",
        lambda _path: {"AI_APPROVAL_CRM_BASE_URL": "http://crm.local:8002"},
    )

    settings = config_module.Settings.from_env()

    assert settings.erp_base_url == "http://crm.local:8002"


def test_erp_base_url_wins_over_approval_project_alias(monkeypatch):
    monkeypatch.delenv("ERP_BASE_URL", raising=False)
    monkeypatch.delenv("AI_APPROVAL_CRM_BASE_URL", raising=False)
    monkeypatch.setattr(
        config_module,
        "dotenv_values",
        lambda _path: {
            "ERP_BASE_URL": "https://erp.local",
            "AI_APPROVAL_CRM_BASE_URL": "http://crm.local:8002",
        },
    )

    settings = config_module.Settings.from_env()

    assert settings.erp_base_url == "https://erp.local"


def test_dashscope_endpoint_is_reused_for_embeddings(monkeypatch):
    _clear_model_environment(monkeypatch)
    monkeypatch.setattr(
        config_module,
        "dotenv_values",
        lambda _path: {
            "DASHSCOPE_API_KEY": "workspace-key",
            "DASHSCOPE_BASE_URL": "https://workspace.example/v1",
            "DASHSCOPE_OPENAI_MODEL": "qwen-plus",
            "DASHSCOPE_EMBEDDING_MODEL": "text-embedding-v4",
            "DASHSCOPE_EMBEDDING_DIMENSIONS": "2048",
        },
    )

    settings = config_module.Settings.from_env()

    assert settings.llm_base_url == "https://workspace.example/v1"
    assert settings.embedding_base_url == "https://workspace.example/v1"
    assert settings.embedding_model == "text-embedding-v4"


def test_openai_base_url_is_deepseek_fallback(monkeypatch):
    _clear_model_environment(monkeypatch)
    monkeypatch.setattr(
        config_module,
        "dotenv_values",
        lambda _path: {
            "DEEPSEEK_API_KEY": "deepseek-key",
            "OPENAI_BASE_URL": "https://api.deepseek.com/anthropic",
            "OPENAI_MODEL": "deepseek-v4-flash",
        },
    )

    settings = config_module.Settings.from_env()

    assert settings.llm_base_url == "https://api.deepseek.com/anthropic"
    assert settings.llm_model == "deepseek-v4-flash"


def test_process_environment_overrides_dotenv(monkeypatch):
    monkeypatch.setattr(
        config_module,
        "dotenv_values",
        lambda _path: {"ERP_BASE_URL": "https://dotenv.example"},
    )
    monkeypatch.setenv("ERP_BASE_URL", "https://process.example")

    settings = config_module.Settings.from_env()

    assert settings.erp_base_url == "https://process.example"
