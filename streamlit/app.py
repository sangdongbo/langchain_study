from __future__ import annotations

import sys
from html import escape
from pathlib import Path
from textwrap import dedent

import streamlit as st
from dotenv import load_dotenv

# 这个文件是通过 `streamlit run streamlit/app.py` 启动的。
# Streamlit 会把脚本所在目录 `streamlit/` 放到导入路径前面，
# 这样直接导入项目根目录下的 `ai_companion` 包时可能找不到。
# 所以这里手动把项目根目录加入 `sys.path`，保证本地模块能稳定导入。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_companion.chat_store import ChatMessage, ConversationStore
from ai_companion.llm import stream_deepseek


APP_DIR = Path(__file__).resolve().parent
CACHE_PATH = APP_DIR / ".cache" / "conversations.json"
DEFAULT_TITLE = "小黑"
DEFAULT_PERSONA = "性格火辣的四川姑娘，回答直接、亲切，偶尔带一点俏皮。"


st.set_page_config(page_title="AI智能助手", page_icon="🤖", layout="wide")
load_dotenv(override=True)


def inject_styles() -> None:
    """注入页面样式，让 Streamlit 默认组件接近截图里的深色聊天界面。

    Streamlit 组件会生成大量内部 DOM 结构，很多样式只能通过
    `data-testid` 或自定义 class 覆盖。这里集中处理：
    - 隐藏顶部默认工具栏和页脚，减少页面空白。
    - 修正侧边栏输入框的深色背景和文字颜色。
    - 统一聊天消息、头像、气泡、输入框的尺寸和布局。
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


@st.cache_resource
def get_store() -> ConversationStore:
    """创建并缓存本地会话存储。

    对话记录保存在 `streamlit/.cache/conversations.json`。
    使用 `st.cache_resource` 可以避免每次页面刷新都重复构造存储对象；
    真正的数据仍然会从 JSON 文件读写，所以刷新页面后历史不会丢。
    """
    return ConversationStore(CACHE_PATH)


def ensure_conversation(store: ConversationStore) -> str:
    """确保至少存在一个会话，并返回当前默认会话 ID。

    第一次打开页面时缓存文件可能为空，此时自动创建一个默认助手会话；
    后续打开页面时直接使用已有会话列表里的第一个会话。
    """
    conversations = store.list_conversations()
    if not conversations:
        conversation = store.create_conversation(DEFAULT_TITLE, DEFAULT_PERSONA)
        return conversation.id
    return conversations[0].id


def message_html(message: ChatMessage) -> str:
    """把一条聊天消息渲染成 HTML 气泡。

    用户消息和助手消息共用同一套 DOM 结构，只切换头像颜色和气泡样式。
    内容会先做 HTML 转义，避免用户输入的特殊字符破坏页面结构。
    这里也顺手把历史里的旧文案“智能伴侣”显示成“智能助手”。
    """
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

    这里故意把标题、会话时间和所有消息拼成一个完整 HTML 块一次性输出。
    如果拆成多次 `st.markdown()`，Streamlit 可能会自动闭合 HTML 标签，
    导致出现大面积空白、消息跳位或流式输出样式错乱。
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
            <div class="status-pill">Deploy · DeepSeek · LangChain</div>
            <div class="chat-title">AI智能助手</div>
            <div class="chat-subtitle">会话名称：{escape(conversation.created_at)}</div>
            {messages}
        </div>
    </section>
    """
    ).strip()


def stream_shell_html(message: ChatMessage) -> str:
    """渲染流式输出中的临时助手消息。

    流式回复过程中，内容会不断增长。如果临时消息不使用和最终消息相同
    的 `chat-shell > chat-inner > message-row` 结构，就会出现左边距、宽度
    和最终缓存消息不一致的问题。
    """
    return dedent(
        f"""
        <section class="chat-shell stream-shell">
            <div class="chat-inner">
                {message_html(message)}
            </div>
        </section>
        """
    ).strip()


