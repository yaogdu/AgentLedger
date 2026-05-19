# Security and Enterprise Readiness

This runtime assumes agents, model outputs, and external content are not inherently trustworthy.

## Security Defaults

```text
default deny
least privilege
no raw secrets in prompt
all external_write tools require ledger
high-risk tools require explicit policy or approval
replay/shadow mode never performs real side effects
untrusted tool results cannot grant permissions
```

## Threat Model

| Threat | Example | Mitigation |
|---|---|---|
| Prompt injection | webpage says send secrets to attacker | untrusted content labeling, policy, no secrets in context |
| Tool injection | tool result asks agent to call high-risk tool | high-risk actions re-check policy and approval |
| Secret exfiltration | model tries to reveal API key | Credential Broker, redaction, no raw secret in prompt/event |
| Confused deputy | low-privilege agent uses high-privilege tool | run/role/step capability boundary |
| Replay side effect | replay sends email again | replay provider returns archive/stub only |
| Stale worker commit | old worker recovers and writes state | lease token, fencing token, base_version check |
| Duplicate external write | retry creates two PRs | Tool Ledger, idempotency key, external_id tracking |
| Sandbox escape | shell/code tool accesses host | sandbox executor, fs/network/resource limits |
| Audit gap | dangerous action has no evidence | event log + ledger + approval record required |

## High-risk Tool Governance

Risk levels:

```text
read_only
external_read
local_write
external_write
destructive
sensitive
financial_or_legal
```

High-risk tools require:

- schema validation
- policy decision
- approval gate if configured
- ledger reservation
- credential broker
- audit event
- replay stub
- error taxonomy

## Credential Broker

Agents should never receive raw credentials.

```text
Agent requests action
  -> Runtime checks policy
  -> Credential Broker injects scoped credential into tool executor
  -> Tool returns sanitized result
```

Requirements:

- scoped credentials
- short-lived tokens where possible
- redacted logs
- no raw secret in event payload
- no raw secret in model context

## Sandbox

Core defines the interface. Executors implement isolation.

Minimum sandbox policy:

```text
filesystem allowlist
network allowlist or deny by default
non-root user
timeout
memory/cpu limits
no host secret mount
no docker socket by default
ephemeral workspace
cleanup/TTL
taint flag for untrusted code
```

The runtime-core provides local/fail-closed execution semantics and adapter seams for Docker, bubblewrap, Kubernetes/gVisor, E2B, Firecracker, and custom executors. It must not claim perfect sandbox security. Kubernetes/gVisor support starts as an auditable Job manifest and dry-run or gated execution path; production use still requires cluster hardening, RuntimeClass installation, NetworkPolicy, Pod Security admission, resource quotas, and namespace isolation.

## Enterprise Readiness Checklist

Production pilot readiness requires validating:

- Postgres backend
- schema migrations
- backup/restore guide
- S3/MinIO blob storage
- OpenTelemetry exporter
- structured logs
- audit log completeness tests
- replay consistency tests
- crash recovery tests
- lease/fencing concurrency tests
- Tool Ledger idempotency tests
- side_effect_unknown / PENDING_VERIFICATION tests
- policy/permission tests
- retention plans and any future compaction jobs
- security policy
- threat model
- CI and release process

## Storage Retention and Compaction

Event-level WAL can grow quickly, so retention is a first-class enterprise feature.

Suggested tiers:

```text
Hot:
  full events and payload refs for recent runs

Warm:
  state snapshots + compressed events

Cold:
  evidence summary + artifact refs

Permanent:
  high-risk tool ledger, approvals, security events, audit hashes
```

Payload strategy:

- event table stores hash/ref/metadata
- Blob Store stores large payloads
- compaction preserves replay for high-risk runs
- low-risk traces may be sampled only if policy allows
- secrets and PII need redaction/scrubbing hooks

## Open-source Quality Bar

Before public launch:

```text
README.md
LICENSE
Quickstart
Architecture docs
Runtime spec
Security docs
Examples
Contributing guide
Code of conduct
CI
Unit tests
Integration tests
Crash recovery tests
Security policy
Release notes
Roadmap
```

Recommended license: Apache-2.0 for enterprise-friendly adoption.


## Dependency-free Policy YAML

