from __future__ import annotations
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """返回轻量级服务健康检查结果。"""
    return {"status": "ok"}
