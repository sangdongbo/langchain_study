# Notebook Model Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the LangGraph notebook select DashScope first and DeepSeek second in automatic mode.

**Architecture:** The connection-check cell owns provider construction and returns an ordered list of models. The later agent and graph cells reuse that list so provider selection cannot diverge. Fallback occurs through direct ordered invocation, agent middleware, or a runnable fallback as appropriate.

**Tech Stack:** Jupyter notebook JSON, pytest, LangChain, `langchain-openai`, `langchain-deepseek`.

---

### Task 1: Lock Down Automatic Selection

**Files:**
- Create: `tests/test_python_langgraph_notebook_model_selection.py`
- Modify: `docs/python_langgraph_notes.ipynb` (model connection-check cell)

- [ ] **Step 1: Write the failing test**

```python
def test_auto_selects_dashscope_before_deepseek_compatible_openai_env(...):
    models = namespace["build_chat_models"]()
    assert [model.kind for model in models] == ["dashscope", "deepseek"]
```

- [ ] **Step 2: Run the one selected test and verify it fails**

Run: `pytest tests/test_python_langgraph_notebook_model_selection.py -q`

Expected: failure because `build_chat_models` does not yet exist.

- [ ] **Step 3: Implement the ordered model builder**

```python
if provider == "auto":
    return [
        builder(timeout)
        for builder in (_build_dashscope_model, _build_deepseek_model)
        if builder has its corresponding API key
    ]
```

- [ ] **Step 4: Re-run the selected test**

Run: `pytest tests/test_python_langgraph_notebook_model_selection.py -q`

Expected: PASS without network access.

### Task 2: Use the Shared Fallback Sequence

**Files:**
- Modify: `docs/python_langgraph_notes.ipynb` (agent and graph cells)

- [ ] **Step 1: Update the agent cell**

```python
agent = create_agent(
    model=models[0],
    middleware=[ModelFallbackMiddleware(*models)] if len(models) > 1 else [],
    tools=[],
    system_prompt="你是一个简洁可靠的中文助手。",
)
```

- [ ] **Step 2: Update the graph model helper**

```python
return models[0].with_fallbacks(models[1:]) if len(models) > 1 else models[0]
```

- [ ] **Step 3: Validate the finished notebook**

Run: `pytest tests/test_python_langgraph_notebook_model_selection.py -q`

Run: `python -c "import json; json.load(open('docs/python_langgraph_notes.ipynb', encoding='utf-8'))"`

Expected: the test passes and the notebook remains valid JSON.
