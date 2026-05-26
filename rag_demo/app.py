from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag_demo.rag_chain import (
    DEFAULT_CHROMA_DIR,
    UploadedText,
    add_documents_to_store,
    answer_with_context,
    documents_from_uploads,
    make_log,
    print_log,
    retrieve_documents,
)


"""Streamlit RAG 演示页面。

左侧负责上传文件和写入 ChromaDB，右侧负责输入问题、检索上下文和展示回答。
真正的 RAG 逻辑在 rag_chain.py，这里只负责页面交互。
"""


st.set_page_config(page_title="本地 RAG 搜索助手", page_icon="🔎", layout="wide")
load_dotenv(override=True)


def inject_styles() -> None:
    """注入页面 CSS。

    Streamlit 默认控件偏白色，这里统一覆盖成深色界面。
    这段 CSS 比较长，是因为 Streamlit 内部 DOM 由 data-testid 和自动 class 组成。
    """

    st.markdown(
        """
        <style>
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
        [data-testid="stSidebar"] {
            background: #252532;
            border-right: 1px solid rgba(255, 255, 255, 0.08);
        }
        [data-testid="stSidebar"] * {
            color: #f4f4f8;
        }
        [data-testid="stSidebar"] .stButton > button,
        .stButton > button {
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: #343246;
            color: #fff;
            min-height: 42px;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] {
            margin-top: 4px;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] label p {
            color: #f7f7fb !important;
            font-weight: 700;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
            min-height: 118px;
            padding: 14px !important;
            border-radius: 8px !important;
            border: 1px dashed rgba(255, 255, 255, 0.22) !important;
            background: #11131c !important;
            color: #f7f7fb !important;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            gap: 12px;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"]:hover {
            border-color: rgba(255, 84, 92, 0.82) !important;
            background: #151824 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
            min-height: 40px;
            border-radius: 8px !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            background: #333143 !important;
            color: #f7f7fb !important;
            box-shadow: none !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button * {
            color: #f7f7fb !important;
            fill: #f7f7fb !important;
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
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] li,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [role="listitem"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] section + div > div {
            background: #1a1d28 !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 8px !important;
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
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [aria-label*="delete"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [aria-label*="Delete"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-icon"] {
            background: #303043 !important;
            border-color: rgba(255, 255, 255, 0.14) !important;
            color: #f7f7fb !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [title],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [class*="file"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [class*="File"] {
            color: #f7f7fb !important;
            background-color: #1a1d28 !important;
            border-color: rgba(255, 255, 255, 0.12) !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-icon"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[kind="icon"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="Remove"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="remove"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="Delete"],
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="delete"] {
            width: 28px !important;
            min-width: 28px !important;
            max-width: 28px !important;
            height: 28px !important;
            min-height: 28px !important;
            max-height: 28px !important;
            padding: 0 !important;
            border-radius: 8px !important;
            background: #242735 !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            display: grid !important;
            place-items: center !important;
            flex: 0 0 28px !important;
            box-shadow: none !important;
            position: relative !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-icon"] *,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[kind="icon"] *,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="Remove"] *,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="Delete"] * {
            visibility: hidden !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-icon"]:hover,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[kind="icon"]:hover,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="Remove"]:hover,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="Delete"]:hover {
            background: #3a3140 !important;
            border-color: rgba(255, 84, 92, 0.72) !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-icon"]::before,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[kind="icon"]::before,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="Remove"]::before,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="remove"]::before,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="Delete"]::before,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button[aria-label*="delete"]::before {
            content: "×";
            color: #f7f7fb;
            font-size: 20px;
            font-weight: 500;
            line-height: 1;
            position: absolute;
            inset: 0;
            display: grid;
            place-items: center;
        }
        .block-container {
            max-width: 1220px;
            padding-top: 46px;
        }
        .rag-pill {
            display: inline-flex;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 999px;
            padding: 7px 13px;
            color: #b8c7e0;
            font-size: 13px;
            margin-bottom: 14px;
        }
        .rag-title {
            font-size: 36px;
            font-weight: 800;
            margin-bottom: 4px;
        }
        .rag-subtitle {
            color: #a8afbd;
            font-size: 14px;
            margin-bottom: 24px;
        }
        .answer-box {
            background: #171a24;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 8px;
            padding: 18px 20px;
            line-height: 1.75;
        }
        .source-box {
            background: #11141d;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 14px 16px;
            margin: 10px 0;
            color: #dce3f2;
            line-height: 1.65;
        }
        .log-box {
            background: #10131b;
            border: 1px dashed rgba(255, 255, 255, 0.16);
            border-radius: 8px;
            padding: 12px 14px;
            color: #aeb7c8;
            font-family: Consolas, monospace;
            font-size: 13px;
            line-height: 1.65;
        }
        textarea,
        input {
            background: #171a24 !important;
            color: #f7f7fb !important;
            border-color: rgba(255, 255, 255, 0.14) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def add_log(stage: str, message: str) -> None:
    """同时把日志写入页面状态和终端。"""

    entry = make_log(stage, message)
    st.session_state.logs.append(entry.render())
    print_log(entry)


def decode_uploads(uploaded_files) -> list[UploadedText]:
    """把 Streamlit 上传文件解码成文本。

    优先按 UTF-8 解码；如果失败，尝试中文 Windows 常见的 gb18030。
    """

    decoded: list[UploadedText] = []
    for uploaded_file in uploaded_files:
        raw = uploaded_file.getvalue()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gb18030", errors="ignore")
            add_log("上传", f"{uploaded_file.name} 使用 gb18030 兜底解码")
        decoded.append(UploadedText(name=uploaded_file.name, text=text))
    return decoded


def render_logs() -> None:
    """渲染左侧日志面板。"""

    logs = st.session_state.get("logs", [])
    if not logs:
        st.markdown('<div class="log-box">暂无日志。上传文件或检索后会显示记录。</div>', unsafe_allow_html=True)
        return
    st.markdown(
        '<div class="log-box">' + "<br>".join(escape(log) for log in logs[-12:]) + "</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    """页面主流程。

    Streamlit 每次按钮点击、输入变化都会重新执行这个函数，所以需要用
    st.session_state 保存日志、最近一次回答和检索片段。
    """

    inject_styles()
    # setdefault 表示：如果 key 不存在就初始化；如果已存在就保留旧值。
    st.session_state.setdefault("logs", [])
    st.session_state.setdefault("indexed_chunks", 0)
    st.session_state.setdefault("last_answer", "")
    st.session_state.setdefault("last_sources", [])

    with st.sidebar:
        st.caption("RAG 控制面板")
        # accept_multiple_files=True 允许一次上传多个 txt/markdown 文件。
        uploaded_files = st.file_uploader(
            "上传本地 txt / markdown 文件",
            type=["txt", "md", "markdown"],
            accept_multiple_files=True,
        )
        k = st.slider("检索返回数量", min_value=1, max_value=8, value=4)
        st.caption(f"向量库路径：{DEFAULT_CHROMA_DIR}")

        if st.button("写入 ChromaDB", use_container_width=True):
            if not uploaded_files:
                st.warning("请先上传至少一个文件。")
            else:
                try:
                    # 第 1 步：记录用户本次选择了几个上传文件。
                    # uploaded_files 是 Streamlit 返回的文件对象列表，还不是普通字符串。
                    add_log("上传", f"收到 {len(uploaded_files)} 个文件")

                    # 第 2 步：把上传文件从“二进制内容”解码成“文本内容”。
                    # decode_uploads 会优先用 UTF-8，失败时再尝试 gb18030。
                    uploads = decode_uploads(uploaded_files)

                    # 第 3 步：把普通文本包装成 LangChain Document。
                    # Document = page_content + metadata，metadata 里会保存文件名、后缀、MD5。
                    documents = documents_from_uploads(uploads)
                    add_log("解析", f"有效文档 {len(documents)} 个")

                    # 第 4 步：把每个文件的 MD5 打印出来。
                    # MD5 是文件内容指纹，用来判断“这个文件内容以前是否已经入库过”。
                    for document in documents:
                        source = document.metadata.get("source", "未知文件")
                        digest = document.metadata.get("file_md5", "")
                        add_log("MD5", f"{source} -> {digest}")

                    # 第 5 步：真正写入 ChromaDB。
                    # add_documents_to_store 内部会做三件事：
                    # 1. 把长文档切成多个小 chunk。
                    # 2. 根据 file_md5 跳过重复文件。
                    # 3. 把新增 chunk 转成向量并保存到本地向量库。
                    result = add_documents_to_store(documents)

                    # 第 6 步：把本次新增 chunk 数累计到页面状态里。
                    # st.session_state 可以在 Streamlit 重跑脚本后继续保留数据。
                    st.session_state.indexed_chunks += result.added_chunks

                    # 第 7 步：把入库结果同时显示在日志区和成功提示里。
                    # result.summary() 会说明写入了多少 chunk、跳过了哪些重复文件。
                    add_log("入库", result.summary())
                    st.success(result.summary())
                except Exception as exc:
                    add_log("错误", str(exc))
                    st.error(str(exc))

        if st.button("清空页面日志", use_container_width=True):
            st.session_state.logs = []
            st.rerun()

        st.markdown("#### 运行日志")
        render_logs()

    st.markdown('<div class="rag-pill">ChromaDB · DeepSeek · LangChain LCEL</div>', unsafe_allow_html=True)
    st.markdown('<div class="rag-title">本地 RAG 搜索助手</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="rag-subtitle">左侧上传资料并入库，右侧输入问题后从本地向量库检索上下文，再交给 DeepSeek 回答。</div>',
        unsafe_allow_html=True,
    )

    question = st.text_area(
        "搜索问题",
        placeholder="例如：请问年假有多少天？申请病假需要哪些信息？",
        height=92,
    )
    search_clicked = st.button("检索并生成回答", use_container_width=False)

    if search_clicked:
        if not question.strip():
            st.warning("请输入问题。")
        else:
            try:
                add_log("检索", f"问题：{question.strip()}")
                # 先检索，再把检索结果作为 context 交给模型。
                docs = retrieve_documents(question.strip(), k=k)
                add_log("检索", f"命中 {len(docs)} 个片段")
                if not docs:
                    st.warning("没有检索到相关片段，请先上传并写入资料。")
                else:
                    add_log("模型", "开始调用 DeepSeek")
                    answer = answer_with_context(question.strip(), docs)
                    add_log("模型", "DeepSeek 返回完成")
                    st.session_state.last_answer = answer
                    st.session_state.last_sources = docs
            except Exception as exc:
                add_log("错误", str(exc))
                st.error(str(exc))

    if st.session_state.last_answer:
        # escape 防止模型输出里的 HTML 符号破坏页面结构。
        st.markdown("#### 回答")
        st.markdown(
            f'<div class="answer-box">{escape(st.session_state.last_answer).replace(chr(10), "<br>")}</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.last_sources:
        st.markdown("#### 检索片段")
        for index, doc in enumerate(st.session_state.last_sources, start=1):
            source = escape(doc.metadata.get("source", "未知来源"))
            content = escape(doc.page_content.strip()).replace("\n", "<br>")
            st.markdown(
                f'<div class="source-box"><strong>[{index}] {source}</strong><br>{content}</div>',
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
