from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_deep_agents_assistant.app.services.approval_service import approval_service


def main() -> None:
    """离线冒烟检查确定性审批规则。"""
    message = "我要报销差旅费，金额 5200 元，因为去上海拜访客户，发票已提供"
    draft = approval_service.build_draft(message, existing_slots={})
    print(json.dumps(draft.model_dump(), ensure_ascii=False, indent=2))
    assert draft.approval_type == "expense"
    assert not draft.missing_fields
    assert draft.preview is not None
    result = approval_service.submit("expense", draft.collected_slots, "U001")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
