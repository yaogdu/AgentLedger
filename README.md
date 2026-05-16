# AgentLedger

[English](README.md) | [中文](README.zh-CN.md)

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Version 1.0.1 stable](https://img.shields.io/badge/Version-1.0.1--stable-111827)
![License Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-0f766e)
![Runtime Durable](https://img.shields.io/badge/Runtime-durable%20execution-1f6feb)
![Storage SQLite/Postgres](https://img.shields.io/badge/Storage-SQLite%20%7C%20Postgres-b45309)
![Replay Evidence](https://img.shields.io/badge/Replay-evidence%20driven-7c3aed)
![Tool Ledger](https://img.shields.io/badge/Tools-ledger%20guarded-d97706)

AgentLedger `1.0.1` is a durable execution and reliability runtime for AI agents. It does not try to teach agents how to reason; it makes agent runs durable, auditable, replayable, policy-governed, and recoverable when workers crash, tools fail, or prompts change.

Most agent frameworks focus on planning, reasoning, and workflow logic. AgentLedger sits underneath or beside LangChain, LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, or custom agents to provide runtime guarantees around state, tools, evidence, replay, and recovery.

Python is the current reference implementation. Rust, TypeScript, and Go implementations should target the same language-neutral runtime contract.

## At a glance

| Question | Answer |
| --- | --- |
| What is stable? | Python v1.0 runtime-core: local durable execution, Tool Ledger, evidence/replay, policy/approval/sandbox boundaries, cost/failure reports, worker/conformance, and the runtime contract. |
| What is optional? | Postgres, S3/MinIO, framework-native packages, OTLP collector transport, sandbox infrastructure, distributed deployment recipes, and real-service hardening. |
| What is preview? | Media/stream artifact contracts and some dependency-free adapter facades. |
| What is not in core? | Planning engines, full eval systems, RAG/vector memory, trace stores, hosted application products, and hosted sandbox infrastructure. |
| How should other languages work? | This repo is contract-first. Python is the reference runtime; TypeScript, Rust, and Go should target `contracts/agentledger.runtime.v1.json` and shared conformance fixtures. |

## Scope principle

AgentLedger keeps the runtime thin but hard to replace: core only owns guarantees that cannot be reliably enforced outside the runtime boundary. Everything else should integrate through adapters, contracts, conformance tests, and examples.

```text
Runtime core:
  durable execution, governed tool use, evidence, replay, policy hooks,
  leases, fencing, cancellation, budgets, attribution, and conformance

Adapters:
  agent frameworks, storage backends, blob stores, sandboxes, model providers,
  observability sinks, policy engines, MCP, media processors, and deployers

External tools:
  planning/workflow engines, full eval systems, trace stores, RAG systems,
  distributed schedulers, and sandbox infrastructure
```

Most extension areas follow a three-layer model:

```text
Core contract:
  stable interfaces, events, invariants, failure semantics, and conformance

Built-in minimal implementation:
  dependency-free local defaults for quickstart, demos, tests, and light use

Optional production adapter:
  mature integrations for real infrastructure, frameworks, and operations
```

For example, sandbox semantics are core, but sandbox infrastructure is not. Core owns `SandboxPolicy`, fail-closed routing, audit/evidence records, and replay safety; Docker, E2B, bubblewrap, Kubernetes/gVisor, Firecracker, or custom executors are adapters.

## What AgentLedger is for

- Making long-running agent tasks resume from the last committed checkpoint after crash or restart
- Preventing duplicate external side effects with a Tool Ledger, idempotency keys, and causal request records
- Exporting complete evidence bundles for debugging, review, regression checks, and audit trails
- Replaying historical runs without repeating model calls or tool side effects
- Enforcing tool permissions, approvals, sandbox boundaries, cost budgets, and failure semantics at runtime
- Providing adapter seams for agent frameworks, storage backends, blob stores, tool systems, traces, and sandbox executors
- Keeping the core dependency-free for local development while allowing optional Postgres, S3/MinIO, OTLP, and framework adapters

## Key capabilities

- Durable state machine: runs, steps, sessions, leases, fencing tokens, retries, cancellation, and checkpoint resume
- Tool governance: schema validation, capability policy, approval gates, sandbox routing, audit events, and side-effect status tracking
- Evidence and replay: event-level WAL, payload archives, evidence bundles, static HTML debug export, replay, diff, divergence, and shadow runs
- Reliability engineering: failure taxonomy, failure injection suite, evidence regression gates, adversarial review checklist, backup readiness checks, and retention planning
- Cost and budget control: token/cost records, in-flight budget enforcement, attribution by run, agent, step, tool, and model
- Framework adoption: plain Python API plus adapter facades for LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, and MCP-style tools/context
- Storage choices: SQLite WAL + local blobs by default; optional Postgres StateStore and S3/MinIO BlobStore adapters
- Media and stream contracts: durable refs, metadata, lineage, chunk refs, offsets, watermarks, and replay validation without codecs or stream transport in core

## Architecture

![AgentLedger runtime architecture](docs/assets/agentledger-runtime-architecture.svg)

- Documentation overview: [docs/README.md](docs/README.md)
- Architecture guide: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Design and implementation: [docs/DESIGN_AND_IMPLEMENTATION.md](docs/DESIGN_AND_IMPLEMENTATION.md)
- Runtime contract: [docs/RUNTIME_SPEC.md](docs/RUNTIME_SPEC.md)

## Project policy

- License: [Apache-2.0](LICENSE)
- Security reporting: [SECURITY.md](SECURITY.md)
- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Community conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Release gates: [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)
- Compatibility policy: [docs/VERSIONING.md](docs/VERSIONING.md)

## Quick start

### 1. Install

From PyPI:

```bash
python3 -m pip install agentledger-runtime
agentledger --help
agentledger doctor
```

The PyPI distribution is named `agentledger-runtime`; the Python import package and CLI remain `agentledger`.

Project homepage and full documentation:

```text
https://github.com/yaogdu/AgentLedger
```

### 2. Install for local development

Use Python 3.11 or newer. If your system `python3` is older, replace `python3` with `python3.11` in the commands below.

```bash
python3 -m pip install -e .
agentledger doctor
```

The source tree also works without installing the package:

```bash
PYTHONPATH=src python3 -m agentledger doctor
```

### 3. Run the minimal API

```python
from agentledger import agent, run

@agent
def hello(ctx):
    return "hello world"

result = run(hello)
print(result.output)
print(result.run_id)
```

This looks like a normal function call, but the runtime still creates a durable run, claims a leased step, records events, commits state atomically, and can export evidence.

### 4. Try CLI flows

```bash
PYTHONPATH=src python3 examples/hello_world/hello.py
PYTHONPATH=src python3 -m agentledger init
PYTHONPATH=src python3 -m agentledger run examples/side_effect_idempotency
PYTHONPATH=src python3 -m agentledger debug <run_id> --json --include-diffs
PYTHONPATH=src python3 -m agentledger replay <run_id>
PYTHONPATH=src python3 -m agentledger evidence <run_id> --dir ./evidence/<run_id>
PYTHONPATH=src python3 -m agentledger evidence <run_id> --html ./evidence.html
PYTHONPATH=src python3 -m agentledger timetravel <run_id> --include-diffs --include-states --html ./time-travel.html
PYTHONPATH=src python3 -m agentledger cost report <run_id>
PYTHONPATH=src python3 -m agentledger failure report <run_id>
PYTHONPATH=src python3 -m agentledger review checklist <run_id> --fail-on-risk
PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/docs
PYTHONPATH=src python3 -m agentledger contract export
```

## Runtime model

| Layer | What it owns | Extension points |
| --- | --- | --- |
| Agent logic | user functions, framework nodes, prompts, model choices | LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, custom workers |
| Runtime boundary | `AgentContext`, tool gateway, policy, approval, budget, sandbox routing | tool registry, policy loader, approval store, sandbox executor |
| Scheduling | step claim, lease, fencing, retry, heartbeat, cancellation, recovery | local worker loop, distributed worker recipes, custom claimers |
| Durable state | runs, sessions, steps, events, tool ledger, checkpoints, migrations | SQLite, Postgres, custom StateStore |
| Evidence | payload refs, blob refs, artifacts, media refs, traces, costs, failures | local blob store, S3/MinIO, OTLP JSON, static HTML export |
| Reliability consumers | replay, diff, shadow mode, evidence regression, conformance, backup check | golden corpus, adapter certification, custom review gates |

## Compatibility boundary

AgentLedger does not replace agent or workflow libraries.

| Agent frameworks own | AgentLedger owns |
| --- | --- |
| Planning, reasoning, routing, graph structure, prompt strategy | Durable state, event log, Tool Ledger, policy, approval, sandbox boundary, evidence, replay, recovery |

AgentLedger is also not a new LLM SDK, not a workflow engine, not a general observability product, not a full eval system, not a RAG system, not a sandbox infrastructure provider, not a replacement for Temporal/Ray/Kubernetes, and not a magic guarantee that every external system becomes exactly-once. The narrower guarantee is: each runtime-managed side effect should have a ledger entry, idempotency key, audit trail, and explicit unknown-state handling.

## Current maturity

AgentLedger is a v1.0 stable runtime-core release. It is suitable for local use, framework adapter integration, reliability semantics validation, and production pilot preparation with explicit adapter boundaries.

The runtime-core contract is stable; optional production adapters and external infrastructure hardening remain separately tracked. See [docs/MATURITY_MODEL.md](docs/MATURITY_MODEL.md), [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md), and [docs/ROADMAP.md](docs/ROADMAP.md).

## Documentation navigation

| Goal | Document |
| --- | --- |
| Use the runtime | [docs/USAGE.md](docs/USAGE.md) |
| Understand architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Read implementation details | [docs/DESIGN_AND_IMPLEMENTATION.md](docs/DESIGN_AND_IMPLEMENTATION.md) |
| Check runtime spec | [docs/RUNTIME_SPEC.md](docs/RUNTIME_SPEC.md) |
| Extend storage, tools, and adapters | [docs/EXTENSIBILITY.md](docs/EXTENSIBILITY.md), [docs/STORAGE.md](docs/STORAGE.md), [docs/ADAPTER_CERTIFICATION.md](docs/ADAPTER_CERTIFICATION.md) |
| Configure Postgres or S3/MinIO | [docs/POSTGRES.md](docs/POSTGRES.md), [docs/S3_MINIO.md](docs/S3_MINIO.md) |
| Prepare releases | [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md), [docs/VERSIONING.md](docs/VERSIONING.md) |
| Read Chinese docs | [README.zh-CN.md](README.zh-CN.md), [docs/zh/README.md](docs/zh/README.md) |

## Repository layout

```text
src/agentledger/     Python reference runtime-core
tests/               unit, conformance, and integration-style tests
examples/            dependency-free examples and adapter facades
docs/                English documentation and runtime design docs
docs/zh/             Chinese primary reader path
contracts/           language-neutral runtime contract snapshot
migrations/          SQLite/Postgres DDL and migration baselines
```

## Automated validation

```bash
PYTHONPYCACHEPREFIX=/tmp/agentledger-pycache PYTHONPATH=src python3 -m compileall -q src tests examples
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src PYTHONTRACEMALLOC=10 python3 -W default::ResourceWarning -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger contract export > /tmp/agentledger-contract.json
python3 -m json.tool /tmp/agentledger-contract.json >/dev/null
diff -u contracts/agentledger.runtime.v1.json /tmp/agentledger-contract.json
```

See [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) for the complete release gate.

## License

Apache-2.0. See [LICENSE](LICENSE).
