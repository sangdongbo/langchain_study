"""创建可选 MySQL 会话；本模块不会建表、迁移或修改数据库结构。"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_erp_rag_assistant.app.config import Settings, get_settings


class DatabaseNotConfiguredError(RuntimeError):
    """需要 MySQL 的功能在连接参数缺失时抛出的配置错误。"""

    pass


def mysql_configured(settings: Settings | None = None) -> bool:
    """判断是否已提供建立 MySQL 连接所需的最小配置。"""
    settings = settings or get_settings()
    return bool(settings.mysql_database.strip() and settings.mysql_user.strip())


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """惰性创建并缓存 MySQL Engine，不主动发起表结构操作。"""
    # 这里只连接人工审核并创建好的表，应用启动路径禁止自动 create_all() 或迁移。
    settings = get_settings()
    if not mysql_configured(settings):
        raise DatabaseNotConfiguredError(
            "MySQL 未配置，请设置 AI_ERP_MYSQL_DATABASE 和 AI_ERP_MYSQL_USER。"
        )
    url = URL.create(
        "mysql+pymysql",
        username=settings.mysql_user,
        password=settings.mysql_password,
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        query={"charset": "utf8mb4"},
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": settings.mysql_connect_timeout},
    )


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    """为必须使用 MySQL 的接口提供请求级 Session。"""
    with _session_factory()() as session:
        yield session


def get_optional_db_session() -> Generator[Session | None, None, None]:
    """未配置 MySQL 时返回 None，使基础 RAG 接口仍可使用默认配置。"""
    if not mysql_configured():
        yield None
        return
    yield from get_db_session()
