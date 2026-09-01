"""离线 RAG 检索效果评测，不创建数据库连接也不修改线上数据。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class RagEvaluationCaseError(ValueError):
    """评测样例缺少必要字段或包含不支持的值。"""


@dataclass(frozen=True)
class RagEvaluationCase:
    """一条带有期望相关文档和无答案标记的评测样例。"""

    case_id: str
    query: str
    company_id: str
    knowledge_base_key: str = ""
    department: str = ""
    permission_tags: tuple[str, ...] = ()
    expected_chunk_ids: tuple[str, ...] = ()
    expected_sources: tuple[str, ...] = ()
    expected_citations: tuple[tuple[str, int | None], ...] = ()
    should_answer: bool = True
    top_k: int = 5

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, line_number: int = 0) -> "RagEvaluationCase":
        """从 JSON 对象读取样例，并在执行外部检索前完成边界校验。"""
        if not isinstance(value, Mapping):
            raise RagEvaluationCaseError(f"第 {line_number or '?'} 行必须是 JSON 对象")

        def text(name: str, *, required: bool = False, limit: int = 256) -> str:
            raw = value.get(name, "")
            if not isinstance(raw, str):
                raise RagEvaluationCaseError(f"{name} 必须是字符串")
            result = raw.strip()
            if required and not result:
                raise RagEvaluationCaseError(f"{name} 不能为空")
            if len(result) > limit:
                raise RagEvaluationCaseError(f"{name} 长度不能超过 {limit}")
            return result

        def strings(name: str, *, limit: int, max_items: int = 100) -> tuple[str, ...]:
            raw = value.get(name, [])
            if isinstance(raw, str):
                raw = [raw]
            if not isinstance(raw, (list, tuple)) or len(raw) > max_items:
                raise RagEvaluationCaseError(f"{name} 必须是最多 {max_items} 项的字符串数组")
            result = tuple(str(item).strip() for item in raw if isinstance(item, str) and item.strip())
            if len(result) != len(raw):
                raise RagEvaluationCaseError(f"{name} 只能包含非空字符串")
            if any(len(item) > limit for item in result):
                raise RagEvaluationCaseError(f"{name} 中单项长度不能超过 {limit}")
            return result

        case_id = text("id", required=True, limit=128)
        query = text("query", required=True, limit=10_000)
        company_id = text("company_id", required=True, limit=64)
        knowledge_base_key = text("knowledge_base_key", limit=64)
        department = text("department", limit=256)
        permission_tags = strings("permission_tags", limit=256, max_items=32)
        expected_chunk_ids = strings("expected_chunk_ids", limit=512)
        expected_sources = strings("expected_sources", limit=1_000)
        raw_expected_citations = value.get("expected_citations", [])
        if not isinstance(raw_expected_citations, (list, tuple)) or len(raw_expected_citations) > 100:
            raise RagEvaluationCaseError("expected_citations 必须是最多 100 项的数组")
        expected_citations: list[tuple[str, int | None]] = []
        for item in raw_expected_citations:
            if not isinstance(item, Mapping):
                raise RagEvaluationCaseError("expected_citations 中每项必须是对象")
            source = item.get("source")
            if not isinstance(source, str) or not source.strip():
                raise RagEvaluationCaseError("expected_citations.source 不能为空")
            page = item.get("page")
            if page is not None and (not isinstance(page, int) or isinstance(page, bool) or page < 1):
                raise RagEvaluationCaseError("expected_citations.page 必须是正整数或 null")
            expected_citations.append((source.strip(), page))

        should_answer = value.get("should_answer", True)
        if not isinstance(should_answer, bool):
            raise RagEvaluationCaseError("should_answer 必须是布尔值")
        top_k = value.get("top_k", 5)
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 50:
            raise RagEvaluationCaseError("top_k 必须是 1..50 的整数")
        if should_answer and not (expected_chunk_ids or expected_sources):
            raise RagEvaluationCaseError(
                "should_answer=true 时至少需要 expected_chunk_ids 或 expected_sources"
            )
        if not should_answer and (expected_chunk_ids or expected_sources or expected_citations):
            raise RagEvaluationCaseError("should_answer=false 时不能配置期望相关文档或引用")
        return cls(
            case_id=case_id,
            query=query,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            department=department,
            permission_tags=permission_tags,
            expected_chunk_ids=expected_chunk_ids,
            expected_sources=expected_sources,
            expected_citations=tuple(expected_citations),
            should_answer=should_answer,
            top_k=top_k,
        )


@dataclass(frozen=True)
class RagCaseResult:
    """单条样例的检索、重排、答案和引用指标。"""

    case_id: str
    should_answer: bool
    retrieved_count: int
    retrieved_chunk_ids: tuple[str, ...]
    relevant_retrieved_count: int = 0
    recall_at_k: float = 0.0
    first_relevant_rank: int | None = None
    reciprocal_rank: float = 0.0
    rerank_top1_hit: bool = False
    no_answer_pass: bool | None = None
    no_answer_abstention_pass: bool | None = None
    answer: str = ""
    citation_count: int = 0
    grounded_citation_count: int = 0
    citation_precision: float | None = None
    expected_citation_recall: float | None = None
    passed: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为 JSON 报告，不暴露完整 Chunk 文本或认证信息。"""
        return {
            "case_id": self.case_id,
            "should_answer": self.should_answer,
            "retrieved_count": self.retrieved_count,
            "retrieved_chunk_ids": list(self.retrieved_chunk_ids),
            "relevant_retrieved_count": self.relevant_retrieved_count,
            "recall_at_k": self.recall_at_k,
            "first_relevant_rank": self.first_relevant_rank,
            "reciprocal_rank": self.reciprocal_rank,
            "rerank_top1_hit": self.rerank_top1_hit,
            "no_answer_pass": self.no_answer_pass,
            "no_answer_abstention_pass": self.no_answer_abstention_pass,
            "answer_present": bool(self.answer.strip()),
            "citation_count": self.citation_count,
            "grounded_citation_count": self.grounded_citation_count,
            "citation_precision": self.citation_precision,
            "expected_citation_recall": self.expected_citation_recall,
            "passed": self.passed,
            "error": self.error,
        }


