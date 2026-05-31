# Open Source Impact

AgentLedger is an early-stage open-source infrastructure project for production AI agent reliability and governance. It is not an agent framework, a hosted platform, or a replacement for LangGraph, Temporal, Langfuse, MCP, or model providers. Its value is the runtime boundary those systems can share: durable state, governed tool use, evidence, replay, policy checks, sandbox routing, and cost/failure attribution.

## Ecosystem Problem

Most agent projects can demonstrate a successful happy path before they can operate safely in production. The harder problems appear after the first demo:

- workers crash after a model call but before the next state commit
- tools timeout after they may already have changed an external system
- retries duplicate emails, tickets, database writes, or infrastructure actions
- prompts, models, and tool schemas change without a reproducible execution record
- reviewers cannot tell which state, tool result, policy decision, or approval caused an outcome
- teams add ad hoc logs and retries instead of a shared reliability contract

These are infrastructure problems, not prompt-engineering problems. AgentLedger focuses on the execution layer where state transitions, tool side effects, approvals, evidence, and replay have to be enforced consistently.

## What AgentLedger Adds

AgentLedger provides a runtime reliability layer that can sit beside or underneath agent frameworks and orchestration systems.

| Capability | Ecosystem value |
| --- | --- |
| Durable execution records | Agent runs can be resumed, inspected, and replayed from committed runtime events instead of in-memory state. |
| Tool Ledger | Tool side effects receive idempotency keys, causal request records, status tracking, and audit evidence. |
| Policy and approval gates | High-risk tools can require explicit permission, human approval, or sandbox routing before execution. |
| Evidence bundles | Debugging, review, compliance, and regression checks can consume one portable record of state, tool results, artifacts, costs, and failures. |
| Replay and shadow semantics | Historical runs can be replayed without repeating external side effects, and new logic can be compared against recorded evidence. |
| Adapter contracts | Frameworks, storage backends, observability sinks, MCP-style tool systems, and sandbox executors can integrate without forcing runtime-core to become a large platform. |
| Multi-language runtime contract | Python, Go, TypeScript, and Rust implementations align on a language-neutral runtime contract and shared conformance fixtures. |

## Why It Is Different From Agent Frameworks

Agent frameworks usually own planning, reasoning, graph routing, prompt strategy, and model/tool selection. AgentLedger owns the reliability boundary around execution:

```text
Agent framework:
  choose what should happen next

AgentLedger:
  make the execution durable, governed, auditable, replayable, and recoverable
```

This means AgentLedger is designed to be used with existing frameworks rather than compete with them. A LangGraph, OpenAI Agents SDK, CrewAI, AutoGen, LlamaIndex, Semantic Kernel, or custom agent can keep its own reasoning model while AgentLedger records durable runtime evidence and governs side effects.

## Current Stage

AgentLedger is a young project. Its current value should be evaluated by infrastructure depth and clarity of contract rather than by broad adoption metrics alone.

What is already in place:

- stable v1.x runtime-core contract
- Python reference implementation
- Go, TypeScript, and Rust runtime-core parity gates
- Tool Ledger, evidence/replay, policy/approval/sandbox boundaries, cost/failure attribution, worker/conformance, and adapter seams
- optional package boundaries for storage, observability, sandbox, framework, and protocol adapters
- formal documentation for architecture, runtime specification, storage, adapters, maturity, release checks, and language parity

What remains intentionally separate or later-stage:

- hosted dashboard products
- full eval platforms
- RAG/vector memory systems
- production claims for every external backend
- replacing mature workflow, tracing, or sandbox infrastructure

## Open Source Maintenance Value

AgentLedger is useful to maintain as open source because the problem is shared across the agent ecosystem. Different teams may use different agent frameworks and deployment stacks, but they face similar runtime reliability questions:

- Which side effects happened?
- Which tool calls were approved?
- Which state version was used?
- Can this run be resumed?
- Can this result be reproduced?
- Can this failure be attributed?
- Can a new agent version be compared against historical evidence?

Open development makes the runtime contract, adapter boundaries, conformance fixtures, and examples easier to review and reuse across ecosystems.

