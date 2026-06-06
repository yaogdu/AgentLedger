# Adapter 认证清单

本文是 `../ADAPTER_CERTIFICATION.md` 的中文主路径版本。它定义 adapter 被认为兼容 AgentLedger runtime 前，应满足哪些语义和证据要求。

## Adapter 类型

```text
StateStore adapter
BlobStore adapter
Framework adapter
Tool/MCP adapter
Sandbox adapter
Observability adapter
Media/stream adapter
Policy adapter
Model provider adapter
```

## 必须保留的不变量

```text
state commits require a valid lease token
stale workers cannot commit after recovery or cancellation
event log is append-only per run sequence
Tool Ledger owns idempotency for managed side effects
shadow/replay paths do not create real side effects
approval-required tools do not execute before approval
sandbox-required tools fail closed when isolation is unavailable
secrets are not expanded into evidence, trace, or artifact plaintext by default
media payloads stay behind durable refs
stream resume points are checkpointed before retry boundaries
```

## StateStore 认证

需要证明：

```text
DDL 或 schema migration 文件存在
事务隔离假设明确
lease / fencing 在并发下有效
schema migration rollout / rollback 有说明
backup / restore 有验证路径
网络分区、锁超时、partial write 的失败模式有说明
```

命令：

```bash
PYTHONPATH=src python3 -m agentledger state conformance --backend sqlite
PYTHONPATH=src python3 -m agentledger worker conformance --backend sqlite --concurrent
```

## BlobStore 认证

需要证明：

```text
content-addressed ref format
immutability guarantees
large object / multipart behavior if supported
retention and lifecycle policy
encryption and IAM model
restore validation with historical refs
```

命令：

```bash
PYTHONPATH=src python3 -m agentledger blob conformance --backend local
```

## Framework Adapter 认证

需要证明：

```text
framework run maps to AgentLedger run/session
framework step/node maps to Runtime.run_once-compatible callable
state/checkpoint data stays behind StateStore or artifact refs
framework tool calls can be routed through ToolGateway
direct SDK bypasses are documented or caught by lint examples
evidence export works for adapter-created runs
```

命令：

```bash
PYTHONPATH=src python3 -m agentledger adapter conformance --kind python-function
PYTHONPATH=src python3 -m agentledger adapter conformance --kind langchain
```

## Tool / Sandbox 认证

Tool adapter 需要证明：

```text
ToolSpec input_schema and output_schema are explicit
risk_level is set deliberately
side_effect and idempotency_required are correct
external writes include stable logical operation/idempotency key
errors preserve side_effect_unknown / PENDING_VERIFICATION semantics
context/resource reads go through ToolGateway when they affect agent inputs
```

Sandbox adapter 需要证明：

```text
SandboxPolicy is enforced or fail-closed
network/filesystem defaults are denied or minimal
metadata avoids leaking secrets
command-style execution rejects unsafe string commands unless explicitly allowed
boundary events are emitted for audit
```

## Media / Stream 认证

需要证明：

```text
large payloads are stored as BlobStore refs or external durable URIs
MediaArtifact includes kind plus uri/content_ref/blob ref
derived artifacts preserve lineage
EventStreamCheckpoint includes stream_id, consumer_id, offset
stream consumers can resume from last committed checkpoint
stream emitters use Tool Ledger idempotency for external writes
replay/evidence regression validate refs without contacting providers or brokers
sensitive media refs are redacted or access-controlled before evidence export
```

## 认证产物

每个 adapter 包建议发布：

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

AgentLedger 可以为官方 adapter profile 生成机器可读的起始认证 bundle：

```bash
PYTHONPATH=src python3 -m agentledger adapter certify --kind postgres --adapter-version 1.3.0
PYTHONPATH=src python3 -m agentledger adapter certify --kind mysql --adapter-version 1.3.0 --out ./mysql-certification.json
PYTHONPATH=src python3 -m agentledger adapter certify --kind s3 --adapter-version 1.3.0 --out ./s3-certification.json
PYTHONPATH=src python3 -m agentledger adapter certify --kind langgraph --adapter-version 1.3.0 --package-name agentledger-langgraph
```

内置 profile：

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

生成结果会包含 package metadata、contract version、conformance command、smoke command、required external services、security assumptions、known limitations 和 `production_validation`。

依赖真实基础设施的 adapter 会明确标记 `production_validation.status=external-required`。这不是失败，而是说明本地 runtime 只能生成认证 contract；真正的生产级声明仍然需要真实凭证、真实服务行为、并发/负载检查，以及 restore 或 rollback drill。P2 类 production hardening 必须有这些外部证据，不能只靠本地 mock 宣称完成。
