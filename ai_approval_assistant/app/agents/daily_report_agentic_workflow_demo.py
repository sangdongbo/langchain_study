from __future__ import annotations

"""日报 agentic workflow 演示节点。

这个文件只负责“节点具体做什么”，不负责“节点怎么连”。
节点之间的执行顺序、条件边和终止位置在
`app.graph.daily_report_agentic_workflow_demo` 里声明。

演示重点：
- agentic 节点：理解用户输入、产出结构化计划、生成日报正文。
- workflow gate 节点：确认日期、加载上下文、保存草稿、展示预览、拦截提交。

也就是说，agent 可以“判断”和“生成”，但真正能不能继续、能不能写入、
能不能提交，都由 workflow 的确定性节点和条件边控制。
"""

from copy import deepcopy

from app.agents.daily_report_create_agent import get_current_daily_report_date
from app.graph.extractors import is_confirm_message
from app.graph.state import ApprovalState
from app.tools import daily_report_tools


def daily_report_agentic_workflow_demo_node(state: ApprovalState) -> ApprovalState:
    """主图入口节点：把一个主图 node 展开成内部 agentic workflow 子图。

    从顶层 workflow 看，`daily_report_agentic_workflow_demo` 是一个普通节点。
    但这个节点内部会执行一整套子图：
    agent 先规划，workflow 再确认日期和加载上下文，agent 再生成正文，
    workflow 最后保存草稿、展示预览并卡住提交。
    """
    from app.graph.daily_report_agentic_workflow_demo import (
        create_daily_report_agentic_workflow_demo,
    )

    return create_daily_report_agentic_workflow_demo().invoke(state)


def demo_agent_plan_node(state: ApprovalState) -> ApprovalState:
    """Agentic 节点 1：理解用户输入，并产出结构化计划。

    这个节点体现 agentic 的“理解/规划”能力：
    - 判断用户是否已经确认提交。
    - 抽取日期表达，例如“今天/今日/2026-06-29”。
    - 抽取日报内容线索，例如“接口联调、修复日报保存 bug”。
    - 输出 `next_action`，表达 agent 建议 workflow 下一步做什么。

    注意：`next_action` 只是 agent 的建议。真正的图路由看 `_route`，
    并且由 graph 里的条件边决定是否能进入保存、预览或提交节点。
    """
    trace = [*state.get("trace", []), "demo_agent_plan"]
    events = [*state.get("daily_report_agentic_demo_events", []), "agent:plan"]
    message = state.get("user_message", "").strip()
    status = state.get("status")

    # 终态保护：如果已经提交过，agent 只能给出 end 建议，不能再次提交。
    if status == "daily_report_submitted":
        plan = {
            "intent": "already_submitted",
            "date_expression": state.get("daily_report_date"),
            "content_hints": [],
            "next_action": "end",
            "reason": "workflow state is already submitted",
        }
        return _with_agent_plan(state, trace, events, plan, "end")

    # 用户已经看过预览并明确确认时，agent 识别出“确认提交”意图。
    # 但它不直接提交，只把 route 交给 submit gate。
    if status == "awaiting_daily_report_confirmation" and is_confirm_message(message):
        plan = {
            "intent": "confirm_submit",
            "date_expression": state.get("daily_report_date"),
            "content_hints": [],
            "next_action": "submit",
            "reason": "user explicitly confirmed the preview",
        }
        return _with_agent_plan(state, trace, events, plan, "submit")

    # 首轮写日报：从自然语言里提取日期和工作内容线索。
    # 例如“演示 agentic workflow 日报：今天完成接口联调，修复日报保存 bug”
    # 会抽取出 date_expression="今天"，content_hints=["今天完成接口联调", "修复日报保存 bug"]。
    content_hints = _extract_content_hints(message)
    date_expression = _extract_date_expression(message)
    next_action = "need_date" if date_expression in {"", "今天", "今日"} else "ready_to_load"
    plan = {
        "intent": "create_daily_report",
        "date_expression": date_expression or "今天",
        "content_hints": content_hints,
        "next_action": "ready_to_save" if content_hints else next_action,
        "reason": (
            "agent extracted report content and workflow must still confirm date"
            if content_hints
            else "agent needs workflow to collect or confirm more information"
        ),
    }
    # 即使 agent 已经抽到了内容，也先走 confirm_date。
    # 这体现 workflow 边界：日期确认必须发生在加载日报上下文之前。
    return _with_agent_plan(state, trace, events, plan, "confirm_date")


