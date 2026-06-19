# Runtime 规范

本文是 `../RUNTIME_SPEC.md` 的中文主路径版本，说明 AgentLedger runtime 的核心对象、状态语义、事件语义、Tool Ledger、replay、evidence、evidence regression、worker 和 adapter 规则。

## 定位

AgentLedger 的 runtime contract 不是 Agent workflow DSL，也不是模型 SDK。它定义的是：

```text
Agent 执行过程如何被持久化
Worker 如何 claim / heartbeat / commit
Tool side effect 如何被治理
Evidence 如何被导出和重放
Adapter 如何证明兼容
```

## 核心对象

```text
Run
  一次逻辑任务执行。包含 session_id、status、state_json、state_version。

Step
  一次可 claim 的执行单元。包含 owner、lease_token、attempt、status。

Event
  append-only 事件日志。按 run_id + seq 排序。

Tool Ledger
  runtime-managed tool call 的幂等和审计记录。

Artifact
  指向 BlobStore 或外部 durable ref 的证据对象。

Evidence Bundle
  一次 run 的可导出证据包。
```

## Run / Step 状态

典型状态：

```text
pending
running
retry_scheduled
waiting_human
completed
failed
cancelled
```

关键规则：

```text
pending step 可以被 worker claim
running step 必须有 owner 和 lease_token
completed / failed / cancelled 是 terminal 状态
waiting_human 需要审批或外部确认后才能继续
retry_scheduled 表示可被重新 claim
```

## Lease 和 Fencing

worker claim step 时，StateStore 生成 `lease_token`。之后所有状态提交都必须携带这个 token。

```text
claim_step
  -> owner = worker_id
  -> lease_token = generated token
  -> lease_until = now + lease_seconds
  -> attempt += 1
```

提交规则：

```text
commit_state_patch 必须校验 lease_token
commit_state_patch 必须校验 base state_version
expired / cancelled / stale worker 不能提交
recover_expired_leases 可以把 abandoned running step 放回 retry_scheduled
```

这保证了 worker replica 可以被中断、恢复、重新调度，但不会污染 logical run state。

## Event Log

事件是 replay 和 evidence 的基础。事件必须 append-only，并按 run 内 `seq` 单调排序。

常见事件：

```text
run_created
step_created
step_claimed
model_call_completed
tool_call_reserved
tool_call_completed
tool_call_failed
artifact_created
state_patch_committed
step_completed
step_failed
step_retry_scheduled
run_cancel_requested
run_cancelled
```

事件 payload 应保存可审计 metadata 和 payload refs，不应默认包含 secret 或大型 raw payload。

## State Patch

Agent 不直接修改 StateStore，而是通过 `AgentContext.write_state_patch(...)` 提交 JSON-merge-patch 风格的 patch。

提交时 runtime：

```text
读取当前 state_version
校验 base_version
合并 patch
增加 state_version
写入 run state
追加 state_patch_committed event
```

并发冲突应该在 StateStore 层暴露，而不是在业务代码中靠 if-else 静默覆盖。

## Tool Ledger

Tool Ledger 是生产语义中最重要的部分之一。

每次 runtime-managed tool call 都应该有：

```text
tool_name
tool_version
tool_call_id
idempotency_key
causal_token
request_hash / request_ref
status
external_id
response_hash / response_ref
error_type
```

状态示例：

```text
RESERVED
RUNNING
SUCCEEDED
FAILED_NO_EFFECT
PENDING_VERIFICATION
COMPENSATED
```

如果外部工具 timeout，且无法证明副作用没有发生，runtime 应进入 `PENDING_VERIFICATION`，而不是自动重复外部写入。

## Policy、Approval、Sandbox

工具调用顺序应保持：

```text
schema validation
policy check
approval check
budget check
sandbox check
ledger reservation
execution
ledger update
```

规则：

```text
approval-required tool 在 approval 前不能执行
sandbox-required tool 在 sandbox 不可用时必须 fail closed
policy denied 时不应产生外部副作用
secret 不应默认出现在 evidence / trace / artifact plaintext 中
```

## Evidence Bundle

Evidence bundle 是一次 run 的可复盘证据包，包含：

```text
summary
run
steps
events
tool_ledger
artifacts
media_artifacts
stream_checkpoints
cost_records
final_state
bundle_hash
```

Evidence 可以导出为：

```bash
PYTHONPATH=src python3 -m agentledger evidence <run_id> --out ./bundle.json
PYTHONPATH=src python3 -m agentledger evidence <run_id> --dir ./bundle-dir
PYTHONPATH=src python3 -m agentledger evidence <run_id> --html ./evidence.html
```

## Replay

Replay 必须 side-effect-free：

```text
读取 event log
读取 archived payload refs
验证 artifact/tool refs
输出 replay summary
不调用真实工具
不调用真实模型 provider
不写外部系统
```

## Runtime Model Evidence Boundary

AgentLedger 记录 model evidence，但不路由 model traffic，也不替代 provider SDK、LiteLLM/new-api/one-api 或企业 model gateway。

可移植 model evidence schema 是 `agentledger.model.evidence.v1`，覆盖：

```text
model_call_requested   归档 request、provider、model、metadata
model_call_completed   归档 response、usage、total_usd、metadata
model_call_failed      timeout/rate-limit/malformed-output/provider-error evidence
tool_call_proposed     模型建议的 tool name/args，发生在 ToolGateway 实际执行前
```

执行模型是：

```text
user code / framework / provider SDK / external gateway
  -> 执行或尝试执行 model call
  -> 把 request/response/failure evidence 记录进 AgentLedger
  -> 可选记录模型建议的 tool call
  -> 真实工具仍通过 ToolGateway / Tool Ledger 执行
```

`model_call_failed` 会作为 `model` 类别进入 failure lifecycle。runtime-core 负责记录 model call 的 cost/failure/replay evidence，但 provider timeout、retry、fallback、key management、routing 和 price catalog 仍属于外部 adapter 或应用代码责任。

## Evidence Regression

Evidence regression 以 evidence 为输入，保持 side-effect-free，不在生产执行路径中运行：

```text
no_failed_steps
no_pending_verification
completed_steps_have_events
managed_side_effects_are_ledgered
media_artifacts_have_refs
stream_checkpoints_have_offsets
max_total_usd
```

Regression check 比较 golden/current evidence：

```bash
PYTHONPATH=src python3 -m agentledger evidence-regression ./golden.json ./current-dir
PYTHONPATH=src python3 -m agentledger divergence ./golden.json ./current-dir --evidence-paths
PYTHONPATH=src python3 -m agentledger corpus check side-effect ./current-dir
```

## Media / Stream

runtime-core 只定义可靠性 contract：

```text
MediaArtifact
MediaMetadata
ArtifactLineage
StreamChunkRef
EventStreamCheckpoint
```

它保存 durable refs、metadata、lineage、offset 和 checkpoint，不负责 codec、转码、抽帧、转写或 stream transport。

## Conformance

兼容实现应通过：

```bash
PYTHONPATH=src python3 -m agentledger conformance
PYTHONPATH=src python3 -m agentledger state conformance --backend sqlite
PYTHONPATH=src python3 -m agentledger blob conformance --backend local
PYTHONPATH=src python3 -m agentledger worker conformance --backend sqlite --concurrent
PYTHONPATH=src python3 -m agentledger adapter conformance --kind langchain
```

跨语言实现应以 `contracts/agentledger.runtime.v1.json` 为语义边界。
