# Use Cases

AgentLedger is useful when the hard question is no longer "can the agent produce an answer?" but:

```text
What actually happened?
Can I retry safely?
Can I prove it later?
Can I replay/debug it without repeating side effects?
```

It is not another planning framework. Use it when an agent crosses runtime boundaries: calling tools, spending model budget, waiting for approvals, writing checkpoints, touching files, calling business APIs, or producing evidence that somebody may need to audit later.

For a product or enterprise team, the practical promise is modest but important: AgentLedger gives every runtime-managed action a receipt. It helps teams see what the agent tried to do, what actually ran, what was approved or denied, what failed, what it cost, and what can be replayed without touching the outside world again.

## When To Use AgentLedger

Use AgentLedger when your agent has one or more of these properties:

| Situation | Why AgentLedger helps |
|---|---|
| The agent calls tools with side effects | Tool Ledger, causal request IDs, idempotency keys, and replay-safe records help avoid unsafe duplicate writes when side effects go through the runtime boundary. |
| A run can last longer than one process lifetime | Durable runs, steps, sessions, checkpoints, leases, and fencing allow resume after crash or restart. |
| Tools need approval, policy, or sandbox controls | Runtime gates run before high-risk tool execution, not only after-the-fact in a trace. |
| You need audit/debug evidence | Evidence bundles, archived payload refs, event logs, Inspector HTML, and replay summaries make a run reviewable. |
| Prompt, model, or tool schema changes may break behavior | Historical evidence can be replayed or compared without re-calling real tools. |
| Model usage and failures matter | Model-call evidence, proposed tool calls, cost records, and structured failures make model/tool responsibility visible. |
| You already use LangGraph, Temporal, Langfuse, MCP, or a model gateway | AgentLedger sits beside them and owns runtime guarantees at the model/tool/state boundary. |

## When Not To Start Here

You probably do not need AgentLedger as the first dependency if:

- the project is a toy chatbot with no tools, no persistence, and no audit need
- you only need a planner, graph builder, prompt framework, or hosted trace UI
- your main problem is long-term semantic memory, RAG retrieval, or vector search
- your main problem is benchmark management or offline eval scoring
- you are still exploring a throwaway prototype where retry safety and evidence do not matter

Those systems can still be used with AgentLedger later. The core rule is simple: add AgentLedger when side effects, recovery, governance, or evidence become part of the engineering problem.

## Problems It Helps Teams Solve

These are the adoption problems AgentLedger is designed to make easier:

| Team question | AgentLedger answer |
|---|---|
| "The agent said it called a tool. Did it really happen?" | The Tool Ledger and event log record the runtime-managed call, arguments, status, evidence refs, and failure state. |
| "Can we retry this run without sending the same email or creating the same ticket twice?" | Idempotency keys, causal request records, and unknown-state handling give the retry path something concrete to check. |
| "Who approved this high-risk tool call?" | Approval records and policy decisions are attached to the run, step, and tool evidence. |
| "Did the model choose the wrong tool, or did our runtime/tool implementation fail?" | Model-call evidence, proposed tool calls, actual tool calls, and structured failures are linked in the run timeline. |
| "Why did cost or latency spike after a prompt/model change?" | Cost/failure attribution can be grouped by run, agent, step, tool, and model. |
| "Can an engineer debug this without rerunning production side effects?" | Evidence bundles, payload refs, Inspector HTML, and replay summaries keep the review path side-effect-free. |

## Common Scenarios

| Scenario | Runtime risk | AgentLedger role |
|---|---|---|
| Customer support agent creates tickets or sends emails | A crash/retry can create duplicate tickets or emails. | Record the causal tool request, enforce idempotency, export evidence for review. |
| Legal, finance, or operations agent queries and updates business systems | A tool call may touch sensitive data or require approval. | Add policy/approval gates, durable evidence, cost/failure attribution, and Inspector review. |
| Coding agent edits files, runs shell commands, or opens pull requests | It can be hard to prove which command or tool produced a file change. | Record tool calls, artifacts, failure causes, and replay-safe evidence refs without storing huge blobs inline. |
| Research or RAG agent uses mutable web/search/vector results | Re-running later may not reproduce the same context. | Store retrieval/model evidence refs and replay against recorded evidence. |
| LangGraph or OpenAI Agents SDK app needs runtime reliability around tools and state | Framework traces may not prevent duplicate side effects or enforce approval before tools run. | Wrap nodes/tools with AgentLedger runtime guarantees. |
| Temporal/Ray/Kubernetes workers run agent steps | The scheduler manages workers, but not agent-specific Tool Ledger, model evidence, or replay contracts. | Run AgentLedger inside worker steps for checkpoint, fencing, evidence, and governance. |
| Incident review after model or prompt upgrade | The team needs to know if the model proposed a bad tool call or the runtime executed it incorrectly. | Link model-call evidence, proposed tool calls, approval/policy decisions, actual tool calls, failures, and costs. |

