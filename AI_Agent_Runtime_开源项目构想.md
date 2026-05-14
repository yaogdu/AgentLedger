# AI Agent Runtime 开源项目构想

> 目标：把这个项目沉淀成一个 **面向长期运行 Agent 的 reliability runtime / durable execution layer**，而不是又一个多 Agent 聊天或 workflow 拼装框架。

相关架构图：`multi_agent_runtime_architecture.svg`

## 一句话定位

现有 Agent 框架多在解决“如何让 Agent 思考和协作”；这个项目解决“如何让 Agent 在生产环境长期、安全、可恢复地活下去”。

英文定位：

> Open runtime layer for reliable long-running AI agents.

更工程化的说法：

> A durable execution and reliability layer for production-grade AI agents.


## 项目目标

这里的目标不是“做完若干功能”，而是定义这个开源项目最终要证明什么、服务谁、在生态里占什么位置。

### North Star

把 Agent 从“能跑的逻辑流”升级为“可长期运行、可恢复、可审计、可回放、可治理副作用的生产级执行单元”。

一句话：

```text
Make AI agent execution durable, auditable, replayable, and safe by default.
```

中文：

```text
让 Agent 的执行默认具备持久化、审计、回放和安全治理能力。
```

### 核心产品目标

1. 让 Agent run 可以恢复

目标不是简单重试，而是：

```text
worker 崩溃、进程重启、任务中断后，runtime 能从上一个一致 checkpoint 继续执行，并拒绝旧 worker 的过期提交。
```

2. 让 Agent tool side effect 可控

目标不是承诺所有外部系统都 exactly-once，而是：

```text
每个 external_write 都有 ledger、idempotency key、audit event 和 side_effect_unknown 处理语义。
```

3. 让 Agent run 可以被解释和回放

目标不是只存日志，而是：

```text
给定 run_id，可以还原当时的 run spec、state、model/tool request/response、artifact、权限策略和失败点。
```

4. 让 Agent 变更可以被安全验证

目标是解决 prompt / workflow / model 变更恐惧：

```text
新版本可以在历史真实 evidence bundle 上 shadow run，对比 trace、结果、成本和风险，不产生真实副作用。
```

5. 让现有 Agent 框架低侵入接入

目标不是替代 LangGraph / CrewAI / OpenAI Agents SDK，而是：

```text
通过 checkpointer、tool wrapper、adapter、decorator，把 durable state、tool ledger、event log 和 replay 能力加到现有 Agent 应用里。
```

6. SDK 不限制接入框架

目标不是只支持 LangChain / LangGraph / CrewAI / AutoGen，而是提供 framework-agnostic runtime contract：

```text
任何框架、任何自研 Agent、任何普通 Python 函数，只要能通过 runtime protocol 提交 run/step/tool/state/event，就可以接入。
```

官方 adapter 只是降低集成成本，不能成为架构前提。

### 非目标

为了避免范围失控，第一阶段明确不做：

- 不做新的通用 Agent workflow framework。
- 不做新的大模型调用 SDK。
- 不做完整 memory 产品。
- 不做全功能 observability SaaS。
- 不承诺任意外部系统的严格 exactly-once side effect。
- 不一开始做复杂 UI，优先 CLI / SDK / adapter。
- 不把 Docker、Ray、Temporal、LangGraph 作为 core 强依赖。
- 不把 LangChain、LangGraph、CrewAI、AutoGen 等任何单一框架作为 SDK 前提。

### 目标用户

第一批目标用户不是所有 AI 开发者，而是已经遇到生产可靠性问题的人：

- 正在用 LangGraph / CrewAI / custom agent 的工程团队。
- 使用其它 Agent 框架或完全自研 Agent runtime 的团队。
- 做 AI coding agent、ops agent、research agent、企业自动化 agent 的团队。
- 需要审计、合规、权限隔离、可恢复任务的企业用户。
- 对工具副作用敏感的场景：邮件、工单、PR、部署、数据库写入、支付、文件删除。

### 成功标准

MVP 成功不是功能数量多，而是能用一个 demo 证明核心闭环：

```text
一个 Agent 调用有副作用工具后 worker 崩溃；
runtime 恢复任务；
不会重复执行外部副作用；
可以用 run_id replay / debug 这次运行；
可以看到 state diff、tool ledger 和 event timeline。
```

可以量化为：

- 5 分钟内跑通 quickstart。
- 1 个命令复现 crash recovery demo。
- 1 个命令查看 run timeline / state diff。
- LangGraph demo 只需少量配置即可接入 runtime checkpointer / tool gateway。
- 非 LangGraph 的普通 Python Agent 也能通过 decorator / protocol 接入。
- 所有 external_write 工具调用必须有 ledger 记录。
- deterministic replay 不触发真实 model/tool call。
- session_id / run_id / step_id 三层 ID 清晰，session state 可 versioned commit。
- quickstart 不依赖外部服务，默认本地可跑。
- 新 tool / state store / policy engine 可以通过插件接口接入。
- high-risk tool 默认被 policy / approval / ledger 保护。


## 项目质量目标：易用性、扩展性、安全性、企业级落地

这个项目不能只做成“架构正确”，还必须满足开源项目和企业落地的基本质量要求。

### 易用性目标

核心原则：先让开发者 5 分钟感受到价值，再逐步引导他们进入完整 runtime 约束。

易用性目标：

- 5 分钟跑通 quickstart。
- 1 个命令运行 crash recovery demo。
- 1 个命令查看 run timeline / state diff / tool ledger。
- 不要求用户一开始理解所有概念，只暴露最小 API。
- local-first：默认 SQLite + 本地文件存储，无需先部署服务。
- progressive adoption：可以先只接入 Tool Ledger / Event Log，再逐步接入 Scheduler / Replay / Policy。

推荐 DX 设计：

```python
@runtime.tool(side_effect="external_write", idempotency=True)
async def create_issue(title: str, body: str):
    ...

@runtime.agent(role="ResearchAgent")
async def run(ctx, state):
    result = await ctx.call_tool("create_issue", {"title": "...", "body": "..."})
    ctx.write_state_patch("issues", {"last_issue": result.id})
```

CLI 应该优先提供：

```bash
agentledger init
agentledger run examples/side_effect_idempotency
agentledger debug <run_id>
agentledger replay <run_id>
agentledger ledger <run_id>
agentledger doctor
```

易用性不是放弃边界，而是用 adapter、decorator、CLI 和默认配置降低进入成本。


### Framework-agnostic SDK 原则

SDK 的核心不能依赖任何上层 Agent 框架。它应该只定义最小 runtime contract：

```text
RunSpec
StepClaim
AgentContext
ToolRequest
ToolResult
StatePatch
MemoryProposal
ArtifactRef
RuntimeEvent
```

任何框架只要能映射到这些对象，就可以接入。

分层设计：

