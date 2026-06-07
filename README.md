# AgentLedger

[English](README.md) | [中文](README.zh-CN.md)

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Version 1.3.x stable](https://img.shields.io/badge/Version-1.3.x--stable-111827)
![License Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-0f766e)
![Runtime Durable](https://img.shields.io/badge/Runtime-durable%20execution-1f6feb)
![Storage SQLite/Postgres/MySQL](https://img.shields.io/badge/Storage-SQLite%20%7C%20Postgres%20%7C%20MySQL-b45309)
![Replay Evidence](https://img.shields.io/badge/Replay-evidence%20driven-7c3aed)
![Tool Ledger](https://img.shields.io/badge/Tools-ledger%20guarded-d97706)

Your agent called a tool. Did it happen? Can you retry safely? Can you prove it later?

AgentLedger `1.3.x` is a runtime reliability layer for Agent Harness stacks. It does not try to teach agents how to reason or replace the surrounding harness ecosystem; it makes agent runs durable, auditable, replayable, policy-governed, and recoverable when workers crash, tools fail, or prompts change.

Most agent frameworks focus on planning, reasoning, and workflow logic. AgentLedger sits underneath or beside LangChain, LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, or custom agents to provide runtime guarantees around state, tools, evidence, replay, and recovery.

In a full harness stack, systems such as LangGraph, Temporal, Langfuse, MCP, model routers, storage backends, and sandbox providers can each own the layer they are good at. AgentLedger owns the reliability substrate between them: durable execution, tool/model governance, evidence, replay, policy/sandbox boundaries, cost/failure attribution, and adapter contracts.

Python remains the reference implementation, and Go, TypeScript, and Rust now have native runtime-core baselines aligned to the same language-neutral runtime contract. Provider-specific drivers and framework-native adapters intentionally vary by ecosystem. See `docs/LANGUAGE_IMPLEMENTATION_COMPARISON.md` for the exact four-language comparison and adapter boundary.

## Start Here

| Need | Go to |
| --- | --- |
| Install and run the first example | [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) |
| Choose Python / Go / TypeScript / Rust | [docs/LANGUAGE_QUICKSTART.md](docs/LANGUAGE_QUICKSTART.md) |
| Find runnable examples | [examples/README.md](examples/README.md), [go/examples/README.md](go/examples/README.md), [typescript/examples/README.md](typescript/examples/README.md), [rust/examples/README.md](rust/examples/README.md) |
| Query runtime tables | [docs/QUERY_EXAMPLES.md](docs/QUERY_EXAMPLES.md) |
| Inspect a run visually | [docs/INSPECTOR.md](docs/INSPECTOR.md) |
| Understand Harness stack composition | [docs/HARNESS_STACK.md](docs/HARNESS_STACK.md) |
| Understand open-source impact | [docs/OPEN_SOURCE_IMPACT.md](docs/OPEN_SOURCE_IMPACT.md) |
| Understand maintainer responsibilities | [docs/MAINTAINER_NOTES.md](docs/MAINTAINER_NOTES.md) |
| Plan adoption work | [docs/ADOPTION.md](docs/ADOPTION.md) |
| Understand what is equal across languages | [docs/LANGUAGE_IMPLEMENTATION_COMPARISON.md](docs/LANGUAGE_IMPLEMENTATION_COMPARISON.md) |
| Install optional adapter packages | [docs/ADAPTER_PACKAGING.md](docs/ADAPTER_PACKAGING.md) |
| Use Go correctly | [go/README.md](go/README.md#install) |
| Read the full documentation map | [docs/README.md](docs/README.md) |

## Inspector Preview

Inspector exports self-contained, read-only HTML for local or internal debugging. It can show a run index before opening a single run, then drill into chronological events, Tool Ledger rows, approvals, artifacts, and full-width JSON details.

![AgentLedger Inspector run index](docs/assets/inspector/runs-index.png)

![AgentLedger Inspector single run](docs/assets/inspector/single-run-timeline.png)

## At a glance

| Question | Answer |
| --- | --- |
| What is stable? | The v1.x runtime-core contract: durable execution, Tool Ledger, evidence/replay, policy/approval/sandbox boundaries, cost/failure reports, worker/conformance, and Python reference implementation with Go/TypeScript/Rust runtime-core parity gates. |
| What is optional? | Postgres, MySQL, S3/MinIO, framework-native packages, OTLP collector transport, sandbox infrastructure, distributed deployment recipes, and real-service hardening. |
| What is experimental? | Some concrete provider adapters, media/stream processing adapters, and real-service hardening paths. Go/TypeScript/Rust runtime-core baselines are native implementations covered by shared conformance. |
| What is not in core? | Planning engines, full eval systems, RAG/vector memory, trace stores, application administration backends, and sandbox infrastructure providers. |
| How should other languages work? | This repo is contract-first. Python is the reference runtime; Go, Node/TypeScript, and Rust now have native runtime baselines under `go/`, `typescript/`, and `rust/`. Runtime-ready requires `contracts/agentledger.runtime.v1.json`, the shared semantic manifest `contracts/conformance/runtime_semantics.v1.json`, shared conformance fixtures, and per-language conformance commands. |

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

## Harness stack composition

AgentLedger is not a full Agent Harness by itself. It is designed to compose with the rest of the harness ecosystem:

For concrete stack patterns, from a minimal local harness to a Temporal + LangGraph + observability harness, see [docs/HARNESS_STACK.md](docs/HARNESS_STACK.md).

| Harness layer | Typical systems | AgentLedger role |
| --- | --- | --- |
| Agent workflow / planning | LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK, custom code | wrap nodes and tools with durable state, policy, Tool Ledger, evidence, and replay guarantees |
| Durable orchestration | Temporal, Ray, Kubernetes workers | provide agent-specific leases, fencing, checkpoints, cancellation, cost/failure attribution, and replay semantics inside the worker step |
| Observability / eval UI | Langfuse, LangSmith, OpenTelemetry, custom dashboards | export structured runtime events, evidence bundles, trace/cost/failure data, and correlation IDs |
| Tool and context protocols | MCP, internal tool servers, provider SDK tools | enforce schema, permissions, approval, sandbox, idempotency, and audit before side effects happen |
| Model providers / routers | OpenAI, Anthropic, Gemini, Bedrock, Ollama, LiteLLM, enterprise gateways | provide the runtime model-call contract, archived responses, budget/fallback/replay semantics, and optional provider adapters |
| Storage / artifacts | SQLite, Postgres, MySQL, S3/MinIO, internal stores | keep runtime metadata, state versions, migrations, blob refs, and evidence refs durable and conformance-tested |

The intended production shape is therefore not `AgentLedger instead of LangGraph/Temporal/Langfuse`. It is `AgentLedger with LangGraph/Temporal/Langfuse` where AgentLedger governs the model/tool/state boundary that those systems otherwise cannot enforce by themselves.

## What AgentLedger is for

- Making long-running agent tasks resume from the last committed checkpoint after crash or restart
- Preventing duplicate external side effects with a Tool Ledger, idempotency keys, and causal request records
- Exporting complete evidence bundles for debugging, review, regression checks, and audit trails
- Replaying historical runs without repeating model calls or tool side effects
- Enforcing tool permissions, approvals, sandbox boundaries, cost budgets, and failure semantics at runtime
- Providing adapter seams for agent frameworks, storage backends, blob stores, tool systems, traces, and sandbox executors
- Keeping the core dependency-free for local development while allowing optional Postgres, MySQL, S3/MinIO, OTLP, and framework adapters

## Key capabilities

- Durable state machine: runs, steps, sessions, leases, fencing tokens, retries, cancellation, and checkpoint resume
- Tool governance: schema validation, capability policy, approval gates, sandbox routing, audit events, and side-effect status tracking
- Evidence and replay: event-level WAL, payload archives, evidence bundles, static HTML debug export, replay, diff, divergence, and shadow runs
- Reliability engineering: failure taxonomy, failure injection suite, evidence regression gates, adversarial review checklist, backup readiness checks, and retention planning
- Cost and budget control: token/cost records, in-flight budget enforcement, attribution by run, agent, step, tool, and model
- Framework adoption: plain Python API plus adapter facades for LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, and MCP-style tools/context
- Storage choices: SQLite WAL + local blobs by default; optional Postgres/MySQL StateStore and S3/MinIO BlobStore adapters
- Media and stream contracts: durable refs, metadata, lineage, chunk refs, offsets, watermarks, and replay validation without codecs or stream transport in core

## Examples

The repository includes cross-language 3-minute side-effect safety demos, MCP governance demos, small quickstarts, and a richer multi-language Travel Assistant demo that shows the same runtime ideas across Python, Go, Rust, and TypeScript.

| Goal | Demo | Run |
| --- | --- | --- |
| 3-minute side-effect safety | Python / Go / Rust / TypeScript | `PYTHONPATH=src python3 examples/three_minute_demo/demo.py`; `cd go && go run ./examples/three_minute_demo`; `cd rust && cargo run --example three_minute_demo`; `cd typescript && node examples/three_minute_demo/three_minute_demo.js` |
| MCP tool governance | Python / Go / Rust / TypeScript | `PYTHONPATH=src python3 examples/mcp_governance/demo.py`; `cd go && go run ./examples/mcp_governance`; `cd rust && cargo run --example mcp_governance`; `cd typescript && node examples/mcp_governance/mcp_governance.js` |
| Python | `examples/travel_assistant/demo.py` | `python3 examples/travel_assistant/demo.py` |
| Go | `go/examples/travel_assistant/main.go` | `cd go && go run examples/travel_assistant/main.go` |
| Rust | `rust/examples/travel_assistant.rs` | `cd rust && cargo run --example travel_assistant` |
| TypeScript | `typescript/examples/travel_assistant/travel_assistant.js` | `node typescript/examples/travel_assistant/travel_assistant.js` |

See [examples/README.md](examples/README.md) for the full example index and language-specific notes.

## Architecture

![AgentLedger runtime architecture](docs/assets/agentledger-runtime-architecture.svg)

## Relationship to adjacent tools

Some capabilities sound similar to existing agent, workflow, observability, and eval tools. The distinction is where the guarantee is enforced.

AgentLedger is intentionally in the execution path. It controls the boundary where agent code reads state, calls models, invokes tools, writes checkpoints, spends budget, and produces evidence. Adjacent tools can still own planning, tracing UI, eval datasets, worker fleets, or retrieval systems.

| Adjacent layer | Best at | AgentLedger owns | How they work together |
| --- | --- | --- | --- |
| LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK | planning, graph routing, agent logic, prompt/workflow structure | durable state, Tool Ledger, policy/approval/sandbox, replay-safe tool/model boundaries | wrap framework nodes or tools with AgentLedger runtime guarantees |
| Temporal, Ray, Kubernetes | distributed workflow lifecycle, worker execution, scheduling infrastructure | agent-specific leases, fencing, checkpoints, evidence, cost/failure attribution | run AgentLedger-managed agent steps inside those execution backends |
| LangSmith, Langfuse, OpenTelemetry | traces, dashboards, evals, monitoring, team debugging | runtime evidence, side-effect governance, replay artifacts, policy decisions before execution | export traces/evidence from AgentLedger into observability/eval systems |
| Eval platforms and benchmark tools | datasets, experiments, scorers, reports | replay, deterministic evidence bundles, side-effect-free regression inputs | eval tools consume AgentLedger evidence instead of re-running unsafe side effects |
| Vector DBs and RAG systems | long-term knowledge retrieval and semantic memory | short-term/session state, durable memory refs, replayable state transitions | store retrieval outputs as runtime-visible refs and evidence |

If a term overlaps, read it this way: AgentLedger records trace/eval/cost/failure data because those records are needed for correctness, recovery, replay, and audit. It does not try to become a full trace store, eval platform, RAG system, workflow engine, or sandbox provider.

## Relative focus and advantages

- In-path enforcement: policy, approval, sandbox, budget, and idempotency checks happen before model/tool side effects, not only after-the-fact in traces.
- Side-effect safety: Tool Ledger, causal tokens, idempotency keys, and pending-verification states prevent unsafe duplicate external writes.
- Crash recovery: leases, fencing tokens, checkpoints, and cancellation semantics let a new worker resume while blocking stale workers.
- Replay-safe evidence: event logs, payload refs, state versions, cost records, and artifacts allow debugging without repeating real model/tool calls.
- Thin core: built-in local defaults work out of the box, while Postgres, MySQL, S3/MinIO, OTLP, framework packages, and sandboxes stay adapter-driven.
- Framework-neutral contract: Python is the stable reference runtime; Go, Node/TypeScript, and Rust runtime-core packages target the same runtime semantics and shared conformance gate.

## LangGraph relationship

![LangGraph and AgentLedger relationship](docs/assets/langgraph-agentledger-relationship.svg)

## Temporal relationship

Temporal, Ray, and Kubernetes should be treated as execution backends, not competitors to AgentLedger. AgentLedger keeps the agent-specific runtime contract above them: Tool Ledger, idempotency, policy/approval/sandbox boundaries, evidence, replay safety, and cost/failure attribution. See [docs/EXECUTION_BACKENDS.md](docs/EXECUTION_BACKENDS.md).

Temporal + LangGraph + AgentLedger is a valid production stack: Temporal runs the outer distributed workflow, LangGraph organizes the agent graph, and AgentLedger governs the inner model/tool/side-effect boundary.

- Documentation overview: [docs/README.md](docs/README.md)
- Architecture guide: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Policy engine guide: [docs/POLICY_ENGINE.md](docs/POLICY_ENGINE.md)
- Comparisons and overlap: [docs/COMPARISONS.md](docs/COMPARISONS.md)
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
| Durable state | runs, sessions, steps, events, tool ledger, checkpoints, migrations | SQLite, Postgres, MySQL, custom StateStore |
| Evidence | payload refs, blob refs, artifacts, media refs, traces, costs, failures | local blob store, S3/MinIO, OTLP JSON, static HTML export |
| Reliability consumers | replay, diff, shadow mode, evidence regression, conformance, backup check | golden corpus, adapter certification, custom review gates |

## Compatibility boundary

AgentLedger does not replace agent or workflow libraries.

| Agent frameworks own | AgentLedger owns |
| --- | --- |
| Planning, reasoning, routing, graph structure, prompt strategy | Durable state, event log, Tool Ledger, policy, approval, sandbox boundary, evidence, replay, recovery |

AgentLedger is also not a new LLM SDK, not a workflow engine, not a general observability product, not a full eval system, not a RAG system, not a sandbox infrastructure provider, not a replacement for Temporal/Ray/Kubernetes, and not a magic guarantee that every external system becomes exactly-once. The narrower guarantee is: each runtime-managed side effect should have a ledger entry, idempotency key, audit trail, and explicit unknown-state handling.

## Current maturity

AgentLedger 1.3.x is a stable runtime-core line with Python as the reference implementation and Go, TypeScript, and Rust covered by shared runtime-core parity gates. The current packaged Inspector patch is 1.3.5; Go, TypeScript, and Rust runtime-core package baselines remain 1.3.1 until their next runtime-core release because their runtime-core semantics did not change. It is suitable for local use, framework adapter integration, reliability semantics validation, and production pilot preparation with explicit adapter boundaries.

The runtime-core contract is stable; optional production adapters and external infrastructure hardening remain separately tracked. See [docs/MATURITY_MODEL.md](docs/MATURITY_MODEL.md), [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md), and [docs/ROADMAP.md](docs/ROADMAP.md).

## Documentation navigation

| Goal | Document |
| --- | --- |
| Use the runtime | [docs/USAGE.md](docs/USAGE.md) |
| Inspect runtime evidence | [docs/INSPECTOR.md](docs/INSPECTOR.md) |
| Understand architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Compare with adjacent tools | [docs/COMPARISONS.md](docs/COMPARISONS.md) |
| Read implementation details | [docs/DESIGN_AND_IMPLEMENTATION.md](docs/DESIGN_AND_IMPLEMENTATION.md) |
| Check runtime spec | [docs/RUNTIME_SPEC.md](docs/RUNTIME_SPEC.md) |
| Extend storage, tools, and adapters | [docs/EXTENSIBILITY.md](docs/EXTENSIBILITY.md), [docs/STORAGE.md](docs/STORAGE.md), [docs/ADAPTER_ROADMAP.md](docs/ADAPTER_ROADMAP.md), [docs/ADAPTER_CERTIFICATION.md](docs/ADAPTER_CERTIFICATION.md) |
| Configure Postgres, MySQL, or S3/MinIO | [docs/POSTGRES.md](docs/POSTGRES.md), [docs/MYSQL.md](docs/MYSQL.md), [docs/S3_MINIO.md](docs/S3_MINIO.md) |
| Prepare releases | [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md), [docs/VERSIONING.md](docs/VERSIONING.md) |
| Understand multi-language parity and Go install/use | [docs/LANGUAGE_QUICKSTART.md](docs/LANGUAGE_QUICKSTART.md), [go/README.md](go/README.md), [docs/MULTI_LANGUAGE.md](docs/MULTI_LANGUAGE.md), [docs/LANGUAGE_PARITY_MATRIX.md](docs/LANGUAGE_PARITY_MATRIX.md) |
| Read Chinese docs | [README.zh-CN.md](README.zh-CN.md), [docs/zh/README.md](docs/zh/README.md) |

## Repository layout

```text
src/agentledger/     Python reference runtime-core
tests/               unit, conformance, and integration-style tests
examples/            dependency-free examples and adapter facades
docs/                English documentation and runtime design docs
docs/zh/             Chinese primary reader path
contracts/           language-neutral runtime contract, semantic manifest, and conformance fixtures
go/                  Go native runtime-core package
typescript/          Node/TypeScript-compatible runtime-core package
rust/                Rust runtime-core package
migrations/          SQLite/Postgres/MySQL DDL and migration baselines
```

## Automated validation

```bash
PYTHONPYCACHEPREFIX=/tmp/agentledger-pycache PYTHONPATH=src python3 -m compileall -q src tests examples
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src PYTHONTRACEMALLOC=10 python3 -W default::ResourceWarning -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger contract export > /tmp/agentledger-contract.json
python3 -m json.tool /tmp/agentledger-contract.json >/dev/null
diff -u contracts/agentledger.runtime.v1.json /tmp/agentledger-contract.json
python3.11 scripts/check_language_parity.py
cd go && go run ./cmd/agentledger-go conformance
cd ../typescript && npm run conformance
cd ../rust && cargo run --quiet -- conformance
```

See [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) for the complete release gate.

## License

Apache-2.0. See [LICENSE](LICENSE).