def sidebar(store: ConversationStore) -> tuple[str, str, str]:
    """渲染左侧控制面板，并返回当前正在编辑的助手配置。

    返回值包含：
    - 当前选中的会话 ID
    - 昵称输入框里的当前值
    - 性格输入框里的当前值

    注意：用户改完昵称后不一定会点击“保存设置”，所以主流程发送消息时
    会再次使用这里返回的当前输入值，并自动同步到缓存。
    """
    # 第 1 步：从 Streamlit 会话状态中取出当前选中的会话 ID。
    # 如果用户是第一次打开页面，`selected_conversation` 还不存在，
    # 就通过 `ensure_conversation()` 创建或获取一个默认会话。
    selected_id = st.session_state.setdefault("selected_conversation", ensure_conversation(store))

    with st.sidebar:
        # 第 2 步：渲染左侧控制面板标题和“新建会话”按钮。
        st.caption("AI控制面板")
        if st.button("🖊️ 新建会话"):
            # 点击新建时，先创建一个默认昵称/默认人设的空会话。
            conversation = store.create_conversation(DEFAULT_TITLE, DEFAULT_PERSONA)
            # 把新会话设置为当前选中会话，然后刷新页面。
            st.session_state.selected_conversation = conversation.id
            st.rerun()

        # 第 3 步：渲染历史会话列表。
        # 每一行左侧是“切换到这个会话”，右侧是“删除这个会话”。
        st.markdown("#### 会话历史")
        for conversation in store.list_conversations():
            col_a, col_b = st.columns([0.78, 0.22])
            label = conversation.created_at.replace(" ", "_").replace(":", "-")
            with col_a:
                if st.button(f"📄 {label}", key=f"select-{conversation.id}"):
                    # 点击历史会话后，只切换当前会话 ID，不修改会话内容。
                    st.session_state.selected_conversation = conversation.id
                    st.rerun()
            with col_b:
                if st.button("✕", key=f"delete-{conversation.id}"):
                    # 删除会话后，需要重新选择一个仍然存在的会话。
                    # 如果没有剩余会话，`ensure_conversation()` 会自动创建默认会话。
                    store.delete_conversation(conversation.id)
                    st.session_state.selected_conversation = ensure_conversation(store)
                    st.rerun()

        # 第 4 步：根据当前选中的会话 ID 读取完整会话对象。
        # 理论上这里应该能读到；如果用户刚删除了会话或者缓存异常，
        # 就兜底创建/选择一个可用会话，避免页面报错。
        conversation = store.get_conversation(st.session_state.selected_conversation)
        if conversation is None:
            st.session_state.selected_conversation = ensure_conversation(store)
            conversation = store.get_conversation(st.session_state.selected_conversation)

        # 第 5 步：渲染助手配置表单。
        # `key` 里带上会话 ID，是为了不同会话之间切换时，
        # Streamlit 不会把上一个会话的输入框状态误用到当前会话。
        st.markdown("#### 助手设置")
        title = st.text_input(
            "昵称",
            value=conversation.title if conversation else DEFAULT_TITLE,
            key=f"title-{st.session_state.selected_conversation}",
        )
        persona = st.text_area(
            "性格",
            value=conversation.persona if conversation else DEFAULT_PERSONA,
            height=110,
            key=f"persona-{st.session_state.selected_conversation}",
        )
        if st.button("保存设置"):
            # “保存设置”是手动保存入口。
            # 即使用户不点这个按钮，发送消息时 main() 也会自动保存一次。
            store.update_profile(st.session_state.selected_conversation, title, persona)
            st.success("已保存到本地缓存")
            st.rerun()

    return selected_id, title, persona


