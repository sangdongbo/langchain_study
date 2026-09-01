"""运行离线 RAG 评测集；默认只调用 Embedding/Milvus，不生成 LLM 答案。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
for import_root in (REPOSITORY_ROOT, PROJECT_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.services.milvus_service import milvus_service
from ai_erp_rag_assistant.app.services.model_service import model_service
from ai_erp_rag_assistant.app.services.rag_evaluation_service import (
    RagEvaluationService,
)


def main() -> int:
    """读取样例、调用真实检索服务并输出指标；不会创建或修改数据库记录。"""
    parser = argparse.ArgumentParser(description="评估 RAG 召回、Rerank、无答案和引用质量")
    parser.add_argument(
        "--cases",
        default=str(PROJECT_ROOT / "evals" / "rag_cases.example.jsonl"),
        help="JSONL 评测集路径",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="额外调用 LLM 生成答案并评估服务端引用；会产生模型调用费用",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="只评估 Milvus 原始排序，作为 Rerank 对照组",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="只输出 JSON，便于 CI 或脚本读取",
    )
    args = parser.parse_args()
    service = RagEvaluationService()
    cases = service.load_jsonl(args.cases)
    settings = get_settings()

    def retriever(case, candidate_count):
        """按每条样例自身的租户和 ACL 检索，评测集不共享身份边界。"""
        return milvus_service.search(
            case.query,
            company_id=case.company_id,
            department=case.department,
            permission_tags=list(case.permission_tags),
            top_k=candidate_count,
            knowledge_base_key=case.knowledge_base_key,
        )

    def reranker(case, evidence, top_k):
        """复用线上同一 Rerank 实现，确保离线结果能代表实际问答顺序。"""
        return model_service.rerank(
            case.query,
            list(evidence),
            top_k=top_k,
        )

    def answerer(case, evidence):
        """可选地复用线上知识问答 Prompt，答案中的引用由服务端追加。"""
        return model_service.answer(
            case.query,
            route="knowledge",
            evidence=list(evidence),
        )

    report = service.evaluate(
        cases,
        retriever=retriever,
        reranker=None if args.no_rerank else reranker,
        answerer=answerer if args.with_llm else None,
        candidate_count=(
            settings.rag_rerank_candidates if not args.no_rerank else None
        ),
    )
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"评测完成：{report.total_cases} 条，通过 {report.passed_cases} 条，失败 {report.failed_cases} 条")
        print(f"Recall@K={report.recall_at_k:.4f}  HitRate={report.retrieval_hit_rate:.4f}  MRR={report.mean_reciprocal_rank:.4f}")
        print(f"Rerank Top-1={report.rerank_top1_accuracy:.4f}  无答案拒答率={report.no_answer_rejection_rate:.4f}")
        if report.no_answer_abstention_rate is not None:
            print(f"无答案明确拒答率={report.no_answer_abstention_rate:.4f}")
        if report.citation_precision is not None:
            print(f"引用落地准确率={report.citation_precision:.4f}")
        if report.error_cases:
            print("存在外部服务错误，详见 --json 输出中的 results.error")
    return 0 if report.error_cases == 0 and report.failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