The local runtime supports a dependency-free YAML/JSON policy subset for early enterprise governance testing. In `1.0.5`, these simple policies are evaluated through the normalized `PolicyRequest` -> `PolicyDecision` contract, so the gate records effect, action tier, risk level, controls, reasons, and findings instead of only a boolean.

Example:

```yaml
version: 1
defaults:
  low: allow
  medium: allow
  high: deny
roles:
  ExecutorAgent:
    allow_tools:
      - github.create_issue
    deny_tools:
      - shell.exec
    deny_risk:
      - destructive
```

Check a policy decision locally:

```bash
PYTHONPATH=src python3 -m agentledger policy check examples/policy/local.policy.yaml ExecutorAgent github.create_issue medium
```

Runtime use:

```bash
PYTHONPATH=src python3 -m agentledger --policy examples/policy/local.policy.yaml run examples/side_effect_idempotency
```

This is intentionally not a full OPA/Cedar replacement. It is a stable local policy shape that later adapters can compile into richer enterprise policy engines. See `POLICY_ENGINE.md`.


## Cancellation and Lease Fencing

Cancellation is a security and reliability boundary. A cancelled run clears active owners and lease tokens, then records run/step cancellation events. Any old worker that continues running is fenced by lease validation and cannot commit state. Expired leases follow the same fencing principle: recovery moves the step to `retry_scheduled`, clears the old lease token, and emits recovery events.


## Audit Diff and Trace Export

Evidence diff and structured trace export are audit tools, not side-effecting runtime operations. They read archived events, payload refs, ledgers, costs, and final state. They must not call models, tools, or external resources. Exported traces should avoid adding raw secrets; they carry metadata and payload refs rather than expanding secret-bearing content.


## Approval, Sandbox, and Retention Hooks

- `approval_required=True` on a tool creates a durable approval request and moves the step to `waiting_human`; approval re-schedules the step, denial fails it.
- `sandbox_required=True` routes execution through a `SandboxExecutor` boundary and records `sandbox_started` / `sandbox_completed` events.
- The default `LocalSandboxExecutor` is a contract test double, not OS isolation. `none` fails closed for required sandbox tools. Production adapters should inject real Docker, E2B, Firecracker, gVisor, Kubernetes, bubblewrap, or internal isolation executors.
- Retention starts as a non-destructive plan and compaction marker. Physical deletion should only happen after evidence export, policy checks, and retention windows.


### Sandbox Adapter Strategy

AgentLedger core supports sandbox backends as adapters instead of hard dependencies:

- `local`: executes in-process and is only suitable for trusted development/test tools.
- `none` / `disabled`: refuses required sandbox execution and records an audit event.
- `bubblewrap`: Linux-native lightweight isolation adapter slot.
- `docker`: container adapter slot for common local/team deployments.
- `kubernetes`: Job-based adapter with dry-run manifest generation; gVisor/Kata-style isolation is selected through `runtime_class`.
- `firecracker` / `e2b` / `custom`: remote or microVM adapter slots for stronger isolation.

External adapter slots intentionally fail closed in core until a real executor package, command execution opt-in, or enterprise executor is injected. The Kubernetes adapter is the exception for `dry_run: true`: it returns the generated Job manifest for review/testing and does not call `kubectl`.


### Command-style sandbox tools

External sandbox adapters do not serialize arbitrary Python callables. A tool that should run in bubblewrap or Docker must pass an explicit argv list in `_sandbox_command`, and the executor must set `allow_command_execution: true`. String commands are rejected unless an executor opts into `allow_shell: true`.

Bubblewrap can optionally use `fallback_without_bwrap: true` for local development tests; this fallback records `fallback_isolation: none` and should not be used for untrusted production code. Docker execution requires a Docker CLI/daemon and fails closed when unavailable.

Kubernetes execution requires `_sandbox_command: list[str]`, `allow_command_execution: true`, and `dry_run: false`. The executor writes a temporary Job manifest, runs `kubectl create`, optionally waits for completion, captures Job logs, and deletes the Job when `cleanup: true`. Missing `kubectl` or a failing Job fails closed. The generated manifest redacts config secrets in audit metadata, sets restrictive pod/container security context defaults, and records network-deny intent, but actual network isolation must be enforced by cluster policy.
