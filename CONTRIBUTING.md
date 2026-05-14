# Contributing to AgentLedger

AgentLedger is intentionally framework-agnostic. Contributions should preserve the runtime boundary: agent business logic runs through `AgentContext`, while durable state, tool calls, policy, audit, and replay remain runtime-managed.

## Local Development

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Contribution Principles

- Keep core dependencies minimal; put framework integrations behind adapters.
- Treat tool side effects as managed operations with idempotency and audit records.
- Prefer explicit state transitions over hidden mutable state.
- Add tests for failure paths, not only happy paths.
- Do not make replay or shadow mode perform real external side effects.

## Roadmap Fit

Good first contribution areas:

- storage adapters behind the existing store boundary
- framework adapters for LangGraph, AutoGen, CrewAI, LlamaIndex, Semantic Kernel, OpenAI Agents SDK, and MCP
- richer policy engines and approval workflows
- replay/evidence bundle export
- observability exporters
