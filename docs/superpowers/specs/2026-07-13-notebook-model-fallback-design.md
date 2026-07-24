# Notebook Model Fallback Design

## Goal

Make `docs/python_langgraph_notes.ipynb` use DashScope first and DeepSeek as the automatic fallback without changing `.env`.

## Selection

- `MODEL_PROVIDER=auto`: construct DashScope first when `DASHSCOPE_API_KEY` exists, then DeepSeek when `DEEPSEEK_API_KEY` exists.
- `MODEL_PROVIDER=dashscope`, `deepseek`, and `openai`: use only the explicitly selected provider.
- `OPENAI_*` variables are ignored in `auto` mode. They remain available for explicit `MODEL_PROVIDER=openai` use.

## Runtime Behavior

The connection-check cell invokes the selected models in order and reports when it changes from DashScope to DeepSeek. The agent cell uses LangChain's `ModelFallbackMiddleware`; the graph example uses the same ordered models through LangChain runnable fallbacks.

## Validation

A pytest test reads only the notebook's model-selection cell, substitutes local fake Chat model classes, and verifies that `auto` selects DashScope before a DeepSeek-compatible `OPENAI_BASE_URL`. No API request, key output, or database operation is allowed.
