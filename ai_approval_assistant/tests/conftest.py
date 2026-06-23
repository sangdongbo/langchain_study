from __future__ import annotations

import pytest

from app.graph.workflow import get_workflow


@pytest.fixture(autouse=True)
def clear_cached_workflow():
    # get_workflow 会缓存 compiled graph。测试里经常 monkeypatch service/node，
    # 每个用例前后清缓存，避免上一个用例编译出的 graph 串到下一个用例。
    get_workflow.cache_clear()
    yield
    get_workflow.cache_clear()
