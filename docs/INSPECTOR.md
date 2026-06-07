# AgentLedger Inspector

AgentLedger Inspector is a language-neutral, read-only debug and audit view for AgentLedger runs. It consumes the same runtime metadata and evidence bundles produced by Python, Go, TypeScript, and Rust implementations.

It is not a long-running service and not a runtime control plane. It does not approve requests, cancel runs, mutate Tool Ledger rows, call tools, or contact model providers.

## Preview

The default renderer is a static reference UI: a paginated run index plus a single-run view with chronological events and full-width JSON details.

![AgentLedger Inspector run index](assets/inspector/runs-index.png)

![AgentLedger Inspector single run](assets/inspector/single-run-timeline.png)

## Install

Inspector is available through the core CLI and as an optional companion package:

```bash
pip install "agentledger-runtime[inspector]"
pip install agentledger-inspector
```

The `agentledger-inspector` package only re-exports the read model and data source API. The CLI entry point remains `agentledger`.

## Language Boundary

Inspector is implemented once as a companion evidence consumer. Go, TypeScript, and Rust implementations do not need their own Inspector UI packages as long as they produce AgentLedger runtime metadata or exported evidence bundles that follow the shared contract.

The boundary is:

- language runtimes write AgentLedger metadata, Tool Ledger rows, events, artifacts, and evidence
- Inspector reads that data through stable read models such as `agentledger.inspector.v1` and `agentledger.inspector.runs.v1`
- users can build their own viewer, API endpoint, or internal debug tool on top of the read model

This keeps Inspector outside runtime-core execution semantics while still making all language implementations debuggable through one tool.

## Data Sources

Inspector supports two read paths.

| Source | Command shape | When to use |
|---|---|---|
| Exported evidence | `agentledger inspector evidence <path>` | Portable artifact from any language implementation or CI job. |
| Local SQLite runtime | `agentledger inspector run <run_id> --root .agentledger` | Local development and small deployments. |
| Run index | `agentledger inspector runs --root .agentledger` | Read-only list of recent runs before opening one run. |
| Direct SQLite path | `agentledger inspector run <run_id> --backend sqlite --db state.db --blob-root blobs` | Custom runtime directory layouts. |
| Postgres metadata | `agentledger inspector run <run_id> --backend postgres --dsn ... --schema ... --blob-root ...` | Server-side StateStore deployments. |
| MySQL metadata | `agentledger inspector run <run_id> --backend mysql --dsn ... --database ... --blob-root ...` | MySQL-backed StateStore deployments. |
| Custom store | `InspectorDataSource.from_runtime_store(...)` | Internal viewers, custom database adapters, or API services. |

### Evidence bundle

This is the most portable path and works for evidence exported by any language implementation:

```bash
agentledger inspector evidence ./evidence/<run_id> --html ./inspector.html
agentledger inspector evidence ./bundle.json --out ./inspector.json
```

### Runtime database

This path reads AgentLedger runtime metadata directly. SQLite is opened in read-only mode and never initialized or migrated by Inspector.

```bash
agentledger inspector run <run_id> --root .agentledger --html ./inspector.html
agentledger inspector run <run_id> --backend sqlite --db .agentledger/state.db --blob-root .agentledger/blobs --out ./inspector.json
agentledger inspector runs --root .agentledger --html ./runs.html
agentledger inspector runs --root .agentledger --out ./runs.json
```

Postgres and MySQL are also supported through the existing StateStore adapter boundaries. Inspector uses read-only store wrappers for these paths and does not run migrations or create tables:

```bash
agentledger inspector run <run_id> --backend postgres --dsn "$AGENTLEDGER_POSTGRES_DSN" --schema agentledger --blob-root .agentledger/blobs --html ./inspector.html
agentledger inspector run <run_id> --backend mysql --dsn "$AGENTLEDGER_MYSQL_DSN" --database agentledger --blob-root .agentledger/blobs --html ./inspector.html
agentledger inspector runs --backend postgres --dsn "$AGENTLEDGER_POSTGRES_DSN" --schema agentledger --html ./runs.html
agentledger inspector runs --backend mysql --dsn "$AGENTLEDGER_MYSQL_DSN" --database agentledger --html ./runs.html
```

