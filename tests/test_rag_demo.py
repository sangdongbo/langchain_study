import os
import unittest
from unittest.mock import patch

from langchain_core.runnables import RunnableLambda

from rag_demo.rag_chain import (
    IndexingResult,
    LocalHashEmbeddings,
    UploadedText,
    build_rag_chain,
    chunk_ids,
    file_md5,
    documents_from_uploads,
    format_documents,
    get_chat_model,
    make_log,
)


"""RAG demo 的纯函数测试。

这些测试刻意不写入 ChromaDB、不请求 DeepSeek，避免测试依赖外部服务。
主要验证：文件转换、MD5、chunk ID、prompt 字段映射和模型配置选择。
"""


class RagDemoHelperTests(unittest.TestCase):
    def test_documents_from_uploads_skips_empty_files_and_sets_metadata(self):
        """空文件应跳过，有内容的文件应带上 source/suffix/file_md5。"""

        docs = documents_from_uploads(
            [
                UploadedText(name="handbook.md", text="# Vacation\nAnnual leave: 12 days"),
                UploadedText(name="empty.txt", text="   "),
            ]
        )

        self.assertEqual(1, len(docs))
        self.assertEqual("# Vacation\nAnnual leave: 12 days", docs[0].page_content)
        self.assertEqual("handbook.md", docs[0].metadata["source"])
        self.assertEqual(".md", docs[0].metadata["suffix"])
        self.assertEqual(file_md5("# Vacation\nAnnual leave: 12 days"), docs[0].metadata["file_md5"])

    def test_file_md5_is_stable_for_same_content(self):
        """相同内容的 MD5 必须稳定，才能用来判断重复上传。"""

        first = file_md5("同一份健康资料")
        second = file_md5("同一份健康资料")

        self.assertEqual(first, second)
        self.assertEqual(32, len(first))

    def test_chunk_ids_use_file_md5_and_chunk_index(self):
        """chunk ID 使用文件 MD5 + 序号，方便后续追踪来源。"""

        docs = documents_from_uploads([UploadedText(name="health.md", text="饮食和睡眠都很重要。")])

        ids = chunk_ids(docs)

        self.assertEqual([f"{docs[0].metadata['file_md5']}-chunk-0"], ids)

    def test_indexing_result_reports_skipped_file_names(self):
        """入库结果摘要要能告诉用户哪些文件被跳过。"""

        result = IndexingResult(
            added_chunks=2,
            skipped_files=["health.md"],
            indexed_files=[("sleep.md", "abc123")],
        )

        self.assertEqual("写入 2 个文本块，跳过重复文件：health.md", result.summary())

    def test_format_documents_includes_source_and_chunk_content(self):
        """检索上下文中应包含来源文件名和文本内容。"""

        docs = documents_from_uploads(
            [
                UploadedText(name="policy.txt", text="Sick leave requires approval."),
                UploadedText(name="faq.md", text="Ask HR before submitting."),
            ]
        )

        context = format_documents(docs)

        self.assertIn("[1] 来源：policy.txt", context)
        self.assertIn("Sick leave requires approval.", context)
        self.assertIn("[2] 来源：faq.md", context)
        self.assertIn("Ask HR before submitting.", context)

    def test_make_log_formats_stage_and_message(self):
        """日志格式固定，便于页面和终端一起展示。"""

        entry = make_log("检索", "命中 3 个片段")

        self.assertEqual("检索", entry.stage)
        self.assertEqual("命中 3 个片段", entry.message)
        self.assertRegex(entry.render(), r"\[\d{2}:\d{2}:\d{2}\] 检索：命中 3 个片段")

    def test_local_hash_embeddings_are_deterministic_normalized_vectors(self):
        """本地 hash embedding 对同一文本应返回相同的归一化向量。"""

        embeddings = LocalHashEmbeddings(dimensions=16)

        first = embeddings.embed_query("年假 12 天")
        second = embeddings.embed_query("年假 12 天")

        self.assertEqual(first, second)
        self.assertEqual(16, len(first))
        self.assertAlmostEqual(1.0, sum(value * value for value in first), places=6)

    def test_rag_chain_maps_question_and_context_fields_into_prompt(self):
        """LCEL 链应把 question/context 两个字段分别填进 prompt。"""

        seen = {}

        def capture_model(messages):
            seen["text"] = messages.to_string()
            return "ok"

        chain = build_rag_chain(model=RunnableLambda(capture_model))

        result = chain.invoke({"question": "年假有几天？", "context": "年假：12 天"})

        self.assertEqual("ok", result)
        self.assertIn("问题：年假有几天？", seen["text"])
        self.assertIn("年假：12 天", seen["text"])
        self.assertNotIn("{'question'", seen["text"])

    def test_get_chat_model_prefers_deepseek_client_when_deepseek_key_exists(self):
        """有 DeepSeek key 时优先用 ChatDeepSeek，避免误用 OPENAI_BASE_URL。"""

        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "OPENAI_API_KEY": "sk-openai",
            "OPENAI_BASE_URL": "https://api.deepseek.com/anthropic",
            "OPENAI_MODEL": "deepseek-v4-flash",
        }

        with patch.dict(os.environ, env, clear=True):
            model = get_chat_model()

        self.assertEqual("ChatDeepSeek", type(model).__name__)


if __name__ == "__main__":
    unittest.main()
