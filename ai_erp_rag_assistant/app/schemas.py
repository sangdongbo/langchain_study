from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = "demo-session"
    user_id: str = "U001"
    uid: str = ""
    authorization: str = ""
    company_id: str = ""
    department: str = ""
    confirm: bool | None = None
    reset: bool = False


class ChatResponse(BaseModel):
    message: str
    route: Literal["knowledge", "erp_status", "approval_workflow", "general_chat", "unknown"]
    plan: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    pending_question: str = ""
    erp_mode: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    erp_data: dict[str, Any] = Field(default_factory=dict)
    preview: dict[str, Any] | None = None
