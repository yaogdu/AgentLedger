# Execution Backends

AgentLedger should not compete with mature durable execution systems. Temporal, Ray, Kubernetes, and similar systems are execution backends. AgentLedger is the agent-specific runtime contract above them.

## Positioning

```text
Temporal / Ray / Kubernetes
  durable scheduling, queues, workers, retries, timers, fleet management

AgentLedger
  agent runtime boundary, Tool Ledger, side-effect safety, evidence,
  replay safety, policy, sandbox, cost attribution, failure attribution
```

The integration goal is:

```text
AgentLedger does not replace Temporal.
AgentLedger makes Temporal-executed agent workflows agent-safe.
```

## What Backends Should Own

Execution backends may own:

- distributed scheduling
- worker queues
- durable timers
- retry backoff
- activity execution
- workflow lifecycle
- worker fleet management
- infrastructure-level heartbeat and timeout behavior
- deployment topology

AgentLedger should expose adapter contracts for these systems instead of rebuilding their full scheduling platforms inside runtime-core.

## What AgentLedger Must Still Own

AgentLedger must keep the agent-specific invariants:

- `AgentContext` runtime boundary
- ToolGateway and Tool Ledger
- tool schema and capability boundary
- idempotency key and causal token
- policy, approval, and sandbox decision records
- LLM request/response archive
- tool request/response archive
- side-effect-safe replay and shadow execution
- evidence bundle and audit trail
- cost attribution by run/agent/step/tool/model
- failure taxonomy for agent/model/tool/runtime failures
- adapter conformance checks

These are not generic workflow guarantees. They are agent execution guarantees.


## Agent Nodes Inside A Workflow

A Temporal workflow can contain many agent activities:

```text
ResearchAgent Activity -> CodeAgent Activity -> ReviewAgent Activity
```

Temporal can make that workflow durable. It can schedule each activity, retry it, time it out, and recover after worker crashes. That covers the outer workflow lifecycle.

AgentLedger is still useful inside each activity because it governs what happens inside the agent node:

```text
model_call_requested / model_call_completed
tool_call_requested / tool_permission_decided / tool_call_completed
tool_ledger RESERVED / RUNNING / SUCCEEDED / PENDING_VERIFICATION
state_patch_proposed / state_patch_committed
artifact_created / cost_recorded / failure_classified
```

If the activity is a black-box `run_research_agent()`, AgentLedger opens that black box. If every tool call is split into a Temporal activity, AgentLedger still prevents agent-specific semantics from being scattered across workflow glue code.

AgentLedger is unnecessary for some Temporal workflows. If an agent node has no high-risk tools, no external writes, no replay-safe debugging requirement, no evidence/audit requirement, and activity input/output is enough, Temporal may be sufficient.

AgentLedger becomes valuable when agent nodes call models and tools, write external systems, need permissions or sandboxing, require evidence bundles, or must replay without repeating real side effects.

## Temporal Adapter Shape

A Temporal integration should usually look like this:

```text
Agent / Framework
  LangGraph, custom agent, plain function
        |
        v
AgentLedger Runtime Boundary
  AgentContext, ToolGateway, Tool Ledger,
  Policy / Approval / Sandbox, Evidence / Replay
        |
        v
TemporalSchedulerAdapter
  maps AgentLedger run/step execution to workflow/activity execution
        |
        v
Temporal
  durable workflow history, activity retry, timers, queues, worker fleet
```

Temporal can run the activity. AgentLedger should still mediate the tool and model boundary.

## Overlap Is Expected

There is real overlap:

| Capability | Temporal | AgentLedger |
|---|---|---|
| durable execution | strong | runtime-core local baseline plus adapters |
| retry | activity/workflow retry | agent/tool/model failure semantics |
| replay/history | workflow history replay | evidence replay without model/tool side effects |
| distributed workers | strong | local worker plus backend adapters |
| cancellation/timeouts | strong | agent step cancellation/fencing semantics |
| observability | workflow/activity visibility | agent evidence, tool audit, cost/failure attribution |

The design choice is not to remove AgentLedger. The design choice is to keep AgentLedger thin and let mature backends own generic distributed execution.

## Backend Adapter Contract

A backend adapter should preserve these behaviors:

```text
create or map an AgentLedger run
claim or schedule an AgentLedger step
execute through AgentContext
route external calls through ToolGateway
commit state only through the runtime store boundary
preserve cancellation and stale-worker fencing semantics
export evidence that links backend ids to AgentLedger run/step ids
avoid real side effects during replay/shadow execution
```

## Non-goals

Runtime-core should not become:

- a Temporal replacement
- a Ray replacement
- a Kubernetes operator product
- a full worker fleet management platform
- a generic distributed workflow engine

AgentLedger should provide local defaults for quickstart and conformance, then integrate with mature backends through adapters.

## Temporal + LangGraph + AgentLedger

The three layers can be used together:

```text
Temporal
  outer durable distributed workflow runtime

LangGraph
  agent graph / workflow logic / multi-agent orchestration

AgentLedger
  inner agent execution safety, evidence, and tool governance layer
```

A typical stack:

```text
Temporal Workflow
  └── LangGraph Run Activity
        ├── ResearchAgent node -> AgentLedger AgentContext / ToolGateway
        ├── CodeAgent node     -> AgentLedger AgentContext / ToolGateway
        └── ReviewAgent node   -> AgentLedger AgentContext / ToolGateway
```

In this setup, Temporal owns workflow lifecycle, worker queues, retries, timers, and distributed execution. LangGraph owns graph nodes, edges, routing, and multi-agent orchestration. AgentLedger owns the model/tool boundary inside each node: Tool Ledger, idempotency, approval, sandbox, evidence, replay safety, and cost/failure attribution.

This is the preferred positioning for complex production systems. AgentLedger should not claim to replace Temporal or LangGraph; it should make LangGraph nodes running inside Temporal agent-safe.
