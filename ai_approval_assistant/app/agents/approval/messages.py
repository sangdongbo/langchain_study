from __future__ import annotations

from app.graph.state import ApprovalState
from app.schemas.approval import ApprovalTemplate


def approval_type_clarification(templates: list[ApprovalTemplate]) -> str:
    """构建列出可用审批分类的澄清消息。"""
    if not templates:
        return "当前没有可发起的审批模板。"
    common = [template.title for template in templates if template.is_common][:5]
    categories: dict[str, int] = {}
    for template in templates:
        categories[template.category] = categories.get(template.category, 0) + 1
    category_text = "、".join(
        (f"{name}({count})" for name, count in sorted(categories.items()))
    )
    if common:
        common_text = "、".join(common)
        return f"请告诉我要办理哪类审批。常用审批包括：{common_text}。当前分类：{category_text}。"
    return f"请告诉我要办理哪类审批。当前分类：{category_text}。"


def template_choice_message(templates: list[ApprovalTemplate]) -> str:
    """构建多个远程审批模板的选择提示。"""
    lines = ["找到多个审批模板，请回复序号或模板名称确认是哪一个审批："]
    for index, template in enumerate(templates, start=1):
        lines.append(f"{index}. {template.title}")
    return "\n".join(lines)


def crm_error_message(error: str) -> str:
    """将 CRM 接口错误转换为用户可理解的聊天提示。"""
    if "401" in error:
        return "CRM 登录已过期或授权无效，请刷新页面重新登录后再试。"
    return f"获取 CRM 审批模板失败：{error}"


def append_resume_hint(answer: str, state: ApprovalState, waiting_label: str | None) -> str:
    """普通问答后附加当前审批等待项，便于用户继续。"""
    hint = resume_message(state, waiting_label)
    return f"{answer}\n\n{hint}" if answer else hint


def resume_message(state: ApprovalState, waiting_label: str | None) -> str:
    """构建继续当前审批的提示。"""
    if waiting_label:
        return f"继续刚才的审批，当前等待填写：{waiting_label}。"
    if state.get("status") == "awaiting_confirmation":
        return "继续刚才的审批，当前等待你确认是否提交。"
    if state.get("status") == "awaiting_assignee_selection":
        return "继续刚才的审批，当前等待选择办理人/审批人。"
    return "继续刚才的审批，请补充下一项信息。"
