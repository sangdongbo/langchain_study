from pathlib import Path

import pytest

from ai_erp_rag_assistant.app.services.rag_evaluation_service import (
    RagEvaluationCase,
    RagEvaluationCaseError,
    RagEvaluationService,
)


def _case(**overrides):
    value = {
        "id": "leave",
        "query": "病假需要什么材料？",
        "company_id": "C001",
        "knowledge_base_key": "handbook",
        "expected_chunk_ids": ["chunk-2"],
        "expected_citations": [{"source": "handbook.pdf", "page": 9}],
        "should_answer": True,
        "top_k": 2,
    }
    value.update(overrides)
    return RagEvaluationCase.from_dict(value)


def test_evaluation_metrics_cover_recall_rerank_and_grounded_citation():
    case = _case()
    service = RagEvaluationService()

    def retriever(case, count):
        return [
            {"chunk_id": "chunk-1", "source": "handbook.pdf", "page": 1, "score": 0.9},
            {"chunk_id": "chunk-2", "source": "handbook.pdf", "page": 9, "score": 0.8},
        ]

    def reranker(case, evidence, top_k):
        return [evidence[1], evidence[0]]

    report = service.evaluate(
        [case],
        retriever=retriever,
        reranker=reranker,
        answerer=lambda case, evidence: "答案\n\n依据：[1]《handbook.pdf》第 9 页",
    )

    assert report.recall_at_k == 1.0
    assert report.mean_reciprocal_rank == 1.0
    assert report.rerank_top1_accuracy == 1.0
    assert report.citation_precision == 1.0
    assert report.expected_citation_recall == 1.0
    assert report.passed_cases == 1


def test_no_answer_case_requires_empty_retrieval():
    case = _case(
        id="unknown",
        query="火星旅游补贴",
        should_answer=False,
        expected_chunk_ids=[],
        expected_citations=[],
    )
    report = RagEvaluationService().evaluate(
        [case], retriever=lambda case, count: [], answerer=lambda case, evidence: "没有依据"
    )

    assert report.no_answer_rejection_rate == 1.0
    assert report.results[0].no_answer_pass is True
    assert report.passed_cases == 1


def test_no_answer_explanation_does_not_need_a_citation():
    case = _case(
        id="unknown-with-explanation",
        query="火星旅游补贴",
        should_answer=False,
        expected_chunk_ids=[],
        expected_citations=[],
    )
    report = RagEvaluationService().evaluate(
        [case],
        retriever=lambda case, count: [],
        answerer=lambda case, evidence: "没有检索到制度依据。",
    )

    assert report.passed_cases == 1
    assert report.results[0].citation_count == 0
    assert report.no_answer_abstention_rate == 1.0


def test_no_answer_confident_text_fails_when_llm_evaluation_is_enabled():
    case = _case(
        id="unknown-confident",
        query="火星旅游补贴",
        should_answer=False,
        expected_chunk_ids=[],
        expected_citations=[],
    )
    report = RagEvaluationService().evaluate(
        [case],
        retriever=lambda case, count: [],
        answerer=lambda case, evidence: "公司提供火星旅游补贴。",
    )

    assert report.no_answer_rejection_rate == 1.0
    assert report.no_answer_abstention_rate == 0.0
    assert report.passed_cases == 0


def test_ungrounded_citation_fails_even_when_retrieval_hits():
    case = _case(expected_citations=[])
    report = RagEvaluationService().evaluate(
        [case],
        retriever=lambda case, count: [
            {"chunk_id": "chunk-2", "source": "handbook.pdf", "page": 9}
        ],
        answerer=lambda case, evidence: "答案\n\n依据：[1]《other.pdf》第 1 页",
    )

    assert report.citation_precision == 0.0
    assert report.passed_cases == 0
    assert report.results[0].grounded_citation_count == 0


def test_missing_answer_citation_is_counted_as_zero_precision():
    case = _case(expected_citations=[])
    report = RagEvaluationService().evaluate(
        [case],
        retriever=lambda case, count: [
            {"chunk_id": "chunk-2", "source": "handbook.pdf", "page": 9}
        ],
        answerer=lambda case, evidence: "有依据的答案，但没有来源标记。",
    )

    assert report.citation_precision == 0.0
    assert report.passed_cases == 0


def test_evaluation_case_validation_rejects_answerable_case_without_expectation():
    with pytest.raises(RagEvaluationCaseError, match="expected_chunk_ids"):
        RagEvaluationCase.from_dict(
            {"id": "missing", "query": "制度", "company_id": "C001"}
        )


def test_load_jsonl_skips_comments_and_blank_lines(tmp_path: Path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '# comment\n\n'
        '{"id":"unknown","query":"未知","company_id":"C001","should_answer":false}\n',
        encoding="utf-8",
    )

    cases = RagEvaluationService.load_jsonl(path)

    assert len(cases) == 1
    assert cases[0].case_id == "unknown"
