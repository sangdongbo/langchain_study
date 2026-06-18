from __future__ import annotations
import os
from pydantic import BaseModel

DEFAULT_CRM_BASE_URL = "http://localhost:8002"
APPROVAL_LIST_PATH = "/api/approval/list"
FORM_FIELDS_PATH = "/api/field/formFields"
GET_NODES_PATH = "/api/approval/getNodes"
ADD_APPROVAL_PATH = "/api/approval/add"
RELATED_LIST_PATH = "/api/Company/getRelatedList"
HOLIDAY_RULE_PATH = "/api/attendance/getHolidayRuleByUser"
USERINFO_PATH = "/api/User/userinfo"
USER_DETAIL_PATH = "/api/person/userDetails"


class CrmEndpointConfig(BaseModel):
    """CRM 审批接口地址配置。"""

    approval_list_url: str
    form_fields_url: str
    get_nodes_url: str
    add_approval_url: str
    related_list_url: str
    holiday_rule_url: str
    userinfo_url: str
    user_detail_url: str


def load_crm_endpoint_config() -> CrmEndpointConfig:
    """从环境变量加载 CRM 地址配置。"""
    base_url = _trim_base_url(os.getenv("AI_APPROVAL_CRM_BASE_URL", DEFAULT_CRM_BASE_URL))
    return CrmEndpointConfig(
        approval_list_url=os.getenv(
            "AI_APPROVAL_LIST_URL", _join_url(base_url, APPROVAL_LIST_PATH)
        ),
        form_fields_url=os.getenv(
            "AI_APPROVAL_FORM_FIELDS_URL", _join_url(base_url, FORM_FIELDS_PATH)
        ),
        get_nodes_url=os.getenv(
            "AI_APPROVAL_GET_NODES_URL", _join_url(base_url, GET_NODES_PATH)
        ),
        add_approval_url=os.getenv(
            "AI_APPROVAL_ADD_URL", _join_url(base_url, ADD_APPROVAL_PATH)
        ),
        related_list_url=os.getenv(
            "AI_APPROVAL_RELATED_LIST_URL", _join_url(base_url, RELATED_LIST_PATH)
        ),
        holiday_rule_url=os.getenv(
            "AI_APPROVAL_HOLIDAY_RULE_URL", _join_url(base_url, HOLIDAY_RULE_PATH)
        ),
        userinfo_url=os.getenv(
            "AI_APPROVAL_USERINFO_URL", _join_url(base_url, USERINFO_PATH)
        ),
        user_detail_url=os.getenv(
            "AI_APPROVAL_USER_DETAIL_URL", _join_url(base_url, USER_DETAIL_PATH)
        ),
    )


def _trim_base_url(base_url: str) -> str:
    """去掉 base URL 末尾斜杠，避免拼接出双斜杠。"""
    return base_url.rstrip("/")


def _join_url(base_url: str, path: str) -> str:
    """拼接 CRM base URL 和接口路径。"""
    return f"{base_url}{path if path.startswith('/') else '/' + path}"
