# Comparisons And Overlap

AgentLedger deliberately overlaps in vocabulary with agent frameworks, workflow runtimes, tracing tools, eval tools, and retrieval systems. The important question is not whether a word appears in both projects; it is which layer can enforce the guarantee.

AgentLedger is the execution safety and evidence layer. It sits where agent code reads state, calls models, calls tools, spends budget, writes checkpoints, and emits evidence. Adjacent tools should remain responsible for planning, workflow shape, trace UI, experiments, retrieval, and deployment-specific infrastructure.

## Short Version

```text
LangGraph / LangChain / CrewAI / AutoGen:
  decide what the agent should do next

Temporal / Ray / Kubernetes:
  run and schedule distributed work

LangSmith / Langfuse / OpenTelemetry:
  observe, compare, evaluate, and debug behavior

RAG / vector stores:
  retrieve long-term knowledge

AgentLedger:
  make each execution step durable, governed, replayable, and safe around side effects
```

## Boundary Matrix

| Area | Adjacent tools usually own | AgentLedger owns | Why AgentLedger still matters |
|---|---|---|---|
| Planning and graph logic | nodes, edges, routing, prompts, planner loops | runtime-managed node execution, state commits, tool/model boundary records | graph logic can be correct while the process still crashes or repeats side effects |
| Distributed workflow | queues, worker pools, retries, timers, deployments | agent step lease, fencing, checkpoint, evidence, cancellation semantics | generic workflow retries do not know whether an agent tool side effect already happened |
| Tracing and monitoring | trace UI, dashboards, feedback, experiments, alerts | structured runtime events, evidence refs, policy decisions, cost/failure attribution | after-the-fact traces cannot prevent an unsafe tool call unless runtime checks happen first |
| Eval and regression | datasets, scorers, judges, benchmark reports | replay-safe evidence bundles, deterministic rerun inputs, side-effect-free checks | eval tools need trustworthy evidence and must not re-run real side effects accidentally |
| Tool calling | framework tool descriptors, SDK wrappers, function calling | Tool Ledger, idempotency keys, causal tokens, approval, sandbox, audit | a tool schema alone does not solve duplicate writes, unknown side effects, or stale workers |
| Memory and RAG | vector search, semantic retrieval, knowledge stores | session state, durable memory refs, state versions, replayable state transitions | retrieval results should become visible runtime evidence when they affect execution |
| Sandbox infrastructure | containers, VMs, cluster policy, remote executors | sandbox-required flags, fail-closed routing, audit, replay safety, executor contract | runtime must decide when sandboxing is mandatory even if the executor is external |

## Agent Frameworks

LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, and custom agents are best treated as agent logic layers.

They answer:

```text
What node should run?
What prompt should be used?
Which agent role owns this task?
How should intermediate messages route?
```

AgentLedger answers:

```text
Can this worker commit state?
Has this tool side effect already been attempted?
Does this tool require approval or sandbox execution?
Can this run be replayed without calling the real tool again?
What evidence proves the final result?
```

This is why AgentLedger can be used under a framework instead of replacing it.

## Workflow Backends

Temporal, Ray, and Kubernetes are execution backends. They can own outer scheduling, queues, worker lifecycles, timers, retries, and deployment mechanics.

AgentLedger owns the agent-specific inner boundary:

```text
step lease and fencing
state version checks
Tool Ledger idempotency
policy / approval / sandbox decisions
evidence / replay / attribution
```

A valid stack is:

```text
Temporal workflow
  -> LangGraph node
    -> AgentLedger Runtime
      -> model call / tool call / checkpoint / evidence
```

Temporal can retry a workflow activity. AgentLedger decides whether retrying an agent step should reuse a Tool Ledger response, wait for human verification, block a stale lease, or resume from a checkpoint.

## Observability And Eval Tools

LangSmith, Langfuse, OpenTelemetry collectors, custom dashboards, and eval tools are valuable consumers of AgentLedger output. They are not the same layer.

They usually answer:

```text
What happened?
How did the output compare to a baseline?
Which prompt or model version regressed?
What traces should a developer inspect?
```

AgentLedger answers:

```text
Was the tool call allowed before it executed?
Was the side effect reserved with an idempotency key?
Can replay skip external model/tool calls?
Which state version and lease produced this result?
Which evidence bundle can be handed to an external evaluator?
```

AgentLedger records traces, costs, failures, and evidence because runtime correctness requires them. It does not try to become a full trace store, dashboard, or eval product. Instead, it should export enough evidence for those tools to consume.

## Relative Advantages

AgentLedger is strongest when the risk is not "the agent gave a bad answer" but "the agent execution must be safe and recoverable."

Examples:

- A worker crashes after creating a GitHub PR, sending an email, or writing a ticket.
- A model/tool timeout leaves the external side effect in an unknown state.
- A stale worker tries to commit state after another worker recovered the lease.
- A high-risk tool should require approval or sandbox execution before running.
- A prompt or workflow change must be replayed against historical evidence without repeating real side effects.
- A team needs an evidence bundle that shows state, tool requests, responses, costs, failures, artifacts, and policy decisions.

## Non-goals

AgentLedger should not grow into:

```text
a graph planner
a workflow engine
a trace database
a full eval runner
a RAG system
a sandbox infrastructure provider
a long-running debug application
```

The intended shape is thin but hard to replace: runtime-core enforces invariants, local defaults make it usable, and adapters connect mature external systems.

