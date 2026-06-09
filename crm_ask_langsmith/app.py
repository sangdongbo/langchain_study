from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


# Streamlit 会把脚本所在目录放到导入路径前面。
# 这里显式加入项目根目录，保证本地包在 `streamlit run streamlit_v2/app.py`
# 和从 `streamlit_v2` 目录启动两种方式下都能被导入。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crm_ask_langsmith.config import configure_langsmith, load_project_env
from crm_ask_langsmith.page import run_app


st.set_page_config(page_title="AI智能助手", page_icon="🤖", layout="wide")
load_project_env()
configure_langsmith()


if __name__ == "__main__":
    run_app()
