# AI Approval Assistant Architecture

## Runtime Layers

```text
app/api                 FastAPI routes
app/graph               LangGraph workflow entrypoints and shared state
app/agents              Agent nodes and agent-specific orchestration
app/tools               LangChain tools exposed to agents and Studio
app/services            Business services, API clients, mappers, payload builders
app/schemas             Pydantic request/response/domain schemas
```

## Top-Level Agent Orchestration

The Studio graph starts with visible agent-level nodes:

```text
START
  -> memory_agent
  -> user_profile_agent
  -> intent_router
      -> user_info_agent
      -> general_chat
      -> approval_creation_agent
          -> approval_creation_subgraph
      -> daily_report_agent
          -> daily_report_subgraph
```

`memory_agent` records the current turn into `ApprovalAgentState.short_term_memory`.
`user_profile_agent` loads current user and superior profiles. `intent_router` decides
whether the turn should go to a user information answer, general chat, the approval
creation workflow, or the daily report agent. Future agents such as `order_agent`, `stock_agent`, or
`approval_process_agent` should be connected at this top orchestration layer instead of
being hidden inside approval node functions.

`approval_creation_agent` is a compiled subgraph. Its internal nodes include
`load_context`, `classify`, `decision_review`, `collect`, `validate`, `assignee`,
`preview`, and `submit`. Studio therefore shows a clean top-level multi-agent graph,
while the chat `trace` still records the internal approval nodes when a request really
enters approval creation.

`daily_report_agent` is a compiled write-log subgraph. Its internal nodes include
`daily_report_entry`, `daily_report_action`, `load_daily_report_context`,
`collect_daily_report_content`, `collect_daily_report_date`, `save_daily_report_draft`,
`preview_daily_report`, `submit_daily_report`, and `cancel_daily_report`. The content,
date, and confirmation handoffs use LangGraph `interrupt` so the frontend can collect
user input and resume the same graph thread.

## Approval Flow

`app.graph.workflow` is the production top-level workflow entrypoint used by the
FastAPI chat route and Studio.

`app.graph.approval_workflow` contains only the approval-creation subgraph, and
`app.graph.daily_report_workflow` contains only the daily-report subgraph.

The approval agent implementation lives in `app.agents.approval_agent`. Pure
helpers that are shared by approval sub-agents live under `app.agents.approval`:

```text
app/agents/approval/constants.py       shared route and field constants
app/agents/approval/state_helpers.py   AgentState serialization helpers
app/agents/approval/messages.py        chat/clarification messages
app/agents/approval/selection.py       template selection helpers
app/agents/approval/assignee.py        approval assignee helpers
app/agents/approval/routing.py         approval intent and route predicates
app/agents/approval/inputs.py          frontend awaiting_input builders
app/agents/approval/responses.py       ChatResponse and preview builders
app/agents/approval/submission.py      submit idempotency helpers
```

## User Agent

`app.agents.user_profile_agent` loads current user and superior profiles into
`ApprovalAgentState.user_profile` and `ApprovalAgentState.superior_profile`.

The user tools live in `app.tools.user_tools`:

```text
get_current_user_info
get_user_superior_info
```

## Daily Report Agents

Daily report code is split by responsibility:

```text
app/graph/daily_report_workflow.py      compiled write-log subgraph
app/agents/daily_report_chat_agent.py   daily report node implementations
app/agents/daily_report/action_agent.py daily report action classifier
app/agents/daily_report_common.py       shared state and preview helpers
app/tools/daily_report_tools.py         LangChain tools for daily report operations
app/services/daily_report_api_client.py ERP daily report HTTP calls
app/services/daily_report_service.py    daily report context, preview, and submit facade
app/schemas/daily_report.py             Pydantic daily report context/result schemas
```

Custom daily report fields are carried by `extends` and `extend_fields`. The agent
keeps the ERP field shape intact, validates the payload, saves the draft before preview,
shows a confirmation, and submits only after an explicit confirmation message.

## Services

Services stay below agents and tools:

```text
app/services/crm_api_client.py          ERP approval HTTP calls
app/services/user_api_client.py         ERP user HTTP calls
app/services/crm_service.py             approval business facade
app/services/user_service.py            user business facade
app/services/daily_report_service.py    daily report business facade
app/services/crm_mapper.py              ERP approval response mapping
app/services/approval_payload_builder.py approval submit payload assembly
app/services/short_term_memory_service.py short session memory helpers
app/services/time_travel_service.py     in-memory checkpoints for learning/debugging
```

Agents and tools should call services, not raw ERP endpoints.

## Short-Term Memory

Short-term memory is stored inside `ApprovalAgentState.short_term_memory` and
saved by the existing session backend. It follows the same Redis key and TTL as
the approval session, so no extra cleanup process is needed.

The memory is intentionally bounded by `AI_APPROVAL_SHORT_MEMORY_TURNS`. It helps
general chat understand recent context, while structured approval submission
continues to rely on explicit state such as `collected_slots`, `awaiting_field`,
and `selected_assignees`.

## Time Travel Checkpoints

The project includes a lightweight learning version of time travel. After
`run_chat_turn` saves the current session state, it records a deep-copied checkpoint
through `time_travel_service.record(...)`.

The FastAPI routes under `/api/ai-approval/time-travel` can list checkpoints, inspect
one snapshot, restore the original session to a checkpoint, or fork a checkpoint into
a new `session_id`. This intentionally stays outside the visible Studio graph because
it is a wrapper around the chat turn, not a business agent node.

The current implementation prefers Redis and falls back to memory when Redis is not
configured or unavailable. Checkpoints use this key shape:

```text
{REDIS_PREFIX}ai_approval:checkpoints:{session_id}
```

This demonstrates the checkpoint model without adding a database or migration. A
production version could swap the service implementation for database storage,
object storage, or LangGraph's native checkpointer while keeping the API shape and
chat-turn hook mostly stable.
