"""为路由模块提供惰性加载的 `app.api` 兼容入口。"""

from __future__ import annotations

from importlib import import_module
from typing import Any


class _ApiModuleProxy:
    """延迟解析统一 API 模块，避免路由单独导入时形成循环依赖。"""

    def __getattr__(self, name: str) -> Any:
        # 路由函数真正执行时，`app.api` 已完成所有模块和兼容导出初始化。
        module = import_module("ai_erp_rag_assistant.app.api")
        return getattr(module, name)


api_module = _ApiModuleProxy()