Use database credentials with read-only permissions. AgentLedger does not add an Inspector-specific permission system; database grants, filesystem ACLs, and deployment policy remain the enforcement layer. The Inspector code path exposes no runtime write/control actions, but Postgres/MySQL client libraries cannot replace database-side read-only grants.

The `--blob-root` argument currently points at a local blob directory containing the payload blobs referenced by the runtime metadata. If payload blobs live in S3/MinIO or another managed object store, export an evidence bundle first or provide a custom `EvidenceBlobStoreProtocol` implementation through the extension API.

For `agentledger inspector runs`, `--blob-root` is optional. When present, Inspector may use it to extract an application-level `agent_run_id` from event payloads. When absent, the run index still works but may show `agent_run_id` as `-`.

## Output

`--out` writes the stable JSON read model:

```json
{
  "schema_version": "agentledger.inspector.v1",
  "run": {},
  "summary": {},
  "agent_run_id": null,
  "event_stream": [],
  "timeline": [],
  "tool_ledger": [],
  "approvals": [],
  "policy_decisions": [],
  "cost_records": [],
  "failure_events": [],
  "artifacts": []
}
```

`--html` writes a static HTML report for local or internal debugging. The file is self-contained and can be opened without a server.

`agentledger inspector runs --out` writes a run-index read model:

```json
{
  "schema_version": "agentledger.inspector.runs.v1",
  "summary": {},
  "runs": []
}
```

`agentledger inspector runs --html` writes a static read-only run list. The default renderer uses a compact paginated vertical list with status, timestamps, counters, optional Inspector links, and folded JSON details instead of a wide table. Use `--run-link-template "/runs/{run_id}/inspector.html"` when an application or internal tool already exposes single-run Inspector pages and should link from the index to those pages.

## Event Stream

`1.3.5` adds an Event Stream section to the Inspector read model and static HTML report. It is a chronological view of the same run events, sorted by event time and tied together by:

- `runtime_run_id`: the AgentLedger runtime run id
- `agent_run_id`: an agent/application run id when one is present in event metadata or payloads
- `seq`: the original AgentLedger event sequence
- `type`, `step_id`, and `summary`: compact event context
- `related_links`: local links back to detailed timeline, step, tool, approval, policy, or artifact records

This view is intended for debugging a single run from top to bottom. It does not replace the detailed section views; it gives operators a time-ordered path through them.

Detailed tables keep compact record columns on the first row and render the folded JSON payload in a full-width row below each record. This keeps long payloads readable without forcing a narrow right-side details column.

## Navigation And Cross-links

`1.3.3` adds stable row anchors and related links to the Inspector read model. Timeline events, steps, Tool Ledger rows, approval requests, policy decisions, and artifacts may include:

```json
{
  "anchor": "event-1",
  "related_refs": [{"kind": "tool", "value": "email.send"}],
  "related_links": [{"kind": "tool", "value": "email.send", "href": "#tool-email-send"}]
}
```

The default static HTML renderer uses those fields for a top-level section navigation bar and internal links between events, tools, approvals, and artifacts. Custom viewers can consume the same fields from `InspectorReport.to_dict()` and do not need to inspect database tables directly.

These links are local report navigation only. They do not fetch blobs, call tools, mutate runtime state, approve requests, or access remote artifact stores.

## Redaction

Inspector output can include sensitive operational evidence, especially when `--include-payloads` is used. `1.3.2` adds explicit redaction for JSON and HTML reports. Redaction is applied to the Inspector read model before rendering, so custom viewers that consume `InspectorReport.to_dict()` receive the same masked data as the default HTML renderer.

Redact one or more keys directly:

```bash
agentledger inspector evidence ./evidence/<run_id> \
  --include-payloads \
  --redact-key password \
  --redact-key api_token \
  --html ./inspector.html
```

Use a policy file when the same rule should be reused:

```json
{
  "keys": ["password", "api_token", "authorization"],
  "replacement": "[redacted]"
}
```

```bash
agentledger inspector run <run_id> \
  --root .agentledger \
  --redaction-policy ./inspector-redaction.json \
  --out ./inspector.json
```

The built-in policy matches exact key names case-insensitively and also redacts JSON strings that can be parsed as objects or arrays. It is a local debug safeguard, not a substitute for upstream secret management, database permissions, or evidence retention policy.

