import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openai import APITimeoutError

from main import build_graph, invoke_llm, load_settings


class LangGraphExampleTests(unittest.TestCase):
    def test_graph_calls_llm_runner_and_returns_answer(self):
        calls = []

        def fake_llm(question: str) -> str:
            calls.append(question)
            return "LangGraph can orchestrate LLM steps."

        graph = build_graph(fake_llm)
        result = graph.invoke({"question": "What does LangGraph do?"})

        self.assertEqual(calls, ["What does LangGraph do?"])
        self.assertEqual(result["answer"], "LangGraph can orchestrate LLM steps.")

    def test_invoke_llm_wraps_connection_errors(self):
        class TimeoutLLM:
            def invoke(self, question: str):
                raise APITimeoutError(request=None)

        with self.assertRaisesRegex(RuntimeError, "连接 OpenAI API 超时"):
            invoke_llm(TimeoutLLM(), "hello")

    def test_load_settings_prefers_project_env_file(self):
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=file-key",
                        "OPENAI_BASE_URL=https://coder.api.visioncoder.cn/v1",
                        "OPENAI_MODEL=vision-model",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "system-key",
                    "OPENAI_BASE_URL": "http://192.168.110.91:8317/v1",
                    "OPENAI_MODEL": "system-model",
                },
            ):
                settings = load_settings(env_file)

        self.assertEqual(settings.api_key, "file-key")
        self.assertEqual(settings.base_url, "https://coder.api.visioncoder.cn/v1")
        self.assertEqual(settings.model, "vision-model")


if __name__ == "__main__":
    unittest.main()
