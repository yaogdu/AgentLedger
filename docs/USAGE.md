# Usage Guide

This guide shows how to use AgentLedger as a runtime reliability layer for Agent Harness stacks. It focuses on the stable runtime-core and dependency-free local usage. For release gates, see `RELEASE_CHECKLIST.md`.

## Install or Run from Source

AgentLedger currently has no mandatory third-party runtime dependency.

Use Python 3.11 or newer. If your system `python3` is older, replace it with `python3.11`.

Install from PyPI:

```bash
python3 -m pip install agentledger-runtime
agentledger --help
agentledger doctor
```

The PyPI distribution is `agentledger-runtime`; import it as `agentledger`:

```python
from agentledger import agent, run
```

`agentledger --help` and `agentledger doctor` print the GitHub documentation URL so users know where to start after installation.

Run from the repository root:

```bash
PYTHONPATH=src python3 -m agentledger --help
PYTHONPATH=src python3 -m agentledger doctor
```

Editable install after packaging setup:

```bash
python3 -m pip install -e .
agentledger --help
```

Optional adapters:

```bash
python3 -m pip install "agentledger-runtime[postgres]"
python3 -m pip install "agentledger-runtime[mysql]"
python3 -m pip install "agentledger-runtime[s3]"
python3 -m pip install "agentledger-runtime[langfuse]"
python3 -m pip install "agentledger-runtime[inspector]"
```

For local development from the repository, use extras such as `python3 -m pip install -e ".[postgres]"`, `python3 -m pip install -e ".[mysql]"`, `python3 -m pip install -e ".[s3]"`, `python3 -m pip install -e ".[langfuse]"`, or `python3 -m pip install -e ".[inspector]"`.

## First 10 Minutes

Use this path to verify the runtime locally before reading the deeper design docs:

```bash
PYTHONPATH=src python3 examples/hello_world/hello.py
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo run examples/side_effect_idempotency
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo debug <run_id> --json --include-diffs
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo ledger <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo replay <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo evidence <run_id> --html ./evidence.html
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo inspector run <run_id> --html ./inspector.html
```

The important behavior to observe is not the text output; it is that the run has durable state, leased steps, a Tool Ledger entry, replay without side effects, and exportable evidence.

## Hello World

```python
from agentledger import agent, run

@agent
def hello(ctx):
    return "hello world"

result = run(hello)
print(result.output)
print(result.run_id)
```

Even this minimal example creates a durable run, claims a step with a lease, records events, commits state, and can export evidence later.

Run the included example:

```bash
PYTHONPATH=src python3 examples/hello_world/hello.py
```

## Side-effect Idempotency Demo

The flagship demo simulates a worker crash after an external side effect. The retry reuses the Tool Ledger instead of duplicating the side effect.

```bash
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo run examples/side_effect_idempotency
```

Use the printed `run_id`:

```bash
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo debug <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo ledger <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo replay <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo evidence <run_id> --dir ./evidence/<run_id>
```

## Register a Runtime-managed Tool

Use `Runtime.tool(...)` or `ToolSpec` so tools go through schema validation, policy, approval, budget, sandbox checks, Tool Ledger, and evidence capture.

The dependency-free schema subset supports portable object, array, string, numeric, enum/const, composition, and uniqueness constraints; framework-specific validators can still live in optional adapters.

```python
from agentledger import Runtime

rt = Runtime.local(".agentledger-tools")

@rt.tool(
    name="docs.read",
    description="Read a document by path.",
    side_effect="none",
    input_schema={
        "type": "object",
        "required": ["path"],
        "properties": {"path": {"type": "string", "minLength": 1}},
        "additionalProperties": False,
    },
)
def read_doc(args):
    return {"path": args["path"], "content": ""}
```

Export a manifest:

```bash
PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/docs
PYTHONPATH=src python3 -m agentledger tools manifest --format openai --example examples/docs
```

## Policy and Approval

Policy files are YAML/JSON-like and map roles to tool permissions. Check a policy without running an agent:

```bash
PYTHONPATH=src python3 -m agentledger policy check examples/policy/local.policy.yaml ExecutorAgent github.create_issue medium
```

Run with a policy:

```bash
PYTHONPATH=src python3 -m agentledger --policy examples/policy/local.policy.yaml run examples/side_effect_idempotency
```

Approval commands:

```bash
PYTHONPATH=src python3 -m agentledger approvals <run_id>
PYTHONPATH=src python3 -m agentledger approve <approval_id> --approver alice --reason "reviewed"
PYTHONPATH=src python3 -m agentledger deny <approval_id> --approver alice --reason "not allowed"
```

## Evidence, Replay, Debug, and Regression Checks

AgentLedger is evidence-first. Most reliability tools read existing runtime metadata and do not call tools or model providers.

```bash
PYTHONPATH=src python3 -m agentledger evidence <run_id> --out ./bundle.json
PYTHONPATH=src python3 -m agentledger evidence <run_id> --dir ./bundle-dir
PYTHONPATH=src python3 -m agentledger evidence <run_id> --html ./evidence.html
PYTHONPATH=src python3 -m agentledger replay <run_id>
PYTHONPATH=src python3 -m agentledger timetravel <run_id> --include-diffs --include-states --html ./time-travel.html
PYTHONPATH=src python3 -m agentledger inspector run <run_id> --root .agentledger-demo --html ./inspector.html
PYTHONPATH=src python3 -m agentledger inspector evidence ./bundle-dir --html ./inspector.html
PYTHONPATH=src python3 examples/inspector/custom_viewer.py
PYTHONPATH=src python3 -m agentledger evidence-check <run_id>  # side-effect-free evidence invariant check
PYTHONPATH=src python3 -m agentledger review checklist <run_id> --fail-on-risk
```

