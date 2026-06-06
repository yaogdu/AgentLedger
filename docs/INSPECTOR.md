# AgentLedger Inspector

AgentLedger Inspector is a language-neutral, read-only debug and audit view for AgentLedger runs. It consumes the same runtime metadata and evidence bundles produced by Python, Go, TypeScript, and Rust implementations.

It is not a long-running service and not a runtime control plane. It does not approve requests, cancel runs, mutate Tool Ledger rows, call tools, or contact model providers.

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
- Inspector reads that data through the stable read model `agentledger.inspector.v1`
- users can build their own viewer, API endpoint, or internal debug tool on top of the read model

This keeps Inspector outside runtime-core execution semantics while still making all language implementations debuggable through one tool.

## Data Sources

Inspector supports two read paths.

| Source | Command shape | When to use |
|---|---|---|
| Exported evidence | `agentledger inspector evidence <path>` | Portable artifact from any language implementation or CI job. |
| Local SQLite runtime | `agentledger inspector run <run_id> --root .agentledger` | Local development and small deployments. |
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
```

Postgres and MySQL are also supported through the existing StateStore adapter boundaries. Inspector uses read-only store wrappers for these paths and does not run migrations or create tables:

```bash
agentledger inspector run <run_id> --backend postgres --dsn "$AGENTLEDGER_POSTGRES_DSN" --schema agentledger --blob-root .agentledger/blobs --html ./inspector.html
agentledger inspector run <run_id> --backend mysql --dsn "$AGENTLEDGER_MYSQL_DSN" --database agentledger --blob-root .agentledger/blobs --html ./inspector.html
```

Use database credentials with read-only permissions. AgentLedger does not add an Inspector-specific permission system; database grants, filesystem ACLs, and deployment policy remain the enforcement layer. The Inspector code path exposes no runtime write/control actions, but Postgres/MySQL client libraries cannot replace database-side read-only grants.

The `--blob-root` argument currently points at a local blob directory containing the payload blobs referenced by the runtime metadata. If payload blobs live in S3/MinIO or another managed object store, export an evidence bundle first or provide a custom `EvidenceBlobStoreProtocol` implementation through the extension API.

## Output

`--out` writes the stable JSON read model:

```json
{
  "schema_version": "agentledger.inspector.v1",
  "run": {},
  "summary": {},
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

## Extension API

Inspector is intentionally split into three pieces so users can extend it:

| Layer | API | Purpose |
|---|---|---|
| Data source | `InspectorDataSource` | Read evidence paths or runtime stores. |
| Read model | `InspectorReportBuilder` | Convert evidence into `agentledger.inspector.v1`. |
| Renderer | `InspectorReport.to_html()` | Reference static HTML renderer. |

Example:

```python
from agentledger import InspectorDataSource, InspectorReportBuilder

report = InspectorDataSource().from_evidence_path("./evidence/run-1")
data = report.to_dict()

custom_report = InspectorReportBuilder().from_evidence_path("./evidence/run-1")
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
- implement `EvidenceStateStoreProtocol` / `EvidenceBlobStoreProtocol` for custom stores
- keep write/control actions out of Inspector surfaces
- use runtime APIs, not Inspector data sources, when an operator needs to approve, deny, cancel, or recover a run

## Security Notes

- Treat Inspector JSON and HTML as sensitive operational evidence.
- Reports can include tool names, tool status, external ids, approval reasons, model metadata, artifact refs, payload summaries, and failure details.
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

Not in this version:

- long-running web server
- write/control-plane actions
- user/organization management
- permission, identity, billing, or administration backend
- full LangSmith/Langfuse replacement
- live remote blob adapters inside the Inspector package
