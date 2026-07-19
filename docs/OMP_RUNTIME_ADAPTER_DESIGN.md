# Oh My Pi Runtime Adapter Design

Status: implemented in `1.5.2` as a normalized runtime bridge in the Python, Go, TypeScript, and Rust runtime packages. The bridge does not change the stable v1.x runtime-core contract.

This document defines the boundary for an optional AgentLedger adapter for the Oh My Pi runtime, also referred to as OMP. The adapter is a generic runtime integration, not a product-specific integration for any application built on top of OMP.

## Positioning

AgentLedger should provide the reliability and evidence contract. OMP-based applications can decide where to emit runtime events, state snapshots, tool evidence, and document mutations into that contract.

```text
OMP runtime events
  -> AgentLedger OMP bridge
  -> AgentLedger runs, steps, model evidence, Tool Ledger, failures, state refs, evidence bundles
```

The adapter fits the existing AgentLedger direction:

- optional runtime/framework bridge
- evidence and replay boundary
- Tool Ledger and side-effect governance
- model-call and proposed-tool evidence
- failure lifecycle and attribution
- versioned state refs and state-change audit

It does not change the v1.x runtime-core semantics.

## Non-Goals

The OMP adapter must not contain application-specific product semantics.

It must not know or encode:

- application-specific memory file meanings
- application-specific workspace paths
- application-specific account, quota, subscription, billing, or gateway logic
- application-specific personality, persona, harness, or user-profile rules
- private local paths, secrets, tokens, cookies, or provider keys

If an application has files named `SOUL.md`, `MEMORY.md`, `USER.md`, or any other domain-specific state, that application owns what those files mean. AgentLedger may record versioned state refs, diffs, causes, commit status, and evidence links, but it must not decide the business or product meaning of the files.

## Adapter Inputs

The bridge accepts normalized OMP-facing records instead of scraping private application internals.

The 1.5.2 bridge implements the domain-neutral evidence categories. Approval and sandbox evidence remain existing AgentLedger runtime concepts that OMP integrations may route through tool metadata and policy decisions, but they are not separate OMP-specific APIs in this release.

| OMP-facing input | AgentLedger mapping |
| --- | --- |
| runtime session metadata | run/session identity, framework/runtime metadata, correlation IDs |
| turn start/end | step lifecycle events |
| model request/response | archived model-call evidence, token/cost/failure records |
| model-proposed tool call | `tool_call_proposed` evidence linked to later tool execution when possible |
| tool call/result | Tool Ledger request, execution status, idempotency key, side-effect status |
| approval or policy checkpoint | existing AgentLedger policy/approval records when emitted by the application or tool gateway |
| sandbox-required execution | existing AgentLedger sandbox policy/result refs when emitted by the application or tool gateway |
| runtime error | failure envelope, causal graph inputs, replay plan hints |
| artifact or file ref | artifact/evidence refs with redaction metadata |
| versioned state mutation | state snapshot refs, diff refs, commit/rollback status, causal run/step links |

Applications may emit only the subset they can safely expose. Missing optional evidence must be explicit when it affects replay or audit completeness.

## State Versioning Boundary

Many OMP-based applications maintain runtime-adjacent documents or local state. AgentLedger can already support versioned state management through blobs, refs, state versions, diffs, evidence bundles, and failure records.

The recommended integration shape is:

```text
before state snapshot hash/ref
mutation request source
runtime/model/tool evidence that caused the mutation
diff or patch summary
after state snapshot hash/ref
commit status
rollback or failure evidence
causal run_id / step_id / external session id
```

This is enough to support audit, rollback evidence, replay inspection, and regression review without making AgentLedger a memory product or a document semantics engine.

AgentLedger may provide generic helpers such as:

- `record_state_snapshot(...)`
- `record_state_change(...)`
- `record_state_diff(...)`
- `record_state_commit(...)`
- `record_state_rollback(...)`

Those helpers should stay domain-neutral.

## Public API Boundary

