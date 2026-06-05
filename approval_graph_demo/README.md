# Approval Graph Demo

This demo shows how to use LangGraph, Streamlit, and DeepSeek for multi-type approval flows.

The important behavior is that the graph never submits an approval immediately after collecting fields. It first builds a preview and waits for explicit user confirmation.

## Run

```powershell
uv run streamlit run approval_graph_demo/app.py
```

## Supported Flows

- Leave request: leave type, start date, end date, reason
- Expense request: expense type, amount, reason, invoice
- Purchase request: item, quantity, budget, purpose

## Example

User:

```text
我想申请病假，2026-06-01 到 2026-06-03，因为发烧需要休息
```

Assistant previews the request and waits for:

```text
确认提交
```

Only then does the graph call the submit tool and return a request id.
