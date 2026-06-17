from __future__ import annotations

import hashlib
import json

from app.graph.state import ApprovalState


def build_idempotency_key(state: ApprovalState) -> str:
    """按会话、审批类型和字段内容生成提交幂等键。"""
    payload = {
        "session_id": state.get("session_id"),
        "user_id": state.get("user_id"),
        "approval_type": state.get("approval_type"),
        "slots": state.get("collected_slots", {}),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"ai-approval:{digest}"