```text
runtime-core
  只包含协议、状态、事件、tool ledger、replay，不依赖上层框架

runtime-sdk-python
  提供 AgentContext、decorator、local runner、CLI

runtime-adapters
  按需支持 LangChain / LangGraph / CrewAI / AutoGen / OpenAI Agents SDK / LlamaIndex / Haystack / Semantic Kernel / PydanticAI / 自研框架

runtime-protocol
  JSON-RPC / gRPC / HTTP，支持非 Python worker 接入
```

官方 adapter 策略：

- 官方优先支持用户最多、价值最高的 adapter。
- 第三方框架通过 adapter interface 自行接入。
- Adapter 不能把框架特有概念泄漏进 core。
- Core 的测试不依赖任何具体 Agent 框架。

这条原则很重要：项目的价值是 runtime reliability，不是押注某个 Agent framework。

### 扩展性目标

核心原则：runtime core 稳定，外部能力插件化。

Core 不应该强绑定某个框架、存储、sandbox、模型或部署方式。扩展点应该从第一天定义清楚。

核心扩展接口：

| 扩展点 | 作用 |
|---|---|
| `StateStore` | SQLite / Postgres / external durable store |
| `EventStore` | SQLite / Postgres / Kafka / object log |
| `BlobStore` | local fs / S3 / GCS / MinIO |
| `ToolExecutor` | local function / HTTP / MCP / sandbox executor |
| `PolicyEngine` | YAML policy / OPA / Cedar / custom RBAC |
| `SandboxExecutor` | local / Docker / E2B / microVM |
| `ModelProvider` | OpenAI / Anthropic / local model / replay model |
| `FrameworkAdapter` | LangChain / LangGraph / CrewAI / AutoGen / OpenAI Agents SDK / LlamaIndex / Haystack / Semantic Kernel / PydanticAI / custom |
| `WorkerProtocol` | Python SDK / JSON-RPC / gRPC / HTTP worker |
| `TraceExporter` | local logs / OpenTelemetry / LangSmith-style backend |
| `EvalRunner` | rule-based / LLM judge / human review / regression suite |

扩展性边界：

- Core 定义协议和不变量。
- Plugin 实现具体后端。
- Adapter 负责接入现有 Agent 框架。
- Runtime 不依赖插件才能运行。
- 所有插件必须通过 conformance tests。

版本策略：

```text
0.x:
  API 可以调整，但 runtime invariants 要稳定。

1.0:
  稳定 AgentContext、Tool Registry、Event Schema、Ledger Schema、StateStore interface。
```

### 安全性目标

核心原则：Agent 不可信，外部内容不可信，模型输出不可信；所有高风险行为必须由 runtime 强制治理。

安全默认值：

- default deny：未授权工具默认不可调用。
- least privilege：按 run / role / step 授权最小 capability。
- no raw secret in prompt：secret 只能由 Credential Broker 使用。
- high-risk tool approval：高风险工具默认需要审批或显式 policy。
- side-effect ledger required：所有 external_write 必须进入 Tool Ledger。
- replay safe：replay / shadow mode 默认不产生真实副作用。
- untrusted content labeling：tool result / webpage / file content 默认视为不可信数据。

必须防的风险：

- prompt injection：外部内容诱导 Agent 忽略系统规则。
- tool injection：工具返回内容诱导 Agent 调高权限工具。
- secret exfiltration：Agent 或外部内容诱导泄露 token / key。
- confused deputy：低权限 Agent 借高权限 tool 完成越权动作。
- sandbox escape：shell/code/browser 工具逃逸执行边界。
- replay side effect：回放时重复创建 PR、发送邮件、写数据库。
- audit gap：危险动作发生但没有证据链。

安全模块：

```text
Capability Policy
  控制 role/run/step 能做什么

Tool Risk Classifier
  标记 read-only / external_write / destructive / sensitive

Credential Broker
  代管 secret，返回脱敏结果

Approval Gate
  高风险动作人工或 supervisor 审批

Sandbox Executor
  限制文件、网络、进程、资源、secret

Audit / Ledger
  所有请求、授权、结果、副作用都有证据
```

安全边界声明：

- MVP 不声称防住所有 sandbox escape。
- MVP 不声称能自动识别所有敏感数据。
- MVP 不承诺外部系统严格 exactly-once。
- MVP 必须保证 high-risk action 不绕过 Tool Gateway。

### 企业级落地目标

企业级不是口号，而是一组可验证能力。

生产候选版本至少需要：

- Postgres backend。
- schema migration。
- lease / fencing 并发测试。
- crash recovery 测试。
- Tool Ledger 幂等测试。
- `PENDING_VERIFICATION` / `side_effect_unknown` 处理。
- audit log 完整性测试。
- replay 一致性测试。
- state patch conflict 测试。
- policy / permission 测试。
- OpenTelemetry exporter。
- retention / compaction / snapshot 策略。
- backup / restore 文档。
- security threat model。
- failure injection suite。
- semver release 和 changelog。

企业级 SLO 可以先这样定义：

```text
Replayability:
  high-risk run 的 deterministic replay 成功率接近 100%。

Ledger Safety:
  external_write 工具必须 100% 有 ledger 记录。

Recovery:
  worker crash 后可以从 last committed checkpoint 恢复。

Auditability:
  每个 high-risk action 都能追溯到 run_id、agent、policy、approval、tool result。
```

### 开源项目标准

达到“像样的开源项目”，至少需要：

```text
README.md
LICENSE
Quickstart
Architecture doc
Examples
API docs
Contributing guide
Code of conduct
CI
Unit tests
Crash recovery integration test
Security policy
Release notes
Roadmap
```

第一版 README 必须把价值说清楚：

```text
AgentLedger does not make your agent smarter.
It makes your agent execution durable, auditable, replayable, and safe.
```

### 项目路线和目标的关系

Phase 不是目标，只是达成目标的路径：

```text
目标：Agent execution durable / auditable / replayable / safe

Phase 1:
  证明最小闭环：AgentContext + Event Log + Tool Ledger + Replay + SQLite

Phase 2:
  证明生产语义：Postgres + lease/fencing + cancellation + failure taxonomy

Phase 3:
  证明可靠性闭环：repro + eval + time travel + shadow mode

Phase 4:
  证明生态价值：LangGraph / OpenAI Agents / Temporal / Ray adapters
```

## 核心价值：从逻辑流到状态机

LangGraph、CrewAI、AutoGen、OpenAI Agents SDK 等框架主要表达 Agent 的 logic flow：

- 下一步谁执行
- 调哪个工具
- 哪个 Agent 接手
- 怎么组织 prompt / role / workflow

这个 runtime 的核心是把 Agent 执行变成受保护的 durable state machine：

```text
load checkpoint
  -> acquire lease
  -> execute one step
  -> call model/tool through runtime
  -> append events
  -> propose state patch
  -> atomic commit
  -> yield / wait / retry / complete
```

