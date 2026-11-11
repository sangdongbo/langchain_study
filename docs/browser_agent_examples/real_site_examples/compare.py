"""只读取两次本机运行产物，对比任务、事实快照、核对结果和指标，不重新访问网站。"""

# 必须显式提供固定脚本和 Agent 的两个成功目录，不自动寻找“最新一次”。
# 对比使用已保存的业务事实，不再次查询真实站点，也不要求模型评价自己的结果。

import argparse
import json
from pathlib import Path

from erp import OrderReport


def compare_runs(script_dir: Path, agent_dir: Path) -> dict:
    # script_dir/result.json 自身就是事实报告；Agent 的事实在 evidence.json，
    # 因为 Agent/result.json 是模型摘要，不能拿模型自己的描述充当网页事实。
    metrics = []
    reports = []
    for directory, mode, evidence in ((script_dir, "script", "result.json"),
                                       (agent_dir, "agent", "evidence.json")):
        # 必须明确选择两次成功运行；不自动挑“最新”结果，以免读到旧成功记录。
        status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        item = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        if status["status"] != "success" or item["status"] != "success" or item["mode"] != mode:
            raise ValueError("请选择固定脚本与 Agent 各一次已验收成功的产物目录。")
        reports.append(OrderReport.model_validate_json((directory / evidence).read_text(encoding="utf-8")))
        # 先通过相同 Pydantic 结构校验，再比较字段，拒绝不兼容或不完整的报告。
        metrics.append(item)
    if any(metrics[0][key] != metrics[1][key] for key in ("keyword", "limit")):
        # 同一次演示应使用同关键词和前 N 条范围，不把不同任务的耗时硬放在一起。
        raise ValueError("两次关键词或 limit 不同，不属于同一演示任务。")
    # 两次运行可能遇到测试数据被修改；把事实快照差异与模型表现分开描述。
    facts = [report.model_dump(exclude={"detail_checks"}) for report in reports]
    # 事实快照与详情选择分别比较：待回款并列时，两次选择不同订单也可能都完成了目标。
    return {
        "same_task": True, "same_snapshot": facts[0] == facts[1],
        "same_checked_orders": [item.order_number for item in reports[0].detail_checks]
            == [item.order_number for item in reports[1].detail_checks],
        "script": metrics[0], "agent": metrics[1],
        "note": "快照不同时不能直接归因于 Agent；待回款并列时允许核对不同订单。",
    }


if __name__ == "__main__":
    # 输出仅写终端；不会修改传入的报告或覆盖原有产物。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script_dir", type=Path, help="固定脚本本次产物目录")
    parser.add_argument("agent_dir", type=Path, help="Agent 本次产物目录")
    args = parser.parse_args()
    print(json.dumps(compare_runs(args.script_dir, args.agent_dir), ensure_ascii=False, indent=2))