## Detailed Comparison With Common Tools

| Tool | Primary layer | Overlap with AgentLedger | Key difference | Best used together as |
| --- | --- | --- | --- | --- |
| LangChain | agent app framework and integrations | tools, callbacks/tracing hooks, memory abstractions, runnable chains | LangChain helps compose agent logic; AgentLedger governs durable execution, Tool Ledger idempotency, replay-safe evidence, approval, sandbox, and recovery | LangChain Runnable wrapped by AgentLedger runtime/tool gateway |
| LangGraph | stateful graph/agent workflow | checkpoints, state, interrupts, multi-step graph execution | LangGraph owns graph topology and node routing; AgentLedger owns side-effect ledger, runtime evidence, policy/sandbox boundary, cost/failure attribution, and cross-framework conformance | LangGraph node/checkpointer adapter plus AgentLedger tool/evidence boundary |
| CrewAI | role/team based agent orchestration | multi-agent roles, task delegation, tool use | CrewAI coordinates roles; AgentLedger makes each execution step recoverable, auditable, replayable, and side-effect safe | CrewAI kickoff/run wrapped as an AgentLedger managed step |
| AutoGen | multi-agent conversation framework | agents, messages, tool calls, group chat | AutoGen owns conversation dynamics; AgentLedger owns durable run state, leases, fenced commits, Tool Ledger, approvals, replay, and evidence bundles | AutoGen agent/team under AgentLedger runtime boundary |
| OpenAI Agents SDK | OpenAI-native agent SDK | agent runs, tools, handoffs, tracing concepts | The SDK gives a model/tool programming surface; AgentLedger is framework-neutral reliability infrastructure with durable state, ledger, replay, policy, sandbox, and adapter contracts | OpenAI agent runner wrapped by AgentLedger for governed tools/evidence |
| LlamaIndex | data/RAG and knowledge-agent framework | agents, tools, memory, callbacks | LlamaIndex is strongest for retrieval and knowledge workflows; AgentLedger does not own retrieval, but records retrieval outputs/refs as execution evidence | LlamaIndex query/agent output stored as AgentLedger state/evidence refs |
| Semantic Kernel | enterprise orchestration and skills/functions | planners, functions, memory connectors | Semantic Kernel composes AI functions; AgentLedger controls runtime invariants and side-effect governance outside a single framework | SK function/kernel adapter behind AgentLedger policy and Tool Ledger |
| LangSmith | tracing, datasets, evals, observability for LangChain ecosystem | traces, run comparison, eval workflows, debugging | LangSmith is mostly after-the-fact observability/eval; AgentLedger is in the execution path and can block/approve/sandbox before side effects occur | Export AgentLedger evidence/traces to LangSmith-style analysis |
| Langfuse | LLM observability, traces, prompt/version analytics, eval workflows | traces, costs, sessions, scoring/eval | Langfuse stores and analyzes traces; AgentLedger produces replay-safe evidence and enforces idempotency/policy before tool execution | AgentLedger OTLP/trace/evidence exported to Langfuse or similar tools |
| OpenTelemetry | vendor-neutral telemetry protocol | spans, metrics/logs, service metadata | OTel transports telemetry; AgentLedger defines agent-specific event/evidence semantics and can export OTLP JSON | AgentLedger as producer, OTel collector/backend as sink |
| Temporal | durable workflow runtime | retries, workflow state, activity execution, timers | Temporal owns generic workflow durability; AgentLedger owns agent-specific tool ledger, model/tool evidence, replay safety, approval/sandbox/cost/failure semantics | Temporal workflow -> AgentLedger-managed agent activity |
| Ray | distributed compute/workers | distributed tasks, actors, scheduling | Ray runs distributed Python workloads; AgentLedger governs agent step correctness and side effects | Ray worker executes AgentLedger runtime steps |
| Kubernetes | deployment and scheduling infrastructure | jobs, pods, worker lifecycle, isolation primitives | Kubernetes schedules containers; AgentLedger defines agent run/step leases, evidence, policy, and tool governance | K8s deploys workers/sandboxes that run AgentLedger |
| Braintrust / eval platforms | eval datasets, scorers, experiments | evidence regression, comparisons, scoring | Eval platforms judge outputs; AgentLedger supplies deterministic evidence bundles and replay-safe artifacts | Eval platform consumes AgentLedger evidence bundles |
| Vector DBs / RAG stores | long-term retrieval and semantic memory | memory refs, retrieval artifacts | Vector DBs own knowledge search; AgentLedger owns session state and records retrieval outputs as evidence when they affect execution | Store retrieval refs/results in AgentLedger evidence/state |

## Honest Positioning

AgentLedger is valuable when the hard problem is execution reliability, not agent intelligence. If a team only needs to prototype a prompt chain, LangChain or LangGraph alone may be enough. If a team only needs a trace dashboard, LangSmith or Langfuse may be enough. If a team only needs generic durable workflows, Temporal may be enough.

AgentLedger becomes useful when a run must answer questions such as:

```text
Did this side-effecting tool execute once or twice?
Can this worker still commit state, or did its lease expire?
Which approval, policy, sandbox, cost, and tool ledger records justify this action?
Can I replay this run without calling the real model or external tool again?
Can another language/runtime produce the same evidence semantics?
```

That is the intended boundary: framework-neutral runtime safety and evidence, not a replacement for every framework around it.

---

generated by codex cli
