# Storage

AgentLedger stores runtime metadata, not application business data.

The default local backend is SQLite with WAL mode. A hello-world user should not need to see or manage any DDL:

```python
from agentledger import agent, run

@agent
def hello(ctx):
    return "hello"

run(hello)
```

The runtime creates `.agentledger/state.db`, applies built-in migrations, and uses the schema for runs, steps, events, tool ledger rows, artifacts, cost records, and approval requests.

## What The Schema Owns

AgentLedger-owned tables are internal runtime metadata:

```text
runs
steps
events
tool_ledger
artifacts
cost_records
approval_requests
schema_migrations
```

They are separate from user application tables such as users, orders, documents, tickets, tasks, or customer records.

## Migrations

Runtime core includes a dependency-free SQLite migration runner and DDL catalog.

```bash
PYTHONPATH=src python3 -m agentledger migrate up
PYTHONPATH=src python3 -m agentledger migrate status
PYTHONPATH=src python3 -m agentledger migrate ddl --dialect sqlite
PYTHONPATH=src python3 -m agentledger migrate ddl --dialect postgres
PYTHONPATH=src python3 -m agentledger migrate ddl --dialect mysql
```

For configured Postgres backends, `migrate up` creates or advances only AgentLedger-owned runtime tables and `schema_migrations`; it does not drop schemas or delete data:

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
AGENTLEDGER_POSTGRES_SCHEMA=agentledger \
PYTHONPATH=src python3 -m agentledger migrate up --dialect postgres

AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
AGENTLEDGER_POSTGRES_SCHEMA=agentledger \
PYTHONPATH=src python3 -m agentledger migrate status --dialect postgres
```

For configured MySQL backends, `migrate up` follows the same non-destructive rule:

```bash
AGENTLEDGER_MYSQL_DSN=mysql://user:password@localhost:3306/database \
PYTHONPATH=src python3 -m agentledger migrate up --dialect mysql

AGENTLEDGER_MYSQL_DSN=mysql://user:password@localhost:3306/database \
PYTHONPATH=src python3 -m agentledger migrate status --dialect mysql
```

The current built-in schema version is:

```text
0001_initial_runtime_metadata
```

Migration state is recorded in `schema_migrations`. The SQLite backend auto-applies migrations during `Runtime.local(...)` and `agentledger init`.

## Extension Contract

The runtime owns semantics, not infrastructure choices.

Storage adapters can use SQLite, Postgres, MySQL, DynamoDB, FoundationDB, or an internal enterprise store as long as they preserve runtime invariants:

```text
append-only event ordering per run
state version checks
lease token and fencing validation
atomic state patch + completion events
Tool Ledger idempotency uniqueness
approval state durability
expired lease recovery
cancellation fencing
```

Adapters should implement `StateStoreProtocol` and pass `StateStoreConformanceRunner`. Backends used by worker pools should also pass `WorkerConformanceRunner` against a shared backing store.

## SQLite

SQLite is the default local-first implementation:

```text
zero external services
WAL mode
foreign keys enabled
busy timeout enabled
automatic migrations
```

It is suitable for local development, examples, tests, and small single-node deployments.

## Postgres

Postgres has an experimental psycopg-backed adapter path with DDL, migration status/apply CLI, schema isolation, JSONB parameter handling, native `FOR UPDATE SKIP LOCKED` worker claiming, connection-injection conformance tests, CLI conformance, opt-in real-service integration tests, and a CI Postgres service conformance job. A hardened production deployment still needs migration rollout guidance, backup/restore procedures, and operational tuning. See `docs/POSTGRES.md`.

Expected production behavior:

```text
transactional claim/commit
SELECT ... FOR UPDATE SKIP LOCKED or equivalent worker claiming
unique idempotency constraints
JSONB runtime payload fields
schema migrations
backup/restore guidance
StateStoreConformanceRunner and WorkerConformanceRunner coverage
real Postgres integration tests
```

Local SQLite state conformance runs without external services:

```bash
PYTHONPATH=src python3 -m agentledger state conformance --backend sqlite
PYTHONPATH=src python3 -m agentledger worker conformance --backend sqlite --concurrent
```

Postgres conformance is explicit and requires `psycopg` plus a configured DSN:

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://agentledger:secret@localhost:5432/agentledger \
AGENTLEDGER_POSTGRES_SCHEMA=agentledger \
PYTHONPATH=src python3 -m agentledger state conformance --backend postgres
PYTHONPATH=src python3 -m agentledger worker conformance --backend postgres --concurrent
```

