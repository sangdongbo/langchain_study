from __future__ import annotations

from html import escape
from textwrap import dedent

import streamlit as st

from common.chat_store import ChatMessage, ConversationStore
from crm_ask_langsmith.config import DEFAULT_PERSONA, DEFAULT_TITLE


def inject_styles() -> None:
    """注入页面样式，让 Streamlit 默认组件接近深色聊天界面。

    Streamlit 默认 DOM 层级较深，这里集中覆盖侧边栏、聊天区和底部表单，
    避免样式分散在页面流程代码里。
    """

    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"], .stApp {
            height: 100%;
        }
        .stApp {
            background: #0b0f16;
            color: #f7f7fb;
        }
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        #MainMenu,
        footer {
            display: none;
        }
        [data-testid="stAppViewContainer"] {
            background: #0b0f16;
        }
        [data-testid="stAppScrollToBottomContainer"] {
            background: #0b0f16;
            overflow-y: auto !important;
        }
        [data-testid="stSidebar"] {
            background: #252532;
            border-right: 1px solid rgba(255, 255, 255, 0.06);
        }
        [data-testid="stSidebar"] * {
            color: #f4f4f8;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
            background: #11131c !important;
            border: 1px solid rgba(255, 255, 255, 0.18) !important;
            color: #f7f7fb !important;
            caret-color: #f7f7fb !important;
            border-radius: 8px !important;
            -webkit-text-fill-color: #f7f7fb !important;
        }
        [data-testid="stSidebar"] [data-testid="stTextAreaRootElement"],
        [data-testid="stSidebar"] [data-testid="stTextInputRootElement"],
        [data-testid="stSidebar"] [data-testid="stTextAreaRootElement"] > div,
        [data-testid="stSidebar"] [data-testid="stTextInputRootElement"] > div {
            background: #11131c !important;
        }
        [data-testid="stSidebar"] input::placeholder,
        [data-testid="stSidebar"] textarea::placeholder {
            color: #8f95a6 !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p {
            color: #f4f4f8 !important;
        }
        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: #333143;
            color: #fff;
        }
        [data-testid="stMainBlockContainer"],
        .stMainBlockContainer.block-container {
            max-width: none;
            width: 100%;
            padding: 0 !important;
            margin: 0 !important;
        }
        .chat-shell {
            min-height: auto;
            overflow: visible;
            border-radius: 0;
            background: #0e1118;
            border: 0;
            padding: 28px clamp(28px, 5vw, 88px) 18px;
            box-shadow: none;
        }
        .stream-shell {
            padding-top: 0;
        }
        .chat-inner {
            max-width: 1060px;
            margin: 0 auto;
        }
        .chat-title {
            font-size: 32px;
            font-weight: 800;
            margin: 12px 0 4px;
            letter-spacing: 0;
        }
        .chat-subtitle {
            color: #a7adba;
            font-size: 13px;
            margin-bottom: 18px;
        }
        .message-row {
            display: flex;
            gap: 12px;
            align-items: flex-start;
            margin: 12px 0;
        }
        .avatar {
            width: 28px;
            height: 28px;
            border-radius: 8px;
            display: grid;
            place-items: center;
            flex: 0 0 28px;
            font-size: 15px;
        }
        .avatar-user {
            background: linear-gradient(135deg, #ff3d34, #ff7a45);
        }
        .avatar-ai {
            background: linear-gradient(135deg, #f59f31, #ffce73);
        }
        .bubble {
            width: min(100%, 920px);
            border-radius: 4px;
            padding: 12px 16px;
            line-height: 1.65;
            color: #f5f7fb;
        }
        .bubble-user {
            background: #181a25;
        }
        .bubble-ai {
            background: transparent;
        }
        .empty-state {
            border: 1px dashed rgba(255, 255, 255, 0.16);
            border-radius: 8px;
            color: #a7adba;
            padding: 20px;
            margin: 28px 0;
        }
        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 999px;
            padding: 6px 12px;
            color: #a7adba;
            font-size: 12px;
        }
        [data-testid="stBottom"] {
            background: #0b0f16;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            min-height: 92px;
            max-height: 112px;
        }
        [data-testid="stBottom"] *,
        [data-testid="stBottomBlockContainer"],
        [data-testid="stBottomBlockContainer"] > div {
            background-color: #0b0f16 !important;
        }
        [data-testid="stChatInput"] {
            max-width: 1060px;
            margin: 0 auto;
        }
        [data-testid="stChatInput"] textarea {
            background: #1a1e27 !important;
            color: #f7f7fb !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            -webkit-text-fill-color: #f7f7fb !important;
        }
        [data-testid="stChatInput"] textarea::placeholder {
            color: #9aa0ad !important;
            opacity: 1 !important;
        }
        [data-testid="stForm"] {
            max-width: 1060px;
            margin: 0 auto !important;
            padding: 12px 0 18px !important;
            border: 0 !important;
            background: #0b0f16 !important;
        }
        [data-testid="stForm"] input {
            background: #1a1e27 !important;
            color: #f7f7fb !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 6px !important;
            min-height: 44px;
            -webkit-text-fill-color: #f7f7fb !important;
        }
        [data-testid="stForm"] input::placeholder {
            color: #9aa0ad !important;
            opacity: 1 !important;
        }
        [data-testid="stForm"] .stButton > button {
            min-height: 44px;
            border-radius: 6px;
            background: #242936;
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #f7f7fb;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def message_html(message: ChatMessage) -> str:
    """把一条聊天消息渲染成 HTML 气泡。"""

    is_user = message.role == "user"
    avatar_class = "avatar-user" if is_user else "avatar-ai"
    bubble_class = "bubble-user" if is_user else "bubble-ai"
    icon = "😊" if is_user else "🤖"
    content = escape(
        message.content.replace("AI智能伴侣", "AI智能助手").replace("智能伴侣", "智能助手")
    ).replace("\n", "<br>")
    return dedent(
        f"""
        <div class="message-row">
            <div class="avatar {avatar_class}">{icon}</div>
            <div class="bubble {bubble_class}">{content}</div>
        </div>
        """
    ).strip()


def chat_shell_html(conversation) -> str:
    """渲染完整聊天历史区域。

    标题、会话时间和消息列表一次性拼成一个 HTML 块，减少 Streamlit
    自动闭合标签导致的布局跳动。
    """

    if conversation.messages:
        messages = "\n".join(message_html(message) for message in conversation.messages)
    else:
        messages = (
            '<div class="empty-state">'
            "还没有聊天记录。输入一句话，开始测试缓存和 DeepSeek 回复。"
            "</div>"
        )
    return dedent(
        f"""
    <section class="chat-shell">
        <div class="chat-inner">
            <div class="status-pill">Deploy · DeepSeek · LangChain · LangSmith</div>
            <div class="chat-title">AI智能助手</div>
            <div class="chat-subtitle">会话名称：{escape(conversation.created_at)}</div>
            {messages}
        </div>
    </section>
    """
    ).strip()


def stream_shell_html(message: ChatMessage) -> str:
    """渲染流式输出中的临时助手消息。"""

    return dedent(
        f"""
        <section class="chat-shell stream-shell">
            <div class="chat-inner">
                {message_html(message)}
            </div>
        </section>
        """
    ).strip()


def sidebar(store: ConversationStore, selected_id: str) -> tuple[str, str, str]:
    """渲染左侧控制面板，并返回当前会话和助手配置。"""

    st.session_state.setdefault("selected_conversation", selected_id)

    with st.sidebar:
        st.caption("AI控制面板")
        if st.button("🖊️ 新建会话"):
            conversation = store.create_conversation(DEFAULT_TITLE, DEFAULT_PERSONA)
            st.session_state.selected_conversation = conversation.id
            st.rerun()

        st.markdown("#### 会话历史")
        for conversation in store.list_conversations():
            col_a, col_b = st.columns([0.78, 0.22])
            label = conversation.created_at.replace(" ", "_").replace(":", "-")
            with col_a:
                if st.button(f"📄 {label}", key=f"select-{conversation.id}"):
                    st.session_state.selected_conversation = conversation.id
                    st.rerun()
            with col_b:
                if st.button("✕", key=f"delete-{conversation.id}"):
                    store.delete_conversation(conversation.id)
                    remaining = store.list_conversations()
                    # 删除当前会话后必须立刻选择一个有效会话，
                    # 否则下一轮页面渲染会拿着旧 ID 读取到 None。
                    if remaining:
                        st.session_state.selected_conversation = remaining[0].id
                    else:
                        conversation = store.create_conversation(DEFAULT_TITLE, DEFAULT_PERSONA)
                        st.session_state.selected_conversation = conversation.id
                    st.rerun()

        conversation = store.get_conversation(st.session_state.selected_conversation)
        if conversation is None:
            conversation = store.create_conversation(DEFAULT_TITLE, DEFAULT_PERSONA)
            st.session_state.selected_conversation = conversation.id

        st.markdown("#### 助手设置")
        title = st.text_input(
            "昵称",
            value=conversation.title,
            key=f"title-{st.session_state.selected_conversation}",
        )
        persona = st.text_area(
            "性格",
            value=conversation.persona,
            height=110,
            key=f"persona-{st.session_state.selected_conversation}",
        )
        if st.button("保存设置"):
            store.update_profile(st.session_state.selected_conversation, title, persona)
            st.success("已保存到本地缓存")
            st.rerun()

    return st.session_state.selected_conversation, title, persona