关键不是“Agent 会不会想”，而是：

- worker 崩了能不能恢复
- 同一个 step 会不会被重复执行
- 外部副作用会不会重复发生
- 状态提交是否原子、可审计、可 replay
- 权限、secret、sandbox 是否由 runtime 强制执行
- token / cost 是否能在运行中被控制
- 新版本上线前能否 shadow / eval / regression

这个项目更接近 Temporal / Erlang OTP 的思想：业务逻辑不是裸跑，而是运行在一层有状态、有恢复语义、有审计证据的 runtime 里。

## 核心价值链：Durable Execution 闭环

这个项目的技术护城河不是单点功能，而是四个机制组合成闭环：

```text
Isolation
  AgentContext 把 Agent 关进 runtime boundary，Worker 只是临时执行载体。

Determinism
  Event-level WAL / archive 让已经发生的 model/tool/state 事件不可篡改、可回放。

Side-effect Governance
  Tool Gateway + Tool Ledger 把外部副作用变成可审计、可幂等、可确认的受控操作。

Reversibility
  Replay / Time Travel / Shadow Mode 让历史 run 可调试、可分叉、可做回归验证。
```

如果类比传统后端，这个项目是在给 Agent 执行补上类似事务、WAL、幂等表、审计日志和调试器的基础设施。Agent 领域现在很像“没有数据库事务保护的早期 Web 开发”，这个 runtime 试图给它建立一套生产语义。


## 架构生命周期

```text
Run Created
  -> Run Spec Frozen
  -> Scheduler creates Step / Continuation
  -> Worker claims Step with Lease
  -> Runtime loads State + Checkpoint
  -> Agent executes through AgentContext
  -> Runtime records Model / Tool / State / Artifact Events
  -> Runtime commits State Patch atomically
  -> Step yields / waits / retries / completes
  -> Evidence Bundle supports Replay / Repro / Eval / Attribution
```

基础状态机：

```text
created
  -> pending
  -> running
  -> waiting_tool / waiting_human / sleeping / retry_scheduled
  -> completed / failed / cancelled
```

## 核心抽象

| 抽象 | 含义 |
|---|---|
| Agent Definition | role、prompt、tools、model config、policy 的定义 |
| Logical Run / Agent | 某次任务中的逻辑 Agent 实例，拥有状态、目标、执行历史 |
| Step / Continuation | 可调度、可恢复、可重试的最小执行单元 |
| Agent Worker / Replica | 物理执行进程，只是临时执行载体 |
| AgentContext | Agent 唯一行动入口，封装 model/tool/state/memory/artifact |
| Run State | 当前 run 的任务状态、checkpoint、state version |
| Shared State | 多 Agent 协作的结构化任务状态 |
| Memory | 跨 run 的长期知识，需要治理和版本化 |
| Tool Registry | 工具 schema、risk、permission、approval、version |
| Tool Gateway | 工具调用唯一入口，做校验、授权、审计、sandbox、幂等 |
| Tool Ledger | 副作用工具的幂等账本，防止重复外部写入 |
| Event Log | append-only 事件日志，支持 replay / audit / attribution |
| Run Evidence Bundle | run spec、event log、trace、archive、state、artifact 的统一证据包 |

## 和普通 Agent 框架的差异

| 功能维度 | 普通 Agent 框架 | 这个 Agent Runtime |
|---|---|---|
| 状态持有 | 内存变量 / 简单 session | durable checkpoint / WAL / versioned state |
| 工具调用 | 直接通过 SDK 调用 | managed Tool Gateway，带 audit + idempotency |
| 崩溃恢复 | 重新开始整个 task 或依赖框架局部恢复 | 从 last successful step / checkpoint 恢复 |
| 副作用 | 可能重复执行，需要应用层自管 | Tool Ledger 管 logical side effect once-only |
| 成本控制 | 运行后统计为主 | in-flight budget enforcement |
| 权限控制 | prompt 约束或简单 allowlist | runtime-enforced capability + policy |
| 重放调试 | 重新运行逻辑，结果可能漂移 | deterministic replay from event log / archive |
| 上线验证 | 靠人工或普通 benchmark | replay regression / shadow mode / eval harness |

## 架构边界

重要边界：

- Agent 不能直接写数据库，只能提交 `state patch`。
- Agent 不能直接调用外部工具，只能请求 `ctx.call_tool()`。
- Agent 不能直接持有 secret，secret 由 `Credential Broker` 代管。
- Agent 不能直接写长期 memory，只能 `ctx.propose_memory()`，再经过 review / commit。
- Worker 不是权威状态持有者，权威状态在 durable store。
- Scheduler 不理解 prompt，只看调度视图：status、lease、dependency、budget、capability。
- Tool Gateway 不负责业务规划，只负责工具治理和副作用边界。
- Replay / shadow mode 不能真实执行有副作用工具，应读取历史 archive / ledger。


## 调度与 Session 管理

这张架构图里的调度层、Run Creation、Logical Run / Agent、Run State Store、Memory Store 都非常适合进入项目文档。它们是 runtime core 的一部分，不是外围功能。

### 调度模型

调度要区分两层：

```text
Agent / Product Orchestration
  业务上下一步做什么：拆任务、派角色、合并结果、发起 review。

Runtime Scheduling
  工程上由谁在什么时候执行：claim step、lease、worker 选择、retry、resume、cancel。
```

这个项目主要负责第二层，但要给第一层提供稳定协议。

Scheduler 不应该理解 prompt，也不应该参与业务推理。它只看调度投影：

```text
run_id
step_id
session_id
status
owner
lease_token
lease_until
attempt
priority
required_capabilities
dependencies
budget_remaining
checkpoint_id
state_version
next_wake_condition
retry_policy
cancellation_state
```

调度对象不只是“新任务”，还包括中间态 continuation：

```text
start_run
continue_from_checkpoint
resume_after_tool_result
resume_after_human_approval
retry_failed_step
wake_sleeping_step
aggregate_child_results
cancel_branch
```

核心不变量：

```text
同一个 step 同一时间最多一个有效 owner。
旧 owner 不能提交过期结果。
调度器只调度可运行 step，不调度 waiting / blocked / cancelling step。
retry 必须有上限，且必须保留 failure event。
```

### Step 状态机

最小 step 状态：

```text
created
  -> pending
  -> claimed
  -> running
  -> waiting_tool
  -> waiting_human
  -> sleeping
  -> retry_scheduled
  -> completed
  -> failed
  -> cancelled
```

`running` 到 `completed` 之间必须经过 runtime commit：

```text
check lease
check fencing token
check state base_version
apply state patch
append event
update checkpoint
schedule next intent
```

### Manager / Worker 架构

如果使用 Manager / Worker 术语，可以这样定义：

