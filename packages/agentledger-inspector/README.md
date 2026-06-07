# agentledger-inspector

Read-only Inspector and evidence viewer package for AgentLedger.

This package is language-neutral. It is implemented once as a companion evidence consumer and can inspect evidence/runtime metadata produced by Python, Go, TypeScript, or Rust implementations when they follow the AgentLedger contract.

```bash
pip install agentledger-inspector
pip install "agentledger-runtime[inspector]"
```

Inspect a local runtime database:

```bash
agentledger inspector run <run_id> --root .agentledger --html ./inspector.html
```

Inspect recent runs from a local runtime database:

```bash
agentledger inspector runs --root .agentledger --html ./runs.html
agentledger inspector runs --root .agentledger --out ./runs.json
```

Inspect an exported evidence bundle:

```bash
agentledger inspector evidence ./evidence/<run_id> --html ./inspector.html
```

Redact sensitive keys before writing JSON or HTML:

```bash
agentledger inspector evidence ./evidence/<run_id> \
  --include-payloads \
  --redact-key password \
  --redact-key api_token \
  --html ./inspector.html
```

Reusable redaction policy:

```json
{
  "keys": ["password", "api_token", "authorization"],
  "replacement": "[redacted]"
}
```

```bash
agentledger inspector run <run_id> --root .agentledger --redaction-policy ./inspector-redaction.json --out ./inspector.json
```

For Postgres or MySQL, use a read-only database credential and pass the local blob root that contains the referenced payload blobs. Inspector uses read-only store wrappers and does not run migrations or create tables:

```bash
agentledger inspector run <run_id> --backend postgres --dsn "$AGENTLEDGER_POSTGRES_DSN" --blob-root .agentledger/blobs --html ./inspector.html
agentledger inspector run <run_id> --backend mysql --dsn "$AGENTLEDGER_MYSQL_DSN" --blob-root .agentledger/blobs --html ./inspector.html
```

The Inspector does not start a server, mutate runtime state, call tools, approve requests, or contact model providers. It builds a language-neutral read model from AgentLedger runtime metadata or exported evidence bundles. AgentLedger does not add a separate permission layer for Inspector; use database grants, filesystem ACLs, and deployment policy.

Static HTML reports include local section navigation, a chronological Event Stream, a read-only run index, and internal cross-links between related timeline events, steps, Tool Ledger rows, approvals, policy decisions, and artifacts. Custom viewers can reuse the same `event_stream`, `anchor`, `related_refs`, `related_links`, and run-index fields from `InspectorReport.to_dict()` / `InspectorRunIndex.to_dict()`.

Extension API:

```python
from agentledger_inspector import EvidenceBlobStoreProtocol, EvidenceStateStoreProtocol, InspectorDataSource, InspectorRedactionPolicy, InspectorReportBuilder

policy = InspectorRedactionPolicy(keys=("password", "api_token"))
report = InspectorDataSource().from_evidence_path("./evidence/run-1", redaction_policy=policy)
data = report.to_dict()
html = report.to_html()

builder = InspectorReportBuilder()
custom_report = builder.from_evidence_path("./evidence/run-1", redaction_policy=policy)

custom_source_report = InspectorDataSource().from_runtime_store(
    store=my_read_only_state_store,
    blobs=my_read_only_blob_store,
    run_id="run_123",
)

run_index = InspectorDataSource().runs_from_runtime_store(
    store=my_read_only_state_store,
    blobs=my_read_only_blob_store,
    run_link_template="/runs/{run_id}/inspector.html",
)
```

The default HTML renderer is a reference renderer. Users can build their own UI by consuming `InspectorReport.to_dict()` / `InspectorRunIndex.to_dict()` and preserving `schema_version == agentledger.inspector.v1` or `agentledger.inspector.runs.v1`. The package does not include a long-running web server, login system, permission system, or runtime control plane.

`EvidenceStateStoreProtocol` and `EvidenceBlobStoreProtocol` describe the minimal read API for custom database/blob backends.

Custom viewers should depend on the read model and protocols instead of undocumented SQL tables. Keep write/control actions outside Inspector surfaces; use runtime APIs for approve, deny, cancel, or recover operations.

Runnable custom-viewer example:

```bash
git clone https://github.com/yaogdu/AgentLedger.git
cd AgentLedger
PYTHONPATH=src python3 examples/inspector/custom_viewer.py
```

That example creates a temporary runtime, reads SQLite metadata, exports an evidence bundle, writes JSON/HTML reports, and builds a compact custom UI/API payload from `InspectorReport.to_dict()`.

Security note: Inspector output may include tool arguments, model metadata, artifact references, approval reasons, and failure details. Treat exported JSON/HTML as sensitive operational evidence.
