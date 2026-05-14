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

MVP can provide local executor and Docker executor as plugin. It should not claim perfect sandbox security.

## Enterprise Readiness Checklist

Production pilot requires:

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
- retention and compaction jobs
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
