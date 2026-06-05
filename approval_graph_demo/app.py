from __future__ import annotations

import streamlit as st

from approval_graph_demo.graph import create_approval_graph
from approval_graph_demo.state import initial_state


@st.cache_resource
def get_graph():
    return create_approval_graph()


def run_app() -> None:
    st.set_page_config(page_title="审批流程 LangGraph Demo", page_icon="✅", layout="centered")
    st.title("审批流程 LangGraph Demo")
    st.caption("LangGraph + Streamlit + DeepSeek。提交前必须由用户确认。")

    graph = get_graph()
    state = st.session_state.setdefault("approval_state", initial_state())
    messages = st.session_state.setdefault("messages", [])

    with st.sidebar:
        st.subheader("支持的审批")
        st.write("- 请假：类型、开始时间、结束时间、原因")
        st.write("- 报销：类型、金额、事由、发票")
        st.write("- 采购：物品、数量、预算、用途")
        if st.button("重置流程"):
            st.session_state.approval_state = initial_state()
            st.session_state.messages = []
            st.rerun()

    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("例如：我想申请病假，2026-06-01 到 2026-06-03，因为发烧")
    if not prompt:
        return

    messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    next_state = graph.invoke({**state, "user_message": prompt})
    st.session_state.approval_state = next_state
    answer = next_state["assistant_message"]
    messages.append({"role": "assistant", "content": answer})

    with st.chat_message("assistant"):
        st.markdown(answer)


if __name__ == "__main__":
    run_app()

