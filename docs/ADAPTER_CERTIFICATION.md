# Adapter Certification Checklist

AgentLedger core stays small by pushing concrete integrations into adapters. An adapter is compatible only if it preserves runtime invariants and can prove that through tests, evidence, and operational documentation.

## Adapter Classes

```text
StateStore adapter:
  stores runs, steps, events, leases, approvals, costs, Tool Ledger, artifacts

BlobStore adapter:
  stores immutable payloads and artifact blobs by content-addressed refs

Framework adapter:
  maps LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents SDK, or custom concepts into Runtime/AgentContext

Tool adapter:
  maps external tools/protocols such as MCP into ToolSpec and ToolGateway

Sandbox adapter:
  executes risky tools behind SandboxExecutor and SandboxPolicy

Observability adapter:
  translates evidence/trace spans to OTLP, LangSmith-style stores, or internal telemetry

Media/stream adapter:
  maps audio, video, frame, transcript, embedding, or external event-stream systems into durable refs and checkpoints
```

## Required Invariants

Every adapter must preserve:

```text
state commits require a valid lease token
stale workers cannot commit after recovery or cancellation
event log is append-only per run sequence
Tool Ledger owns idempotency for managed side effects
shadow/replay paths do not create real side effects
approval-required tools do not execute before approval
sandbox-required tools fail closed when isolation is unavailable
secrets are not expanded into evidence, trace, or artifact plaintext by default
media payloads stay behind durable refs and stream resume points are checkpointed before retry boundaries
```

## StateStore Certification

Required checks:

```bash
PYTHONPATH=src python3 -m agentledger state conformance --backend <backend>
PYTHONPATH=src python3 -m agentledger worker conformance --backend <backend> --concurrent
```

Certification evidence:

```text
DDL or schema migration files
transaction isolation assumptions
lease and fencing behavior under concurrency
schema migration rollout and rollback notes
backup/restore validation
failure mode documentation for network partitions, lock timeouts, and partial writes
```

## BlobStore Certification

Required checks:

```bash
PYTHONPATH=src python3 -m agentledger blob conformance --backend <backend>
```

Certification evidence:

```text
content-addressed ref format
immutability guarantees
large object and multipart behavior if supported
retention and lifecycle policy
encryption and IAM model
restore validation with historical refs
```

## Framework Adapter Certification

Required checks:

```text
framework run maps to AgentLedger run/session
framework step/node maps to Runtime.run_once-compatible callable
state/checkpoint data stays behind StateStore or artifact refs
framework tool calls can be routed through ToolGateway
direct tool/model SDK bypasses are documented or caught by lint examples
evidence export works for adapter-created runs
```

Recommended smoke:

```bash
PYTHONPATH=src python3 -m agentledger adapter conformance --kind python-function
PYTHONPATH=src python3 -m agentledger adapter conformance --kind langchain
PYTHONPATH=src python3 examples/autogen/basic_agent.py
PYTHONPATH=src python3 examples/crewai/basic_crew.py
PYTHONPATH=src python3 examples/langchain/basic_runnable.py
PYTHONPATH=src python3 examples/langgraph/basic_graph.py
PYTHONPATH=src python3 examples/openai_agents/basic_agent.py
PYTHONPATH=src python3 -m agentledger lint boundary examples
```

Available dependency-free fixture kinds:

```text
python-function
langgraph-node
langchain
crewai
autogen
openai-agents
llamaindex
semantic-kernel
```

These checks prove that an adapter can expose a run spec, return a `Runtime.run_once`-compatible callable, complete a local run, and produce exportable evidence. Exact optional packages should add their own framework-native smoke on top of this baseline.

## Tool and Sandbox Adapter Certification

Tool adapters must prove:

```text
ToolSpec input_schema and output_schema are explicit
risk_level is set deliberately
side_effect and idempotency_required are correct
external writes include a stable logical operation/idempotency key
errors are represented without hiding side_effect_unknown/PENDING_VERIFICATION states
context/resource reads are routed through ToolGateway when they affect agent inputs
```

Sandbox adapters must prove:

```text
SandboxPolicy is enforced or fail-closed
network/filesystem defaults are denied or minimal
metadata avoids leaking secrets
command-style execution rejects unsafe string commands unless explicitly allowed
boundary events are emitted for audit
```

## Media and Stream Adapter Certification

Media and stream adapters must prove:

```text
large payloads are stored as BlobStore refs or external durable URIs, not embedded in event payloads
MediaArtifact records include kind plus uri, content_ref, or blob ref
derived artifacts preserve lineage to source artifacts, blob refs, tool call ids, or event ids
EventStreamCheckpoint records include stream_id, consumer_id, and offset
stream consumers can resume from the last committed checkpoint without duplicate side effects
stream emitters use Tool Ledger idempotency for external writes
replay and evidence regression can validate refs/checkpoints without contacting media providers or stream brokers
sensitive media refs are redacted or access-controlled before evidence leaves the local environment
```

Recommended smoke:

```bash
PYTHONPATH=src python3 examples/media_stream/basic_media_stream.py
PYTHONPATH=src python3 examples/media_stream/managed_tool.py
PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/media_stream
PYTHONPATH=src python3 -m agentledger conformance
```

Certification evidence:

```text
supported media kinds and provider APIs
ref format and retention assumptions
lineage fields produced by derived tools
checkpoint offset semantics and duplicate-delivery handling
redaction/access-control policy for exported evidence
known limits for payload size, codec handling, and stream backpressure
```

## Observability Adapter Certification

Observability adapters should translate, not mutate, runtime evidence:

```text
TraceExporter or OTLPTraceExporter output is the source
payload refs stay refs unless explicit redaction policy permits expansion
trace IDs and span IDs remain stable for a run export
collector/network failures do not affect runtime state commits
```

## Certification Artifact

Each adapter package should publish a small certification bundle:

```text
adapter name and version
supported AgentLedger contract version
conformance command output
smoke test commands
known limitations
required external services
security assumptions
backup/restore notes if stateful
```

This does not make an adapter production-ready by itself. It gives users a concrete compatibility baseline and makes gaps explicit before pilots.

AgentLedger can generate a machine-readable starting bundle for official adapter profiles:

```bash
PYTHONPATH=src python3 -m agentledger adapter certify --kind postgres --adapter-version 1.3.0
PYTHONPATH=src python3 -m agentledger adapter certify --kind mysql --adapter-version 1.3.0 --out ./mysql-certification.json
PYTHONPATH=src python3 -m agentledger adapter certify --kind s3 --adapter-version 1.3.0 --out ./s3-certification.json
PYTHONPATH=src python3 -m agentledger adapter certify --kind langgraph --adapter-version 1.3.0 --package-name agentledger-langgraph
```

Supported built-in profiles:

```text
postgres
mysql
s3
mcp
docker
otel
langgraph
temporal
```

The generated bundle includes package metadata, contract version, conformance commands, smoke commands, required external services, security assumptions, known limitations, and a `production_validation` block.

For adapters that depend on real infrastructure, `production_validation.status` is intentionally `external-required`. That is not a failure. It means the local runtime has produced the certification contract, but a production claim still needs real credentials, service behavior, concurrency/load checks, and restore or rollback drills. P2-style production hardening must be backed by those external artifacts, not by local mocks alone.