`inspector` is a read-only evidence consumer. It can read exported evidence bundles or connect to SQLite/Postgres/MySQL runtime metadata with read-only credentials. It does not mutate runtime state or act as a web control plane. `examples/inspector/custom_viewer.py` shows how to build a custom viewer/API payload from the stable read model. See `INSPECTOR.md` for DB options and extension APIs.

Regression and corpus commands:

```bash
PYTHONPATH=src python3 -m agentledger evidence-regression ./golden-bundle.json ./current-bundle-dir
PYTHONPATH=src python3 -m agentledger corpus seed --list-builtins
PYTHONPATH=src python3 -m agentledger corpus seed minimal-success
PYTHONPATH=src python3 -m agentledger corpus seed tool-ledger-success
PYTHONPATH=src python3 -m agentledger corpus seed media-stream-checkpoint
PYTHONPATH=src python3 -m agentledger corpus add side-effect ./golden-bundle.json
PYTHONPATH=src python3 -m agentledger corpus check side-effect ./current-bundle-dir
PYTHONPATH=src python3 -m agentledger divergence ./golden-bundle.json ./current-bundle-dir --evidence-paths
```

## Workers, Cancellation, and Recovery

Run a transient retry worker example:

```bash
PYTHONPATH=src python3 -m agentledger --root .agentledger-worker worker-run examples/transient_retry
PYTHONPATH=src python3 -m agentledger --root .agentledger-worker worker serve examples/transient_retry --max-loops 5
PYTHONPATH=src python3 -m agentledger --root .agentledger-worker worker plan examples/transient_retry --replicas 2
```

Operate on a run:

```bash
PYTHONPATH=src python3 -m agentledger status <run_id>
PYTHONPATH=src python3 -m agentledger cancel <run_id> --reason "operator requested"
PYTHONPATH=src python3 -m agentledger recover-expired
```

## Storage

Default local storage:

```text
SQLite WAL StateStore + local file BlobStore
```

SQLite migration commands:

```bash
PYTHONPATH=src python3 -m agentledger migrate status
PYTHONPATH=src python3 -m agentledger migrate ddl --dialect sqlite
```

Postgres and MySQL are optional adapter boundaries:

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
PYTHONPATH=src python3 -m agentledger migrate up --dialect postgres

AGENTLEDGER_MYSQL_DSN=mysql://user:password@localhost:3306/database \
PYTHONPATH=src python3 -m agentledger migrate up --dialect mysql
```

Do not run adapter conformance against real application data. Use temporary test services. MySQL support in `1.4.0` is an official adapter boundary; production use still requires real-service concurrency, permission, backup, and restore validation.

## Media and Streams

Runtime core stores refs, metadata, lineage, offsets, and checkpoints. It does not decode media or implement stream transport.

```bash
PYTHONPATH=src python3 examples/media_stream/basic_media_stream.py
PYTHONPATH=src python3 examples/media_stream/managed_tool.py
PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/media_stream
```

## Boundary Lint and Conformance

```bash
PYTHONPATH=src python3 -m agentledger lint boundary examples src --exclude src/agentledger --no-fail
PYTHONPATH=src python3 -m agentledger lint boundary ./my_agents --rules examples/lint/boundary_rules.json
PYTHONPATH=src python3 -m agentledger conformance
PYTHONPATH=src python3 -m agentledger state conformance --backend sqlite
PYTHONPATH=src python3 -m agentledger blob conformance --backend local
PYTHONPATH=src python3 -m agentledger worker conformance --backend sqlite --concurrent
PYTHONPATH=src python3 -m agentledger adapter conformance --kind langchain
PYTHONPATH=src python3 -m agentledger adapter certify --kind postgres --adapter-version 1.4.0 --out ./postgres-certification.json
PYTHONPATH=src python3 -m agentledger adapter certify --kind mysql --adapter-version 1.4.0 --out ./mysql-certification.json
```

`adapter certify` emits a machine-readable adapter certification bundle. It records package metadata, conformance commands, smoke commands, required external services, security assumptions, known limitations, and whether production validation still requires real infrastructure. For example, Postgres/MySQL/S3/Docker/Temporal bundles are marked `external-required` until they have real service credentials, concurrency/load checks, and restore or rollback drills.

## What Not To Do

- Do not call risky tools directly from agent code when they should be runtime-managed.
- Do not store secrets or raw large media payloads in event payloads.
- Do not treat replay or shadow mode as permission to call external systems.
- Do not point conformance or destructive experiments at real application data.
- Do not put application business schemas inside AgentLedger runtime metadata.

## Where To Go Next

| Need | Read |
| --- | --- |
| Understand the runtime boundary | `ARCHITECTURE.md` |
| Learn state, Tool Ledger, replay, and worker internals | `DESIGN_AND_IMPLEMENTATION.md` |
| Extend tools, storage, frameworks, sandbox, or observability | `EXTENSIBILITY.md` |
| Check what is stable, preview, or roadmap | `IMPLEMENTATION_STATUS.md` and `MATURITY_MODEL.md` |
| Prepare a release or contribution | `RELEASE_CHECKLIST.md` and `../CONTRIBUTING.md` |

---

generated by codex cli