```text
Manager:
  维护 run/session 的调度视图，决定哪些 step 可运行，分配 worker，处理 retry/cancel/resume。

Worker:
  临时执行载体，拿 lease 后加载 checkpoint，通过 AgentContext 推进一步，然后 yield 给 runtime。
```

Manager 不应该持有权威业务状态；权威状态在 durable store。Worker 更不应该持有权威状态。

### Session 管理

Session 不是简单 chat history。它是用户、渠道、会话、多个 run、长期 memory 之间的关联层。

需要明确区分：

```text
Session:
  用户/渠道维度的会话容器，可能跨多个 run。

Run:
  一次具体任务执行，有 run spec、状态机、event log。

Step:
  run 内可调度的执行单元。

Memory:
  跨 session / run 的长期知识，需要治理。

Artifact:
  文件、报告、代码、tool result、model payload 等内容寻址产物。
```

Session State 至少包括：

```text
session_id
user_id / tenant_id
channel: api / web / telegram / whatsapp / matrix
external_conversation_id
active_run_ids
last_run_id
message_refs
conversation_summary
session_variables
capability_grants
memory_refs
artifact_refs
session_version
retention_policy
```

Session 管理要解决：

- 同一个用户多条消息并发到达时，如何排序和去重。
- webhook duplicate delivery 如何处理。
- 同一个 session 是否允许多个 active run 并行。
- 新消息到达时是追加到已有 run，还是创建新 run。
- conversation history 如何压缩成 summary，避免上下文无限增长。
- session state 如何 versioned commit，避免 stale write。
- session 与 long-term memory 的边界，避免把临时对话误写入长期记忆。

### 通信渠道与 Session

WhatsApp、Telegram、Matrix 这类通信插件应该通过 channel adapter 接入 session：

```text
External Message
  -> Channel Adapter
  -> idempotency check by external_message_id
  -> append session event
  -> create or continue run
  -> Agent response
  -> outbound message ledger
```

关键点：

- external message id 必须映射到 runtime event id。
- inbound/outbound message 都要有幂等记录。
- channel token / secret 不进入 Agent context。
- channel rate limit 和 backpressure 由 adapter/runtime 控制。
- replay 时不能真的重复发送消息。

### Session 与 Evidence Bundle

Session 也要进入证据链，但不能把所有历史消息都塞进 event 表。

推荐：

```text
Event Log:
  存 message received / message sent / summary updated 等结构化事件。

Blob Store:
  存完整消息 payload、附件、原始 webhook body。

Session Snapshot:
  定期保存 conversation summary、active runs、message refs。

Evidence Bundle:
  记录本次 run 使用了哪个 session snapshot 和哪些 message refs。
```

这样既能 replay，又不会让 session history 无限膨胀。

### 调度与 Session 的 MVP 范围

MVP 不需要一开始支持复杂多渠道，但应该把接口留好：

```text
Phase 1:
  单 session / 单 run / SQLite / local worker
  支持 session_id、run_id、step_id、event log

Phase 2:
  session version、message refs、conversation summary、active runs
  支持 webhook duplicate delivery demo

Phase 3:
  Matrix / Telegram adapter
  多 run 并发策略、session-level conflict handling
```

## 技术选型倾向

### 语言：Python first，协议语言无关

MVP 首选 Python：

- AI / Agent 生态主要在 Python，例如 LangGraph、LangChain、LlamaIndex、OpenAI SDK。
- 开发者认知成本低，demo 和 adapter 更容易做。
- eval、replay、tool wrapper、sandbox demo 都更容易落地。

但核心协议不要绑定 Python 对象语义。`AgentContext` 应该被定义成标准 API / protocol，未来允许 worker 通过 JSON-RPC、gRPC 或 HTTP 与 runtime 通信。

```text
Runtime Core:
  Python first

Agent Worker:
  Python SDK first
  later: TypeScript / JVM worker via protocol
```

### State Store：BaseStateStore + SQLite WAL MVP

先定义接口：

```python
class BaseStateStore:
    async def create_run(self, spec): ...
    async def claim_step(self, worker_id, capability): ...
    async def heartbeat(self, lease_token): ...
    async def load_state(self, run_id): ...
    async def commit_state_patch(self, patch, lease_token, base_version): ...
    async def append_event(self, event): ...
```

MVP 先实现 SQLite：

- 本地零配置，适合开源项目上手。
- 支持事务。
- 开启 WAL 模式后足够支撑单机开发和小规模并发。

后续插件：

- Postgres：生产持久化和多 worker 并发。
- Redis：只适合作 queue / cache / lease 辅助，不建议作为唯一权威状态。
- Object Store：保存 request / response blob、artifact、archive。

### Replay 粒度：event-level

Replay 应该做到事件级，而不是 step 级。

原因：

- 一个 step 内可能有多个 model/tool call。
- 失败可能发生在 step 中间。
- tool call 成功但 state commit 失败是关键恢复场景。
- deterministic replay 需要逐个返回历史 model/tool response。

最小事件集合：

```text
run_created
step_claimed
agent_started
model_call_requested
model_call_completed
tool_call_requested
tool_permission_decided
tool_call_completed
state_patch_proposed
state_committed
artifact_created
error_raised
run_completed
run_failed
run_cancelled
```

### Tool Ledger：引入 Causal Token

可以区分三个 ID：

```text
tool_call_id:
  每次具体尝试一次工具调用都有一个

idempotency_key:
  同一个 logical side effect 的稳定幂等键

causal_token:
  runtime 生成的因果令牌，把 tool request 与 step/event/state version 绑定
```

`causal_token` 不应该只是随机 ID，应该编码最小因果上下文，类似 Lamport clock / fencing token 的工程用途：

```text
causal_token = {
  run_id,
  step_id,
  attempt,
  state_version,
  event_seq,
  lease_token
}
```

Tool Gateway 在执行前校验：

```text
当前 step lease 是否仍然有效
当前 state_version 是否仍匹配
event_seq 是否在当前 run 的因果链上
attempt 是否已经过期
```

这样旧 worker、旧 retry、旧 Agent 逻辑即使恢复，也不能继续提交过期的 tool request。

对于不支持幂等的 legacy API，runtime 需要通过 Tool Ledger 和 wrapper 尽量模拟幂等：

```text
reserve ledger row
  -> execute external call
  -> record external_id / response
  -> retry returns archived result
```

如果出现 `side_effect_unknown`，必须进入人工确认或补偿流程，不能盲目重试。

建议把外部副作用状态显式化：

```text
RESERVED
  -> RUNNING
  -> SUCCEEDED
  -> FAILED_NO_EFFECT
  -> PENDING_VERIFICATION
  -> COMPENSATED
```

其中 `PENDING_VERIFICATION` 用来处理最棘手的情况：外部工具超时、网络断开、5xx、worker crash，导致 runtime 不知道副作用是否已经发生。

这类状态不能自动重试，应该：

