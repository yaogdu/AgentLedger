# 扩展模型

本文是 `../EXTENSIBILITY.md` 的中文主路径版本，说明 AgentLedger 如何通过 adapter 扩展，而不污染 runtime-core。

## 设计原则

```text
Core owns protocol and invariants.
Adapters own integration details.
No adapter should pollute runtime core.
Python is the reference implementation, not the protocol boundary.
If core is not the only layer that can enforce the guarantee, prefer an adapter.
```

中文解释：

```text
core 负责协议、状态语义、Tool Ledger、replay、evidence 和不变量。
adapter 负责具体框架、存储、sandbox、observability、MCP、media/stream 等外部系统。
如果某个保证不必须由 core 才能强制执行，优先做 adapter。
```

AgentLedger 应保持“薄但不可替代”的 core。它不重做成熟的 planning、workflow、observability、eval、RAG、sandbox 或 deployment 系统；它定义这些系统接入 runtime boundary 的方式，以及证明它们没有破坏 runtime invariants 的 conformance checks。

## Adapter 成熟度模型

每个扩展点都应该显式拆成三层：

```text
Core contract
  接口、事件形状、状态转换、失败语义和不变量。

Built-in minimal implementation
  dependency-free 的参考行为，足够支撑本地开发、example、test 和简单部署。

Optional production adapter
  对接成熟外部系统，提供更强隔离、更强规模能力或 framework-native 行为。
```

示例：

| 领域 | Core contract | Built-in minimal implementation | Optional production adapter |
|---|---|---|---|
| Storage | `StateStoreProtocol`、migration、lease/fencing invariants | SQLite WAL + local blob store | Postgres、S3/MinIO、自定义 store |
| Sandbox | `SandboxPolicy`、`SandboxExecutor`、fail-closed routing、audit/evidence | fail-closed `none`、local executor、dry-run manifest | Docker、E2B、bubblewrap、Kubernetes/gVisor、Firecracker |
| Observability | structured event、evidence link、trace span shape | JSONL 和 OTLP/JSON export | OpenTelemetry SDK、collector recipe、trace store |
| Policy | capability check、approval、pre/postcondition hook | YAML/JSON role-capability policy | OPA、Cedar、内部 policy service |
| Framework | `FrameworkAdapter`、`AgentContext`、`ToolGateway` boundary | plain Python 和 dependency-free facade | framework-native package 和 smoke fixture |
| Media/Stream | durable ref、metadata、lineage、stream cursor | artifact contract 和 tool schema convention | codec、transcription、frame extraction、stream transport |

## 扩展点

| 层 | 接口 | 常见实现 |
|---|---|---|
| State | `StateStore` | SQLite WAL, Postgres, custom store |
| Blob | `BlobStore` | local fs, S3, MinIO, object store |
| Tools | `ToolExecutor` | local function, HTTP, MCP, sandbox executor |
| Policy | `PolicyEngine` | YAML, RBAC, ABAC, OPA/Cedar adapter |
| Sandbox | `SandboxExecutor` | none, local, Docker, bubblewrap, Kubernetes/gVisor, Firecracker, E2B |
| Framework | `FrameworkAdapter` | LangGraph, CrewAI, AutoGen, LangChain, custom |
| Worker | `WorkerProtocol` | Python SDK, TS client, JSON-RPC, gRPC, HTTP |
| Observability | `TraceExporter` | JSONL, OpenTelemetry, custom trace store |
| Media/Stream | `MediaArtifact`, `EventStreamCheckpoint` | audio/video/frame refs, stream chunk refs |

## Framework Adapter

一个 framework adapter 应该把框架概念映射到 AgentLedger 对象：

```text
framework run -> AgentLedger run/session
framework node/step -> Runtime.run_once-compatible callable
framework tool -> ToolSpec / ToolGateway
framework checkpoint -> StateStore / artifact refs
```

adapter 不应该绕过 ToolGateway 执行有副作用的工具。

## Storage Adapter

Storage adapter 必须保留：

```text
lease token fencing
state version check
append-only event ordering
Tool Ledger idempotency
approval-before-execution
cancellation fencing
```

Redis/cache/queue 可以辅助调度，但不应成为 durable state 的唯一事实来源。

## MCP Adapter

MCP 应放在 ToolGateway 后面：

```text
Agent
  -> Runtime ToolGateway
  -> Policy / Ledger / Audit / Sandbox
  -> MCP Client
  -> MCP Server
  -> External Resource
```

MCP 标准化 tool/context，AgentLedger 增加 policy、audit、idempotency、side-effect handling 和 replay safety。

## Media 和 Stream Adapter

runtime-core 只保存：

```text
durable media refs
metadata
lineage
stream offsets
watermarks
partial result refs
```

adapter 负责：

```text
capture
decode
transcribe
extract frames
summarize
embed
consume/emit stream
backpressure integration
```

media/stream 工具约定：

```text
audio.transcribe
video.extract_frames
frame.describe
video.summarize
stream.consume
stream.emit
```

这些是约定，不是强制内置实现。

## Runtime Boundary Lint

`agentledger lint boundary` 是 best-effort AST 检查，用来发现直接绕过 runtime 的常见调用，包括 shell、HTTP、云 SDK、GitHub SDK，以及 OpenAI、Anthropic、LiteLLM、Google GenAI、Mistral、Cohere、Groq、Ollama、Vertex AI 等 model SDK：

```bash
PYTHONPATH=src python3 -m agentledger lint boundary ./examples ./my_agents
PYTHONPATH=src python3 -m agentledger lint boundary ./my_agents --exclude .venv --no-fail
PYTHONPATH=src python3 -m agentledger lint boundary ./my_agents --rules examples/lint/boundary_rules.json
PYTHONPATH=src python3 -m agentledger lint boundary ./my_agents --rules examples/lint/boundary_rules.json --replace-defaults
```

项目可以通过 dependency-free JSON rule pack 补充自己的规则。每条规则包含 `rule_id`、`pattern`、`category`、`message`、`suggestion`，以及可选的 `prefix`。默认会把自定义规则追加到内置规则；`--replace-defaults` 表示只使用传入的规则包。

它不是安全 sandbox，但能在开发和 CI 中提前暴露常见 bypass。

## Conformance

adapter 应尽量通过对应 conformance：

```bash
PYTHONPATH=src python3 -m agentledger state conformance --backend sqlite
PYTHONPATH=src python3 -m agentledger worker conformance --backend sqlite --concurrent
PYTHONPATH=src python3 -m agentledger blob conformance --backend local
PYTHONPATH=src python3 -m agentledger adapter conformance --kind langchain
```