def main() -> None:
    # 第 1 步：注入页面 CSS。
    # Streamlit 默认样式比较偏白色工具面板，这里先统一成深色聊天界面。
    inject_styles()

    # 第 2 步：获取本地 JSON 会话存储。
    # 所有会话、昵称、人设、消息都会读写到 `streamlit/.cache/conversations.json`。
    store = get_store()

    # 第 3 步：渲染左侧控制面板，并拿到当前会话和当前输入框里的助手配置。
    # 注意这里拿到的是“输入框当前值”，不一定已经被用户点击保存。
    selected_id, current_title, current_persona = sidebar(store)

    # 第 4 步：读取当前选中的会话对象。
    # 如果缓存里找不到这个会话，说明状态和文件不同步了，就自动兜底创建/选择会话。
    conversation = store.get_conversation(selected_id)
    if conversation is None:
        selected_id = ensure_conversation(store)
        conversation = store.get_conversation(selected_id)

    # 第 5 步：检查是否有“等待流式回复”的会话。
    # 用户提交问题后，代码会先写入用户消息，然后设置这个标记并 rerun。
    # 下一轮页面运行时看到这个标记，就开始调用 DeepSeek 做流式输出。
    pending_stream_id = st.session_state.get("pending_stream_conversation")

    # 第 6 步：重新读取一次会话并渲染聊天历史。
    # 这里重新读取是为了确保刚刚写入缓存的用户消息能显示出来。
    conversation = store.get_conversation(selected_id)
    st.markdown(chat_shell_html(conversation), unsafe_allow_html=True)

    # 第 7 步：如果当前会话正在等待回复，就在聊天历史末尾开始流式输出。
    # 表单提交后不会立即在当前位置流式输出，而是先写入用户消息并触发一次 rerun。
    # 这样下一轮渲染时，用户消息已经在聊天历史里，助手的临时流式气泡就能
    # 出现在“聊天历史末尾、输入框上方”。如果不这样做，流式气泡会先出现在
    # 输入框下面，等写入缓存后又跳回上面，视觉上会很突兀。
    if pending_stream_id == selected_id:
        # 用于累计 DeepSeek 每次返回的 chunk，最后写入缓存。
        answer = ""
        # 创建一个占位区域。流式输出时会不断刷新这个占位区域的 HTML。
        answer_placeholder = st.empty()
        try:
            for chunk in stream_deepseek(conversation.title, conversation.persona, conversation.messages):
                # 每收到一个片段，就追加到完整答案里。
                answer += chunk
                # 输出过程中在末尾加一个光标符号，让用户知道还在生成。
                answer_placeholder.markdown(
                    stream_shell_html(ChatMessage(role="assistant", content=f"{answer}▌")),
                    unsafe_allow_html=True,
                )
            # 模型输出结束后，去掉光标符号，显示最终版本。
            answer_placeholder.markdown(
                stream_shell_html(ChatMessage(role="assistant", content=answer)),
                unsafe_allow_html=True,
            )
        except RuntimeError as exc:
            # 如果 API Key 缺失、网络超时或 DeepSeek 返回错误，
            # 这里把错误信息作为本轮 assistant 回复保存，方便页面上看到原因。
            answer = f"{exc}"
            answer_placeholder.error(answer)
        # 把完整回复写入本地缓存，这样刷新页面后仍然能看到。
        store.append_message(selected_id, ChatMessage(role="assistant", content=answer))
        # 清掉“等待流式回复”的标记，避免下一次刷新重复请求模型。
        st.session_state.pop("pending_stream_conversation", None)
        # 再刷新一次，让刚保存的 assistant 回复进入正常聊天历史。
        st.rerun()

    # 第 8 步：渲染底部输入表单。
    # 这里使用普通 `st.form`，而不是 `st.chat_input`，
    # 是为了避免 Streamlit 自动滚动导致消息先在下面、再跳到上面。
    with st.form("chat-form", clear_on_submit=True):
        # 左侧放输入框，右侧放提交按钮。
        input_col, submit_col = st.columns([0.94, 0.06], vertical_alignment="bottom")
        with input_col:
            user_input = st.text_input(
                "问题",
                placeholder="请输入您要问的问题",
                label_visibility="collapsed",
            )
        with submit_col:
            submitted = st.form_submit_button("↑")

    # 第 9 步：处理用户提交。
    # 这里只负责保存用户消息并设置“待回复”标记，不直接请求 DeepSeek。
    # 真正的模型调用会在下一轮 rerun 的第 7 步执行。
    if submitted and user_input.strip():
        # 发送消息前自动保存当前侧边栏配置。
        # 这样用户把昵称从“小黑”改成“小白”后，可以直接提问，
        # DeepSeek 本次调用会立刻使用“小白”，不需要额外点击“保存设置”。
        store.update_profile(selected_id, current_title, current_persona)
        # 先把用户问题写入缓存。下一轮 rerun 时，聊天历史里就能看到这条用户消息。
        store.append_message(selected_id, ChatMessage(role="user", content=user_input.strip()))
        # 标记当前会话需要生成 assistant 回复。
        st.session_state.pending_stream_conversation = selected_id
        # 触发 rerun，进入“先显示用户消息，再流式输出助手回复”的流程。
        st.rerun()


if __name__ == "__main__":
    main()
