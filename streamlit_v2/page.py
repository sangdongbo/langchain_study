from __future__ import annotations

import streamlit as st

from ai_companion.chat_store import ChatMessage, ConversationStore
from streamlit_v2.agent.erp_agent import ERPFlowState, handle_erp_message
from streamlit_v2.config import CACHE_PATH, DEFAULT_PERSONA, DEFAULT_TITLE
from streamlit_v2.llm import stream_deepseek
from streamlit_v2.ui import chat_shell_html, inject_styles, sidebar, stream_shell_html


# page.py 负责把 UI、会话存储、ERP agent、LLM 串起来。
# 具体样式在 ui.py，业务工具在 erp_tools.py，避免 app.py 重新变成大杂烩。
@st.cache_resource
def get_store() -> ConversationStore:
    """创建并缓存本地会话存储。

    缓存的是 ConversationStore 对象，不是聊天内容本身；
    聊天内容仍然由 ConversationStore 读写 JSON 文件。
    """

    return ConversationStore(CACHE_PATH)


def ensure_conversation(store: ConversationStore) -> str:
    """确保至少存在一个会话，并返回默认会话 ID。"""

    conversations = store.list_conversations()
    if not conversations:
        conversation = store.create_conversation(DEFAULT_TITLE, DEFAULT_PERSONA)
        return conversation.id
    return conversations[0].id


def run_app() -> None:
    """渲染一轮 Streamlit 页面。

    Streamlit 每次交互都会从头执行脚本，所以这里的顺序很重要：
    先恢复会话和状态，再渲染历史，再处理待输出或新提交。
    """

    inject_styles()

    store = get_store()
    selected_id = st.session_state.setdefault(
        "selected_conversation",
        ensure_conversation(store),
    )
    selected_id, current_title, current_persona = sidebar(store, selected_id)

    # 侧边栏切换或删除会话时，session_state 里的 ID 可能短暂指向旧会话。
    # 这里兜底重新选择一个可用会话，避免后续渲染拿到 None。
    conversation = store.get_conversation(selected_id)
    if conversation is None:
        selected_id = ensure_conversation(store)
        conversation = store.get_conversation(selected_id)

    # 普通 LLM 回复采用“两段式”：
    # 第一次提交只保存用户消息并设置 pending_stream_conversation；
    # 第二次 rerun 时再开始流式输出，这样用户消息会先出现在正确位置。
    pending_stream_id = st.session_state.get("pending_stream_conversation")
    conversation = store.get_conversation(selected_id)
    st.markdown(chat_shell_html(conversation), unsafe_allow_html=True)

    if pending_stream_id == selected_id:
        _stream_llm_reply(store, selected_id, conversation)

    user_input, submitted = _chat_form()
    if submitted and user_input.strip():
        _handle_user_submit(
            store=store,
            selected_id=selected_id,
            current_title=current_title,
            current_persona=current_persona,
            user_input=user_input.strip(),
        )


def _stream_llm_reply(store: ConversationStore, selected_id: str, conversation) -> None:
    """把 LLM 流式回复写到页面和本地会话缓存。"""

    answer = ""
    answer_placeholder = st.empty()
    try:
        for chunk in stream_deepseek(
            conversation.title,
            conversation.persona,
            conversation.messages,
        ):
            answer += chunk
            # 输出中显示光标，让用户知道当前回复仍在生成。
            answer_placeholder.markdown(
                stream_shell_html(ChatMessage(role="assistant", content=f"{answer}▌")),
                unsafe_allow_html=True,
            )
        answer_placeholder.markdown(
            stream_shell_html(ChatMessage(role="assistant", content=answer)),
            unsafe_allow_html=True,
        )
    except RuntimeError as exc:
        # DeepSeek 配置或网络错误也保存成 assistant 消息，方便刷新后看到原因。
        answer = f"{exc}"
        answer_placeholder.error(answer)

    store.append_message(selected_id, ChatMessage(role="assistant", content=answer))
    st.session_state.pop("pending_stream_conversation", None)
    st.rerun()


def _chat_form() -> tuple[str, bool]:
    """渲染底部输入表单，返回输入内容和提交状态。"""

    with st.form("chat-form", clear_on_submit=True):
        input_col, submit_col = st.columns([0.94, 0.06], vertical_alignment="bottom")
        with input_col:
            user_input = st.text_input(
                "问题",
                placeholder="请输入您要问的问题",
                label_visibility="collapsed",
            )
        with submit_col:
            submitted = st.form_submit_button("↑")
    return user_input, submitted


def _handle_user_submit(
    store: ConversationStore,
    selected_id: str,
    current_title: str,
    current_persona: str,
    user_input: str,
) -> None:
    """处理用户提交。

    ERP 流程优先于 LLM：如果 handle_erp_message 能处理这句话，
    就直接写入 ERP 回复；否则再标记本会话进入 LLM 流式回复。
    """

    # 发送消息时顺手保存侧边栏里的当前昵称/人设，
    # 用户不用额外点击“保存设置”也能让本轮 LLM 使用最新配置。
    store.update_profile(selected_id, current_title, current_persona)
    store.append_message(selected_id, ChatMessage(role="user", content=user_input))

    # 每个会话维护一份独立 ERP 流程状态，避免 A 会话的请假表单串到 B 会话。
    erp_state_key = f"erp_flow_state_{selected_id}"
    erp_state = st.session_state.setdefault(erp_state_key, ERPFlowState())
    erp_response, next_erp_state = handle_erp_message(user_input, erp_state)
    st.session_state[erp_state_key] = next_erp_state

    if erp_response.handled:
        store.append_message(
            selected_id,
            ChatMessage(role="assistant", content=erp_response.message),
        )
        
    else:
        st.session_state.pending_stream_conversation = selected_id
    st.rerun()
