# Agent Harness Stack

AgentLedger 是面向 Agent Harness stack 的 runtime reliability layer。它本身不是完整 Harness 产品；当它和 planning、orchestration、observability、model access、tools、storage、sandbox infrastructure 等系统组合时，才构成更完整的生产 Agent Harness。

本文说明这些组件应该怎么组合，同时避免把 AgentLedger 做成 LangGraph、Temporal、Langfuse、LiteLLM、MCP、Kubernetes 或 eval platform 的重复实现。

## 分层地图

| Harness 层 | 典型系统 | AgentLedger 角色 |
|---|---|---|
| Agent workflow / planning | LangGraph、LangChain、CrewAI、AutoGen、OpenAI Agents SDK、自定义代码 | 用 durable state、policy、Tool Ledger、evidence、replay guarantee 包住 node 和 tool |
| Durable orchestration | Temporal、Ray、Kubernetes workers | 在 worker step 内提供 agent-specific lease、fencing、checkpoint、cancellation、cost/failure attribution、replay semantics |
| Observability / eval UI | Langfuse、LangSmith、OpenTelemetry、自定义 dashboard | 导出 structured events、evidence bundle、trace、cost、failure 和 correlation IDs |
| Tool/context protocol | MCP、internal tool servers、provider SDK tools | 在副作用发生前强制 schema、permission、approval、sandbox、idempotency、audit |
| Model gateway/router | OpenAI、Anthropic、Gemini、Bedrock、Ollama、LiteLLM、企业 gateway | 提供 runtime model-call contract、archived responses、budget/fallback/replay semantics 和 optional provider adapters |
| Execution environment | Docker、E2B、Kubernetes/gVisor、Firecracker、内部 sandbox | 定义 sandbox policy/result contract 和 fail-closed execution routing |
| State/artifacts | SQLite、Postgres、MySQL、S3/MinIO、内部存储 | 持久化 runtime metadata、state version、migration、blob ref 和 evidence ref，并通过 conformance 验证 |

## Minimal Harness

适合本地开发、示例和单进程应用。

```text
Agent code / simple framework
  -> AgentLedger Runtime
       -> SQLite StateStore
       -> LocalBlobStore
       -> ToolGateway / Tool Ledger
       -> evidence / replay / static debug export
```

它能证明：

- 每个 run 都有 durable state 和 events；
- tool call 经过 schema、policy、ledger 和 evidence；
- replay 可以检查历史 run，而不重复真实 model/tool side effect；
- 开发者可以用 CLI 或 static HTML export 调试。

它不覆盖：

- distributed scheduling；
- 生产 trace UI；
- 外部 model routing；
- managed sandbox infrastructure；
- 团队级 eval workflow。

## Durable Workflow Harness

适合长期运行、可重试、分布式的 Agent 工作。

```text
Temporal workflow
  -> activity: run LangGraph graph or custom agent step
       -> AgentLedger Runtime
            -> claim step / heartbeat / checkpoint
            -> call model or tool through runtime boundary
            -> commit state with lease and version checks
            -> export evidence
```

职责划分：

| 组件 | 负责 |
|---|---|
| Temporal | workflow lifecycle、queue、timer、generic retry、deployment topology |
| LangGraph 或自定义代码 | graph node、routing、planner logic、agent role |
| AgentLedger | agent-specific lease、fencing、Tool Ledger、evidence、replay、policy、approval、sandbox、cost/failure attribution |

关键边界：

Temporal 可以 retry 一个 workflow activity。AgentLedger 决定 agent step retry 时应该复用已有 tool result、阻止 stale worker、等待人工 verification，还是从 checkpoint 恢复。

## Observable Harness

适合团队需要 trace UI、debug、eval 或 prompt/model regression workflow 的场景。

```text
AgentLedger Runtime
  -> structured events
  -> evidence bundle
  -> cost/failure attribution
  -> OTLP / JSON / evidence export
       -> Langfuse / LangSmith / OpenTelemetry backend / custom dashboard
```

