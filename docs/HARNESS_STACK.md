# Agent Harness Stack

AgentLedger is a runtime reliability layer for Agent Harness stacks. It is not a full harness product by itself. It becomes useful when combined with systems that own planning, orchestration, observability, model access, tools, storage, and sandbox infrastructure.

The goal of this document is to show how those pieces fit together without turning AgentLedger into a duplicate of LangGraph, Temporal, Langfuse, LiteLLM, MCP, Kubernetes, or eval platforms.

## Layer Map

| Harness layer | Typical owner | AgentLedger role |
|---|---|---|
| Agent workflow / planning | LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK, custom code | wrap nodes and tools with durable state, policy, Tool Ledger, evidence, and replay guarantees |
| Durable orchestration | Temporal, Ray, Kubernetes workers | provide agent-specific leases, fencing, checkpoints, cancellation, cost/failure attribution, and replay semantics inside worker steps |
| Observability / eval UI | Langfuse, LangSmith, OpenTelemetry, custom dashboards | export structured events, evidence bundles, traces, costs, failures, and correlation IDs |
| Tool/context protocol | MCP, internal tool servers, provider SDK tools | enforce schema, permission, approval, sandbox, idempotency, and audit before side effects happen |
| Model gateway/router | OpenAI, Anthropic, Gemini, Bedrock, Ollama, LiteLLM, enterprise gateways | provide the runtime model-call contract, archived responses, budget/fallback/replay semantics, and optional provider adapters |
| Execution environment | Docker, E2B, Kubernetes/gVisor, Firecracker, internal sandboxes | define sandbox policy/result contracts and fail-closed execution routing |
| State/artifacts | SQLite, Postgres, MySQL, S3/MinIO, internal stores | keep runtime metadata, state versions, migrations, blob refs, and evidence refs durable and conformance-tested |

## Minimal Harness

Use this when the team wants local development, examples, or a single-process app.

```text
Agent code / simple framework
  -> AgentLedger Runtime
       -> SQLite StateStore
       -> LocalBlobStore
       -> ToolGateway / Tool Ledger
       -> evidence / replay / static debug export
```

What it proves:

- every run has durable state and events;
- tool calls go through schema, policy, ledger, and evidence;
- replay can inspect a run without repeating model/tool side effects;
- a developer can debug with CLI or static HTML exports.

What it does not cover:

- distributed scheduling;
- production trace UI;
- external model routing;
- managed sandbox infrastructure;
- team-level eval workflow.

## Durable Workflow Harness

Use this when agent work is long-running, retried, or distributed.

```text
Temporal workflow
  -> activity: run LangGraph graph or custom agent step
       -> AgentLedger Runtime
            -> claim step / heartbeat / checkpoint
            -> call model or tool through runtime boundary
            -> commit state with lease and version checks
            -> export evidence
```

Responsibilities:

| Component | Owns |
|---|---|
| Temporal | workflow lifecycle, queues, timers, generic retries, deployment topology |
| LangGraph or custom code | graph nodes, routing, planner logic, agent roles |
| AgentLedger | agent-specific leases, fencing, Tool Ledger, evidence, replay, policy, approval, sandbox, cost/failure attribution |

Important boundary:

Temporal may retry an activity. AgentLedger decides whether the agent step should reuse a previous tool result, block a stale worker, wait for human verification, or resume from a checkpoint.

## Observable Harness

Use this when teams need trace UI, debugging, eval, or prompt/model regression workflows.

```text
AgentLedger Runtime
  -> structured events
  -> evidence bundle
  -> cost/failure attribution
  -> OTLP / JSON / evidence export
       -> Langfuse / LangSmith / OpenTelemetry backend / custom dashboard
```

Responsibilities:

| Component | Owns |
|---|---|
| AgentLedger | source-of-truth runtime evidence, side-effect ledger, replay-safe payload refs, policy decisions |
| Langfuse / LangSmith / OTel backend | trace storage, dashboard, scoring, prompt/version analytics, team debugging |

AgentLedger should not become a full trace database. It should export enough structured evidence for observability tools to correlate:

```text
run_id
session_id
step_id
trace_id
span_id
tool_call_id
model_call_id
causal_token
idempotency_key
evidence_bundle_ref
```

