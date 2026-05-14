# AgentLedger / Agent Runtime

> **AgentLedger** is a durable execution and reliability layer for production-grade AI agents.

Most agent frameworks help agents think, plan, and coordinate. AgentLedger focuses on a different problem:

```text
Make AI agent execution durable, auditable, replayable, and safe by default.
```

It is not intended to replace LangChain, LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, or custom agent frameworks. It is a framework-agnostic runtime layer that can sit underneath or beside them.

## Core Thesis

Agent systems fail less like ordinary request/response apps and more like distributed workflows with untrusted decision makers:

- workers crash mid-run
- tools time out after producing side effects
- retries duplicate external writes
- memory and shared state get polluted
- prompt or workflow changes introduce silent regressions
- logs are insufficient for replay or attribution
- high-risk tools need policy, audit, approval, and sandboxing

AgentLedger treats agent execution as a durable state machine:

```text
load checkpoint
  -> acquire lease
  -> execute one step through AgentContext
  -> record model/tool/state/artifact events
  -> commit state patch atomically with completion events
  -> yield / wait / retry / complete
```

## What It Provides

- **Durable Resume**: resume from the last committed checkpoint after worker crash or restart.
- **Tool Ledger**: idempotency and audit ledger for external side effects.
- **Event-level Replay**: deterministic replay from model/tool archives and event log.
- **Run Evidence Bundle**: run spec, state, events, payload refs, artifacts, cost, failures.
- **Policy Boundary**: runtime-enforced capability and tool access control.
- **Shadow Mode**: run new prompts/workflows against historical evidence without real side effects.
- **Time Travel Debugging**: inspect event timeline, state diffs, tool calls, and artifacts.
- **Framework-agnostic SDK**: core runtime contracts plus optional adapters.

## What It Is Not

- Not a new general-purpose agent framework.
- Not a new LLM SDK.
- Not a full observability SaaS.
- Not a replacement for Temporal, Ray, Kubernetes, or LangGraph.
- Not a magic guarantee that all external systems are exactly-once.

The honest guarantee is narrower: every runtime-managed side effect has a ledger entry, idempotency key, audit chain, and explicit `side_effect_unknown` / `PENDING_VERIFICATION` handling.

## Architecture Layers

```text
Agent / Framework Layer
  LangGraph, CrewAI, AutoGen, custom agents, Python functions, TS workers

Runtime Boundary
  AgentContext, ToolGateway, PolicyEngine, BudgetController, CredentialBroker

Scheduling Layer
  Scheduler, Lease, Fencing Token, Worker Pool, Retry, Cancellation

Durable State Layer
  RunState, SessionState, StepState, EventLog, ToolLedger, Checkpoints

Evidence Layer
  Model/Tool Archive, Artifact Store, Blob Store, Trace, Cost, Failure Records

Reliability Consumers
  Replay, Repro Harness, Eval, Time Travel Debugger, Shadow Mode
```

## Local-first Storage Defaults

```text
v0.1 local dev:
  SQLite WAL + local blob store

team / production:
  Postgres + S3/MinIO + OpenTelemetry

optional high-throughput event stream:
  Kafka / Redpanda / Pulsar
```

## Quickstart

Current scaffold has no third-party runtime dependencies. From the repo root:

```bash
PYTHONPATH=src python3 -m agentledger init
PYTHONPATH=src python3 -m agentledger run examples/side_effect_idempotency
PYTHONPATH=src python3 -m agentledger debug <run_id>
PYTHONPATH=src python3 -m agentledger replay <run_id>
PYTHONPATH=src python3 -m agentledger ledger <run_id>
PYTHONPATH=src python3 -m agentledger doctor
```

After packaging/installing in editable mode, the CLI target is:

```bash
agentledger run examples/side_effect_idempotency
```

The flagship demo:

```text
1. Agent calls a side-effect tool, e.g. github.create_issue.
2. Tool succeeds externally.
3. Worker crashes before state commit.
4. Runtime resumes from checkpoint.
5. Tool Ledger prevents duplicate issue creation.
6. Replay shows the full timeline and state diff.
```

## Development

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Documentation

- `AI_Agent_Runtime_开源项目构想.md`: long-form project vision and architecture notes.
- `docs/IMPLEMENTATION_PLAN.md`: phased implementation plan beyond MVP.
- `docs/RUNTIME_SPEC.md`: runtime concepts, state model, event schema, tool ledger, invariants.
- `docs/EXTENSIBILITY.md`: adapter model for storage, tools, frameworks, protocols, observability.
- `docs/SECURITY_ENTERPRISE.md`: security model, enterprise readiness, open-source quality bar.

## License

Apache-2.0. See `LICENSE`.