- 挂起当前 step，进入 `waiting_human` 或 `waiting_verification`。
- 触发 Tool Circuit Breaker，短时间内限制同类高风险工具调用。
- 通过 external_id 查询、人工确认或补偿工具来确定结果。
- 确认后再把 ledger 标记为 `SUCCEEDED`、`FAILED_NO_EFFECT` 或 `COMPENSATED`。

### Policy Engine：MVP 用 YAML policy

第一版不建议直接接 OPA / Cedar，否则上手门槛太高。

MVP 可以用 YAML-based policy：

```yaml
roles:
  ResearchAgent:
    tools:
      allow:
        - web.search
        - docs.read
    state:
      read:
        - task_graph
      write:
        - findings.candidates
    memory:
      read:
        - project_memory
      propose:
        - long_term_memory
```

后续再提供 OPA / Cedar adapter。

### Sandbox：core 只定义接口，executor 插件化

MVP 不要把 Docker / E2B / Firecracker 强绑定进 core。

先定义：

```python
class SandboxExecutor:
    async def execute(self, tool, args, sandbox_policy): ...
```

插件可以包括：

- local process executor：本地开发。
- Docker executor：隔离 shell / code。
- E2B executor：云端 sandbox。
- microVM executor：高风险不可信代码。

### State Patch：JSON Merge Patch / JSON Patch

Agent 并发 tool call 或多分支执行时，state patch 合并是高风险点。

第一版建议：

- 普通对象更新用 JSON Merge Patch。
- 精确数组/路径操作用 JSON Patch。
- 提交时必须带 `base_version`。
- version mismatch 时拒绝提交或进入 merge conflict。
- 不允许 Agent 直接覆盖整块 shared state。

## MVP 范围

第一版不要做成完整大平台，先做一个小而硬的 runtime core。

### 1. AgentContext

```python
class AgentContext:
    async def call_model(self, request): ...
    async def call_tool(self, tool_name, args): ...
    def write_state_patch(self, key, patch): ...
    def propose_memory(self, memory_candidate): ...
    async def create_artifact(self, content, metadata): ...
    def yield_(self, reason, next_intent=None): ...
```

### 2. State Store

保存：

- runs
- steps
- state snapshots
- state versions
- checkpoints
- lease / owner / heartbeat

### 3. Scheduler / Lease

实现：

- atomic claim
- lease token
- heartbeat
- fencing token
- retry policy
- step status machine

核心不变量：

```text
同一个 step 同一时间最多只有一个有效 owner。
旧 owner 即使恢复，也不能提交过期结果。
```

### 4. Event Log

所有 model/tool/state/error/cost 事件结构化记录，作为 replay、audit、attribution 的基础。

### 5. Tool Registry / Gateway

每个工具必须注册：

```yaml
name: github.create_pr
version: v1
input_schema: ...
output_schema: ...
side_effect: external_write
risk_level: medium
required_permissions:
  - github:repo:write
requires_approval: false
idempotency_required: true
timeout_seconds: 30
```

调用链：

```text
Agent requests tool
  -> schema validation
  -> policy check
  -> budget check
  -> approval gate if needed
  -> sandbox / executor
  -> audit log
  -> tool ledger
  -> sanitized result
```

### 6. Tool Ledger

治理有副作用工具：

```text
github.create_pr
email.send
db.write
payment.charge
file.delete
```

用 `idempotency_key` 防重复：

```text
idempotency_key = run_id + step_id + logical_operation
```

核心不变量：

```text
同一个 logical side effect 最多成功一次。
任何 external_write 必须先 reserve ledger，再执行外部调用。
任何 side_effect_unknown 不能自动重试，必须被标记、审计、确认。
```

### 7. Replay Engine

先做 deterministic replay：

- model call 返回历史 response
- tool call 返回历史 response
- state transition 按 event log 重放
- 对比 state hash / artifact hash

目标不是让 LLM 每次字节级一致，而是让一次历史 run 可以被还原、审计和调试。

## Reliability Loop

后续应该把运行证据统一成 `Run Evidence Bundle`：

```text
Run Evidence Bundle
  - run spec
  - workflow version
  - agent definition version
  - prompt version
  - policy snapshot
  - tool registry version
  - memory snapshot
  - state snapshot
  - event log
  - trace
  - model request / response archive
  - tool request / response archive
  - artifact refs
  - cost records
  - failure records
```

基于这份证据包做：

- Replay Engine：还原历史运行。
- Repro Harness：受控重跑和 divergence detection。
- Eval Harness：质量、安全、可靠性、成本评估。
- Failure Attribution：失败分类和根因归因。
- Cost Attribution：token/tool/worker 成本归因。
- Adversarial Review：上线前风险检查。

## 差异化功能构想

### Time Travel Debugger

第一版如果能提供 CLI-based Time Travel Debugger，会非常有辨识度：

```bash
agentledger debug <run_id>
```

展示一条垂直事件线，允许开发者 step back 到任意一个 model/tool/state event，并查看事件前后的 state diff：

```text
event 12 前的 state
event 12 的 model request
event 13 的 model response
event 14 的 tool call
event 15 后的 state diff
```

进一步可以支持：

- 从任意 event 查看 state diff。
- 查看 artifact lineage。
- 查看 tool side effect ledger。
- 从某个历史点 fork 出一条新 run。

这个能力会让项目从“日志系统”变成真正的 Agent debugger。

### Shadow Mode

新版本 Agent Logic 上线前，不直接影响生产结果，而是读取生产 run 的 evidence bundle 做影子执行。

```text
production run event log
  -> old version produced output A
  -> new version in shadow mode produces output B
  -> diff A/B
  -> no real side effect
```

用途：

- prompt / tool / policy 变更回归验证。
- 新模型替换前评估行为漂移。
- 新 workflow 上线前比较成本和质量。
- 高风险工具调用在 shadow mode 中强制 stub。

### LangGraph Adapter

这是一个关键增长入口。

目标是让 LangGraph 用户尽量低成本接入：

```text
把 LangGraph checkpointer / store 替换为 RuntimeStateStore
把 tool node 包到 ToolGateway
把 graph run 事件映射到 Event Log
```

理想卖点：

```text
一行接入 durable state + tool audit + replay evidence
```


## 工程挑战与对策

### Performance Overhead

每一次 model/tool/state 操作都要写 WAL、校验 policy、检查 ledger、记录 audit，必然有延迟和吞吐开销。

对策：

- `Batching Patch`：AgentContext 支持一次提交多个 state patch。
- `Buffered Event Writer`：低风险事件可批量 flush，但关键 side effect ledger 必须同步提交。
- `Policy Cache`：对同一 run / role / tool 的授权结果短期缓存。
- `Selective Capture`：MVP 默认全量 capture，生产可按风险等级采样非关键 payload，但 side effect 不能采样。
- `Async Archive`：大 request / response blob 可先落本地 WAL，再异步上传 object store。