@dataclass(frozen=True)
class RagEvaluationReport:
    """整个评测集的聚合指标和逐样例明细。"""

    total_cases: int
    answerable_cases: int
    no_answer_cases: int
    retrieval_hit_rate: float
    recall_at_k: float
    mean_reciprocal_rank: float
    rerank_top1_accuracy: float
    no_answer_rejection_rate: float
    no_answer_abstention_rate: float | None
    citation_precision: float | None
    expected_citation_recall: float | None
    passed_cases: int
    failed_cases: int
    error_cases: int
    results: tuple[RagCaseResult, ...]

    def to_dict(self) -> dict[str, Any]:
        """返回可写入 JSON 的评测报告。"""
        return {
            "total_cases": self.total_cases,
            "answerable_cases": self.answerable_cases,
            "no_answer_cases": self.no_answer_cases,
            "retrieval_hit_rate": self.retrieval_hit_rate,
            "recall_at_k": self.recall_at_k,
            "mean_reciprocal_rank": self.mean_reciprocal_rank,
            "rerank_top1_accuracy": self.rerank_top1_accuracy,
            "no_answer_rejection_rate": self.no_answer_rejection_rate,
            "no_answer_abstention_rate": self.no_answer_abstention_rate,
            "citation_precision": self.citation_precision,
            "expected_citation_recall": self.expected_citation_recall,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "error_cases": self.error_cases,
            "results": [result.to_dict() for result in self.results],
        }


Retriever = Callable[[RagEvaluationCase, int], Sequence[Mapping[str, Any]]]
Reranker = Callable[[RagEvaluationCase, Sequence[Mapping[str, Any]], int], Sequence[Mapping[str, Any]]]
Answerer = Callable[[RagEvaluationCase, Sequence[Mapping[str, Any]]], str | Mapping[str, Any]]

_CITATION_PATTERN = re.compile(
    r"\[\s*(?P<id>\d+)\s*\]\s*《(?P<source>[^》]+)》"
    r"(?:第\s*(?P<page>\d+)\s*页|页码未知)"
)

_ABSTENTION_MARKERS = (
    "没有检索到",
    "没有依据",
    "无法确认",
    "无法确定",
    "暂无依据",
    "未找到相关",
    "未检索到",
    "cannot determine",
    "no evidence",
    "not enough information",
)


