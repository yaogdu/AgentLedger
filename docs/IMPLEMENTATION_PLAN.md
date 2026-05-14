# Implementation Plan

This project should not be implemented as a giant platform from day one. It should be built in phases, where each phase proves a specific reliability claim.

## North Star

```text
Make AI agent execution durable, auditable, replayable, and safe by default.
```

## Product Milestones

### v0.1 - Local Durable Runtime

Goal: prove the smallest reliability loop locally.

Scope:

- Python SDK
- local runner
- SQLite WAL state store
- local blob store
- AgentContext
- Tool Registry
- Tool Gateway
- Tool Ledger
- Event Log
- deterministic replay
- CLI debug timeline MVP
- side-effect crash recovery demo

Non-goals:

- Postgres
- Kubernetes
- distributed workers
- full UI
- full sandbox
- all framework adapters
- strict multi-tenant isolation

Success criteria:

- quickstart runs without external services
- worker crash after tool success does not duplicate the side effect
- `agentledger replay <run_id>` does not call real model/tool providers
- `agentledger debug <run_id>` shows event timeline, state version, tool ledger
- all `external_write` tools require ledger reservation

Deliverables:

```text
agentledger init
agentledger run examples/side_effect_idempotency
agentledger debug <run_id>
agentledger replay <run_id>
agentledger ledger <run_id>
```

### v0.2 - Runtime Semantics Hardening

Goal: make local runtime semantics precise and testable.

Scope:

- state patch validation
- JSON Merge Patch / JSON Patch support
- state version checks
- lease token and fencing token validation
- cancellation state machine
- retry policy and failure taxonomy
- `PENDING_VERIFICATION` side-effect state
- basic policy YAML
- cost records
- conformance tests for state store and tool ledger

Success criteria:

- stale worker commit is rejected
- state version conflict is detected
- side-effect unknown never auto-retries
- replay detects divergence by event/state hash
- high-risk tool is denied by default policy

### v0.3 - Framework Adapter and DX

Goal: prove low-friction adoption.

Scope:

- LangGraph checkpointer adapter
- generic function decorator API
- tool wrapper API
- framework-agnostic runtime protocol draft
- CLI time-travel improvements
- docs and examples
- lint for bypassing runtime boundary

Success criteria:

- a LangGraph app can adopt runtime state and tool ledger with minimal code changes
- a plain Python function agent can use decorators only
- developer can inspect state diff before/after model/tool events
- bypassing `ctx.call_tool` can be detected by lint in example projects

### v0.5 - Production Pilot Runtime

Goal: support serious pilot deployments.

Scope:

- Postgres state store
- S3/MinIO blob store
- schema migrations
- worker heartbeat
- multi-worker lease claim
- OpenTelemetry exporter
- Docker sandbox plugin MVP
- approval gate
- retention and compaction jobs
- backup/restore guide
- failure injection suite

Success criteria:

- multiple workers can claim distinct steps safely
- lease expiry and old-owner recovery are tested
- high-risk action has full audit chain
- run evidence bundle can be exported
- compaction preserves replay for high-risk events

### v0.8 - Reliability Harness

Goal: make runtime useful for regression and change safety.

Scope:

- Repro Harness
- Eval Harness
- Shadow Mode
- replay diff
- failure attribution summaries
- cost attribution summaries
- policy lint
- adversarial review checklist
- benchmark corpus for historical runs

Success criteria:

- prompt/workflow changes can be shadow-run against historical evidence
- replay vs rerun divergence is reported at event level
- cost regressions can be attributed to agent/step/tool/model
- eval results link back to evidence bundle

### v1.0 - Stable Runtime Core

Goal: stable enough for production pilots with clear boundaries.

Scope:

- stable AgentContext API
- stable event schema
- stable Tool Registry schema
- stable Tool Ledger schema
- stable StateStore interface
- security policy
- versioning and migration policy
- adapter conformance tests
- semver release process

Success criteria:

- runtime invariants are documented and tested
- all critical state backends pass conformance tests
- all high-risk tool flows have audit, approval, ledger, replay safety
- project has README, quickstart, architecture docs, security docs, CI, tests, examples, changelog

## Parallel Workstreams

### Runtime Core

- AgentContext
- Run / Session / Step models
- State Store
- Event Store
- Tool Ledger
- Replay Engine

### Developer Experience

- decorators
- CLI
- examples
- docs
- lint
- local-first defaults

### Adapters

- LangGraph checkpointer
- OpenAI Agents SDK adapter
- generic Python adapter
- TypeScript worker client
- MCP tool adapter

### Enterprise Readiness

- Postgres
- S3/MinIO
- OpenTelemetry
- Docker sandbox
- approvals
- retention / compaction
- threat model

## First Three Demos

1. Side-effect idempotency after worker crash.
2. Time-travel debug of a model/tool/state sequence.
3. LangGraph app with AgentLedgerCheckpointer and ToolGatewayNode.