### DX Friction

强迫开发者只能用 `ctx.call_tool()`，不能直接 `requests.get()`、`os.system()`、SDK client 调外部服务，会带来心智负担。

对策：

- 提供很顺手的 SDK，让 `ctx.call_tool()` 比裸 SDK 更省事。
- 提供 lint：扫描 Agent 代码里绕过 runtime 的外部调用。
- 提供 monkey patch / wrapper：可选拦截常见 SDK，例如 `requests`、`openai`、`subprocess`。
- 提供 adapter：LangGraph / OpenAI Agents SDK 用户不需要大改业务代码。
- 在文档里明确边界：MVP 先强约束核心 demo，后续再做低侵入迁移工具。

### Correctness vs Throughput

这个项目的核心卖点是 correctness / reliability，而不是极限吞吐。第一版应优先证明：

```text
崩溃不丢状态
重试不重复副作用
历史 run 可 replay
工具调用可审计
```

性能优化应该在这些不变量成立之后再做。

## Demo 场景

第一个开源 demo 可以做一个很有辨识度的可靠性场景：

```text
1. Agent 执行任务，需要调用 github.create_issue。
2. 工具调用已经成功创建 issue。
3. worker 在提交 state 前模拟 crash。
4. scheduler 重新调度 step。
5. 新 worker 从 checkpoint 恢复并重试。
6. Tool Ledger 发现同一个 idempotency_key 已成功。
7. 系统返回历史 issue，不创建第二个 issue。
8. Replay Engine 可以还原第一次发生了什么。
```

后续 demo：

- `time_travel_debugger_demo`：展示 event timeline 和 state diff。
- `shadow_mode_demo`：同一份历史 event log 对比新旧 Agent 输出。
- `langgraph_adapter_demo`：把 LangGraph workflow 接入 runtime state / event log / tool gateway。
- `prompt_injection_tool_governance_demo`：外部网页诱导高风险工具，runtime 拒绝执行。

## 项目结构草案

```text
agent-runtime/
  runtime/
    context.py
    agent.py
    run.py
    step.py
    session.py
    message.py
    result.py

  scheduler/
    claim.py
    lease.py
    worker.py
    retry.py
    projection.py
    wake.py

  state/
    sqlite_store.py
    postgres_store.py
    session_store.py
    checkpoint.py
    migrations.py

  tools/
    registry.py
    gateway.py
    ledger.py
    schema.py
    sandbox.py

  policy/
    engine.py
    manifest.py
    approval.py

  observability/
    event_log.py
    trace.py
    cost.py
    failure.py

  replay/
    engine.py
    diff.py

  evals/
    harness.py
    checks.py
    adversarial.py

  adapters/
    langgraph.py
    openai_agents.py

  protocol/
    jsonrpc.py
    grpc.py
    schemas.py

  communication/
    matrix.py
    telegram.py
    whatsapp.py

  blobstore/
    local.py
    s3.py
    minio.py

  examples/
    side_effect_idempotency/
    time_travel_debugger/
    shadow_mode/
    langgraph_adapter/
    node_ts_worker/
    mcp_github_tool/
    matrix_telegram_channel/
    research_agent/
    coding_agent/
```


## 工程能力映射：从 Runtime 到真实 AI 应用平台

图片里的岗位能力点非常适合纳入项目蓝图，但要放在正确层级：它们大多不是 runtime core，而是围绕 core 的 SDK、adapter、tool server、deployment 和 enterprise integration。

### 适合放进项目的能力点

| 能力点 | 在本项目中的位置 | 说明 |
|---|---|---|
| Manager / Worker 架构 | Runtime Scheduling / Worker Protocol | 对应 scheduler、lease、worker pool、heartbeat、fencing |
| 技能系统 / Skill System | Tool Registry / Capability Registry | 把工具、技能、权限、schema、版本统一注册 |
| 复杂会话状态管理 | Run State / Session State / Checkpoint | 对话、任务、agent state 都要 versioned + checkpoint |
| WhatsApp / Telegram 插件 | Communication Adapters | 作为外部 channel adapter，不进入 core |
| Matrix Protocol | Communication Protocol Adapter | 适合做去中心化消息通道和 multi-agent messaging demo |
| MCP Server | Tool / Context Server Adapter | 很适合做外部资源访问层，例如 GitHub、文件、数据库、浏览器 |
| GitHub 操作 | Managed Tool / MCP Tool | 必须经过 Tool Gateway + Ledger + Permission |
| 外部 API 对接 | Tool Gateway / Tool Executor | 统一 schema、policy、audit、retry、idempotency |
| Docker 容器化 | Sandbox / Deployment | local sandbox、worker isolation、demo deployment |
| CI/CD | Open Source Engineering / Enterprise Readiness | 测试、release、adapter conformance、security scan |
| 监控体系 | Observability / OpenTelemetry | trace、metrics、structured event、cost attribution |
| MinIO / S3 | BlobStore / Artifact Store | 保存 model/tool payload、artifact、evidence bundle |
| Node.js / TypeScript | SDK / Worker Protocol | 不作为 MVP core，但应支持 TS worker / SDK 接入 |
| 高并发网关 Higress | Enterprise Gateway Integration | 后期支持 gateway policy、rate limit、auth、traffic control |
| 冷启动优化 | Worker Pool / Sandbox Pool | worker container 预热、snapshot、sandbox reuse、TTL |
| 文档与支持 | Open Source DX | README、quickstart、architecture、troubleshooting |

### Node.js / TypeScript 的定位

虽然 MVP 可以 Python first，但这个项目不应该变成 Python-only。

图片里的岗位强调 Node.js / TypeScript，是因为很多 AI 应用、通信插件、Bot、前端 demo、企业集成服务都在 TS 生态里。项目应该把 TS 放在第二阶段的重要 SDK：

```text
Phase 1:
  Python SDK + framework-agnostic protocol

Phase 2:
  TypeScript SDK / Worker Client
  Node.js Tool Server SDK
  Communication adapter examples
```

TypeScript SDK 不需要一开始复制全部 runtime core，只要能通过 protocol 接入：

```text
create_run
claim_step
call_tool
append_event
write_state_patch
read_checkpoint
```

### 通信插件的定位

WhatsApp、Telegram、Matrix 不应进入 runtime core。它们应该是 channel adapter：

```text
External Channel
  -> Communication Adapter
  -> Runtime Run / Step / Event
  -> Agent Worker
  -> Tool Gateway / MCP Server
```

通信 adapter 需要关注：

- 消息收发实时性
- 去重和 idempotency
- channel-specific message id 到 runtime event id 的映射
- webhook retry 和 duplicate delivery
- 用户/session 到 run/session 的映射
- secret 和 token 管理
- rate limit 和 backpressure

这些能力和 runtime 的 event log / ledger 非常契合。