def demo_confirm_date_node(state: ApprovalState) -> ApprovalState:
    """Workflow gate 1：确认日报日期。

    这个节点不是 agentic 节点，而是确定性流程闸门。
    它把 agent 提取出的日期表达变成后续接口可用的明确日期。

    真实流程里：
    - 用户说“今天/今日”时，应调用后端权威日期工具。
    - 用户给出明确 ISO 日期时，才可以直接使用。

    演示版复用 `get_current_daily_report_date` 工具来体现这个边界。
    """
    trace = [*state.get("trace", []), "demo_confirm_date"]
    events = [*state.get("daily_report_agentic_demo_events", []), "workflow:confirm_date"]
    plan = state.get("daily_report_agentic_plan") or {}
    date_expression = str(plan.get("date_expression") or "").strip()
    # 明确日期直接使用；相对日期或空值统一走日期工具。
    report_date = (
        date_expression
        if _looks_like_iso_date(date_expression)
        else _current_daily_report_date()
    )
    return {
        **state,
        "intent": "daily_report",
        "daily_report_mode": "agentic_workflow_demo",
        "daily_report_date": report_date,
        "trace": trace,
        "daily_report_agentic_demo_events": events,
        "_route": "load_context",
    }


def demo_load_context_node(state: ApprovalState) -> ApprovalState:
    """Workflow gate 2：加载日报上下文。

    这里模拟 ERP 页面初始化时要加载的内容：
    - 字段配置。
    - 日报配置。
    - 当天草稿。
    - 同步数据。
    - 默认 payload。

    这个 demo 故意不复用旧日报节点，方便单独展示 agentic workflow 的结构。
    """
    trace = [*state.get("trace", []), "demo_load_context"]
    events = [*state.get("daily_report_agentic_demo_events", []), "workflow:load_context"]
    # 这里直接调用已有日报工具，模拟真实 ERP 接口加载流程。
    # 这一步的目标不是“自己拼一个 payload”，而是让 workflow 真正依赖
    # 日报服务返回的默认 payload，这样更贴近生产路径。
    loaded_context = daily_report_tools.load_daily_report_context.invoke(
        {
            "user_id": state.get("user_id", ""),
            "uid": state.get("uid"),
            "authorization": state.get("authorization"),
            "report_type": 1,
            "report_date": state.get("daily_report_date") or _current_daily_report_date(),
        }
    )
    payload = deepcopy(loaded_context.get("default_payload") or {})
    # 演示版依然要强调：agent 只能在 payload 骨架上写 content，
    # 其他 ERP 字段必须保留。
    if not isinstance(payload.get("extends"), dict):
        payload["extends"] = {}
    if not isinstance(payload.get("extend_fields"), list):
        payload["extend_fields"] = []
    if not isinstance(payload.get("recipients"), list):
        payload["recipients"] = []
    if not isinstance(payload.get("cc_recipients"), list):
        payload["cc_recipients"] = []
    if not isinstance(payload.get("files"), list):
        payload["files"] = []
    if not isinstance(payload.get("at_uids"), list):
        payload["at_uids"] = []
    # context 是给后续 agent 生成节点看的上下文。
    # 在真实系统里这里会放接口返回的草稿、配置和同步数据。
    context = {
        "source": "agentic_workflow_demo",
        "loaded_endpoints": [
            "load_daily_report_context",
        ],
        "sync_data": list(loaded_context.get("sync_data") or []),
    }
    return {
        **state,
        "daily_report_payload": payload,
        "daily_report_agentic_context": context,
        "trace": trace,
        "daily_report_agentic_demo_events": events,
        "_route": "compose",
    }


def demo_agent_compose_node(state: ApprovalState) -> ApprovalState:
    """Agentic 节点 2：根据计划和上下文生成日报正文。

    这个节点体现 agentic 的“生成/整理”能力：
    - 读取 `daily_report_agentic_plan` 里的用户内容线索。
    - 读取 `daily_report_agentic_context` 里的同步数据。
    - 在完整 ERP payload 骨架上只更新 `content`。

    这样可以展示：agent 负责写内容，但 workflow 仍然负责保存、预览和提交边界。
    """
    trace = [*state.get("trace", []), "demo_agent_compose"]
    events = [*state.get("daily_report_agentic_demo_events", []), "agent:compose"]
    # 避免直接修改上游 state 中的 payload 引用。
    payload = deepcopy(state.get("daily_report_payload") or {})
    plan = state.get("daily_report_agentic_plan") or {}
    context = state.get("daily_report_agentic_context") or {}
    # 优先使用用户原话中抽取出的内容线索；
    # 如果用户没给具体内容，就不要擅自拿同步数据替你写，
    # 而是停下来请用户补充工作内容。
    hints = [str(item) for item in plan.get("content_hints") or [] if str(item).strip()]
    content = _compose_content(hints)
    payload["content"] = content
    # agent 的结构化生成结果，便于 Studio/测试观察 agentic 过程：
    # 它生成了什么、用了哪些上下文、建议下一步是什么、保留了哪些字段。
    compose_result = {
        "role": "content_agent",
        "used_context": bool(context.get("sync_data")),
        "content": content,
        "preserved_fields": [
            "extends",
            "extend_fields",
            "recipients",
            "cc_recipients",
            "files",
            "at_uids",
        ],
        "next_action": "save_draft" if content else "ask_content",
        "reason": (
            "agent generated report content; workflow owns the save and preview gates"
            if content
            else "agent needs the user to provide report content instead of inventing it"
        ),
    }
    # 有内容才允许进入 save gate；没有内容就停下，先让用户补内容。
    if not content:
        ask_message = "请补充工作内容后再继续，我不会替你自动编日报。"
        return {
            **state,
            "status": "collecting",
            "awaiting_field": "daily_report_content",
            "daily_report_payload": payload,
            "daily_report_agentic_compose": compose_result,
            "assistant_message": ask_message,
            "trace": trace,
            "daily_report_agentic_demo_events": events,
            "_route": "end",
        }
    return {
        **state,
        "daily_report_payload": payload,
        "daily_report_agentic_compose": compose_result,
        "trace": trace,
        "daily_report_agentic_demo_events": events,
        "_route": "save" if content else "end",
    }