## Tool-Governed Harness

Use this when agents call APIs, shell commands, code tools, browsers, databases, or internal services.

```text
Agent/framework node
  -> ctx.call_tool(...)
       -> ToolSpec validation
       -> policy decision
       -> approval gate if needed
       -> sandbox routing if required
       -> Tool Ledger reservation
       -> executor / MCP server / internal service
       -> response archive
       -> evidence event
```

AgentLedger owns the execution-path guarantees:

- input schema validation before execution;
- permission and approval before side effects;
- sandbox-required fail-closed behavior;
- idempotency key and causal token;
- request/response refs;
- pending-verification state for unknown side effects;
- replay that reuses archived tool results instead of calling the tool again.

External systems can still own tool hosting, MCP server lifecycle, credential vaults, tool marketplaces, or service-specific SDKs.

## Model-Governed Harness

This is a roadmap area. The intended shape is:

```text
Agent/framework node
  -> ctx.call_model(...)
       -> ModelGateway
       -> ModelRouterPolicy
       -> provider adapter or LiteLLM-style bridge
       -> archived model response
       -> token/cost attribution
       -> replay-safe response reuse
```

AgentLedger should own:

- model-call events;
- selected provider/model records;
- request/response refs and redaction;
- budget checks before calls;
- fallback/failure semantics;
- archived-response replay.

Provider SDKs and routing engines should stay optional adapters:

```text
OpenAI
Anthropic
Gemini
Bedrock
Azure OpenAI
Ollama
LiteLLM-style bridge
enterprise model gateway
```

## Full Production Harness

A fuller production harness can look like this:

```text
User / product workflow
  -> Temporal workflow
       -> LangGraph graph
            -> AgentLedger Runtime
                 -> ModelGateway / provider adapter
                 -> ToolGateway / MCP / internal tools
                 -> Sandbox executor
                 -> Postgres/MySQL StateStore
                 -> S3/MinIO BlobStore
                 -> evidence bundle
                 -> OTLP/Langfuse/LangSmith export
```

Control and data flow:

```text
request_id / trace_id enters at product boundary
  -> Temporal workflow id
  -> LangGraph run/config id
  -> AgentLedger run_id / session_id / step_id
  -> model_call_id / tool_call_id / causal_token
  -> evidence_bundle_ref
  -> observability trace/export
```

In this stack:

- Temporal provides outer durable workflow execution.
- LangGraph provides graph topology and agent routing.
- AgentLedger provides reliable execution boundaries inside each agent step.
- MCP/tool systems provide external capabilities.
- Model providers or routers provide model access.
- Sandbox infrastructure isolates dangerous execution.
- Postgres/MySQL and S3/MinIO persist runtime metadata and evidence artifacts.
- Langfuse/LangSmith/OpenTelemetry provide team-facing trace and eval surfaces.

## Integration Rules

1. One run must have stable identifiers across systems: `run_id`, `session_id`, `step_id`, `trace_id`, and external workflow IDs should be correlated, not invented independently in every layer.
2. Side-effecting tools must enter through AgentLedger's ToolGateway if the result needs audit, idempotency, approval, sandbox, or replay guarantees.
3. Model calls should enter through a runtime model boundary once `ModelGateway` is implemented; until then, provider calls should at least be recorded as evidence/cost artifacts.
4. Generic workflow retries should not bypass AgentLedger's lease, Tool Ledger, or checkpoint semantics.
5. Observability tools should consume AgentLedger evidence instead of re-running tools or treating traces as the source of truth for side effects.
6. Storage adapters must pass StateStore/BlobStore conformance before being used as production runtime metadata stores.
7. UI tools should start read-only. Mutating runtime state from dashboards needs a separate permission, approval, and audit design.

## What AgentLedger Does Not Become

AgentLedger should not become:

- a complete graph planner;
- a generic workflow engine;
- a Langfuse/LangSmith replacement;
- a full eval platform;
- a RAG or vector memory platform;
- a model marketplace or billing system;
- a hosted sandbox platform;
- a SaaS or multi-tenant app platform.

The long-term direction is to make AgentLedger the reliability substrate that allows a harness stack to be assembled from mature components without losing durable execution, governance, evidence, replay, and side-effect safety.
