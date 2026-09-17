from types import SimpleNamespace

from ai_erp_rag_assistant.app.services.model_service import (
    ApprovalFieldExtraction,
    ModelService,
    RerankResult,
)


def test_model_client_is_reused_for_same_generation_parameters(monkeypatch):
    created = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)
    service = ModelService()
    service.settings = SimpleNamespace(
        llm_api_key="test-key",
        llm_base_url="https://llm.example/v1",
        llm_model="test-model",
        llm_timeout=20.0,
    )

    first = service._model({"temperature": 0.2, "max_tokens": 512})
    second = service._model({"temperature": 0.2, "max_tokens": 512})

    assert first is second
    assert len(created) == 1
    assert created[0]["max_retries"] == 0
    assert created[0]["timeout"] == 20.0


def test_structured_parse_error_reuses_raw_response_without_second_model_call(monkeypatch):
    calls = {"invoke": 0}

    class FakeRunnable:
        def invoke(self, messages):
            calls["invoke"] += 1
            return {
                # 模拟 LangChain include_raw=True：解析字段为空，但 raw 仍保留原文。
                "parsed": None,
                "raw": SimpleNamespace(content='{"fields":{"reason":"就医"}}'),
                "parsing_error": ValueError("schema parser failed"),
            }

    class FakeModel:
        def with_structured_output(self, schema, *, method, include_raw):
            assert schema is ApprovalFieldExtraction
            assert method == "json_mode"
            assert include_raw is True
            return FakeRunnable()

    service = ModelService()
    service.settings = SimpleNamespace(
        llm_api_key="test-key",
        llm_structured_output_method="json_mode",
        llm_max_retries=0,
    )
    monkeypatch.setattr(service, "_model", lambda *_args, **_kwargs: FakeModel())
    monkeypatch.setattr(
        service,
        "_invoke",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("结构化解析失败不应重新请求模型")
        ),
    )

    result = service._invoke_structured(
        "提取字段",
        {"user_message": "因为就医"},
        ApprovalFieldExtraction,
    )

    assert result == {"fields": {"reason": "就医"}}
    assert calls["invoke"] == 1


def test_runnable_retry_uses_configured_attempts_for_transient_failures():
    captured = {}

    class FakeRunnable:
        def with_retry(self, **kwargs):
            captured.update(kwargs)
            return self

        def invoke(self, messages):
            return "ok"

    service = ModelService()
    service.settings = SimpleNamespace(llm_max_retries=2)

    assert service._invoke_runnable(FakeRunnable(), []) == "ok"
    assert captured["stop_after_attempt"] == 3
    assert TimeoutError in captured["retry_if_exception_type"]


def test_prompt_context_limits_keep_recent_messages_and_citation_metadata():
    conversation = [
        {"role": "user", "content": "旧消息"},
        {"role": "assistant", "content": "旧回复"},
        {"role": "user", "content": "新消息"},
    ]
    bounded = ModelService._bounded_conversation(conversation, max_messages=2, max_chars=5)
    assert [item["content"] for item in bounded] == ["旧回复"[:2], "新消息"]

    evidence = [
        {
            "chunk_id": "c1",
            "source": "制度.pdf",
            "knowledge_base_key": "hr",
            "text": "x" * 10_000,
            "internal_secret": "must-not-pass",
        }
    ]
    prompt_evidence = ModelService._evidence_for_prompt(evidence)
    assert len(prompt_evidence[0]["text"]) <= 4_000
    assert prompt_evidence[0]["knowledge_base_key"] == "hr"
    assert "internal_secret" not in prompt_evidence[0]


def test_rerank_limits_total_candidate_text_sent_to_model(monkeypatch):
    captured = {}
    service = ModelService()
    monkeypatch.setattr(service, "is_configured", lambda: True)

    def fake_structured(system, payload, schema, **kwargs):
        captured["payload"] = payload
        assert schema is RerankResult
        return RerankResult(items=[])

    monkeypatch.setattr(service, "_invoke_structured", fake_structured)
    evidence = [
        {"chunk_id": f"chunk-{index}", "text": "x" * 3_000, "score": 0.9}
        for index in range(50)
    ]

    service.rerank("制度", evidence, top_k=5)

    text_size = sum(len(item["text"]) for item in captured["payload"]["candidates"])
    assert text_size <= 24_000
