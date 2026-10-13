"""独立运行 Agent Evals，默认不访问任何外部服务。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
for import_root in (PROJECT_ROOT.parent, PROJECT_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from ai_erp_rag_assistant.app.services.agent_evaluation_service import AgentEvaluationService
from ai_erp_rag_assistant.evals.workflow_runner import WorkflowEvalRunner


def main() -> int:
    """失败返回 1，配置错误返回 2，便于本地回归和 CI 阻止问题版本。"""
    parser = argparse.ArgumentParser(description="评估 Agent 路由、工具参数、引用、隔离、审批确认和步骤重放")
    parser.add_argument("--cases", default=str(PROJECT_ROOT / "evals" / "agent_cases.example.jsonl"), help="JSONL 评估集")
    parser.add_argument("--with-llm", action="store_true", help="调用真实 LLM 评估规划和回答；ERP/Milvus/数据库仍被替换，会产生模型费用")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    args = parser.parse_args()
    try:
        cases = AgentEvaluationService.load_jsonl(args.cases)
        runner = WorkflowEvalRunner(with_llm=args.with_llm)
        report = AgentEvaluationService.evaluate(cases, runner, mode="llm" if args.with_llm else "offline")
    except (ValueError, OSError):
        print("评估配置无效：请检查评估集路径、字段类型和重复 ID", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Agent Evals ({report['mode']})：{report['total_cases']} 个场景 / {report['total_turns']} 轮，通过 {report['passed_cases']}，失败 {report['failed_cases']}")
        for name, metric in report["metrics"].items():
            print(f"{name}: {metric['passed']}/{metric['total']} = {metric['rate']:.2%}")
        for result in report["results"]:
            if not result["passed"]:
                failures = "; ".join(f"第 {turn['turn']} 轮: {', '.join(turn['failed_checks'])}" for turn in result["turns"] if turn["failed_checks"])
                print(f"失败 {result['id']}: {result['error'] or failures}")
    return 1 if report["failed_cases"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