def demo_save_draft_node(state: ApprovalState) -> ApprovalState:
    """Workflow gate 3：保存草稿。

    这个节点演示“写入动作由 workflow 执行，而不是 agent 自由调用”。
    agent 只能建议 `next_action=save_draft`，真正的保存动作必须进入这个 gate。

    演示版不调用真实接口，只写入 `daily_report_agentic_draft_saved=True`。
    """
    trace = [*state.get("trace", []), "demo_save_draft"]
    events = [*state.get("daily_report_agentic_demo_events", []), "workflow:save_draft"]
    return {
        **state,
        "daily_report_agentic_draft_saved": True,
        "trace": trace,
        "daily_report_agentic_demo_events": events,
        "_route": "preview",
    }


def demo_preview_gate_node(state: ApprovalState) -> ApprovalState:
    """Workflow gate 4：生成预览，并停下来等待用户确认。

    这是提交前的人类确认闸门：
    - 生成 `daily_report_preview`。
    - 返回可读的 `assistant_message`。
    - 设置 `status=awaiting_daily_report_confirmation`。
    - 设置 `ui_action`，告诉前端这里需要用户点确认/修改/取消。

    进入这个节点后必须停止，不能自动提交。
    """
    trace = [*state.get("trace", []), "demo_preview_gate"]
    events = [*state.get("daily_report_agentic_demo_events", []), "workflow:preview_gate"]
    payload = deepcopy(state.get("daily_report_payload") or {})
    # preview 从 payload 中提取展示字段，避免重新生成导致字段丢失。
    preview = {
        "report_type": payload.get("type"),
        "date": payload.get("date"),
        "content": payload.get("content"),
        "fields": [
            {
                "name": "field_demo_mood",
                "label": "今日状态",
                "value": payload.get("extends", {})
                .get("field_demo_mood", {})
                .get("value", ""),
            }
        ],
        "recipients": payload.get("recipients", []),
        "cc_recipients": payload.get("cc_recipients", []),
    }
    message = _preview_message(payload, state)
    return {
        **state,
        "status": "awaiting_daily_report_confirmation",
        "awaiting_field": None,
        "daily_report_preview": preview,
        "assistant_message": message,
        # ui_action 模拟前端确认弹窗。这里让用户动作成为提交前的硬闸门。
        "ui_action": {
            "type": "interrupt",
            "field_key": "daily_report_agentic_demo_confirmation",
            "label": "确认提交",
            "input_type": "action",
            "required": True,
            "value": None,
            "message": message,
            "actions": ["confirm", "modify", "cancel"],
        },
        "trace": trace,
        "daily_report_agentic_demo_events": events,
        "_route": "end",
    }


def demo_submit_gate_node(state: ApprovalState) -> ApprovalState:
    """Workflow gate 5：提交闸门。

    这是最关键的安全边界。只有同时满足两个条件才允许提交：
    1. 当前状态已经是 `awaiting_daily_report_confirmation`。
    2. 用户本轮消息是明确确认，例如“确认提交”。

    如果没有经过预览，或者用户没有明确确认，即使 agent 建议 submit，
    workflow 也会拦住。
    """
    trace = [*state.get("trace", []), "demo_submit_gate"]
    events = [*state.get("daily_report_agentic_demo_events", []), "workflow:submit_gate"]
    if state.get("status") != "awaiting_daily_report_confirmation" or not is_confirm_message(
        state.get("user_message", "")
    ):
        return {
            **state,
            "assistant_message": "agentic workflow demo：还没有通过预览确认 gate，不能提交。",
            "trace": trace,
            "daily_report_agentic_demo_events": events,
            "_route": "end",
        }
    return {
        **state,
        "status": "daily_report_submitted",
        "daily_report_request_id": "DEMO-AGENTIC-1001",
        "assistant_message": "agentic workflow demo 已提交。\n\n- 日报编号：DEMO-AGENTIC-1001\n- 当前状态：submitted",
        "ui_action": None,
        "trace": trace,
        "daily_report_agentic_demo_events": events,
        "_route": "end",
    }