### MCP 的定位

MCP 很适合作为 tool / context 接入层，但 runtime 要在 MCP 之上补治理：

```text
Agent
  -> Runtime Tool Gateway
  -> Policy / Ledger / Audit / Sandbox
  -> MCP Client
  -> MCP Server
  -> GitHub / Files / DB / Browser / API
```

也就是说，MCP 负责标准化工具和上下文连接；AgentLedger 负责权限、审计、幂等、副作用和 replay。

第一批 MCP demo 可以是：

- GitHub MCP：创建 issue / branch / PR，但必须有 ledger。
- Filesystem MCP：只允许 workspace allowlist。
- Browser/Search MCP：结果归档，用于 replay。
- DB MCP：默认 read-only，write 需要 approval。

### 基础设施能力的定位

Docker、CI/CD、监控、MinIO/S3 都应该进入 enterprise readiness，而不是 runtime 业务逻辑。

推荐默认部署形态：

```text
Local Dev:
  SQLite + local blob store + local worker

Team Dev:
  Postgres + MinIO + worker deployment + OpenTelemetry

Production Pilot:
  Postgres HA + S3/MinIO + Kubernetes workers + sandbox executor + OTel backend
```

### 典型任务可以变成项目 Demo

图片里的“典型任务”很适合作为后续 examples：

1. 通信插件开发

```text
Telegram/Matrix message -> Runtime event -> Agent run -> reply message
```

重点验证：message idempotency、session state、event trace。

2. GitHub MCP Server

```text
Agent requests repo operation -> Tool Gateway -> GitHub MCP -> Tool Ledger -> Replay
```

重点验证：repo write permission、PR/issue 幂等、side_effect_unknown。

3. Worker 冷启动优化

```text
fresh container: 45s
pooled/snapshot worker: 15s
```

重点验证：sandbox pool、worker prewarm、TTL、taint flag。

## 可以集成但不依赖的外部框架

这个项目最好是 framework-agnostic，可以和现有生态共存。

可选集成：

- LangChain：chain / tool / agent 生态。
- LangGraph：复杂状态图和 Agent workflow。
- OpenAI Agents SDK：Agent / tool / tracing 生态。
- CrewAI：role/task/crew 风格编排。
- AutoGen：multi-agent conversation / event-driven agents。
- LlamaIndex：RAG / agent workflow / data agent 场景。
- Haystack：search / RAG pipeline 场景。
- Semantic Kernel：企业 .NET / planner / plugin 生态。
- PydanticAI：类型安全 Python Agent 场景。
- MCP：tool / context server 协议。
- Temporal：durable workflow、long-running job、retry、timeout。
- Ray：分布式 Python worker / actor。
- Kubernetes：部署、扩缩容、资源隔离。
- OpenTelemetry：trace / metrics。

定位上不要直接替代它们，而是补可靠性 runtime 层。任何 adapter 都应该是可选包，不能污染 core。

## 夹缝生存策略：不争地盘，只做可靠性插件

这个项目不要和 LangGraph、Ray、Temporal 正面对抗。更好的战略是：做它们缺失的 reliability layer。

对 LangGraph 用户：

```text
让你的 Graph 拥有银行级可靠性。
```

落地形式：

- `AgentLedgerCheckpointer`：替换默认 checkpointer，提供 versioned checkpoint + WAL。
- `ToolGatewayNode`：包住 tool node，自动做 schema、policy、ledger、audit。
- `RunEvidenceExporter`：把 graph execution 导出为 replayable evidence bundle。

对 Ray 用户：

```text
给你的分布式 Agent worker 套上合规与治理的笼子。
```

落地形式：

- Ray 负责 distributed execution。
- AgentLedger 负责 lease、fencing、tool ledger、event log、replay 和 audit。

对其它 Agent 框架用户：

```text
不要求换框架，只给你的现有 Agent 加 durable execution、tool ledger、event log 和 replay。
```

落地形式：

- decorator 包装普通函数。
- tool wrapper 接管外部调用。
- checkpointer/store adapter 接管状态。
- event exporter 生成 Run Evidence Bundle。

对 Temporal 用户：

```text
Temporal 管 durable workflow，AgentLedger 管 Agent-specific tool/state/memory semantics。
```

这样项目定位更像中间件，而不是又一个上层 Agent framework。


## 项目命名备选

命名应该传达“可靠、运行时、轻量、状态一致性”。

备选：

- `Reliant`：直白强调可靠。
- `AgentKernel`：强调底层 runtime/kernel。
- `AgentLedger`：强调状态一致性和稳定运行。
- `AetherRuntime`：轻量、无处不在，但略抽象。
- `Checkpoint`：简单有力，突出恢复能力。
- `Runbox`：强调 run 的受控执行容器。
- `AgentOS`：记忆点强，但可能过大。
- `DurableAgent`：定位清晰，但略直白。
- `AgentWAL`：技术味很强，适合开发者，但品牌延展性稍弱。

当前更推荐：

```text
AgentLedger
AgentKernel
Checkpoint
```

其中 `AgentLedger` 最贴近这个项目的精神：让不确定的 Agent 执行进入稳定状态。AgentLedger 是当前首选。


## 最终体检报告：异常路径优先

这个项目的核心判断是：Agent 进入生产环境后，最难的不是 happy path，而是异常路径。

现有 Agent 框架大多在打通路径：

```text
用户输入 -> Agent 思考 -> 调工具 -> 产出结果
```

这个 runtime 要专注处理异常：

```text
worker 崩溃
外部工具超时
副作用结果未知
状态提交冲突
memory 被污染
prompt 变更导致回归
成本失控
权限越界
replay 无法重建
```

这也是它能落地的原因：它不挑战复杂 AI 算法，而是用成熟后端工程里的事务、WAL、幂等、审计、checkpoint、隔离和回放思想，去约束 AI execution 的不确定性。

### 可落地的三个基础

1. 解耦“思考”和“执行”

```text
Agent Logic:
  决定要做什么

Runtime:
  决定能不能做、怎么做、怎么记录、失败后怎么恢复
```

AgentContext 把 Agent 行动限制在受控 API 内，解决乱写数据库、乱调 API、绕过权限和缺少审计的问题。

2. Tool Ledger 是生产必需品

任何涉及钱、邮件、工单、PR、部署、数据库写入、文件删除的 Agent，如果没有幂等账本，都不应该进入生产环境。

Tool Ledger 的价值非常清晰：

```text
同一个 logical side effect 最多成功一次
side_effect_unknown 必须确认，不允许盲目重试
历史副作用可以被审计、replay 和归因
```

3. State Patch + WAL 是成熟工程模式

State Patch、base_version、append-only event log、checkpoint 不是新发明，而是把数据库事务、Redux/React state update、event sourcing、WAL 的成熟思想迁移到 Agent runtime。

这意味着底层技术可实现，真正难点在产品边界、DX 和生态集成。

