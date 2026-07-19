# Oh My Pi Runtime Adapter 技术方案

状态：`1.5.2` 已在 Python、Go、TypeScript、Rust runtime 包内实现 normalized runtime bridge。这个 bridge 不改变稳定的 v1.x runtime-core contract。

本文定义 AgentLedger 面向 Oh My Pi runtime（下文简称 OMP）的可选 adapter 边界。这个 adapter 是通用 runtime 集成，不是面向某个 OMP 上层应用的产品定制集成。

## 定位

AgentLedger 提供 reliability 和 evidence contract。基于 OMP 的应用可以根据自己的运行时、文件事务和业务边界，选择把哪些 runtime event、state snapshot、tool evidence 和 document mutation 写入这个 contract。

```text
OMP runtime events
  -> AgentLedger OMP bridge
  -> AgentLedger runs, steps, model evidence, Tool Ledger, failures, state refs, evidence bundles
```

这个 adapter 符合 AgentLedger 既定方向：

- optional runtime/framework bridge
- evidence 和 replay boundary
- Tool Ledger 和 side-effect governance
- model-call 和 proposed-tool evidence
- failure lifecycle 和 attribution
- versioned state refs 和 state-change audit

它不改变 v1.x runtime-core semantics。

## 不做什么

OMP adapter 不能包含应用专属产品语义。

它不能知道或写死：

- 应用专属 memory 文件含义
- 应用专属 workspace 路径
- 应用专属账号、额度、订阅、计费、gateway 逻辑
- 应用专属 personality、persona、harness、user-profile 规则
- 私有本地路径、secret、token、cookie、provider key

如果某个应用有 `SOUL.md`、`MEMORY.md`、`USER.md` 或其它领域状态文件，应用自己拥有这些文件的语义。AgentLedger 可以记录 versioned state refs、diff、原因、commit status 和 evidence link，但不能决定这些文件的业务或产品含义。

## Adapter 输入

bridge 接收面向 OMP 的规范化记录，而不是抓取私有应用内部实现。

1.5.2 bridge 已实现 domain-neutral evidence 类别。approval 和 sandbox 仍然是 AgentLedger 已有 runtime 概念，OMP 集成可以通过 tool metadata 和 policy decision 写入这些证据，但本版本没有提供独立的 OMP-specific approval/sandbox API。

| OMP-facing input | AgentLedger mapping |
| --- | --- |
| runtime session metadata | run/session identity、framework/runtime metadata、correlation IDs |
| turn start/end | step lifecycle events |
| model request/response | archived model-call evidence、token/cost/failure records |
| model-proposed tool call | `tool_call_proposed` evidence，并在可能时关联后续 tool execution |
| tool call/result | Tool Ledger request、execution status、idempotency key、side-effect status |
| approval or policy checkpoint | 应用或 tool gateway 发出时，写入 AgentLedger 既有 policy/approval records |
| sandbox-required execution | 应用或 tool gateway 发出时，写入 AgentLedger 既有 sandbox policy/result refs |
| runtime error | failure envelope、causal graph inputs、replay plan hints |
| artifact or file ref | artifact/evidence refs 和 redaction metadata |
| versioned state mutation | state snapshot refs、diff refs、commit/rollback status、causal run/step links |

应用可以只发出自己能安全暴露的子集。缺少可选 evidence 但会影响 replay 或 audit 完整性时，必须显式标记。

## State Versioning 边界

很多 OMP 应用会维护 runtime-adjacent documents 或本地状态。AgentLedger 现有 blob、ref、state version、diff、evidence bundle 和 failure record 能支撑通用版本化状态管理。

推荐接入形态：

```text
before state snapshot hash/ref
mutation request source
runtime/model/tool evidence that caused the mutation
diff or patch summary
after state snapshot hash/ref
commit status
rollback or failure evidence
causal run_id / step_id / external session id
```

这足够支撑 audit、rollback evidence、replay inspection 和 regression review，同时不会把 AgentLedger 变成 memory product 或 document semantics engine。

AgentLedger 可以提供通用 helper：

- `record_state_snapshot(...)`
- `record_state_change(...)`
- `record_state_diff(...)`
- `record_state_commit(...)`
- `record_state_rollback(...)`

这些 helper 必须保持 domain-neutral。

