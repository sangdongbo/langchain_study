from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from ai_erp_rag_assistant.app.config import get_settings


_STATE_KEYS = {
    "active_approval",
    "company_id",
    "conversation",
    "consumed_preview",
    "department",
    "draft_key",
    "fields",
    "form_schema",
    "pending_question",
    "plan",
    "preview",
    "route",
    "selected_assignees",
    "template",
    "template_candidates",
    "workflow_status",
}
_SECRET_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "token",
}
_CLOSED_STATUSES = {"submitted", "cancelled", "blocked"}


def resumable_state(state: dict[str, Any]) -> dict[str, Any]:
    """Keep only state required by the next turn and remove credentials."""
    return _strip_secrets({key: state[key] for key in _STATE_KEYS if key in state})


class SessionRepository:
    """MySQL 长期会话仓储；消息写入后保持不可变。"""

    @property
    def enabled(self) -> bool:
        return get_settings().session_store == "mysql"

    def list_sessions(
        self,
        *,
        company_id: str,
        assistant_key: str,
        user_id: str,
        status: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        """按公司、Assistant 和用户隔离查询会话，并返回是否还有下一页。"""

        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.session_key AS session_id, s.title, s.status,
                           s.current_route, s.workflow_status, s.active_approval,
                           s.last_message_seq, s.last_active_at, s.created_at, s.updated_at
                    FROM ai_erp_sessions AS s
                    INNER JOIN ai_erp_assistants AS a
                        ON a.company_id = s.company_id AND a.id = s.assistant_id
                    WHERE s.company_id = %s AND a.assistant_key = %s
                      AND s.user_id = %s AND s.status = %s
                    ORDER BY s.last_active_at DESC, s.id DESC
                    LIMIT %s OFFSET %s
                    """,
                    # 多取一条仅用于判断 has_more，避免额外执行 COUNT 查询。
                    (company_id, assistant_key, user_id, status, page_size + 1, (page - 1) * page_size),
                )
                rows = list(cursor.fetchall())
                return rows[:page_size], len(rows) > page_size
        finally:
            connection.close()

    def list_messages(
        self,
        *,
        company_id: str,
        assistant_key: str,
        user_id: str,
        session_key: str,
        before_seq: int | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        """按会话序号向前分页读取消息，查询条件同时校验会话所有者。"""

        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.message_seq, m.request_id, m.role, m.content,
                           m.route, m.status, m.created_at
                    FROM ai_erp_messages AS m
                    INNER JOIN ai_erp_sessions AS s
                        ON s.company_id = m.company_id
                       AND s.assistant_id = m.assistant_id
                       AND s.id = m.session_id
                    INNER JOIN ai_erp_assistants AS a
                        ON a.company_id = s.company_id AND a.id = s.assistant_id
                    WHERE s.company_id = %s AND a.assistant_key = %s
                      AND s.user_id = %s AND s.session_key = %s
                      AND s.status != 'deleted'
                      AND (%s IS NULL OR m.message_seq < %s)
                    ORDER BY m.message_seq DESC
                    LIMIT %s
                    """,
                    (
                        company_id,
                        assistant_key,
                        user_id,
                        session_key,
                        before_seq,
                        before_seq,
                        page_size + 1,
                    ),
                )
                rows = list(cursor.fetchall())
                has_more = len(rows) > page_size
                # SQL 倒序取最近一页，返回前恢复为聊天界面需要的时间正序。
                return list(reversed(rows[:page_size])), has_more
        finally:
            connection.close()

    def load_state(
        self,
        *,
        company_id: str,
        assistant_key: str,
        user_id: str,
        session_key: str,
    ) -> dict[str, Any]:
        """加载下一轮工作流所需的脱敏状态，不返回认证凭证。"""

        if not self.enabled:
            return {}
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.state_json
                    FROM ai_erp_sessions AS s
                    INNER JOIN ai_erp_assistants AS a
                        ON a.company_id = s.company_id AND a.id = s.assistant_id
                    WHERE s.company_id = %s AND a.assistant_key = %s
                      AND s.user_id = %s AND s.session_key = %s
                      AND s.status = 'active'
                    LIMIT 1
                    """,
                    (company_id, assistant_key, user_id, session_key),
                )
                row = cursor.fetchone()
                return _json_object(row.get("state_json")) if row else {}
        finally:
            connection.close()

    def cached_response(
        self,
        *,
        company_id: str,
        assistant_key: str,
        user_id: str,
        session_key: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        """根据前端 request_id 返回已完成响应，实现安全重试幂等。"""

        if not self.enabled or not request_id:
            return None
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.metadata_json
                    FROM ai_erp_messages AS m
                    INNER JOIN ai_erp_sessions AS s
                        ON s.company_id = m.company_id
                       AND s.assistant_id = m.assistant_id
                       AND s.id = m.session_id
                    INNER JOIN ai_erp_assistants AS a
                        ON a.company_id = s.company_id AND a.id = s.assistant_id
                    WHERE s.company_id = %s AND a.assistant_key = %s
                      AND s.user_id = %s AND s.session_key = %s
                      AND m.request_id = %s AND m.role = 'assistant'
                    LIMIT 1
                    """,
                    (company_id, assistant_key, user_id, session_key, request_id),
                )
                row = cursor.fetchone()
                metadata = _json_object(row.get("metadata_json")) if row else {}
                response = metadata.get("response")
                return response if isinstance(response, dict) else None
        finally:
            connection.close()

    def save_exchange(
        self,
        *,
        company_id: str,
        assistant_key: str,
        session_key: str,
        user_id: str,
        erp_uid: str,
        request_id: str,
        user_message: str,
        state: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        """在同一事务保存消息、可恢复状态、审批快照和脱敏工具事件。"""

        if not self.enabled:
            return
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                assistant_id, config_version_id = self._assistant(cursor, company_id, assistant_key)
                cursor.execute(
                    """
                    SELECT id, last_message_seq
                    FROM ai_erp_sessions
                    WHERE company_id = %s AND assistant_id = %s
                      AND user_id = %s AND session_key = %s
                    FOR UPDATE
                    """,
                    (company_id, assistant_id, user_id, session_key),
                )
                session = cursor.fetchone()
                if not session:
                    cursor.execute(
                        """
                        INSERT INTO ai_erp_sessions (
                            company_id, assistant_id, config_version_id, session_key,
                            user_id, erp_uid, title, current_route, workflow_status,
                            active_approval, state_version, state_json, last_message_seq
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, 0)
                        """,
                        (
                            company_id,
                            assistant_id,
                            config_version_id,
                            session_key,
                            user_id,
                            erp_uid or None,
                            user_message[:255],
                            state.get("route"),
                            state.get("workflow_status") or "idle",
                            int(bool(state.get("active_approval"))),
                            _json_dump(resumable_state(state)),
                        ),
                    )
                    session_id, last_seq = int(cursor.lastrowid), 0
                else:
                    session_id = int(session["id"])
                    last_seq = int(session.get("last_message_seq") or 0)
                if request_id:
                    cursor.execute(
                        "SELECT id FROM ai_erp_messages WHERE session_id = %s AND request_id = %s LIMIT 1",
                        (session_id, request_id),
                    )
                    if cursor.fetchone():
                        connection.commit()
                        return
                self._insert_message(
                    cursor,
                    company_id,
                    assistant_id,
                    session_id,
                    config_version_id,
                    last_seq + 1,
                    None,
                    "user",
                    user_message,
                    state.get("route"),
                    None,
                )
                self._insert_message(
                    cursor,
                    company_id,
                    assistant_id,
                    session_id,
                    config_version_id,
                    last_seq + 2,
                    request_id or None,
                    "assistant",
                    str(response.get("message") or ""),
                    state.get("route"),
                    {"response": _strip_secrets(response)},
                )
                draft_id = self._persist_approval_state(
                    cursor,
                    company_id=company_id,
                    assistant_id=assistant_id,
                    session_id=session_id,
                    user_id=user_id,
                    state=state,
                )
                self._persist_tool_events(
                    cursor,
                    company_id=company_id,
                    assistant_id=assistant_id,
                    session_id=session_id,
                    request_id=request_id,
                    tool_calls=response.get("tool_calls") or [],
                )
                self._persist_submission_attempt(
                    cursor,
                    company_id=company_id,
                    assistant_id=assistant_id,
                    session_id=session_id,
                    draft_id=draft_id,
                    request_id=request_id,
                    state=state,
                )
                cursor.execute(
                    """
                    UPDATE ai_erp_sessions
                    SET config_version_id = %s, erp_uid = %s,
                        current_route = %s, workflow_status = %s,
                        active_approval = %s, state_version = state_version + 1,
                        state_json = %s, last_message_seq = %s,
                        last_active_at = CURRENT_TIMESTAMP(6)
                    WHERE id = %s
                    """,
                    (
                        config_version_id,
                        erp_uid or None,
                        state.get("route"),
                        state.get("workflow_status") or "idle",
                        int(bool(state.get("active_approval"))),
                        _json_dump(resumable_state(state)),
                        last_seq + 2,
                        session_id,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _persist_approval_state(
        cursor: Any,
        *,
        company_id: str,
        assistant_id: int,
        session_id: int,
        user_id: str,
        state: dict[str, Any],
    ) -> int | None:
        draft_key = str(state.get("draft_key") or "")
        preview = state.get("preview") or state.get("consumed_preview") or {}
        template = state.get("template") or {}
        template_id = str(
            template.get("template_id")
            or preview.get("template_id")
            or state.get("erp_data", {}).get("template_code")
            or ""
        )
        if not draft_key:
            return None
        workflow_status = str(state.get("workflow_status") or "collecting_fields")
        if template_id:
            cursor.execute(
                """
                INSERT INTO ai_erp_approval_drafts (
                    company_id, assistant_id, session_id, user_id, draft_key,
                    template_id, template_title, workflow_status, fields_json,
                    selected_assignees_json, state_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    template_id = VALUES(template_id),
                    template_title = VALUES(template_title),
                    workflow_status = VALUES(workflow_status),
                    fields_json = VALUES(fields_json),
                    selected_assignees_json = VALUES(selected_assignees_json),
                    state_version = state_version + 1
                """,
                (
                    company_id,
                    assistant_id,
                    session_id,
                    user_id,
                    draft_key,
                    template_id,
                    str(template.get("title") or preview.get("title") or ""),
                    workflow_status,
                    _json_dump(_strip_secrets(state.get("fields") or {})),
                    _json_dump(_strip_secrets(state.get("selected_assignees") or {})),
                ),
            )
        cursor.execute(
            """
            SELECT id FROM ai_erp_approval_drafts
            WHERE company_id = %s AND assistant_id = %s AND draft_key = %s
            LIMIT 1
            """,
            (company_id, assistant_id, draft_key),
        )
        row = cursor.fetchone()
        if not row:
            return None
        draft_id = int(row["id"])
        if workflow_status in _CLOSED_STATUSES:
            cursor.execute(
                """
                UPDATE ai_erp_approval_drafts
                SET workflow_status = %s, fields_json = JSON_OBJECT(),
                    selected_assignees_json = JSON_OBJECT(), state_version = state_version + 1
                WHERE id = %s
                """,
                (workflow_status, draft_id),
            )
        preview_id = str(preview.get("preview_id") or "")
        if preview_id:
            workflow_status = str(state.get("workflow_status") or "")
            confirmation_status = str(preview.get("confirmation_status") or "")
            if not confirmation_status:
                confirmation_status = "consumed" if workflow_status == "submitted" else "pending"
            cursor.execute(
                """
                INSERT INTO ai_erp_approval_previews (
                    company_id, assistant_id, draft_id, preview_id, preview_version,
                    preview_hash, template_id, submission_fields_json, nodes_json,
                    submit_nodes_json, approval_flow_json, requires_confirmation,
                    confirmation_status, idempotency_key, consumed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s IN ('consumed','write_disabled') THEN CURRENT_TIMESTAMP(6) ELSE NULL END)
                ON DUPLICATE KEY UPDATE
                    requires_confirmation = VALUES(requires_confirmation),
                    confirmation_status = VALUES(confirmation_status),
                    consumed_at = VALUES(consumed_at)
                """,
                (
                    company_id,
                    assistant_id,
                    draft_id,
                    preview_id,
                    int(preview.get("preview_version") or 1),
                    str(preview.get("preview_hash") or ""),
                    template_id,
                    _json_dump(_strip_secrets(preview.get("submission_fields") or {})),
                    _json_dump(_strip_secrets(preview.get("nodes") or [])),
                    _json_dump(_strip_secrets(preview.get("submit_nodes") or [])),
                    _json_dump(_strip_secrets(preview.get("approval_flow") or [])),
                    int(bool(preview.get("requires_confirmation"))),
                    confirmation_status,
                    str(preview.get("idempotency_key") or ""),
                    confirmation_status,
                ),
            )
        return draft_id

    @staticmethod
    def _persist_tool_events(
        cursor: Any,
        *,
        company_id: str,
        assistant_id: int,
        session_id: int,
        request_id: str,
        tool_calls: list[Any],
    ) -> None:
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            tool_name = str(call.get("tool") or "unknown")
            failed = tool_name == "system.error" or bool(call.get("error"))
            cursor.execute(
                """
                INSERT INTO ai_erp_tool_events (
                    company_id, assistant_id, session_id, request_id, event_id,
                    tool_name, event_type, success, payload_summary_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    company_id,
                    assistant_id,
                    session_id,
                    request_id,
                    uuid4().hex,
                    tool_name,
                    "error" if failed else "decision",
                    int(not failed),
                    _json_dump(_tool_summary(call)),
                ),
            )

    @staticmethod
    def _persist_submission_attempt(
        cursor: Any,
        *,
        company_id: str,
        assistant_id: int,
        session_id: int,
        draft_id: int | None,
        request_id: str,
        state: dict[str, Any],
    ) -> None:
        """记录一次真实提交或写入被禁用的结果，供幂等与审计使用。"""

        result = state.get("erp_data") if isinstance(state.get("erp_data"), dict) else {}
        idempotency_key = str(result.get("idempotency_key") or "")
        if not idempotency_key:
            return
        preview = state.get("preview") or state.get("consumed_preview") or {}
        write_mode = str(result.get("erp_write_mode") or "")
        status = "blocked" if write_mode == "disabled" else "succeeded"
        cursor.execute(
            """
            INSERT INTO ai_erp_submission_attempts (
                company_id, assistant_id, session_id, draft_id, preview_id,
                idempotency_key, template_id, request_id, attempt_no, status,
                erp_mode, erp_write_mode, response_summary_json, finished_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, CURRENT_TIMESTAMP(6))
            ON DUPLICATE KEY UPDATE
                request_id = VALUES(request_id), status = VALUES(status),
                erp_mode = VALUES(erp_mode), erp_write_mode = VALUES(erp_write_mode),
                response_summary_json = VALUES(response_summary_json),
                finished_at = VALUES(finished_at)
            """,
            (
                company_id,
                assistant_id,
                session_id,
                draft_id,
                str(preview.get("preview_id") or "") or None,
                idempotency_key,
                str(preview.get("template_id") or result.get("template_code") or ""),
                # request_id 关联前端请求；ERP approval_id 只属于响应摘要，二者不能混用。
                request_id or None,
                status,
                str(result.get("erp_mode") or ""),
                write_mode,
                _json_dump({"keys": sorted(result.keys()), "has_approval_id": bool(result.get("approval_id"))}),
            ),
        )

    @staticmethod
    def _assistant(cursor: Any, company_id: str, assistant_key: str) -> tuple[int, int | None]:
        cursor.execute(
            """
            SELECT id, published_config_version_id
            FROM ai_erp_assistants
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
        config_id = row.get("published_config_version_id")
        return int(row["id"]), int(config_id) if config_id is not None else None

    @staticmethod
    def _insert_message(
        cursor: Any,
        company_id: str,
        assistant_id: int,
        session_id: int,
        config_version_id: int | None,
        sequence: int,
        request_id: str | None,
        role: str,
        content: str,
        route: Any,
        metadata: dict[str, Any] | None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO ai_erp_messages (
                company_id, assistant_id, session_id, config_version_id,
                message_seq, request_id, role, content, route, status, metadata_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'completed', %s)
            """,
            (
                company_id,
                assistant_id,
                session_id,
                config_version_id,
                sequence,
                request_id,
                role,
                content,
                route,
                _json_dump(metadata) if metadata else None,
            ),
        )

    @staticmethod
    def _connect() -> Any:
        settings = get_settings()
        missing = [
            name
            for name, value in (
                ("AI_ERP_MYSQL_DATABASE", settings.mysql_database),
                ("AI_ERP_MYSQL_USER", settings.mysql_user),
            )
            if not value
        ]
        if missing:
            raise RuntimeError("MySQL会话存储缺少配置：" + "、".join(missing))
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError("MySQL会话存储缺少 PyMySQL，请执行 uv sync。") from exc
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


def _strip_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_secrets(item)
            for key, item in value.items()
            if str(key).lower() not in _SECRET_KEYS and str(key).lower() != "raw_userinfo"
        }
    if isinstance(value, list):
        return [_strip_secrets(item) for item in value]
    return value


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _tool_summary(call: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"tool": str(call.get("tool") or "unknown")}
    for key, value in call.items():
        if key == "tool":
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            summary[str(key)] = value if not isinstance(value, str) else value[:500]
        elif isinstance(value, list):
            summary[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            summary[f"{key}_keys"] = sorted(str(item) for item in value.keys())[:50]
    return _strip_secrets(summary)


session_repository = SessionRepository()
