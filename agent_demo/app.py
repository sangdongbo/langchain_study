from __future__ import annotations

"""综合智能体学习项目的 Streamlit 页面。

这个文件只负责“页面交互”和“结果展示”，尽量不放复杂业务逻辑。
真正的智能体路由在 `react_agent.py`，RAG 检索和总结在 `rag/` 目录，
向量库写入在 `VectorStoreService`，这样学习时可以按模块逐层展开。
"""

import sys
from html import escape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Streamlit 直接运行 `agent_demo/app.py` 时，Python 的导入根目录可能不是项目根目录。
# 这里把仓库根目录加入 sys.path，保证 `from agent_demo...` 在命令行启动时也能正常导入。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_demo.rag.rag_service import RagSummarizeService
from agent_demo.rag.vector_store import VectorStoreService, documents_from_uploads
from agent_demo.react_agent import ReactAgent
from agent_demo.utils.file_handler import decode_uploaded_bytes
from agent_demo.utils.logger_handler import LogStore, make_log
from agent_demo.utils.path_tools import chroma_dir, logs_dir


# Streamlit 页面全局配置必须尽量靠前执行。
# page_icon 用普通 ASCII 文本，避免不同环境对 emoji 渲染不一致。
st.set_page_config(page_title="综合智能体学习项目", page_icon="AI", layout="wide")

# 复用项目根目录 `.env`。override=True 方便本地学习调试时刷新环境变量。
load_dotenv(override=True)