## 公开 API 边界

1.5.2 实现内置在现有 runtime 包中：

| Ecosystem | 当前入口 |
| --- | --- |
| Python | `from agentledger import OmpLedgerBridge` |
| TypeScript | `import { OmpLedgerBridge } from "agentledger-runtime"` |
| Go | `github.com/yaogdu/AgentLedger/go` 中的 `agentledger.NewOmpLedgerBridge(...)` |
| Rust | `agentledger::OmpLedgerBridge` |

后续如果 bridge 超出薄翻译层，可以再拆独立 optional package，例如 `agentledger-omp`。当前版本不要求额外安装独立 OMP 包。

## 最小 API 形态

adapter 应是薄翻译层，不要求 OMP 深度依赖 AgentLedger 内部。

```python
from agentledger import OmpLedgerBridge

bridge = OmpLedgerBridge(runtime=runtime, app_name="my-omp-app")

bridge.record_session_started(session)
bridge.record_turn_started(turn)
bridge.record_model_call(model_call)
bridge.record_tool_proposal(tool_proposal)
bridge.record_tool_execution(tool_call, result)
bridge.record_state_change(state_change)
bridge.record_failure(error)
bridge.record_turn_completed(turn)
```

Go、TypeScript、Rust adapter 应保持同一组语义事件，即使 API 风格不同。

## Redaction 和 Privacy

adapter 默认必须安全：

- 优先存 hash、ref、size、bounded summary，而不是 raw body
- raw prompt、model response、tool payload archive 必须 opt-in
- redact credential、API key、cookie、auth header、private token 和疑似 secret 值
- 支持 application-provided redaction hooks
- 省略内容时保留 evidence completeness flags
- 公开文档和 fixture 不包含应用私有路径

需要更完整 evidence 的应用，可以在自己的 redaction 规则下选择 BlobStore-backed payload archive。

## Replay Semantics

adapter 必须保持 AgentLedger replay invariants：

- replay 可以复用 archived model response，而不是重新调用模型
- replay 不能重复外部副作用
- side-effect status unknown 的 tool execution 不能自动 replay
- state mutation 默认以 ref/diff 形式 replay，除非应用显式提供安全 restore hook
- 外部 OMP session ID 是 correlation evidence，不是 AgentLedger 唯一事实源

## 实施状态

### Phase 0: Documentation And Contract

- 状态：1.5.2 文档已完成
- 增加本文和英文版技术方案
- 增加 roadmap 和 adapter-roadmap 条目
- 明确这是 OMP runtime bridge，不是应用专属 adapter

### Phase 1: Evidence Mapping Prototype

- 状态：1.5.2 已在 Python、Go、TypeScript、Rust 完成
- 定义 `OmpSession`、`OmpTurn`、`OmpModelCall`、`OmpToolProposal`、`OmpToolExecution`、`OmpFailure`、`OmpStateChange` 输入类型
- 映射到现有 AgentLedger runtime events 和 read models
- 增加无 OMP 依赖的测试
- 增加 synthetic OMP events -> AgentLedger 的小示例

### Phase 2: Optional Package

- 状态：后续可选 packaging
- 当 API surface 成熟后发布 optional adapter packages
- 增加 session/turn/tool/model/failure/state-change translation conformance fixtures
- 增加 redaction 和 evidence-completeness tests
- 在 OMP 生态存在的语言里补 language-specific quickstarts

### Phase 3: Application Integration Guidance

- 状态：roadmap
- 说明 OMP 应用如何自行选择 event emission points
- 说明应用如何记录 versioned document changes，同时不暴露领域语义
- 增加 adoption note：私有应用应把业务路径和产品规则留在自己项目里，不进入 AgentLedger

## 验收标准

- adapter boundary 被清楚定义为 OMP-specific，不是 application-specific。
- roadmap 明确 runtime-core 仍保持 framework-neutral，不学习应用业务语义。
- state versioning 被描述为通用 refs/diffs/evidence，不是 memory product。
- 当前内置 bridge 已在 Python、Go、TypeScript、Rust 提供，并有测试和示例。
- 后续 optional package 名和 hardening 阶段足够清楚，可以直接拆 issue。
- 文档不包含私有路径、secret 或应用专属实现承诺。