职责划分：

| 组件 | 负责 |
|---|---|
| AgentLedger | runtime evidence source of truth、side-effect ledger、replay-safe payload refs、policy decisions |
| Langfuse / LangSmith / OTel backend | trace storage、dashboard、scoring、prompt/version analytics、团队调试 |

AgentLedger 不应该变成完整 trace database。它应该导出足够结构化的 evidence，让 observability 工具能关联：

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

适合 Agent 调用 API、shell command、code tool、browser、database 或内部服务的场景。

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

AgentLedger 负责执行路径上的保证：

- 执行前 input schema validation；
- 副作用前 permission 和 approval；
- sandbox-required fail-closed；
- idempotency key 和 causal token；
- request/response refs；
- unknown side effect 的 pending-verification 状态；
- replay 时复用 archived tool result，而不是再次调用工具。

外部系统仍然可以负责 tool hosting、MCP server lifecycle、credential vault、tool marketplace 或 service-specific SDK。

## Model-Governed Harness

这是 roadmap 能力。目标形态是：

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

AgentLedger 应负责：

- model-call events；
- selected provider/model records；
- request/response refs 和 redaction；
- 调用前 budget checks；
- fallback/failure semantics；
- archived-response replay。

Provider SDK 和 routing engine 应保持 optional adapters：

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

更完整的生产 Harness 可以长这样：

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

控制流和数据流：

```text
request_id / trace_id enters at product boundary
  -> Temporal workflow id
  -> LangGraph run/config id
  -> AgentLedger run_id / session_id / step_id
  -> model_call_id / tool_call_id / causal_token
  -> evidence_bundle_ref
  -> observability trace/export
```

在这套 stack 里：

- Temporal 提供外层 durable workflow execution。
- LangGraph 提供 graph topology 和 agent routing。
- AgentLedger 提供每个 agent step 内部的可靠执行边界。
- MCP/tool systems 提供外部能力。
- Model providers 或 routers 提供模型访问。
- Sandbox infrastructure 隔离危险执行。
- Postgres/MySQL 和 S3/MinIO 持久化 runtime metadata 与 evidence artifacts。
- Langfuse/LangSmith/OpenTelemetry 提供团队可见的 trace 和 eval surface。

## 集成规则

1. 一个 run 必须在多个系统之间有稳定标识：`run_id`、`session_id`、`step_id`、`trace_id` 和外部 workflow id 应该关联起来，而不是每一层独立发明一套 ID。
2. 有副作用的工具如果需要 audit、idempotency、approval、sandbox 或 replay guarantee，就必须进入 AgentLedger ToolGateway。
3. `ModelGateway` 实现后，model call 应进入 runtime model boundary；在此之前，provider call 至少应作为 evidence/cost artifact 记录。
4. 通用 workflow retry 不应该绕过 AgentLedger 的 lease、Tool Ledger 或 checkpoint semantics。
5. Observability 工具应该消费 AgentLedger evidence，而不是重新执行工具，或把 trace 当成副作用的 source of truth。
6. Storage adapter 在作为生产 runtime metadata store 使用前，必须通过 StateStore/BlobStore conformance。
7. UI 工具应从 read-only 开始。dashboard 修改 runtime state 需要单独设计 permission、approval 和 audit。

## AgentLedger 不应该变成什么

AgentLedger 不应该变成：

- 完整 graph planner；
- 通用 workflow engine；
- Langfuse/LangSmith 替代品；
- 完整 eval platform；
- RAG 或 vector memory platform；
- model marketplace 或 billing system；
- hosted sandbox platform；
- SaaS 或多租户 app platform。

长期方向是让 AgentLedger 成为 reliability substrate：用户可以用成熟组件组装 Harness stack，同时不丢失 durable execution、governance、evidence、replay 和 side-effect safety。
