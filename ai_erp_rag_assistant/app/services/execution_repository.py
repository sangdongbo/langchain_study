"""持久化 ERP Agent 的运行、步骤和检查点，支持中断后安全恢复。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.services.sensitive_data import is_sensitive_field_name
from ai_erp_rag_assistant.app.services.session_repository import resumable_state


if TYPE_CHECKING:
    from ai_erp_rag_assistant.app.services.execution_runtime import DurableExecutionContext


class ExecutionConflictError(RuntimeError):
    """同一请求正在执行，或 request_id 被用于不同业务输入。"""


class ExecutionNotFoundError(RuntimeError):
    """当前租户和用户范围内不存在指定运行。"""


class ExecutionLeaseLostError(RuntimeError):
    """当前进程不再持有运行租约，必须停止产生外部副作用。"""


@dataclass(frozen=True)
class StepStart:
    """步骤开始结果；cached=True 时直接复用已经持久化的输出。"""

    cached: bool
    output: dict[str, Any]


@dataclass(frozen=True)
class RunClaim:
    """创建或重新领取一次运行后的恢复信息。"""

    context: "DurableExecutionContext | None"
    completed_response: dict[str, Any] | None
    checkpoint_state: dict[str, Any]
    retry_count: int


def _strip_secrets(value: Any) -> Any:
    """递归移除认证字段，防止 Token 随检查点写入数据库。"""
    if isinstance(value, dict):
        return {
            str(key): _strip_secrets(item)
            for key, item in value.items()
            if not is_sensitive_field_name(key)
            and str(key).lower() != "raw_userinfo"
        }
    if isinstance(value, list):
        return [_strip_secrets(item) for item in value]
    return value


def _execution_state(state: dict[str, Any]) -> dict[str, Any]:
    """保留恢复和最终补写会话所需状态，同时移除运行凭据。"""
    snapshot = resumable_state(state)
    for key in (
        "assistant_type",
        "assistant_message",
        "erp_data",
        "errors",
        "tool_calls",
        "execution_run_id",
        "execution_status",
        "execution_retry_count",
        "execution_current_step",
    ):
        if key in state:
            snapshot[key] = state[key]
    return _strip_secrets(snapshot)


def _json_dump(value: Any) -> str:
    return json.dumps(
        _strip_secrets(value),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def execution_request_hash(request: Any, assistant_key: str) -> str:
    """生成不含凭据和传输选项的业务输入摘要。"""
    payload = request.model_dump(exclude={"authorization", "stream"})
    payload["assistant_key"] = assistant_key
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


class ExecutionRepository:
    """MySQL Durable Execution 仓储；本类不会创建或修改表结构。"""

    @property
    def enabled(self) -> bool:
        return get_settings().session_store == "mysql"

    def claim_run(
        self,
        *,
        company_id: str,
        assistant_key: str,
        session_key: str,
        user_id: str,
        request_id: str,
        request_hash: str,
    ) -> RunClaim:
        """按 request_id 创建运行，或领取失败、过期的原运行继续执行。"""
        if not self.enabled:
            raise RuntimeError("Durable Execution 需要 AI_ERP_SESSION_STORE=mysql")
        if not request_id:
            raise ValueError("ERP Agent 启用 Durable Execution 后 request_id 不能为空")

        connection = self._connect()
        new_run_key = uuid4().hex
        owner_token = uuid4().hex
        try:
            with connection.cursor() as cursor:
                assistant_id = self._assistant_id(cursor, company_id, assistant_key)
                # LAST_INSERT_ID(id) 让新增和唯一键命中都能用同一路径锁定目标行。
                cursor.execute(
                    """
                    INSERT INTO ai_erp_agent_runs (
                        company_id, assistant_id, run_key, session_key, user_id,
                        request_id, request_hash, status, owner_token,
                        lease_expires_at, started_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'running', %s,
                              DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL 10 MINUTE),
                              CURRENT_TIMESTAMP(6))
                    ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)
                    """,
                    (
                        company_id,
                        assistant_id,
                        new_run_key,
                        session_key,
                        user_id,
                        request_id,
                        request_hash,
                        owner_token,
                    ),
                )
                run_id = int(cursor.lastrowid)
                cursor.execute(
                    """
                    SELECT id, run_key, session_key, user_id, request_id,
                           request_hash, status, state_json, result_json,
                           retry_count, owner_token,
                           CASE WHEN lease_expires_at > CURRENT_TIMESTAMP(6)
                                THEN 1 ELSE 0 END AS lease_active
                    FROM ai_erp_agent_runs
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (run_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise RuntimeError("创建 ERP Agent 运行失败")
                if str(row.get("request_hash") or "") != request_hash:
                    raise ExecutionConflictError(
                        "同一个 request_id 不能用于不同的 ERP Agent 请求"
                    )

                is_new = str(row.get("run_key") or "") == new_run_key
                if str(row.get("status") or "") == "completed":
                    connection.commit()
                    return RunClaim(
                        context=None,
                        completed_response=_json_object(row.get("result_json")),
                        checkpoint_state=_json_object(row.get("state_json")),
                        retry_count=int(row.get("retry_count") or 0),
                    )
                if not is_new and str(row.get("status") or "") == "running" and bool(
                    row.get("lease_active")
                ):
                    raise ExecutionConflictError(
                        "该 request_id 正在执行，请勿并发重复提交"
                    )
                if not is_new:
                    # 失败运行或租约过期运行沿用原 run_key，并增加恢复次数。
                    owner_token = uuid4().hex
                    cursor.execute(
                        """
                        UPDATE ai_erp_agent_runs
                        SET status = 'running', owner_token = %s,
                            lease_expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL 10 MINUTE),
                            retry_count = retry_count + 1,
                            last_error_code = '', last_error_message = '',
                            completed_at = NULL, updated_at = CURRENT_TIMESTAMP(6)
                        WHERE id = %s
                        """,
                        (owner_token, run_id),
                    )
                    row["retry_count"] = int(row.get("retry_count") or 0) + 1

                connection.commit()
                # 局部导入避免仓储类型与 LangGraph 运行包装器产生模块循环。
                from ai_erp_rag_assistant.app.services.execution_runtime import (
                    DurableExecutionContext,
                )

                context = DurableExecutionContext(
                    repository=self,
                    run_key=str(row["run_key"]),
                    owner_token=owner_token,
                    retry_count=int(row.get("retry_count") or 0),
                )
                return RunClaim(
                    context=context,
                    completed_response=None,
                    checkpoint_state=_json_object(row.get("state_json")),
                    retry_count=context.retry_count,
                )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin_step(
        self,
        *,
        run_key: str,
        owner_token: str,
        step_name: str,
        state: dict[str, Any],
        replay_completed: bool,
    ) -> StepStart:
        """在业务节点执行前写检查点，并判断是否可以复用已完成输出。"""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                run = self._owned_run(cursor, run_key, owner_token)
                cursor.execute(
                    """
                    SELECT status, output_json
                    FROM ai_erp_agent_steps
                    WHERE run_id = %s AND step_name = %s
                    FOR UPDATE
                    """,
                    (run["id"], step_name),
                )
                step = cursor.fetchone()
                if step and step.get("status") == "completed" and replay_completed:
                    # 已完成的 ERP 写步骤绝不能再次产生副作用，直接返回上次输出。
                    cursor.execute(
                        """
                        UPDATE ai_erp_agent_runs
                        SET current_step = %s,
                            lease_expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL 10 MINUTE),
                            updated_at = CURRENT_TIMESTAMP(6)
                        WHERE id = %s
                        """,
                        (step_name, run["id"]),
                    )
                    connection.commit()
                    return StepStart(True, _json_object(step.get("output_json")))

                snapshot = _execution_state(state)
                cursor.execute(
                    """
                    INSERT INTO ai_erp_agent_steps (
                        company_id, assistant_id, run_id, step_name, status,
                        attempt_count, replayable, input_json, started_at
                    ) VALUES (%s, %s, %s, %s, 'running', 1, %s, %s,
                              CURRENT_TIMESTAMP(6))
                    ON DUPLICATE KEY UPDATE
                        status = 'running', attempt_count = attempt_count + 1,
                        replayable = VALUES(replayable), input_json = VALUES(input_json),
                        output_json = NULL, error_message = '',
                        started_at = CURRENT_TIMESTAMP(6), finished_at = NULL
                    """,
                    (
                        run["company_id"],
                        run["assistant_id"],
                        run["id"],
                        step_name,
                        int(replay_completed),
                        _json_dump(snapshot),
                    ),
                )
                next_version = int(run.get("state_version") or 0) + 1
                self._insert_checkpoint(
                    cursor,
                    run=run,
                    sequence=next_version,
                    step_name=step_name,
                    phase="before_step",
                    state=snapshot,
                )
                cursor.execute(
                    """
                    UPDATE ai_erp_agent_runs
                    SET current_step = %s, state_json = %s, state_version = %s,
                        lease_expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL 10 MINUTE),
                        updated_at = CURRENT_TIMESTAMP(6)
                    WHERE id = %s
                    """,
                    (step_name, _json_dump(snapshot), next_version, run["id"]),
                )
            connection.commit()
            return StepStart(False, {})
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def complete_step(
        self,
        *,
        run_key: str,
        owner_token: str,
        step_name: str,
        state: dict[str, Any],
        output: dict[str, Any],
    ) -> None:
        """原子保存节点输出和 after_step 检查点。"""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                run = self._owned_run(cursor, run_key, owner_token)
                merged = _execution_state({**state, **output})
                cursor.execute(
                    """
                    UPDATE ai_erp_agent_steps
                    SET status = 'completed', output_json = %s,
                        error_message = '', finished_at = CURRENT_TIMESTAMP(6)
                    WHERE run_id = %s AND step_name = %s
                    """,
                    (_json_dump(output), run["id"], step_name),
                )
                next_version = int(run.get("state_version") or 0) + 1
                self._insert_checkpoint(
                    cursor,
                    run=run,
                    sequence=next_version,
                    step_name=step_name,
                    phase="after_step",
                    state=merged,
                )
                cursor.execute(
                    """
                    UPDATE ai_erp_agent_runs
                    SET state_json = %s, state_version = %s, current_step = %s,
                        lease_expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL 10 MINUTE),
                        updated_at = CURRENT_TIMESTAMP(6)
                    WHERE id = %s
                    """,
                    (_json_dump(merged), next_version, step_name, run["id"]),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fail_step(
        self,
        *,
        run_key: str,
        owner_token: str,
        step_name: str,
        state: dict[str, Any],
        error: Exception,
    ) -> None:
        """记录失败节点和最后安全输入，使相同请求可以从该点恢复。"""
        message = str(error)[:1000]
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                run = self._owned_run(cursor, run_key, owner_token)
                snapshot = _execution_state(state)
                cursor.execute(
                    """
                    UPDATE ai_erp_agent_steps
                    SET status = 'failed', error_message = %s,
                        finished_at = CURRENT_TIMESTAMP(6)
                    WHERE run_id = %s AND step_name = %s
                    """,
                    (message, run["id"], step_name),
                )
                next_version = int(run.get("state_version") or 0) + 1
                self._insert_checkpoint(
                    cursor,
                    run=run,
                    sequence=next_version,
                    step_name=step_name,
                    phase="failed",
                    state=snapshot,
                )
                cursor.execute(
                    """
                    UPDATE ai_erp_agent_runs
                    SET status = 'failed', state_json = %s, state_version = %s,
                        current_step = %s, last_error_code = 'step_failed',
                        last_error_message = %s, owner_token = NULL,
                        lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP(6)
                    WHERE id = %s
                    """,
                    (_json_dump(snapshot), next_version, step_name, message, run["id"]),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def complete_run(
        self,
        *,
        run_key: str,
        owner_token: str,
        state: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        """保存最终权威响应；会话落库失败时可据此补写而不重跑 ERP。"""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ai_erp_agent_runs
                    SET status = 'completed', state_json = %s, result_json = %s,
                        last_error_code = '', last_error_message = '',
                        owner_token = NULL, lease_expires_at = NULL,
                        completed_at = CURRENT_TIMESTAMP(6), updated_at = CURRENT_TIMESTAMP(6)
                    WHERE run_key = %s AND owner_token = %s AND status = 'running'
                      AND lease_expires_at > CURRENT_TIMESTAMP(6)
                    """,
                    (
                        _json_dump(_execution_state(state)),
                        _json_dump(response),
                        run_key,
                        owner_token,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ExecutionLeaseLostError("ERP Agent 运行租约已失效")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fail_run(
        self,
        *,
        run_key: str,
        owner_token: str,
        state: dict[str, Any],
        error: Exception,
    ) -> None:
        """处理节点包装器之外的异常，并保留最后安全状态。"""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ai_erp_agent_runs
                    SET status = 'failed', state_json = %s,
                        last_error_code = 'run_failed', last_error_message = %s,
                        owner_token = NULL, lease_expires_at = NULL,
                        updated_at = CURRENT_TIMESTAMP(6)
                    WHERE run_key = %s AND status != 'completed'
                      AND owner_token = %s
                      AND lease_expires_at > CURRENT_TIMESTAMP(6)
                    """,
                    (
                        _json_dump(_execution_state(state)),
                        str(error)[:1000],
                        run_key,
                        owner_token,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_status(
        self,
        *,
        company_id: str,
        assistant_key: str,
        user_id: str,
        run_key: str,
    ) -> dict[str, Any]:
        """按租户、助手和用户隔离返回运行状态，不暴露检查点业务数据。"""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.run_key AS run_id, r.request_id,
                           r.session_key AS session_id, r.status,
                           r.current_step, r.state_version, r.retry_count,
                           r.last_error_code, r.last_error_message,
                           r.lease_expires_at,
                           CASE
                               WHEN r.status = 'failed' THEN 1
                               WHEN r.status = 'running'
                                    AND r.lease_expires_at <= CURRENT_TIMESTAMP(6) THEN 1
                               ELSE 0
                           END AS recoverable,
                           r.started_at, r.completed_at, r.created_at, r.updated_at
                    FROM ai_erp_agent_runs AS r
                    INNER JOIN ai_erp_assistants AS a
                        ON a.company_id = r.company_id AND a.id = r.assistant_id
                    WHERE r.company_id = %s AND a.assistant_key = %s
                      AND r.user_id = %s AND r.run_key = %s
                    LIMIT 1
                    """,
                    (company_id, assistant_key, user_id, run_key),
                )
                row = cursor.fetchone()
                if not row:
                    raise ExecutionNotFoundError("ERP Agent 运行不存在")
                return dict(row)
        finally:
            connection.close()

    @staticmethod
    def _assistant_id(cursor: Any, company_id: str, assistant_key: str) -> int:
        cursor.execute(
            """
            SELECT id FROM ai_erp_assistants
            WHERE company_id = %s AND assistant_key = %s AND status = 'active'
            LIMIT 1
            """,
            (company_id, assistant_key),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(
                f"未找到启用的 Assistant 配置：company_id={company_id}, assistant_key={assistant_key}"
            )
        return int(row["id"])

    @staticmethod
    def _owned_run(cursor: Any, run_key: str, owner_token: str) -> dict[str, Any]:
        cursor.execute(
            """
            SELECT id, company_id, assistant_id, state_version
            FROM ai_erp_agent_runs
            WHERE run_key = %s AND owner_token = %s AND status = 'running'
              AND lease_expires_at > CURRENT_TIMESTAMP(6)
            FOR UPDATE
            """,
            (run_key, owner_token),
        )
        row = cursor.fetchone()
        if not row:
            raise ExecutionLeaseLostError("ERP Agent 运行租约已失效")
        return dict(row)

    @staticmethod
    def _insert_checkpoint(
        cursor: Any,
        *,
        run: dict[str, Any],
        sequence: int,
        step_name: str,
        phase: str,
        state: dict[str, Any],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO ai_erp_agent_checkpoints (
                company_id, assistant_id, run_id, checkpoint_seq,
                step_name, phase, state_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run["company_id"],
                run["assistant_id"],
                run["id"],
                sequence,
                step_name,
                phase,
                _json_dump(state),
            ),
        )

    @staticmethod
    def _connect() -> Any:
        """创建独立短事务连接；执行记录不能与长时间 ERP 调用共用连接。"""
        settings = get_settings()
        if not settings.mysql_database or not settings.mysql_user:
            raise RuntimeError("Durable Execution 缺少 MySQL 数据库或用户配置")
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError("Durable Execution 缺少 PyMySQL，请执行 uv sync。") from exc
        return pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            connect_timeout=settings.mysql_connect_timeout,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )


execution_repository = ExecutionRepository()