## The 3-Minute Demo

Start with the side-effect safety demo. It intentionally simulates a worker crash after a tool changes the outside world. In this controlled flow, the tool is routed through AgentLedger with an idempotency key, so the retry can reuse the recorded side effect instead of creating another one.

```bash
PYTHONPATH=src python3 examples/three_minute_demo/demo.py
```

Cross-language versions:

```bash
cd go && go run ./examples/three_minute_demo
cd typescript && node examples/three_minute_demo/three_minute_demo.js
cd rust && cargo run --example three_minute_demo
```

Expected result:

- the first attempt fails after the external side effect
- the retry succeeds
- the external write count stays at `1`
- there is one Tool Ledger record for the side effect
- replay validates evidence without calling the real tool again

That is the shortest way to see the core value: AgentLedger makes a dangerous retry observable, reviewable, and safer to execute when the integration follows the runtime boundary.

## Guarantee Boundaries

AgentLedger should not be described as a magic exactly-once layer for every external system. Its reliability claims depend on integration boundaries:

- runtime-managed tool calls must go through AgentLedger APIs or adapters
- side-effecting tools should provide stable idempotency keys
- external systems should expose enough identifiers to verify completed work when possible
- large or sensitive payloads should be stored as controlled blob refs or redacted evidence, not blindly inlined
- model calls should be recorded through the model evidence boundary if replay/debug needs to distinguish model behavior from runtime behavior
- production use still needs normal operational controls: backups, migrations, secrets management, network policy, sandbox infrastructure, and monitoring

With those boundaries in place, AgentLedger gives teams a concrete runtime record and replay path. Without those boundaries, it can still store evidence, but it cannot govern side effects it never sees.

## How It Fits With Other Tools

AgentLedger is designed to compose with existing agent infrastructure instead of replacing it.

| Existing tool | Keep using it for | Add AgentLedger for |
|---|---|---|
| LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK | planning, graph routing, agent logic, prompt/workflow structure | durable state, Tool Ledger, approval/policy/sandbox gates, evidence, replay-safe model/tool boundaries |
| Temporal, Ray, Kubernetes | distributed workflow lifecycle, worker scheduling, retries at infrastructure level | agent-specific checkpoint semantics, leases/fencing, model/tool evidence, cost/failure attribution |
| Langfuse, LangSmith, OpenTelemetry | trace UI, monitoring, datasets, dashboards | in-path runtime evidence, side-effect governance, replay artifacts, policy decisions before execution |
| MCP servers and internal tool servers | exposing tools, resources, and prompts | tool governance gateway semantics: schema, permission, approval, sandbox, idempotency, audit |
| LiteLLM, new-api, one-api, enterprise gateways | model routing, provider failover, credentials, quotas | model-call evidence, proposed tool-call records, replay semantics, model failure attribution |
| Vector DBs and memory systems | long-term semantic memory and retrieval | session state, checkpointed state transitions, retrieval evidence refs, lossless replay inputs |

## Adoption Checklist

Before integrating deeply, answer these questions:

- Which tool calls can create external side effects?
- Which side effects need idempotency keys or pending-verification states?
- Which tools require approval, policy, or sandbox controls?
- What evidence would you need during an incident review?
- Which model calls and tool proposals must be recorded for replay?
- Where should runtime metadata live: SQLite, Postgres, MySQL, or a custom StateStore?
- Which large payloads should be stored as blob refs instead of inline records?
- Which framework or scheduler owns planning/execution around AgentLedger?

If those questions feel relevant, AgentLedger is solving a real problem in your stack.

---

generated by codex cli