The 1.5.2 implementation is built into the existing runtime packages:

| Ecosystem | Current import |
| --- | --- |
| Python | `from agentledger import OmpLedgerBridge` |
| TypeScript | `import { OmpLedgerBridge } from "agentledger-runtime"` |
| Go | `agentledger.NewOmpLedgerBridge(...)` from `github.com/yaogdu/AgentLedger/go` |
| Rust | `agentledger::OmpLedgerBridge` |

A separate optional package such as `agentledger-omp` may still be created later if the bridge grows beyond the thin translation layer. It is not required for the current release.

## Minimal API Shape

The adapter should expose a small translation layer rather than forcing OMP to depend deeply on AgentLedger internals.

```python
from agentledger import OmpLedgerBridge

bridge = OmpLedgerBridge(runtime=runtime, app_name="my-omp-app")

bridge.record_session_started(session)
bridge.record_turn_started(turn)
bridge.record_model_call(model_call)
bridge.record_tool_proposal(tool_proposal)
bridge.record_tool_execution(tool_call, result)
bridge.record_state_change(state_change)
bridge.record_failure(error)
bridge.record_turn_completed(turn)
```

Equivalent Go, TypeScript, and Rust adapters should follow the same semantic events even when the exact API style differs.

## Redaction And Privacy

The adapter must default to safe records:

- store hashes, refs, sizes, and bounded summaries before storing raw bodies
- make raw prompt, model response, and tool payload archival opt-in
- redact credentials, API keys, cookies, auth headers, private tokens, and secret-looking values
- support application-provided redaction hooks
- preserve evidence completeness flags when content is omitted
- keep application-private paths out of public docs and fixtures

Applications that need richer evidence can opt into BlobStore-backed payload archives with their own redaction rules.

## Replay Semantics

The adapter should preserve AgentLedger replay invariants:

- replay may reuse archived model responses instead of calling the model again
- replay must not repeat external side effects
- tool executions with unknown side-effect status must be marked unsafe for automatic replay
- state mutations should be replayed as refs/diffs unless the application explicitly supplies a safe restore hook
- externally supplied OMP session IDs are correlation evidence, not AgentLedger's only source of truth

## Implementation Status

### Phase 0: Documentation And Contract

- status: complete in 1.5.2 docs
- added this design document and Chinese counterpart
- added roadmap and adapter-roadmap entries
- documented the non-goal that this is an OMP runtime bridge, not an application-specific adapter

### Phase 1: Evidence Mapping Prototype

- status: complete in 1.5.2 across Python, Go, TypeScript, and Rust
- defined `OmpSession`, `OmpTurn`, `OmpModelCall`, `OmpToolProposal`, `OmpToolExecution`, `OmpFailure`, and `OmpStateChange` input types
- mapped these records to existing AgentLedger runtime events and read models
- added tests with no OMP dependency
- added small examples that feed synthetic OMP events into AgentLedger

### Phase 2: Optional Package

- status: future optional packaging
- publish the adapter as optional packages where there is real API surface
- add conformance fixtures for session/turn/tool/model/failure/state-change translation
- add redaction and evidence-completeness tests
- add language-specific quickstarts where the OMP ecosystem exists

### Phase 3: Application Integration Guidance

- status: roadmap
- document how an OMP-based application can choose its own event emission points
- document how applications can record versioned document changes without exposing domain-specific semantics
- add an adoption note that private applications should keep their own business paths and product rules outside AgentLedger

## Acceptance Criteria

- The adapter boundary is documented as OMP-specific, not application-specific.
- The roadmap makes clear that runtime-core remains framework-neutral and does not learn application business semantics.
- State versioning is described as generic versioned refs/diffs/evidence, not as a memory product.
- The current built-in bridge is available across Python, Go, TypeScript, and Rust with tests and examples.
- Optional package names and later hardening phases are clear enough to create issues without re-litigating scope.
- Documentation contains no private paths, secrets, or product-specific implementation claims.
