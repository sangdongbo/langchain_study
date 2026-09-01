"""封装真实或 Mock ERP 的身份、审批读取、动态字段和写入接口。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.services.approval_form_service import (
    find_field,
    normalize_approval_nodes,
    normalize_erp_fields,
    project_chat_fields,
)
from ai_erp_rag_assistant.app.services.audit_log_service import (
    summarize_response,
    write_audit_event,
)


logger = logging.getLogger("ai_erp_rag_assistant.erp")


# “病假”等表单值表示请假子类型，而不是审批模板名称；将这组词汇放在适配器边界，
# 确保所有调用方都按一致的业务语义搜索 ERP 动态目录。
_APPROVAL_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "请假": (
        "请假", "休假", "病假", "事假", "年假", "调休", "婚假", "产假",
        "陪产假", "丧假", "哺乳假", "育儿假",
    ),
    "报销": ("报销", "费用报销", "差旅费", "发票报销"),
    "采购": ("采购", "购买", "申购"),
    "用章": ("用章", "盖章", "印章"),
    "外出": ("外出",),
    "出差": ("出差", "差旅申请"),
    "加班": ("加班",),
    "入库": ("入库",),
    "出库": ("出库",),
}

_GENERIC_APPROVAL_WORDS = (
    "麻烦", "帮我", "我要", "我想", "需要", "请帮忙", "发起", "办理",
    "提交", "审批", "申请", "流程", "一个", "一下",
)


class ErpClient:
    """ERP 适配器。

    remote 模式调用 ai_approval_assistant 使用的同一组审批接口；mock 模式只用于
    离线演练，响应会带 ``erp_mode=mock``，避免被误认为真实 ERP 数据。
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def read_mode(self) -> str:
        """返回标准化的 ERP 读取模式。"""
        return (self.settings.erp_read_mode or self.settings.erp_mode).lower().strip()

    @property
    def write_mode(self) -> str:
        """返回独立于读取模式的 ERP 写入开关。"""
        return self.settings.erp_write_mode.lower().strip()

    def _headers(self, user: dict[str, Any]) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": str(user.get("authorization") or self.settings.erp_authorization),
            "UID": str(user.get("uid") or self.settings.erp_uid),
        }

    def _post(
        self,
        path: str,
        body: dict[str, Any],
        user: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """调用 ERP JSON 接口，并记录脱敏请求摘要、耗时和响应摘要。"""
        url = f"{self.settings.erp_base_url.rstrip('/')}{path}"
        headers = self._headers(user)
        headers.update(extra_headers or {})
        request_id = uuid4().hex
        started_at = monotonic()
        status_code: int | None = None
        # 审计层会移除认证信息和表单值，这里只传结构化请求用于关联排障。
        write_audit_event(
            "erp.request",
            {
                "request_id": request_id,
                "path": path,
                "company_id": user.get("company_id"),
                "user_id": user.get("user_id"),
                "uid": user.get("uid"),
                "body": body,
            },
        )
        try:
            # 所有远程 ERP 调用统一使用短超时、HTTP 状态检查和 JSON 对象校验。
            response = httpx.post(url, headers=headers, json=body, timeout=15)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"ERP 返回不是 JSON 对象：{path}")
            write_audit_event(
                "erp.response",
                {
                    "request_id": request_id,
                    "path": path,
                    "status_code": status_code,
                    **summarize_response(payload),
                },
            )
            return payload
        except Exception as exc:
            # 错误事件与成功响应共用 request_id，便于关联网关和应用日志。
            write_audit_event(
                "erp.error",
                {
                    "request_id": request_id,
                    "path": path,
                    "status_code": status_code,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise
        finally:
            # 无论成功或失败都记录耗时，不在日志中回显请求凭据。
            write_audit_event(
                "erp.timing",
                {
                    "request_id": request_id,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": max(0, int((monotonic() - started_at) * 1000)),
                },
            )

    def _get(
        self,
        path: str,
        params: dict[str, Any],
        user: dict[str, Any],
    ) -> dict[str, Any]:
        """调用 ERP 只读 GET 接口，并沿用与 POST 相同的审计和超时策略。"""
        url = f"{self.settings.erp_base_url.rstrip('/')}{path}"
        headers = self._headers(user)
        request_id = uuid4().hex
        started_at = monotonic()
        status_code: int | None = None
        write_audit_event(
            "erp.request",
            {
                "request_id": request_id,
                "path": path,
                "method": "GET",
                "company_id": user.get("company_id"),
                "user_id": user.get("user_id"),
                "uid": user.get("uid"),
                "body": params,
            },
        )
        try:
            response = httpx.get(url, headers=headers, params=params, timeout=15)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"ERP 返回不是 JSON 对象：{path}")
            write_audit_event(
                "erp.response",
                {
                    "request_id": request_id,
                    "path": path,
                    "method": "GET",
                    "status_code": status_code,
                    **summarize_response(payload),
                },
            )
            return payload
        except Exception as exc:
            write_audit_event(
                "erp.error",
                {
                    "request_id": request_id,
                    "path": path,
                    "method": "GET",
                    "status_code": status_code,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise
        finally:
            write_audit_event(
                "erp.timing",
                {
                    "request_id": request_id,
                    "path": path,
                    "method": "GET",
                    "status_code": status_code,
                    "duration_ms": max(0, int((monotonic() - started_at) * 1000)),
                },
            )

    def get_workstation_layout(self, *, user: dict[str, Any]) -> list[dict[str, Any]]:
        """读取 ERP 已保存的工作台组件布局。"""
        if self.read_mode == "mock":
            return []
        payload = self._post("/api/workstation/getWorkstationLayout", {}, user)
        _require_success(payload, "工作台布局")
        data = payload.get("data")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def get_user_layout(self, layout_type: str, *, user: dict[str, Any]) -> list[dict[str, Any]]:
        """读取一个工作台看板的个人显示配置。"""
        if self.read_mode == "mock":
            return []
        payload = self._post("/api/workstation/userLayoutGet", {"layout_type": layout_type}, user)
        _require_success(payload, "个人工作台布局")
        data = payload.get("data")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def get_todo_count(self, *, platform: str = "pc", user: dict[str, Any]) -> dict[str, Any]:
        """读取待办顶部数量；ERP 当前接口为 GET。"""
        if self.read_mode == "mock":
            return {"basic": 0, "approval": 0, "total": 0}
        payload = self._get("/api/todo/count", {"platform": platform}, user)
        _require_success(payload, "待办总数")
        data = payload.get("data")
        if isinstance(data, dict):
            result = dict(data)
            # 不同 ERP 版本分别使用 total/count/total_num；统一补齐工作台契约。
            if "total" not in result:
                for key in ("count", "total_num", "todo_count", "num"):
                    if isinstance(result.get(key), (int, float, str)):
                        result["total"] = result[key]
                        break
            if "total" not in result and all(
                isinstance(result.get(key), (int, float)) for key in ("basic", "approval")
            ):
                result["total"] = result["basic"] + result["approval"]
            return result
        return {"total": int(data or 0)}

    def get_todo_types(self, *, platform: str = "pc", user: dict[str, Any]) -> list[dict[str, Any]]:
        """读取待办分类及数量。"""
        if self.read_mode == "mock":
            return []
        payload = self._get("/api/todo/typeLists", {"platform": platform}, user)
        _require_success(payload, "待办分类")
        return _list_values(payload.get("data"))

    def get_todo_items(self, *, page_size: int, user: dict[str, Any]) -> list[dict[str, Any]]:
        """读取工作台可直接展示的少量待办，失败由聚合层按模块隔离。"""
        if self.read_mode == "mock":
            return []
        items: list[dict[str, Any]] = []
        for path, params in (
            ("/api/todo/lists/orders", {"page": 1, "pageSize": page_size}),
            ("/api/todo/lists/personnel", {"page": 1, "pageSize": page_size}),
        ):
            payload = self._get(path, params, user)
            _require_success(payload, "待办明细")
            items.extend(_list_values(payload.get("data")))
        return items[:page_size]

    def get_oa_todo_items(self, *, page_size: int, user: dict[str, Any]) -> list[dict[str, Any]]:
        """读取 OA 工单/日志/公告/资产待办的少量明细。

        OA 在不同部署中同时存在 v2、pc 两个 GET 端点；工单待办使用独立的
        ``/api/WorkOrder/workorderTodoList`` POST 端点。每个端点单独容错，
        某个旧版本不存在时仍返回其他分类，避免影响工作台数量卡片。
        """
        if self.read_mode == "mock":
            return []
        items: list[dict[str, Any]] = []
        requests: tuple[tuple[str, str, dict[str, Any]], ...] = (
            ("GET", "/oa/todo/lists/v2", {"page": 1, "pageSize": page_size}),
            ("GET", "/oa/todo/lists/pc", {"page": 1, "pageSize": page_size}),
        )
        for method, path, params in requests:
            try:
                payload = self._get(path, params, user)
                _require_success(payload, "OA待办明细")
                items.extend(_list_values(payload.get("data")))
            except Exception as exc:
                logger.info("OA 待办端点不可用，继续尝试其他端点：%s (%s)", path, exc)
        try:
            payload = self._post(
                "/api/WorkOrder/workorderTodoList",
                {"page": 1, "pageSize": page_size},
                user,
            )
            _require_success(payload, "工单待办明细")
            items.extend(_list_values(payload.get("data")))
        except Exception as exc:
            logger.info("工单待办端点不可用，继续返回已读取的 OA 待办：%s", exc)
        return items[:page_size]

    def get_approval_center_counts(self, *, user: dict[str, Any]) -> dict[str, Any]:
        """读取审批中心待处理和已收到数量。"""
        if self.read_mode == "mock":
            return {"pending_num": 0, "received_num": 0}
        payload = self._post("/api/approval/stateTypeNum", {
            "keyword": "",
            "approval_set_id": [],
            "creator_uid": [],
            "date_range": "",
            "approval_status": [],
        }, user)
        _require_success(payload, "审批中心数量")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_pending_approvals(self, *, page_size: int, user: dict[str, Any]) -> dict[str, Any]:
        """读取审批中心待处理列表，使用现网实际的 overviewList 接口。"""
        if self.read_mode == "mock":
            return {"list": [], "total": 0}
        payload = self._post("/api/approvalCenter/overviewList", {
            "keyword": "",
            "type": "awaiting_my_action",
            "page": 1,
            "pageSize": page_size,
            "approval_set_id": [],
            "creator_uid": [],
            "date_range": "",
            "sort_field": "desc",
            "approval_status": [],
        }, user)
        _require_success(payload, "审批列表")
        data = payload.get("data")
        if isinstance(data, list):
            return {"list": _list_values(data)[:page_size], "total": len(data)}
        if not isinstance(data, dict):
            return {"list": [], "total": 0}
        values = _list_values(data)
        total = data.get("total")
        if total is None:
            total = data.get("count")
        return {"list": values[:page_size], "total": total if total is not None else len(values)}

    def get_message_groups(self, *, user: dict[str, Any]) -> dict[str, Any]:
        """读取消息分组、未读数量和分类摘要。"""
        if self.read_mode == "mock":
            return {"all": {"data": [], "total_unread": 0}, "unread": {"data": [], "total_unread": 0}, "disturb": {"data": [], "total_unread": 0}, "later": {"data": [], "total_unread": 0}}
        payload = self._post("/api/message/get-group-counts", {}, user)
        _require_success(payload, "消息分组")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_message_items(self, *, page_size: int, user: dict[str, Any]) -> list[dict[str, Any]]:
        """读取审批、订单和公告等高价值未读消息的前几条。"""
        if self.read_mode == "mock":
            return []
        items: list[dict[str, Any]] = []
        for category in ("approval", "order", "announcement"):
            payload = self._post("/api/message/get-category-messages", {
                "group_type": "unread",
                "category_name_en": category,
                "order": "desc",
                "limit": page_size,
            }, user)
            _require_success(payload, "消息列表")
            data = payload.get("data")
            values = data.get("list_data") if isinstance(data, dict) else data
            items.extend(_list_values(values))
        return items[:page_size]

    def get_today_attendance(self, *, user: dict[str, Any]) -> dict[str, Any]:
        """读取工作台今日考勤看板。"""
        if self.read_mode == "mock":
            return {"data": [], "total": 0}
        payload = self._post("/api/workstation/getTodayAttendance", {}, user)
        _require_success(payload, "今日考勤")
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return {"data": data if isinstance(data, list) else []}

    def get_new_add_dashboard(self, types: list[str], *, user: dict[str, Any]) -> dict[str, Any]:
        """按布局中启用的类型读取今日新增卡片。"""
        if self.read_mode == "mock" or not types:
            return {}
        payload = self._post("/api/workstation/newAddDashboard", {"newAddType": types}, user)
        _require_success(payload, "今日新增看板")
        return payload.get("data") if isinstance(payload.get("data"), dict) else {}

    def get_stats_dashboard(self, types: list[str], *, user: dict[str, Any]) -> dict[str, Any]:
        """按布局中启用的类型读取统计卡片。"""
        if self.read_mode == "mock" or not types:
            return {}
        payload = self._post("/api/workstation/statsDashboard", {"statsType": types, "queryDate": []}, user)
        _require_success(payload, "统计看板")
        return payload.get("data") if isinstance(payload.get("data"), dict) else {}

    def get_workbench_summary(
        self,
        *,
        user: dict[str, Any],
        modules: set[str],
        page_size: int = 5,
        include_todo_items: bool = False,
        include_extended_todo_items: bool = False,
        include_message_items: bool = True,
        include_cards: bool = False,
    ) -> dict[str, Any]:
        """并行聚合个人工作台只读数据；单个 ERP 模块失败不会拖垮整页。"""
        selected = modules or {"layout", "todo", "approvals", "messages", "attendance"}
        result: dict[str, Any] = {
            "user": {
                "uid": str(user.get("uid") or user.get("user_id") or ""),
                "name": str(user.get("name") or user.get("real_name") or user.get("username") or ""),
                "department": str(user.get("department") or user.get("department_name") or ""),
                "avatar": str(user.get("avatar") or user.get("avatar_url") or ""),
            },
            "layout": {"status": "empty", "items": [], "count": 0},
            "todo": {"status": "empty", "categories": [], "items": [], "count": 0},
            "approvals": {"status": "empty", "items": [], "total": 0, "counts": {}},
            "messages": {"status": "empty", "groups": {}, "important": [], "count": 0},
            "attendance": {"status": "empty", "today": {}},
            "cards": [],
            "counts": {},
        }

        def call(name: str) -> Any:
            if name == "layout":
                return self.get_workstation_layout(user=user)
            if name == "todo":
                return {
                    "count": self.get_todo_count(user=user),
                    "categories": self.get_todo_types(user=user),
                    "items": (
                        self.get_todo_items(page_size=page_size, user=user)
                        + (
                            self.get_oa_todo_items(page_size=page_size, user=user)
                            if include_extended_todo_items
                            else []
                        )
                    )[:page_size] if include_todo_items else [],
                }
            if name == "approvals":
                return {"list": self.get_pending_approvals(page_size=page_size, user=user), "counts": self.get_approval_center_counts(user=user)}
            if name == "messages":
                return {"groups": self.get_message_groups(user=user), "items": self.get_message_items(page_size=page_size, user=user) if include_message_items else []}
            if name == "attendance":
                return self.get_today_attendance(user=user)
            raise ValueError(name)

        names = [name for name in ("layout", "todo", "approvals", "messages", "attendance") if name in selected]
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=max(1, len(names))) as pool:
            futures = {pool.submit(call, name): name for name in names}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    value = future.result()
                    if name == "layout":
                        result["layout"] = {"status": "ok" if value else "empty", "items": value, "count": len(value)}
                    elif name == "todo":
                        raw_count = value["count"]
                        result["todo"] = {"status": "ok", "categories": value["categories"], "items": value["items"], "count": raw_count.get("total", raw_count.get("basic", 0))}
                        result["counts"].update({"todo_basic": raw_count.get("basic", 0), "todo_approval": raw_count.get("approval", 0), "todo_total": raw_count.get("total", 0)})
                    elif name == "approvals":
                        approval_list = value["list"]
                        result["approvals"] = {"status": "ok", "items": approval_list.get("list", []), "total": approval_list.get("total", 0), "counts": value["counts"]}
                        result["counts"].update({"pending_approval": value["counts"].get("pending_num", 0), "approval_received": value["counts"].get("received_num", 0)})
                    elif name == "messages":
                        groups = value["groups"]
                        unread = groups.get("unread", {}) if isinstance(groups, dict) else {}
                        result["messages"] = {"status": "ok", "groups": groups, "important": value["items"], "count": unread.get("total_unread", 0)}
                        result["counts"]["unread_message"] = unread.get("total_unread", 0)
                    elif name == "attendance":
                        result["attendance"] = {"status": "ok", "today": value}
                except Exception as exc:
                    errors[name] = str(exc)[:300]
                    result[name]["status"] = "error"
                    result[name]["error"] = str(exc)[:300]
        if include_cards and result["layout"]["items"]:
            layout_types = {str(item.get("type")) for item in result["layout"]["items"] if isinstance(item, dict)}
            if "newAddDashboard" in layout_types:
                try:
                    configured = self.get_user_layout("newAddDashboard", user=user)
                    configured_types = [
                        str(item.get("type")) for item in configured
                        if isinstance(item, dict) and item.get("is_show") is not False and item.get("type")
                    ]
                    if configured_types:
                        result["cards"].append({
                            "type": "newAddDashboard",
                            "status": "ok",
                            "data": self.get_new_add_dashboard(configured_types, user=user),
                        })
                except Exception as exc:
                    errors["newAddDashboard"] = str(exc)[:300]
            if "statsDashboard" in layout_types:
                try:
                    configured = self.get_user_layout("statsDashboard", user=user)
                    configured_types = [
                        str(item.get("type")) for item in configured
                        if isinstance(item, dict) and item.get("is_show") is not False and item.get("type")
                    ]
                    if configured_types:
                        result["cards"].append({
                            "type": "statsDashboard",
                            "status": "ok",
                            "data": self.get_stats_dashboard(configured_types, user=user),
                        })
                except Exception as exc:
                    errors["statsDashboard"] = str(exc)[:300]
        if errors:
            result["errors"] = errors
        return result

    def get_current_user(self, user_id: str, *, uid: str, authorization: str, company_id: str, department: str) -> dict[str, Any]:
        """通过 ERP 凭据解析可信用户、公司、部门和权限信息。"""
        user = {
            "user_id": user_id,
            "uid": uid or self.settings.erp_uid,
            "authorization": authorization or self.settings.erp_authorization,
            "company_id": company_id,
            "department": department,
        }
        if self.read_mode == "mock":
            user.update({
                # 与项目自带员工手册写入的租户元数据保持一致；其他公司仍可通过
                # 请求参数或配置覆盖这两个值。
                "company_id": company_id or self.settings.erp_demo_company_id or "lanjing",
                "department": department or self.settings.erp_demo_department or "研发部",
                "roles": ["employee"],
                "permissions": ["approval:create", "knowledge:employee_handbook"],
                "erp_mode": "mock",
                "erp_write_mode": self.write_mode,
            })
            return user
        # 有凭据时从真实 ERP 获取身份；演示场景中 user_id 仍作为调用方关联标识保留。
        if not user["uid"] or not user["authorization"]:
            if not self.settings.erp_skip_userinfo_validation:
                raise RuntimeError("ERP_MODE=remote 时必须在请求或 .env 提供 uid 和 authorization。")
        if self.settings.erp_skip_userinfo_validation:
            # 仅用于演示的回退：保留调用方凭据供后续真实 ERP 调用，但跳过 /userinfo，
            # 避免过期令牌阻塞公共知识库问题；该分支绝不执行写入。
            user.update({
                "company_id": company_id or self.settings.erp_demo_company_id or self.settings.rag_company_id,
                "department": department or self.settings.erp_demo_department or self.settings.rag_department,
                "roles": ["employee"],
                "permissions": ["approval:create", *self.settings.rag_permission_tags],
                "erp_mode": "remote",
                "erp_write_mode": self.write_mode,
                "erp_auth_verified": False,
                "erp_identity_source": "demo_fallback",
            })
            logger.warning("ERP userinfo validation skipped by ERP_SKIP_USERINFO_VALIDATION; demo identity only.")
            return user
        payload = self._post(self.settings.erp_userinfo_path, {}, user)
        _require_success(payload, "用户信息")
        raw_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        data = raw_data.get("user") if isinstance(raw_data.get("user"), dict) else raw_data
        user.update(data)
        # 远程模式已经完成 /userinfo 校验，租户和部门只能来自该可信响应；请求参数
        # 仅用于发起身份查询，不能在响应缺字段时反向成为授权依据。
        user["company_id"] = str(
            _scalar(data.get("company_id"))
            or _scalar(data.get("companyId"))
            or _scalar(data.get("company_code"))
            or ""
        )
        user["department"] = str(
            _department_value(data.get("department"))
            or _department_value(data.get("department_name"))
            or _department_value(data.get("departmentName"))
            or ""
        )
        user["permissions"] = _string_list(
            data.get("permissions")
            or data.get("permission_tags")
            or data.get("permissionTags")
            or []
        )
        user["erp_mode"] = "remote"
        user["erp_write_mode"] = self.write_mode
        user["raw_userinfo"] = raw_data
        return user

    def list_approval_templates(self, query: str, *, company_id: str, user: dict[str, Any]) -> list[dict[str, Any]]:
        """查询并规范化与用户意图确定相关的审批模板。"""
        if self.read_mode == "mock":
            catalog = [
                {"template_id": "demo-leave", "title": "请假申请", "description": "员工请假：事假、病假、年假", "company_id": company_id},
                {"template_id": "demo-expense", "title": "费用报销", "description": "费用报销、发票、餐饮费", "company_id": company_id},
                {"template_id": "demo-purchase", "title": "采购申请", "description": "采购物品、购买、预算", "company_id": company_id},
                {"template_id": "demo-seal", "title": "合同用章", "description": "合同盖章、公章、合同章", "company_id": company_id},
            ]
            return _filter_relevant_templates(query, catalog)
        queries = [query.strip()]
        queries.extend(_approval_search_keywords(query))
        for search_query in dict.fromkeys(queries):
            payload = self._post(self.settings.erp_approval_list_path, {"keyword": search_query}, user)
            _require_success(payload, "审批模板列表")
            templates = [_normalize_template_summary(item, company_id) for item in _approval_items(payload.get("data"))]
            relevant = _filter_relevant_templates(query, templates)
            if relevant:
                return relevant
        # 对非空且明确的请求不能回退到完整目录。有些 ERP 部署会忽略 keyword，
        # 直接返回完整目录会把无关模板暴露给 LLM。
        return []

    def get_approval_template(self, template_id: str, *, company_id: str, title: str = "", user: dict[str, Any]) -> dict[str, Any]:
        """读取一个审批模板并规范化其全部动态字段。"""
        if self.read_mode == "mock":
            # Mock 模板只用于离线联调，返回值显式标记 erp_mode=mock。
            templates = {
                "demo-leave": {
                    "fields": [
                        {"name": "leave_category", "label": "请假类型", "type": "select", "options": ["事假", "病假", "年假"], "required": True},
                        {"name": "begin_at", "label": "开始时间", "type": "datetime", "required": True},
                        {"name": "finish_at", "label": "结束时间", "type": "datetime", "required": True},
                        {"name": "leave_reason", "label": "请假原因", "type": "textarea", "required": True},
                    ]
                },
                "demo-expense": {
                    "fields": [
                        {"name": "expense_category", "label": "费用类型", "type": "select", "options": ["办公用品", "差旅", "招待"], "required": True},
                        {"name": "total_amount", "label": "报销金额", "type": "number", "required": True},
                        {"name": "expense_description", "label": "费用说明", "type": "textarea", "required": True},
                        {"name": "invoice_attachment", "label": "发票附件", "type": "attachment", "required": True},
                    ]
                },
                "demo-purchase": {
                    "fields": [
                        {"name": "item_name", "label": "物品名称", "type": "text", "required": True},
                        {"name": "quantity", "label": "数量", "type": "number", "required": True},
                        {"name": "budget", "label": "预算", "type": "number", "required": True},
                        {"name": "purchase_reason", "label": "采购原因", "type": "textarea", "required": True},
                    ]
                },
                "demo-seal": {
                    "fields": [
                        {"name": "contract_name", "label": "合同名称", "type": "text", "required": True},
                        {"name": "seal_type", "label": "印章类型", "type": "select", "options": ["公章", "合同章"], "required": True},
                        {"name": "copy_count", "label": "用章份数", "type": "number", "required": True},
                    ]
                },
            }
            template = templates.get(template_id)
            if not template:
                raise RuntimeError(f"演示 ERP 未找到模板：{template_id}")
            return {
                "template_code": template_id,
                "template_id": template_id,
                "title": title or template_id,
                "company_id": company_id,
                "fields": template["fields"],
                "erp_mode": "mock",
                "erp_write_mode": self.write_mode,
            }
        fields_payload = self._post(self.settings.erp_form_fields_path, {"field_form": f"approval_type_{template_id}"}, user)
        _require_success(fields_payload, "审批表单字段")
        # ERP 字段结构随版本和控件变化，先统一为稳定的前端组件契约。
        form_fields = normalize_erp_fields(fields_payload.get("data") or [])
        self._enrich_dynamic_fields(form_fields, user)
        # 聊天流程只使用必填字段投影，完整字段仍通过 all_fields 提供给管理页面。
        fields = project_chat_fields(form_fields)
        return {
            "template_code": template_id,
            "template_id": template_id,
            "title": title or template_id,
            "company_id": company_id,
            "fields": fields,
            "all_fields": form_fields,
            "form_schema": {
                "schema_version": "1.0",
                "template": {
                    "template_id": str(template_id),
                    "template_code": str(template_id),
                    "title": title or template_id,
                    "company_id": company_id,
                },
                "fields": deepcopy(form_fields),
                "values": {},
                "missing_field_keys": [],
                "invalid_fields": [],
            },
            "erp_mode": "remote",
            "erp_write_mode": self.write_mode,
        }

    def query_approval_status(self, user_id: str, *, user: dict[str, Any]) -> dict[str, Any]:
        """查询当前用户最近审批记录和状态。"""
        if self.read_mode == "mock":
            return {
                "user_id": user_id,
                "approval_id": f"DEMO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "status": "演示模式：未连接 ERP",
                "current_assignee": "请配置 ERP 凭证后查询",
                "erp_mode": "mock",
                "erp_write_mode": self.write_mode,
            }
        payload = self._post(
            self.settings.erp_approval_status_path,
            {"user_id": user.get("user_id"), "page": 1, "pageSize": 10},
            user,
        )
        _require_success(payload, "审批状态")
        data = payload.get("data") or []
        items = data.get("list") if isinstance(data, dict) else data
        items = items if isinstance(items, list) else []
        return {"user_id": user_id, "items": items[:10], "erp_mode": "remote", "erp_write_mode": self.write_mode}

    def get_approval_nodes(
        self,
        template_id: str,
        fields: dict[str, Any],
        *,
        user: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """在生成预览前读取真实审批流；该接口只读，不会写入 ERP。"""
        if self.read_mode == "mock" or not str(template_id).isdigit():
            return []
        form_value = [
            {"field_key": str(key), "value": _structured_value(value)}
            for key, value in fields.items()
        ]
        payload = self._post(
            self.settings.erp_get_nodes_path,
            {"approval_set_id": int(template_id), "form_value": form_value},
            user,
        )
        _require_success(payload, "审批节点")
        data = payload.get("data")
        nodes = data if isinstance(data, list) else []
        self._enrich_unrestricted_node_candidates(nodes, user)
        return nodes

    def _enrich_dynamic_fields(self, fields: list[dict[str, Any]], user: dict[str, Any]) -> None:
        """读取 ERP 通过独立接口暴露的字段选项。"""
        holiday_field = find_field(fields, "rest_holiday_rule_id")
        if not holiday_field or self.read_mode == "mock":
            return
        option_values = [_holiday_rule_option(item) for item in self.get_holiday_rules(user)]
        option_values = [option for option in option_values if option]
        holiday_field["option_values"] = option_values
        holiday_field["options"] = [str(option["label"]) for option in option_values]
        holiday_field["option_source"] = {
            "type": "holiday_rule",
            "lazy": False,
            "searchable": False,
        }

    def get_field_options(
        self,
        template_id: str,
        field_key: str,
        *,
        company_id: str,
        user: dict[str, Any],
        title: str = "",
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """解析一个动态 ERP 字段的静态或远程候选项。"""
        # 每次读取最新模板定义，避免页面缓存继续使用已经变更的选项来源。
        template = self.get_approval_template(
            template_id,
            company_id=company_id,
            title=title,
            user=user,
        )
        field_definitions = template.get("all_fields") or template.get("fields") or []
        if field_definitions and not any(
            isinstance(item, dict) and item.get("component") for item in field_definitions
        ):
            field_definitions = normalize_erp_fields(field_definitions)
        field = find_field(field_definitions, field_key)
        if not field:
            raise RuntimeError(f"审批模板中不存在字段：{field_key}")
        source = field.get("option_source") if isinstance(field.get("option_source"), dict) else {}
        source_type = str(source.get("type") or "")
        # 静态 options 直接复用，关联对象和人员字段在后续分支远程加载。
        options = list(field.get("option_values") or [])
        if not options:
            options = [
                {"label": str(option), "value": option, "disabled": False, "meta": {}}
                for option in field.get("options", [])
                if option not in (None, "")
            ]
        total: int | None = len(options)
        if source_type == "related_list":
            items, total = self.get_related_list(
                str(source.get("relate_type") or ""),
                user=user,
                keyword=keyword,
                page=page,
                page_size=page_size,
            )
            options = [_related_item_option(item) for item in items]
        elif source_type == "user_list":
            items = self.get_user_list(user, keyword=keyword, page_size=page_size)
            options = [_user_option(item) for item in items]
            total = len(options)
        options = [option for option in options if option]
        # 静态和假期选项不支持 ERP 远程搜索，只在已授权结果上本地过滤。
        if keyword and source_type in {"", "static", "holiday_rule"}:
            marker = keyword.lower().strip()
            options = [option for option in options if marker in str(option.get("label") or "").lower()]
            total = len(options)
        return {
            "template_id": str(template_id),
            "field_key": str(field_key),
            "source": source or {"type": "static", "lazy": False, "searchable": False},
            "options": options,
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": bool(total is not None and page * page_size < total),
        }

    def get_related_list(
        self,
        relate_type: str,
        *,
        user: dict[str, Any],
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int | None]:
        """分页读取 ERP 关联业务对象候选项。"""
        # relate_type 来自模板字段配置，调用方不能借此指定任意接口路径。
        payload = self._post(
            self.settings.erp_related_list_path,
            {
                "relate_type": relate_type,
                "page": page,
                "pageSize": page_size,
                "keyword": keyword,
                "status": 0,
                "created_at": "",
                "hasNoAccess": False,
                "type": "",
            },
            user,
        )
        _require_success(payload, "关联字段选项")
        # 兼容 ERP 将分页数组放在 data/list/items 任一字段的响应形态。
        data = payload.get("data")
        if isinstance(data, dict):
            items = data.get("data") or data.get("list") or data.get("items") or []
            total_value = data.get("total") or data.get("count")
            total = int(total_value) if str(total_value or "").isdigit() else None
        else:
            items, total = data or [], None
        return [item for item in items if isinstance(item, dict)], total

    def get_holiday_rules(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        """读取当前用户可选择的假期类型与余额规则。"""
        payload = self._post(self.settings.erp_holiday_rule_path, {}, user)
        _require_success(payload, "假期类型")
        data = payload.get("data")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def get_user_list(
        self,
        user: dict[str, Any],
        *,
        keyword: str = "",
        page_size: int = 2000,
    ) -> list[dict[str, Any]]:
        """读取审批字段或节点可选择的公司人员。"""
        payload = self._post(
            self.settings.erp_user_list_path,
            {"keyword": keyword, "pageSize": page_size},
            user,
        )
        _require_success(payload, "可选人员")
        data = payload.get("data")
        if isinstance(data, dict):
            data = data.get("data") or data.get("list") or data.get("items") or []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def _enrich_unrestricted_node_candidates(
        self,
        nodes: list[dict[str, Any]],
        user: dict[str, Any],
    ) -> None:
        normalized = normalize_approval_nodes(nodes)
        needs_users = any(
            node.get("requires_selection") and not node.get("candidates")
            for node in normalized
        )
        if not needs_users:
            return
        users = self.get_user_list(user)
        for node in nodes:
            handle = _node_handle(node.get("handle"))
            if str(handle.get("type") or "") == "submitter_choice" and not _node_candidate_items(handle):
                handle["relate_user"] = users

    def submit_approval(self, preview: dict[str, Any], *, user: dict[str, Any]) -> dict[str, Any]:
        """根据独立写入模式阻止、模拟或真实提交已确认审批。"""
        # 写入模式独立于读取模式；disabled/mock 分支绝不调用 ERP add 接口。
        if self.write_mode == "disabled":
            return {
                "status": "演示模式：已阻止写入 ERP，仅生成预览",
                "template_code": preview.get("template_code"),
                "idempotency_key": preview.get("idempotency_key"),
                "erp_mode": user.get("erp_mode") or self.read_mode,
                "erp_write_mode": "disabled",
            }
        if self.write_mode == "mock":
            return {
                "approval_id": f"DEMO-{uuid4().hex[:12]}",
                "status": "演示模式：未写入 ERP",
                "template_code": preview.get("template_code"),
                "idempotency_key": preview.get("idempotency_key"),
                "erp_mode": "mock",
                "erp_write_mode": "mock",
            }
        template_id = str(preview.get("template_id") or preview.get("template_code") or "")
        if not template_id.isdigit():
            raise RuntimeError("ERP 提交需要远程 approval_set_id，当前模板没有返回数字 ID。")
        # 表单先转成 getNodes 所需 field_key/value 数组，节点优先使用已确认预览。
        submission_fields = preview.get("submission_fields") or preview.get("fields") or {}
        form_value = [
            {"field_key": str(key), "value": _structured_value(value)}
            for key, value in submission_fields.items()
        ]
        nodes = preview.get("submit_nodes") or preview.get("nodes") or []
        if not nodes:
            # 旧预览没有节点时重新读取，但仍使用同一组提交字段。
            node_payload = self._post(
                self.settings.erp_get_nodes_path,
                {"approval_set_id": int(template_id), "form_value": form_value},
                user,
            )
            _require_success(node_payload, "审批节点")
            nodes = node_payload.get("data") if isinstance(node_payload.get("data"), list) else []
        idempotency_key = str(preview.get("idempotency_key") or uuid4().hex)
        # 请假模板在真实写入前补齐 ERP 计算出的时长与规则快照。
        form_data = self._remote_submission_form_data(submission_fields, user)
        payload = self._post(
            self.settings.erp_add_approval_path,
            {
                "approval_set_id": int(template_id),
                "node_list": nodes,
                "form_data": form_data,
            },
            user,
            extra_headers={"Idempotency-Key": idempotency_key},
        )
        _require_success(payload, "创建审批")
        data = payload.get("data")
        approval_id = ""
        if isinstance(data, dict):
            approval_id = str(data.get("id") or data.get("approval_id") or data.get("approvalId") or "")
        logger.info(
            "ERP approval submitted",
            extra={
                "approval_id": approval_id,
                "template_id": template_id,
                "idempotency_key": idempotency_key,
                "user_id": user.get("user_id"),
                "company_id": user.get("company_id"),
            },
        )
        return {
            "approval_id": approval_id,
            "data": data,
            "message": payload.get("message"),
            "erp_mode": "remote",
            "erp_write_mode": "remote",
            "nodes": nodes,
            "idempotency_key": idempotency_key,
        }

    def _remote_submission_form_data(
        self,
        fields: dict[str, Any],
        user: dict[str, Any],
    ) -> dict[str, Any]:
        """在真实写入前补充 ERP 计算出的请假控制字段。"""
        form_data = _remote_form_data(fields)
        holiday_rule_id = _structured_value(form_data.get("rest_holiday_rule_id"))
        start_date = _structured_value(form_data.get("rest_start_time"))
        end_date = _structured_value(form_data.get("rest_end_time"))
        if holiday_rule_id is None or not start_date or not end_date:
            # 非请假模板或关键字段未齐全时不调用假期计算接口。
            return form_data
        # 假期规则必须重新从 ERP 获取，不能信任页面回传的余额和规则详情。
        selected_rule = next(
            (
                item
                for item in self.get_holiday_rules(user)
                if str(item.get("id")) == str(holiday_rule_id)
            ),
            None,
        )
        if not selected_rule:
            raise RuntimeError("ERP 未找到所选假期规则，不能提交请假审批。")
        start_text, end_text = _normalize_leave_time_fields(
            form_data,
            selected_rule,
            str(start_date),
            str(end_date),
        )
        duration_payload = self._post(
            self.settings.erp_calculate_holiday_duration_path,
            {
                "attendance_holiday_config_id": int(holiday_rule_id),
                "start_date": start_text,
                "end_date": end_text,
            },
            user,
        )
        _require_success(duration_payload, "请假时长计算")
        # 保存 ERP 计算快照，审批记录可以追溯提交时使用的规则和日期明细。
        duration_data = duration_payload.get("data") if isinstance(duration_payload.get("data"), dict) else {}
        rest_rule_json = deepcopy(selected_rule)
        rest_rule_json["holiday_day_list"] = duration_data.get("holiday_day_list") or []
        rest_rule_json["web_show_day_list"] = duration_data.get("web_show_day_list") or []
        form_data["rest_rule_json"] = rest_rule_json
        if duration_data.get("all_duration") is not None:
            duration = duration_data["all_duration"]
            form_data["rest_duration"] = {"label": str(duration), "value": duration}
        form_data.setdefault("rest_prove", [])
        return form_data


def _first_approval(data: Any) -> dict[str, Any] | None:
    """展开 ERP approval/list 返回的分组审批数据。"""
    if isinstance(data, dict):
        for key in ("approvals", "list", "data", "items"):
            found = _first_approval(data.get(key))
            if found:
                return found
        return data if data.get("id") or data.get("approval_set_id") else None
    if isinstance(data, list):
        for item in data:
            found = _first_approval(item)
            if found:
                return found
    return None


def _require_success(payload: dict[str, Any], label: str) -> None:
    code = payload.get("code")
    if code not in (None, 200):
        raise RuntimeError(f"ERP {label}接口返回错误：{code} {payload.get('message') or ''}".strip())


def _scalar(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value") or value.get("id") or value.get("name")
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _department_value(value: Any) -> Any:
    """从 ERP 部门字符串或对象中提取用于 ACL 匹配的可读名称。"""
    if isinstance(value, dict):
        # 部门 ACL 写入的是名称；对象存在 id/name 时不能优先取内部 ID。
        return value.get("name") or value.get("label") or value.get("value") or value.get("id")
    if isinstance(value, (list, tuple)):
        return _department_value(value[0]) if value else None
    return value


def _list_values(value: Any) -> list[dict[str, Any]]:
    """从 ERP 不同版本的分页包装中提取对象列表。

    已观测到的返回形态包括 ``data.data``、``data.list``、``items``、
    ``rows``、``records`` 和消息专用的 ``list_data``；递归处理一层以上
    的包装可避免把接口版本差异泄漏到工作台响应。
    """
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("list", "data", "items", "rows", "records", "list_data", "results"):
        nested = value.get(key)
        if isinstance(nested, (dict, list)):
            found = _list_values(nested)
            if found:
                return found
    return []


def _approval_items(data: Any, parent: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """展开 /api/approval/list 返回的分组审批数据。"""
    if isinstance(data, dict):
        context = dict(parent or {})
        child_keys = ("approvals", "list", "data", "items", "groups", "children", "_child")
        has_children = any(isinstance(data.get(key), (dict, list)) for key in child_keys)
        if has_children:
            # 分组节点的类别信息向下传递，叶子模板缺字段时仍可用于相关度匹配。
            group_name = str(
                data.get("group_name")
                or data.get("category")
                or data.get("group_title")
                or data.get("name")
                or ""
            ).strip()
            if group_name:
                context["group_name"] = group_name
                context["category"] = str(data.get("category") or group_name).strip()
            template_type = str(
                data.get("template_type")
                or data.get("business_type")
                or data.get("approval_type")
                or ""
            ).strip()
            if template_type:
                context["template_type"] = template_type
        if not has_children and (data.get("id") or data.get("approval_set_id") or data.get("template_id")):
            # 只收集带真实模板 ID 的叶子节点，纯分组不会进入候选列表。
            item = dict(data)
            for key, value in context.items():
                if value and not item.get(key):
                    item[key] = value
            return [item]
        items: list[dict[str, Any]] = []
        for key in child_keys:
            items.extend(_approval_items(data.get(key), context))
        return items
    if isinstance(data, list):
        items: list[dict[str, Any]] = []
        for item in data:
            items.extend(_approval_items(item, parent))
        return items
    return []


def _normalize_template_summary(item: dict[str, Any], company_id: str) -> dict[str, Any]:
    template_id = str(item.get("id") or item.get("approval_set_id") or item.get("template_id") or "").strip()
    title = str(item.get("name") or item.get("title") or item.get("approval_name") or template_id).strip()
    group_name = str(item.get("group_name") or item.get("category") or "").strip()
    return {
        "template_id": template_id,
        "title": title,
        "description": str(item.get("description") or item.get("remark") or "").strip(),
        "category": str(item.get("category") or group_name).strip(),
        "group_name": group_name,
        "template_type": str(
            item.get("template_type")
            or item.get("business_type")
            or item.get("approval_type")
            or item.get("type")
            or ""
        ).strip(),
        "company_id": company_id,
    }


def _approval_search_keywords(keyword: str) -> list[str]:
    result: list[str] = []
    for approval_type in _approval_types(keyword):
        result.append(approval_type)
        result.extend(
            alias
            for alias in _APPROVAL_TYPE_ALIASES[approval_type]
            if alias in keyword
        )
    if not result:
        result.extend(_query_business_terms(keyword))
    return list(dict.fromkeys(result))


def _approval_types(text: str) -> list[str]:
    """将“病假”等字段级词汇映射到审批业务类型。"""
    normalized = _compact_text(text)
    return [
        approval_type
        for approval_type, aliases in _APPROVAL_TYPE_ALIASES.items()
        if any(_compact_text(alias) in normalized for alias in aliases)
    ]


def _filter_relevant_templates(query: str, templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只保留与请求确定相关的模板。

    ERP 仍是模板 ID 和动态字段的唯一来源；本函数只防止 ERP 列表接口在传入
    keyword 时仍返回完整目录。
    """
    if not templates:
        return []
    if not query.strip() or _is_vague_approval_query(query):
        return _deduplicate_templates(templates)

    scored = [
        (_template_match_score(query, template), index, template)
        for index, template in enumerate(templates)
    ]
    relevant = [item for item in scored if item[0] > 0]
    relevant.sort(key=lambda item: (-item[0], item[1]))
    return _deduplicate_templates([item[2] for item in relevant])


def _template_match_score(query: str, template: dict[str, Any]) -> int:
    """按业务类型、标题、描述和结构字段确定性计算模板相关度。"""
    approval_types = _approval_types(query)
    title = _compact_text(template.get("title"))
    description = _compact_text(template.get("description"))
    structural_values = [
        _compact_text(template.get("template_type")),
        _compact_text(template.get("category")),
        _compact_text(template.get("group_name")),
    ]
    if approval_types:
        # 已识别标准业务类型时按标题、结构类别、描述的顺序给出递减权重。
        score = 0
        for approval_type in approval_types:
            aliases = _APPROVAL_TYPE_ALIASES[approval_type]
            canonical = _compact_text(approval_type)
            if canonical and canonical in title:
                score = max(score, 120)
            elif any(_compact_text(alias) in title for alias in aliases):
                score = max(score, 110)
            if any(
                marker and marker in value
                for value in structural_values
                for marker in (canonical, *(_compact_text(alias) for alias in aliases))
            ):
                score = max(score, 100)
            if any(_compact_text(alias) in description for alias in aliases):
                score = max(score, 40)
        return score

    # 无标准业务类型时先去掉“申请/审批”等泛词，再匹配剩余业务词。
    terms = _query_business_terms(query)
    score = 0
    for term in terms:
        normalized_term = _compact_text(term)
        if not normalized_term:
            continue
        if normalized_term in title or title in normalized_term:
            score = max(score, 100)
        elif any(
            value and (normalized_term in value or value in normalized_term)
            for value in structural_values
        ):
            score = max(score, 80)
        elif normalized_term in description:
            score = max(score, 30)
    return score


def _query_business_terms(query: str) -> list[str]:
    cleaned = _compact_text(query)
    for word in _GENERIC_APPROVAL_WORDS:
        cleaned = cleaned.replace(_compact_text(word), "")
    return [cleaned] if len(cleaned) >= 2 else []


def _is_vague_approval_query(query: str) -> bool:
    return not _approval_types(query) and not _query_business_terms(query)


def _deduplicate_templates(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for template in templates:
        identity = str(template.get("template_id") or "").strip()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        result.append(template)
    return result


def _compact_text(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def _normalize_fields(data: Any) -> list[dict[str, Any]]:
    """为现有调用方提供向后兼容的紧凑字段投影。"""
    result: list[dict[str, Any]] = []
    for field in normalize_erp_fields(data):
        if not field.get("required"):
            continue
        result.append(
            {
                "name": field["name"],
                "label": field["label"],
                "required": True,
                "type": field["type"],
                "erp_field_type": field["erp_field_type"],
                "options": field.get("options", []),
                "option_values": [
                    {"label": option.get("label"), "value": option.get("value")}
                    for option in field.get("option_values", [])
                ],
                "input_type": field.get("input_type") or "",
            }
        )
    return result


def _remote_form_data(fields: dict[str, Any]) -> dict[str, Any]:
    """构造主助手调用 approval/add 时使用的字段值封装。"""
    result: dict[str, Any] = {}
    for key, value in fields.items():
        result[str(key)] = value if isinstance(value, (dict, list)) else {"value": value}
    return result


def _structured_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _holiday_rule_option(item: dict[str, Any]) -> dict[str, Any] | None:
    rule_id = item.get("id")
    name = str(item.get("name") or item.get("title") or item.get("label") or "").strip()
    if rule_id is None or not name:
        return None
    unit = "小时" if item.get("time_unit") == "hour" else "天"
    if int(item.get("balance_rule") or 0) == 1:
        label = f"{name}（余{item.get('balance') or 0}{unit}）"
    else:
        rule = item.get("json_rule") if isinstance(item.get("json_rule"), dict) else {}
        if int(rule.get("is_continuous_holidays") or 0) == 1:
            label = f"{name}（{rule.get('continuous_holidays_day') or 0}{unit}）"
        else:
            label = name
    return {
        "label": label,
        "value": rule_id,
        "disabled": False,
        "meta": {"time_unit": item.get("time_unit")},
    }


def _related_item_option(item: dict[str, Any]) -> dict[str, Any] | None:
    label = ""
    for key in ("order_num", "name", "title", "num", "no", "id"):
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("text") or value.get("value") or value.get("name")
        if str(value or "").strip():
            label = str(value).strip()
            break
    if not label:
        return None
    value = item.get("id") or item.get("value") or label
    return {"label": label, "value": value, "disabled": False, "meta": {}}


def _user_option(item: dict[str, Any]) -> dict[str, Any] | None:
    uid = item.get("uid") or item.get("id")
    name = str(item.get("display_name") or item.get("name") or "").strip()
    if uid is None or not name:
        return None
    return {
        "label": name,
        "value": uid,
        "disabled": False,
        "meta": {"avatar": item.get("avatar")},
    }


def _node_handle(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        handles = [item for item in value if isinstance(item, dict)]
        return next(
            (item for item in handles if str(item.get("type") or "") == "submitter_choice"),
            handles[0] if handles else {},
        )
    return {}


def _node_candidate_items(handle: dict[str, Any]) -> list[Any]:
    items = handle.get("relate_id") if int(handle.get("is_all_company") or 0) == 2 else handle.get("relate_user")
    return items if isinstance(items, list) else []


def _normalize_leave_time_fields(
    form_data: dict[str, Any],
    holiday_rule: dict[str, Any],
    start_date: str,
    end_date: str,
) -> tuple[str, str]:
    """将按天假期转换为 ERP 需要的日期边界和次日结束时间。"""
    if str(holiday_rule.get("time_unit") or "") != "day":
        return start_date, end_date
    # ERP 按天结束边界使用开区间，用户选择的结束日需转换为次日 real_date。
    start_day = start_date[:10]
    end_day = end_date[:10]
    next_end_day = (
        datetime.strptime(end_day, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")
    form_data["rest_start_time"] = {
        "label": start_day,
        "value": start_day,
        "text": start_day,
        "time_unit": "05:00",
        "real_date": start_day,
    }
    form_data["rest_end_time"] = {
        "label": end_day,
        "value": end_day,
        "text": end_day,
        "time_unit": "05:00",
        "real_date": next_end_day,
    }
    # 计算接口仍使用用户可见的起止日，只有提交字段 real_date 使用次日边界。
    return start_day, end_day


def _string_list(value: Any) -> list[str]:
    """兼容字符串、布尔字典和对象列表形式的权限字段。"""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, dict):
        return [str(key) for key, enabled in value.items() if enabled]
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                normalized = item.get("code") or item.get("name") or item.get("permission") or item.get("value")
                if normalized:
                    result.append(str(normalized))
            elif item is not None:
                result.append(str(item))
        return result
    return []


erp_client = ErpClient()
