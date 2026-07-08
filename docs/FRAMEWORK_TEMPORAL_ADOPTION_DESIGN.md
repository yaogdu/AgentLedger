# 1.5.0 Framework and Temporal Adoption Design

Status: design draft for the next adoption-focused release.

This release should make AgentLedger easier to adopt inside existing agent and workflow stacks without expanding runtime-core into a framework, workflow engine, trace UI, eval platform, or model gateway.

## Goal

`1.5.0` should prove three integration paths:

```text
OpenAI Agents SDK-style agents can route tool/model evidence through AgentLedger.
Framework-native examples can demonstrate the runtime boundary without replacing the framework.
Temporal-style workflow execution can call AgentLedger inside workflow activities while preserving ownership boundaries.
```

The target user should be able to look at the examples and answer:

```text
Where does AgentLedger sit?
What does my existing framework still own?
What evidence does AgentLedger add?
How do I replay/debug without repeating side effects?
```

## Scope

Included:

- focused OpenAI Agents SDK-style example
- Temporal bridge example and optional adapter boundary
- framework-native smoke fixtures for common adoption paths
- documentation that explains framework/workflow ownership boundaries
- CI smoke checks that keep examples runnable

Excluded:

- no new planner, graph engine, team orchestration, or agent collaboration framework
- no replacement for OpenAI Agents SDK, LangGraph, CrewAI, AutoGen, LangChain, or Temporal
- no Temporal server requirement in core tests
- no long-running web service or hosted control plane
- no model provider routing or provider SDK bundling

## Layering

```text
Agent framework
  owns: agent definitions, prompts, planning, handoffs, graph/team topology

Workflow backend
  owns: long-running workflow lifecycle, activity retries, worker orchestration, timers

AgentLedger
  owns: run/step evidence, model/tool boundary records, Tool Ledger,
        approval/sandbox/budget gates, replay-safe evidence, cost/failure attribution
```

AgentLedger should be embedded at the execution boundary of a framework node, activity, or tool call. It should not own the framework's planning loop or Temporal's workflow lifecycle.

## OpenAI Agents SDK-style Example

The example should remain dependency-light. If the exact SDK is not installed, a small local facade can model the integration shape while the docs explain the real SDK boundary.

Required flow:

```text
create AgentLedger run
record model request/response or model failure evidence
record model-proposed tool call
call a runtime-managed tool through ctx.call_tool(...)
trigger approval for a high-risk tool
commit state after approval/tool execution
export evidence
open Inspector or replay summary
```

Required evidence:

- `model_call_requested`
- `model_call_completed` or `model_call_failed`
- `tool_call_proposed`
- Tool Ledger row
- approval request and approval decision when the tool is high risk
- cost records for model/tool usage where available
- replay summary that does not call the provider or tool again

Acceptance criteria:

- example runs without network access by default
- output includes run id, evidence path, replay summary, and Inspector/static debug path when available
- failure path demonstrates model/tool evidence without requiring a real provider
- docs state clearly that OpenAI endorsement or certification is not implied

## Framework-native Smoke Fixtures

The smoke fixtures should not be large demos. They should prove that common frameworks can preserve the AgentLedger boundary.

Initial fixture set:

```text
LangGraph-style node
OpenAI Agents SDK-style agent/tool call
LangChain runnable facade
CrewAI / AutoGen method facade where dependency-free fixtures already exist
```

Each fixture should prove:

- framework code can call into an AgentLedger run
- framework-owned input/output is attached as evidence or final state
- tool calls with side effects still go through ToolGateway
- model evidence can be recorded even when the framework or provider SDK executes the call
- replay/debug reads evidence instead of rerunning framework work

CI should prefer dependency-free fixtures. Exact framework SDK smoke tests can be optional and guarded behind extras or environment variables.

## Temporal Bridge Design

Temporal should be treated as an execution backend, not as an AgentLedger replacement.

Temporal owns:

- workflow lifecycle
- activity scheduling
- workflow/activity retry policy
- timers and long waits
- worker orchestration
- workflow history

