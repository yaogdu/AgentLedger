# Adoption Plan

This document tracks near-term work that makes AgentLedger easier to understand, try, discuss, and validate. It does not change runtime-core scope.

## Why This Track Exists

AgentLedger already has substantial runtime-core depth. The next adoption bottleneck is not another large feature; it is helping a new user answer three questions quickly:

```text
What problem does this solve?
Can I see it in three minutes?
Can I verify the reliability claim myself?
```

## Current Adoption Priorities

| Priority | Item | Acceptance criteria |
|---|---|---|
| P0 | 3-minute demo | A user can run the Python, Go, TypeScript, or Rust 3-minute demo and see one external side effect, one Tool Ledger entry, safe retry, and replay-safe evidence. |
| P0 | README first-screen pain point | The first screen explains the tool side-effect problem before listing architecture. |
| P1 | MCP governance example | Dependency-free MCP-style tools demonstrate schema, approval, sandbox metadata, idempotency, and audit evidence across Python, Go, TypeScript, and Rust. |
| P1 | Public issue/discussion list | The next adoption tasks are easy to open as GitHub issues or discussions. |
| P1 | Case study template | A real integration can be documented without exposing private data. |

## Suggested Public Issues

These can be opened as GitHub issues when the project is ready for public tracking.

| Title | Type | Why it matters |
|---|---|---|
| Build a cross-language 3-minute Tool Ledger demo | example | Shows the core value in a few minutes across Python, Go, TypeScript, and Rust. |
| Add OpenAI Agents SDK approval/replay example | example | Connects AgentLedger to a major agent SDK boundary without claiming official endorsement. |
| Add MCP tool governance example | example | Shows how MCP-style tools should pass through policy, approval, sandbox, idempotency, and evidence. |
| Prototype AgentLedger Inspector | product | Makes run timelines, Tool Ledger, approvals, replay, and failures visible. |
| Add Temporal bridge example | integration | Clarifies Temporal owns workflow lifecycle while AgentLedger owns node-internal reliability. |
| Add tool-injection risk scanner | security | Detects risky tool schemas, missing approval/sandbox, and runtime-boundary bypass patterns. |
| Publish legal-agent case study | case study | Shows a realistic audit/evidence use case without private data. |

## Case Study Rules

Case studies should be useful but conservative:

- remove private data, customer data, secrets, and internal implementation details
- describe the runtime problem before describing AgentLedger
- show the AgentLedger integration boundary
- include concrete evidence artifacts only when safe
- avoid claiming production hardening unless real operational evidence exists

## Good Adoption Evidence

- runnable examples
- short terminal recordings or GIFs
- public issues and discussions
- package downloads
- real integration notes
- external demos or blog posts
- adapter conformance reports
- real-service hardening reports