class RagEvaluationService:
    """运行可注入检索器、Rerank 器和答案生成器的离线评测。"""

    @staticmethod
    def load_jsonl(path: str | Path) -> list[RagEvaluationCase]:
        """逐行加载评测集；空行和以 ``#`` 开头的行会被忽略。"""
        cases: list[RagEvaluationCase] = []
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                try:
                    value = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise RagEvaluationCaseError(f"第 {line_number} 行不是合法 JSON：{exc}") from exc
                cases.append(RagEvaluationCase.from_dict(value, line_number=line_number))
        if not cases:
            raise RagEvaluationCaseError("评测集不能为空")
        return cases

    def evaluate(
        self,
        cases: Sequence[RagEvaluationCase],
        *,
        retriever: Retriever,
        reranker: Reranker | None = None,
        answerer: Answerer | None = None,
        candidate_count: int | None = None,
    ) -> RagEvaluationReport:
        """逐条执行检索并聚合指标；单条外部服务错误不会吞掉其他样例。"""
        results: list[RagCaseResult] = []
        for case in cases:
            results.append(
                self._evaluate_case(
                    case,
                    retriever=retriever,
                    reranker=reranker,
                    answerer=answerer,
                    candidate_count=candidate_count,
                )
            )
        answerable = [item for item in results if item.should_answer and not item.error]
        no_answer = [item for item in results if not item.should_answer and not item.error]
        with_citation_precision = [
            item.citation_precision for item in answerable if item.citation_precision is not None
        ]
        with_expected_citations = [
            item.expected_citation_recall
            for item in answerable
            if item.expected_citation_recall is not None
        ]
        with_abstention = [
            bool(item.no_answer_abstention_pass)
            for item in no_answer
            if item.no_answer_abstention_pass is not None
        ]
        errors = [item for item in results if item.error]
        return RagEvaluationReport(
            total_cases=len(results),
            answerable_cases=len(answerable),
            no_answer_cases=len(no_answer),
            retrieval_hit_rate=_average(bool(item.first_relevant_rank) for item in answerable),
            recall_at_k=_average(item.recall_at_k for item in answerable),
            mean_reciprocal_rank=_average(item.reciprocal_rank for item in answerable),
            rerank_top1_accuracy=_average(item.rerank_top1_hit for item in answerable),
            no_answer_rejection_rate=_average(bool(item.no_answer_pass) for item in no_answer),
            no_answer_abstention_rate=(
                _average(with_abstention) if with_abstention else None
            ),
            citation_precision=(
                _average(value for value in with_citation_precision)
                if with_citation_precision
                else None
            ),
            expected_citation_recall=(
                _average(value for value in with_expected_citations)
                if with_expected_citations
                else None
            ),
            passed_cases=sum(1 for item in results if item.passed),
            failed_cases=sum(1 for item in results if not item.passed),
            error_cases=len(errors),
            results=tuple(results),
        )

    def _evaluate_case(
        self,
        case: RagEvaluationCase,
        *,
        retriever: Retriever,
        reranker: Reranker | None,
        answerer: Answerer | None,
        candidate_count: int | None,
    ) -> RagCaseResult:
        """执行一条样例，确保失败被记录而不是伪装成无答案。"""
        try:
            requested_count = candidate_count or case.top_k
            if not 1 <= requested_count <= 50:
                raise RagEvaluationCaseError("candidate_count 必须是 1..50")
            raw_evidence = retriever(case, requested_count)
            evidence = [dict(item) for item in (raw_evidence or []) if isinstance(item, Mapping)]
            ranked = (
                [dict(item) for item in reranker(case, evidence, case.top_k)]
                if reranker
                else evidence[: case.top_k]
            )
            ranked = ranked[: case.top_k]
            answer = ""
            citations: list[tuple[str, int | None]] = []
            if answerer:
                answer_payload = answerer(case, ranked)
                if isinstance(answer_payload, Mapping):
                    answer = str(answer_payload.get("answer") or answer_payload.get("message") or "")
                    citations = _citations_from_payload(answer_payload.get("citations"))
                else:
                    answer = str(answer_payload or "")
                if not citations:
                    citations = _extract_citations(answer)
            return self._score_case(
                case,
                ranked,
                answer=answer,
                citations=citations,
                answer_evaluated=answerer is not None,
            )
        except Exception as exc:
            return RagCaseResult(
                case_id=case.case_id,
                should_answer=case.should_answer,
                retrieved_count=0,
                retrieved_chunk_ids=(),
                passed=False,
                error=str(exc)[:1_000],
            )

    @staticmethod
    def _score_case(
        case: RagEvaluationCase,
        evidence: Sequence[Mapping[str, Any]],
        *,
        answer: str,
        citations: Sequence[tuple[str, int | None]],
        answer_evaluated: bool,
    ) -> RagCaseResult:
        """按期望 Chunk 优先、期望来源兜底的口径计算单条指标。"""
        chunk_ids = tuple(str(item.get("chunk_id") or "") for item in evidence)
        expected = set(case.expected_chunk_ids or case.expected_sources)
        use_chunk_ids = bool(case.expected_chunk_ids)
        relevant_indexes: list[int] = []
        matched: set[str] = set()
        for index, item in enumerate(evidence, start=1):
            key = str(item.get("chunk_id") or "") if use_chunk_ids else str(item.get("source") or "")
            if key in expected:
                matched.add(key)
                relevant_indexes.append(index)
        first_rank = min(relevant_indexes) if relevant_indexes else None
        recall = len(matched) / len(expected) if expected else 0.0
        no_answer_pass = (not evidence) if not case.should_answer else None
        no_answer_abstention_pass = (
            _looks_like_abstention(answer) if not case.should_answer and answer_evaluated else None
        )
        grounded = [citation for citation in citations if _citation_is_grounded(citation, evidence)]
        citation_precision = (
            len(grounded) / len(citations)
            if citations
            else (0.0 if answer_evaluated and case.should_answer else None)
        )
        expected_recall = None
        if case.expected_citations:
            expected_set = set(case.expected_citations)
            expected_recall = len(expected_set.intersection(citations)) / len(expected_set)
        # 无答案场景允许有解释性文本，但绝不能附带无法依据的引用。
        citation_ok = (
            not citations
            if not case.should_answer
            else bool(citations) and citation_precision == 1.0
        )
        if case.expected_citations:
            citation_ok = citation_ok and expected_recall == 1.0
        answer_present = not answer_evaluated or (not case.should_answer or bool(answer.strip()))
        passed = (
            (
                not case.should_answer
                and bool(no_answer_pass)
                and (no_answer_abstention_pass is not False)
            )
            or (case.should_answer and recall == 1.0)
        ) and answer_present and (not answer_evaluated or citation_ok)
        return RagCaseResult(
            case_id=case.case_id,
            should_answer=case.should_answer,
            retrieved_count=len(evidence),
            retrieved_chunk_ids=chunk_ids,
            relevant_retrieved_count=len(matched),
            recall_at_k=recall,
            first_relevant_rank=first_rank,
            reciprocal_rank=1 / first_rank if first_rank else 0.0,
            rerank_top1_hit=bool(evidence and relevant_indexes and relevant_indexes[0] == 1),
            no_answer_pass=no_answer_pass,
            no_answer_abstention_pass=no_answer_abstention_pass,
            answer=answer,
            citation_count=len(citations),
            grounded_citation_count=len(grounded),
            citation_precision=citation_precision,
            expected_citation_recall=expected_recall,
            passed=passed,
        )