def _with_agent_plan(
    state: ApprovalState,
    trace: list[str],
    events: list[str],
    plan: dict,
    route: str,
) -> ApprovalState:
    """保存 agent 的结构化计划，并把下一跳写入 `_route`。

    LangGraph 条件边读取 `_route`，不是直接读取 plan 里的 `next_action`。
    这里相当于把 agent 输出翻译成 workflow 可执行的路由。
    """
    return {
        **state,
        "intent": "daily_report",
        "daily_report_mode": "agentic_workflow_demo",
        "daily_report_agentic_plan": plan,
        "trace": trace,
        "daily_report_agentic_demo_events": events,
        "_route": route,
    }


def _current_daily_report_date() -> str:
    """通过现有日期工具获取当前日报日期。

    这里故意包一层函数，便于测试 monkeypatch，也让 demo 更清楚地表达：
    “今天/今日/未指定日期”不是直接用本地常量，而是走日报日期工具确认。
    """
    result = get_current_daily_report_date.invoke({})
    return str(result.get("date") or "")


def _extract_date_expression(message: str) -> str:
    """从用户原话中提取日期表达。

    演示版只识别：
    - 明确 ISO 日期：2026-06-29
    - 今日
    - 今天

    真实版本可以替换成 LLM 或工具调用，支持“昨天、上周五”等复杂表达。
    """
    for token in message.replace("：", " ").replace(":", " ").split():
        if _looks_like_iso_date(token):
            return token
    if "今日" in message:
        return "今日"
    if "今天" in message:
        return "今天"
    return ""


def _extract_content_hints(message: str) -> list[str]:
    """从用户原话中抽取日报内容线索。

    例如：
    “演示 agentic workflow 日报：今天完成接口联调，修复日报保存 bug”

    会得到：
    ["今天完成接口联调", "修复日报保存 bug"]

    这一步模拟 agent 对自然语言的理解能力。
    """
    text = message.strip()
    for separator in ("：", ":"):
        if separator in text:
            text = text.split(separator, 1)[1]
            break
    for marker in ("演示", "agentic workflow", "agentic", "日报", "写日志", "写日报"):
        text = text.replace(marker, "")
    return [
        item.strip(" ，,。；;")
        for item in text.replace("，", ",").replace("、", ",").split(",")
        if item.strip(" ，,。；;")
    ]


def _compose_content(hints: list[str]) -> str:
    """把 agent 提取出的内容线索整理成日报正文。

    这里用规则拼接，保证演示和测试稳定。
    真实版本可以替换成 LLM，让日报表达更自然。
    """
    if not hints:
        return ""
    lines = ["今日工作内容："]
    for index, hint in enumerate(hints, start=1):
        lines.append(f"{index}. {hint}")
    return "\n".join(lines)


def _preview_message(payload: dict, state: ApprovalState) -> str:
    """构造给用户看的预览文案。

    文案里故意展示两个 agentic 输出：
    - agent 计划 next_action。
    - agent 生成 next_action。

    这样在接口返回或 Studio 里可以直观看到：
    agent 做了判断和生成，但提交仍然被 workflow gate 卡住。
    """
    plan = state.get("daily_report_agentic_plan") or {}
    compose = state.get("daily_report_agentic_compose") or {}
    return "\n".join(
        [
            "agentic workflow 演示：已由 agent 生成日报内容，并由 workflow 保存草稿后进入预览 gate。",
            "",
            f"- 日志时间：{payload.get('date')}",
            f"- 工作内容：{payload.get('content')}",
            f"- 自定义字段保留：{list((payload.get('extends') or {}).keys())}",
            f"- agent 计划 next_action：{plan.get('next_action')}",
            f"- agent 生成 next_action：{compose.get('next_action')}",
            "",
            "回复“确认提交”才会进入提交 gate；否则不会调用提交动作。",
        ]
    )


def _looks_like_iso_date(value: str) -> bool:
    """判断字符串是否像 YYYY-MM-DD。

    这里只做轻量格式判断，不做真实日历合法性校验。
    演示重点是 agentic workflow 结构，不是日期解析完整性。
    """
    parts = value.split("-")
    return (
        len(parts) == 3
        and len(parts[0]) == 4
        and len(parts[1]) == 2
        and len(parts[2]) == 2
        and all(part.isdigit() for part in parts)
    )