## Extension API

Inspector is intentionally split into three pieces so users can extend it:

| Layer | API | Purpose |
|---|---|---|
| Data source | `InspectorDataSource` | Read evidence paths or runtime stores. |
| Read model | `InspectorReportBuilder` | Convert evidence into `agentledger.inspector.v1`. |
| Renderer | `InspectorReport.to_html()` | Reference static HTML renderer. |

Example:

```python
from agentledger import InspectorDataSource, InspectorRedactionPolicy, InspectorReportBuilder

policy = InspectorRedactionPolicy(keys=("password", "api_token"))
report = InspectorDataSource().from_evidence_path("./evidence/run-1", redaction_policy=policy)
data = report.to_dict()

custom_report = InspectorReportBuilder().from_evidence_path("./evidence/run-1", redaction_policy=policy)
html = custom_report.to_html()
```

See `../examples/inspector/custom_viewer.py` for a runnable example that creates a temporary runtime, reads SQLite metadata, exports an evidence bundle, and builds a compact custom view from `InspectorReport.to_dict()`.

Custom UIs should consume `InspectorReport.to_dict()` rather than reading undocumented database tables directly. This keeps the UI stable across storage adapters and language implementations.

Custom storage integrations can also provide their own read-only StateStore/BlobStore and reuse the builder:

```python
from agentledger import EvidenceBlobStoreProtocol, EvidenceStateStoreProtocol, InspectorDataSource

report = InspectorDataSource().from_runtime_store(
    store=my_read_only_state_store,
    blobs=my_read_only_blob_store,
    run_id="run_123",
)
data = report.to_dict()
```

`EvidenceStateStoreProtocol` and `EvidenceBlobStoreProtocol` document the minimal read API needed by custom backends. This is the intended extension point for users who want to build a richer internal viewer, an API endpoint, or a different renderer without coupling to internal SQL tables.

For secondary development, keep these contracts stable:

- accept `InspectorReport.to_dict()` as the UI/API input
- preserve `schema_version == "agentledger.inspector.v1"`
- apply `InspectorRedactionPolicy` before exposing reports to users when payloads may contain secrets
- implement `EvidenceStateStoreProtocol` / `EvidenceBlobStoreProtocol` for custom stores
- keep write/control actions out of Inspector surfaces
- use runtime APIs, not Inspector data sources, when an operator needs to approve, deny, cancel, or recover a run

## Security Notes

- Treat Inspector JSON and HTML as sensitive operational evidence.
- Reports can include tool names, tool status, external ids, approval reasons, model metadata, artifact refs, payload summaries, and failure details.
- Use `--redact-key` or `--redaction-policy` before sharing reports outside the local debugging boundary.
- Use read-only DB credentials for Postgres/MySQL.
- Do not build custom write actions on top of Inspector reports. Use runtime APIs for runtime control and keep debug viewers read-only.
- Prefer evidence-bundle input when the blob store is remote or managed by another service.
- Do not point Inspector at production databases with credentials that can mutate runtime tables.

## Current Boundary

Implemented in `1.3.0`:

- language-neutral read model `agentledger.inspector.v1`
- static HTML report export
- evidence bundle input
- SQLite read-only DB input
- Postgres/MySQL DB input through existing adapter boundaries
- extension API for custom data sources and renderers
- optional `agentledger-inspector` companion package

Implemented in `1.3.2`:

- configurable JSON/HTML report redaction through `--redact-key`, `--redaction-policy`, and `InspectorRedactionPolicy`

Implemented in `1.3.3`:

- stable read-model anchors for timeline, step, Tool Ledger, approval, policy, and artifact rows
- static HTML section navigation and internal cross-links between related runtime records

Implemented in `1.3.5`:

- chronological Event Stream in JSON and static HTML reports
- read-only run index through `agentledger inspector runs`
- `agentledger.inspector.runs.v1` run-index read model for custom viewers
- runtime run id and extracted agent run id in event/timeline read-model rows
- safer static HTML layout for long ids, full-width JSON details, and paginated run lists

Not in this version:

- long-running web server
- login, permission, user, or organization management for Inspector surfaces
- write/control-plane actions
- permission, identity, billing, or administration backend
- full LangSmith/Langfuse replacement
- live remote blob adapters inside the Inspector package