def _average(values: Sequence[float | bool]) -> float:
    """对空集合返回 0，避免报告出现 NaN 导致前端无法解析。"""
    numbers = [float(value) for value in values]
    return round(sum(numbers) / len(numbers), 6) if numbers else 0.0


def _extract_citations(answer: str) -> list[tuple[str, int | None]]:
    """解析服务端追加的 `[n]《来源》页码` 引用，不解析用户正文中的任意链接。"""
    citations: list[tuple[str, int | None]] = []
    for match in _CITATION_PATTERN.finditer(answer):
        page = int(match.group("page")) if match.group("page") else None
        citations.append((match.group("source").strip(), page))
    return citations


def _looks_like_abstention(answer: str) -> bool:
    """识别无证据时的明确拒答措辞；没有答案文本也视为失败。"""
    normalized = "".join(answer.strip().lower().split())
    return bool(normalized) and any(marker.replace(" ", "") in normalized for marker in _ABSTENTION_MARKERS)


def _citations_from_payload(value: Any) -> list[tuple[str, int | None]]:
    """兼容前端或自定义答案器直接返回结构化 citations。"""
    if not isinstance(value, (list, tuple)):
        return []
    result: list[tuple[str, int | None]] = []
    for item in value:
        if not isinstance(item, Mapping) or not isinstance(item.get("source"), str):
            continue
        page = item.get("page")
        result.append((item["source"].strip(), page if isinstance(page, int) else None))
    return result


def _citation_is_grounded(
    citation: tuple[str, int | None], evidence: Sequence[Mapping[str, Any]]
) -> bool:
    """引用必须同时匹配证据来源和页码；页码未知只允许匹配无页码证据。"""
    source, page = citation
    for item in evidence:
        if str(item.get("source") or "") != source:
            continue
        raw_page = item.get("page")
        evidence_page = raw_page if isinstance(raw_page, int) and raw_page >= 1 else None
        if evidence_page == page:
            return True
    return False