AgentLedger owns inside the activity:

- `run_id` and `step_id` evidence
- Tool Ledger idempotency
- model-call evidence and tool-call proposals
- approval/sandbox/budget gates
- cost/failure attribution
- replay-safe evidence export

Recommended mapping:

| Temporal concept | AgentLedger concept |
|---|---|
| workflow id | `external_workflow_id` metadata on run/session |
| workflow run id | `external_workflow_run_id` metadata |
| activity id | `external_activity_id` metadata on step or event |
| activity retry attempt | AgentLedger step attempt metadata, not the source of truth for Tool Ledger idempotency |
| activity failure | failure event and failure envelope inside AgentLedger when it occurs inside the runtime boundary |
| workflow cancellation | AgentLedger cancellation request propagated to active run/steps when the activity observes cancellation |

Key rule:

```text
Temporal may retry the activity.
AgentLedger must prevent duplicate tool side effects inside the retried activity.
```

The bridge example should intentionally simulate:

```text
activity starts
runtime-managed tool side effect succeeds
activity crashes before framework/workflow-level success
Temporal-style retry calls the activity again
AgentLedger Tool Ledger reuses the prior side-effect result
evidence proves one external side effect and two activity attempts
```

Replay behavior:

- AgentLedger replay should not start a new Temporal workflow.
- AgentLedger replay should read evidence and report the Temporal/workflow metadata.
- If a candidate rerun would execute Temporal activities again, it must be labeled as a new run, not replay.

Failure ownership:

- Temporal workflow failure explains scheduling/activity outcome.
- AgentLedger failure attribution explains model/tool/policy/sandbox/budget/state outcome inside the activity.
- Reports should cross-link through workflow/activity metadata, not merge both systems into one hidden state machine.

Cancellation ownership:

- Temporal cancellation is external input.
- AgentLedger should record cancellation intent and fence stale commits when the runtime observes it.
- Child or activity-local side effects still follow Tool Ledger and sandbox/approval rules.

Acceptance criteria:

- dependency-free Temporal-style bridge example runs in CI
- docs explain how to replace the local facade with the real Temporal SDK
- output proves activity retry did not duplicate external side effects
- evidence export includes workflow/activity correlation metadata
- failure/cost attribution remains visible through AgentLedger reports

## Contract and Schema Impact

Prefer metadata and event payload additions before adding new required schema fields.

Allowed in this release:

- framework/workflow metadata in event payloads, run metadata, or evidence exports
- adapter helper functions or optional package boundaries
- examples and smoke fixtures

Avoid unless proven necessary:

- required StateStore schema migrations
- new stable runtime-core event types
- changing Tool Ledger idempotency semantics
- making Temporal or any framework SDK a core dependency

## Tests and Gates

Required local checks:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python scripts/benchmark_runtime.py --iterations 20 --output-dir /tmp/agentledger-benchmark
python scripts/check_language_parity.py
```

Required new checks:

- OpenAI Agents SDK-style example smoke
- Temporal bridge retry/idempotency smoke
- at least one framework-native boundary smoke
- boundary lint remains clean
- benchmark coverage either reuses current semantic checks or adds a new semantic check only if a durable runtime invariant changes

## Documentation Deliverables

- example README for OpenAI Agents SDK-style integration
- example README for Temporal bridge
- update `docs/EXECUTION_BACKENDS.md` with the Temporal ownership split if needed
- update `docs/USE_CASES.md` with framework/workflow adoption path
- update `docs/ROADMAP.md` implementation status after release

## Definition of Done

`1.5.0` is complete when:

- a developer can run the OpenAI Agents SDK-style example and see model/tool/approval/evidence/replay output
- a developer can run the Temporal bridge example and see retry without duplicate side effects
- framework-native smoke fixtures are covered by tests or CI
- benchmark and language parity gates remain green
- docs clearly state what AgentLedger owns and what the framework/workflow backend owns

---

generated by codex cli
