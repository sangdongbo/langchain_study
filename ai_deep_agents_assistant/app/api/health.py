from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}
