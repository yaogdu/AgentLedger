# 安全与高风险工具治理

本文是 `../SECURITY_ENTERPRISE.md` 的中文主路径版本，描述 AgentLedger runtime-core 的安全边界和生产使用时需要外部补强的内容。

## 安全定位

AgentLedger core 提供：

```text
policy hooks
approval gates
Tool Ledger audit trail
sandbox adapter boundary
evidence and trace records
replay/shadow side-effect blocking
lease/fencing correctness
```

它不声称自己是完整安全系统，也不应该作为不可信代码执行的唯一防线。

## 主要风险

```text
prompt injection
tool injection
permission bypass
secret leakage
data exfiltration
sandbox fail-open
side-effect duplication
stale worker commit
replay/shadow accidentally producing side effects
```

## 权限和工具治理

工具调用应通过 `ToolGateway`：

```text
schema validation
PolicyRequest -> PolicyDecision
approval gate
budget check
sandbox check
Tool Ledger reservation
execution
audit/evidence recording
```

`1.1.0` 起，简单 YAML/JSON policy 也会通过 normalized decision contract 记录 effect、action_tier、risk_level、controls、reasons 和 findings。详见 `POLICY_ENGINE.md`。

高风险工具应配置：

```text
risk_level
approval_required
sandbox_required
idempotency_required
least privilege credentials
redaction policy
```

## Secret 管理

原则：

```text
secret 不写入 event payload
secret 不默认写入 evidence / trace
tool result 应返回 durable refs 或 redacted metadata
adapter 负责和外部 secret manager 集成
```

## Sandbox

runtime-core 提供 sandbox contract，不提供完整生产隔离。

```text
none: fail closed for sandbox-required tools
local: explicit no-isolation mode
Docker/bubblewrap: command-style execution paths
Kubernetes/gVisor: dry-run/gated path
Firecracker/E2B/custom: adapter slots
```

生产环境需要额外处理：

```text
network policy
filesystem isolation
resource limits
secret injection
image provenance
egress control
audit logs
operator approval
```

## Replay / Shadow 安全

Replay 和 shadow mode 必须：

```text
read archived events and payloads
reuse Tool Ledger records
not call real tools
not call real model providers unless explicitly configured as a side-effect-free comparison
not write external systems
```

## 企业落地检查

进入生产 pilot 前，应至少完成：

```text
threat model
policy review
high-risk tool inventory
approval workflow
secret management integration
sandbox hardening
backup/restore validation
observability and alerting
failure drill
adapter certification evidence
```