## 商业价值和生态位

一句话：

```text
LangGraph / CrewAI 是厨师，负责把菜做出来。
AgentLedger 是厨房 SOP、安全系统和溯源系统，负责不着火、不投毒、可追责、可复盘。
```

这个生态位很聪明，因为它不需要正面替代现有框架，而是为它们补生产可靠性短板。

### 对企业用户的价值

- 可控 AI：Agent 所有外部动作都有权限、审计和审批。
- 合规证据：Evidence Bundle 记录当时输入、状态、工具返回、权限策略和模型输出。
- 事故复盘：Replay / Time Travel 能还原一次 run 为什么失败。
- 风险上线：Shadow Mode 让 prompt / workflow / model 变更先在历史真实 run 上影子测试。
- 生产恢复：Durable Resume 让长期任务从上一个安全 checkpoint 恢复。

### 三个最强护城河功能

1. Durable Resume

普通 Agent 挂了通常只能重跑或人工翻日志。这个 runtime 应该做到：给一个 `run_id`，从 last successful step / checkpoint 恢复。

2. Evidence Bundle

不仅记录 Agent 说了什么，还记录：

```text
run spec
state snapshot
model request / response
tool request / response
权限策略快照
tool ledger
artifact lineage
cost records
failure records
```

这对金融、法律、医疗、企业 IT 自动化等严监管场景很有价值。

3. Shadow Mode

解决“Prompt 变更恐惧症”。新 prompt、新模型、新 workflow 可以先在历史真实 Event Log 上跑 shadow execution，对比输出、trace、成本和风险，而不产生实际副作用。

## 落地硬骨头

### SDK 侵入性

强制开发者把所有外部调用都改成 `await ctx.call_tool(...)` 会有阻力。

对策：

- 提供 decorator，让普通函数快速注册成 managed tool。
- 提供自动注入的 `AgentContext`，减少样板代码。
- 提供 lint，扫描直接调用 `requests`、`subprocess`、裸 SDK 的绕行代码。
- 可选 monkey patch 常用 SDK，把调用拦截进 runtime，但不要作为唯一方案。
- Adapter first：先让 LangGraph 用户通过 checkpointer/tool wrapper 接入，而不是重写全部 Agent。

### 状态爆炸

Event-level WAL 会产生大量日志、payload 和 artifact。

对策：

- Snapshot + AOF：定期压缩历史事件，保留 checkpoint 和最近增量。
- Payload 分层：event 表只存 hash / ref，大对象进入 blob/object store。
- Retention policy：按 run 风险等级、合规要求和调试价值决定保留周期。
- Compaction job：把老 run 压缩成 state snapshot + evidence summary。
- Side-effect / permission / failure 事件永不采样，低风险 trace 可降采样。

### 并发冲突

多个 Agent 同时修改 shared state 时，简单 last-write-wins 会导致状态污染。

对策：

- 每次 patch 必须带 `base_version`。
- namespace ownership：不同 Agent 写不同 state namespace。
- JSON Merge Patch / JSON Patch 只适合 MVP，后续需要 conflict-aware merge。
- 对 append-only findings、claims、evidence 可以采用 CRDT-like append/merge。
- 对 root_cause、decision、approval 这类唯一字段必须走 reviewer / coordinator gate。
- 冲突不应被静默覆盖，应进入 `conflict_detected` event 和 review flow。

## MVP 杀手锏排序

第一版最应该优先证明这三件事：

```text
1. Tool side effect 不重复
2. Worker crash 后可 resume
3. Run 可以 time-travel debug / deterministic replay
```

这三个 demo 能直接说明：这个项目不是另一个 Agent workflow wrapper，而是 production reliability runtime。

## 后续路线

### Phase 1：Runtime Core

- AgentContext
- SQLite State Store
- Event Log
- Tool Registry / Gateway
- Tool Ledger
- Simple Scheduler / Worker
- Session State MVP
- Deterministic Replay
- YAML policy
- JSON Merge Patch state commit
- CLI Time Travel Debugger 最小版

### Phase 2：Production Semantics

- Postgres backend
- lease heartbeat / fencing token
- session version / message refs / conversation summary
- cancellation semantics
- failure taxonomy
- cost attribution
- sandbox executor
- approval gate
- side_effect_unknown handling
- Docker sandbox plugin

### Phase 3：Reliability Harness

- Repro Harness
- Eval Harness
- replay diff
- failure injection
- adversarial review checklist
- regression corpus
- Time Travel Debugger MVP
- Shadow Mode MVP

### Phase 4：Integrations

- TypeScript SDK / Worker client
- MCP client / server examples
- Matrix / Telegram communication adapters
- S3 / MinIO blob store backend
- LangChain / LangGraph adapter
- OpenAI Agents SDK adapter
- CrewAI / AutoGen adapter
- LlamaIndex / Semantic Kernel adapter
- Temporal backend
- Ray worker backend
- Kubernetes deployment examples
- OpenTelemetry exporter
- JSON-RPC / gRPC worker protocol

## 项目卖点

- Runtime-enforced AgentContext
- Versioned run state
- Append-only event log
- Tool governance by default
- Idempotent side-effect tools
- Deterministic replay
- Checkpoint / resume
- Lease / fencing for distributed workers
- Failure and cost attribution
- Eval and adversarial review hooks
- Time Travel Debugger
- Shadow Mode
- Framework-agnostic

## 需要继续想清楚的问题

- Python MVP 下，哪些接口必须从第一天保持语言无关？
- SQLite WAL 的并发边界和何时切 Postgres？
- Event-level replay 的最小事件集合是什么？
- Tool schema 用 JSON Schema 还是 Pydantic model？
- YAML policy 的表达力边界在哪里，何时接 OPA/Cedar？
- AgentContext 如何适配 LangGraph / OpenAI Agents SDK？
- runtime-core 如何保持完全 framework-agnostic，避免被任一 adapter 反向污染？
- TypeScript SDK 的最小协议边界是什么，哪些能力只做 worker client？
- MCP 放在 Tool Gateway 之下还是作为平级 tool runtime？
- 通信 channel adapter 如何处理 webhook duplicate delivery 和 session mapping？
- `AgentLedgerCheckpointer` 的最小 LangGraph 接口是什么？
- Sandbox 第一版是否只做接口，还是提供 Docker executor？
- Eval Harness 是否放进 core，还是作为 optional package？
- `causal_token`、`tool_call_id`、`idempotency_key` 的最终命名和关系如何定？
- Time Travel Debugger 是 CLI first 还是 Web UI first？
- Shadow Mode 的 diff 标准如何定义：trace-level、semantic-level 还是 cost-level？
- `Batching Patch` 如何在性能和 replay 粒度之间取舍？
- 是否提供 monkey patch / lint 来降低 DX friction？
- 开源项目名称最终选哪个？

