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

## Approval Flow

`app.graph.approval_workflow` is the production workflow entrypoint used by the
FastAPI chat route and Studio.

`app.graph.workflow` is kept as a compatibility shim for older imports and
tests. New code should import from `app.graph.approval_workflow`.

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

## Services

Services stay below agents and tools:

```text
app/services/crm_api_client.py          ERP approval HTTP calls
app/services/user_api_client.py         ERP user HTTP calls
app/services/crm_service.py             approval business facade
app/services/user_service.py            user business facade
app/services/crm_mapper.py              ERP approval response mapping
app/services/approval_payload_builder.py approval submit payload assembly
```

Agents and tools should call services, not raw ERP endpoints.