def inject_styles() -> None:
    """注入页面样式。

    Streamlit 的内置组件没有稳定的业务 class，所以这里使用 data-testid 覆盖样式。
    重点处理 file uploader：它内部有 dropzone、按钮、说明文字、图标等多层 DOM，
    只改侧边栏全局颜色不够，容易出现白底浅字的问题。
    """

    st.markdown(
        """
        <style>
        .stApp { background: #101116; color: #f7f7fb; }
        [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer { display: none; }
        [data-testid="stSidebar"] { background: #20222c; border-right: 1px solid rgba(255,255,255,.08); }
        [data-testid="stSidebar"] * { color: #f4f4f8; }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] { margin-top: 4px; }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] label p {
            color: #f7f7fb !important;
            font-weight: 700;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
            min-height: 118px;
            padding: 14px !important;
            border-radius: 8px !important;
            border: 1px dashed rgba(255, 255, 255, 0.22) !important;
            background: #151824 !important;
            color: #f7f7fb !important;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            gap: 12px;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"]:hover {
            border-color: rgba(255, 84, 92, 0.82) !important;
            background: #181b28 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
            min-height: 40px;
            border-radius: 8px !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            background: #303446 !important;
            color: #f7f7fb !important;
            box-shadow: none !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button * {
            color: #f7f7fb !important;
            fill: #f7f7fb !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] * {
            color: #aeb7c8 !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] > div,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-baseweb],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [class*="uploadedFile"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [class*="UploadedFile"] {
            background: transparent !important;
            color: #f7f7fb !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] p,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] span,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small {
            color: #f7f7fb !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] svg,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] {
            color: #dce3f2 !important;
            fill: #dce3f2 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section + div,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section + div > div,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [class*="uploadedFile"],
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [class*="UploadedFile"] {
            background: #151824 !important;
            border-color: rgba(255, 255, 255, 0.16) !important;
            color: #f7f7fb !important;
            border-radius: 8px !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section + div p,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section + div span,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section + div small,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] * {
            color: #f7f7fb !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section + div svg,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] svg {
            color: #dce3f2 !important;
            fill: #dce3f2 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button[aria-label*="Delete"],
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button[aria-label*="delete"],
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button[aria-label*="Remove"],
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button[aria-label*="remove"],
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stBaseButton-icon"] {
            background: #303446 !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            color: #f7f7fb !important;
            border-radius: 8px !important;
        }
        .block-container { max-width: 1180px; padding-top: 42px; }
        .agent-title { font-size: 34px; font-weight: 800; margin-bottom: 6px; }
        .agent-subtitle { color: #aeb7c8; margin-bottom: 20px; }
        .tag-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 22px; }
        .tag { border: 1px solid rgba(255,255,255,.12); border-radius: 999px; padding: 6px 10px; color: #cbd5e1; font-size: 13px; }
        .answer-box, .source-box, .log-box {
            background: #171a22; border: 1px solid rgba(255,255,255,.08); border-radius: 8px;
            padding: 14px 16px; line-height: 1.7;
        }
        .source-box { margin: 8px 0; background: #12151d; }
        .log-box { font-family: Consolas, monospace; color: #b7c0d4; font-size: 13px; }
        textarea, input { background: #171a22 !important; color: #f7f7fb !important; }
        .stButton > button {
            border-radius: 8px; border: 1px solid rgba(255,255,255,.12);
            background: #343746; color: #fff; min-height: 40px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_logs() -> LogStore:
    """从 Streamlit session_state 里获取本轮会话日志。

    Streamlit 每次按钮点击都会从头重跑脚本，因此不能用普通局部变量保存日志。
    session_state 可以跨 rerun 保留对象，适合保存“本次浏览器会话”的运行过程。
    """

    if "agent_demo_logs" not in st.session_state:
        st.session_state.agent_demo_logs = LogStore()
    return st.session_state.agent_demo_logs


def render_logs(logs: LogStore) -> None:
    """把日志渲染成侧边栏里的等宽文本面板。"""

    lines = logs.render_lines()
    if not lines:
        st.markdown('<div class="log-box">暂无日志。</div>', unsafe_allow_html=True)
        return

    # escape 防止日志内容里出现 <、> 等字符时破坏页面 HTML 结构。
    # 这里只展示最近 18 条，避免长时间演示后侧边栏被日志撑得过长。
    st.markdown(
        '<div class="log-box">' + "<br>".join(escape(line) for line in lines[-18:]) + "</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    """页面主流程。

    页面分成两部分：
    - 侧边栏：上传文档、写入知识库、设置检索数量、查看日志。
    - 主区域：输入问题、运行智能体、展示回答和检索片段。
    """

    inject_styles()
    logs = get_logs()

    # 这些字段保存最近一次 Agent 执行结果。
    # 如果用户只是移动 slider 或点击其他按钮，Streamlit 会 rerun，
    # 但上一次回答仍然能保留在页面上。
    st.session_state.setdefault("agent_demo_answer", "")
    st.session_state.setdefault("agent_demo_sources", [])
    st.session_state.setdefault("agent_demo_route", "")

    with st.sidebar:
        st.caption("智能体控制台")
        uploaded_files = st.file_uploader(
            "上传 txt / markdown 文档",
            type=["txt", "md", "markdown"],
            accept_multiple_files=True,
        )
        retrieval_k = st.slider("检索片段数量", min_value=1, max_value=8, value=4)
        st.caption(f"向量库路径：{chroma_dir()}")
        st.caption(f"日志路径：{logs_dir()}")

        if st.button("写入知识库", use_container_width=True):
            if not uploaded_files:
                st.warning("请先上传至少一个文档。")
            else:
                try:
                    # Streamlit 上传对象是二进制文件；先解码成 UploadedText，
                    # 再转成 LangChain Document，最后交给 VectorStoreService 入库。
                    uploads = [decode_uploaded_bytes(file.name, file.getvalue()) for file in uploaded_files]
                    documents = documents_from_uploads(uploads)
                    result = VectorStoreService().load_documents(documents)
                    logs.add(make_log("入库", result.summary()))
                    st.success(result.summary())
                except Exception as exc:
                    logs.add(make_log("错误", str(exc)))
                    st.error(str(exc))

        if st.button("清空日志", use_container_width=True):
            # 清空后立刻 rerun，让侧边栏日志面板马上回到“暂无日志”。
            logs.clear()
            st.rerun()

        st.markdown("#### 运行日志")
        render_logs(logs)

    st.markdown('<div class="agent-title">综合智能体学习项目</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="agent-subtitle">演示 Agent 编排、工具调用、RAG 检索、Prompt 切换、中间件日志和 Streamlit 页面如何协同工作。</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="tag-row"><span class="tag">Agent</span><span class="tag">Tools</span><span class="tag">RAG</span><span class="tag">ChromaDB</span><span class="tag">Middleware Logs</span></div>',
        unsafe_allow_html=True,
    )

    question = st.text_area(
        "输入问题",
        placeholder="例如：总结一下智能体项目；帮我查一下北京天气；智能体项目由哪些模块组成？",
        height=96,
    )

    if st.button("运行智能体"):
        if not question.strip():
            st.warning("请输入问题。")
        else:
            try:
                # 页面层只组装依赖，不直接判断意图。
                # ReactAgent 会根据问题内容决定调用工具、总结链路还是普通 RAG 问答。
                rag_service = RagSummarizeService(vector_store=VectorStoreService())
                agent = ReactAgent(rag_service=rag_service, logs=logs, retrieval_k=retrieval_k)
                response = agent.execute(question)

                # 把结果写回 session_state，保证 rerun 后回答仍然可见。
                st.session_state.agent_demo_answer = response.answer
                st.session_state.agent_demo_sources = response.sources
                st.session_state.agent_demo_route = response.route
            except Exception as exc:
                logs.add(make_log("错误", str(exc)))
                st.error(str(exc))

    if st.session_state.agent_demo_answer:
        st.markdown(f"#### 回答 · `{escape(st.session_state.agent_demo_route)}`")
        st.markdown(
            # 模型输出可能含换行和 HTML 特殊字符：
            # - escape 保护页面结构。
            # - replace 换行，让回答在 HTML div 里保持可读。
            f'<div class="answer-box">{escape(st.session_state.agent_demo_answer).replace(chr(10), "<br>")}</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.agent_demo_sources:
        st.markdown("#### 检索片段")
        for index, source in enumerate(st.session_state.agent_demo_sources, start=1):
            # 检索片段用于学习观察：用户可以看到回答引用了哪些本地资料。
            st.markdown(
                f'<div class="source-box"><strong>[{index}] {escape(source["source"])}</strong><br>{escape(source["content"]).replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