## MySQL

MySQL has an optional `pymysql`-backed adapter path with DDL, migration status/apply CLI, JSON runtime payload fields, and cross-language injected SQL adapter contracts. A hardened production deployment still needs migration rollout guidance, backup/restore procedures, real-service concurrency checks, and operational tuning. See `docs/MYSQL.md`.

MySQL conformance is explicit and requires `pymysql` plus a configured DSN:

```bash
AGENTLEDGER_MYSQL_DSN=mysql://agentledger:secret@localhost:3306/agentledger \
PYTHONPATH=src python3 -m agentledger state conformance --backend mysql
PYTHONPATH=src python3 -m agentledger worker conformance --backend mysql --concurrent
```

## Blob Stores

Blob stores hold immutable JSON payloads and artifacts referenced by the event log, evidence bundles, tool ledger rows, and trace exports. The runtime database should keep metadata, hashes, refs, indexes, and state versions; large immutable payloads should live behind `BlobStoreProtocol`.

Media and stream artifacts follow the same rule: runtime-core stores JSON manifests with refs, metadata, lineage, offsets, and watermarks. Raw audio/video bytes, codecs, frame extraction, transcription, and stream transport belong in tools or optional adapters.

Implemented adapters:

```text
LocalBlobStore: file-backed content-addressed JSON for local development
S3BlobStore: experimental S3/MinIO-compatible content-addressed JSON adapter
```

`S3BlobStore` keeps cloud SDKs optional. Production wiring can either inject an S3-compatible client or install/configure boto3 outside runtime core:

```python
from agentledger import S3BlobStore, S3BlobStoreConfig

blobs = S3BlobStore(
    S3BlobStoreConfig(
        bucket="agentledger-runs",
        prefix="prod/blobs",
        endpoint_url="http://minio.local:9000",  # omit for AWS S3
    ),
    client=my_s3_client,  # optional; useful for tests or enterprise wrappers
)
```

The same config can be loaded from environment variables for CLI and deployment smoke tests:

```text
AGENTLEDGER_S3_BUCKET=agentledger-runs
AGENTLEDGER_S3_PREFIX=prod/blobs
AGENTLEDGER_S3_ENDPOINT_URL=http://minio.local:9000
AGENTLEDGER_S3_REGION=us-east-1
AGENTLEDGER_S3_PROFILE=dev
```

Local conformance runs without cloud dependencies:

```bash
PYTHONPATH=src python3 -m agentledger blob conformance --backend local
```

S3/MinIO conformance is explicit and requires either a configured boto3 environment or a user-provided wrapper/client in application code:

```bash
AGENTLEDGER_S3_BUCKET=agentledger-runs \
AGENTLEDGER_S3_ENDPOINT_URL=http://localhost:9000 \
PYTHONPATH=src python3 -m agentledger blob conformance --backend s3
```

Adapter invariants:

```text
put_json returns a sha256 digest and stable content-addressed ref
get_json rejects unsupported refs and bucket mismatches
same JSON value produces the same digest/ref
runtime core does not import boto3 unless the adapter is explicitly instantiated without an injected client
BlobStoreConformanceRunner must pass before an adapter is considered compatible
```

The current S3/MinIO path is experimental. It has opt-in real-service conformance tests, a CI MinIO service conformance job, and setup guidance in `docs/S3_MINIO.md`, but still needs IAM review, lifecycle policy validation, multipart/large-object guidance, and deployment hardening before production-pilot status.

## Compatibility Policy

Before v1.0, schema changes may still evolve. After v1.0, the project should treat storage compatibility as a public contract:

```text
minor versions add backward-compatible migrations
major versions may contain breaking migrations
migrations must be documented
production backends must expose migration status
conformance tests must cover critical runtime invariants
```

---

generated by codex cli
