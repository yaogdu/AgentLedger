# Backup and Restore

AgentLedger runtime data is split across a StateStore and a BlobStore:

```text
StateStore:
  runs, steps, events, tool_ledger, approvals, costs, artifact refs, schema_migrations

BlobStore:
  model/tool payloads, evidence payload refs, artifact content, trace/export payloads
```

Backups must preserve both sides. A database snapshot without blob objects cannot fully replay, audit, or export evidence. Blob objects without StateStore metadata cannot explain causality, leases, approvals, or Tool Ledger status.

## Local SQLite

For local development, stop active workers before copying `.agentledger`:

```bash
cp .agentledger/state.db /backup/agentledger/state.db
cp -R .agentledger/blobs /backup/agentledger/blobs
```

If workers are active, use the SQLite backup API or an infrastructure snapshot that preserves file consistency. Do not copy a hot database file and assume it is a valid recovery point.

Restore by placing the database and blob directory back under the runtime root:

```text
.agentledger/state.db
.agentledger/blobs/
```

Then run read-only checks:

```bash
PYTHONPATH=src python3 -m agentledger doctor
PYTHONPATH=src python3 -m agentledger conformance
```

## Postgres + S3/MinIO

For production-pilot deployments, treat Postgres as the source of runtime metadata and S3/MinIO as the source of immutable payload/artifact content.

Required backup coverage:

```text
Postgres schema containing AgentLedger tables
S3/MinIO prefix containing content-addressed blob refs
configuration that maps runtime to the same schema/prefix
runtime contract and schema migration version
media/stream nested blob refs inside artifact metadata when they use `blob://`
```

Recommended restore validation:

```bash
PYTHONPATH=src python3 -m agentledger state conformance --backend postgres
PYTHONPATH=src python3 -m agentledger worker conformance --backend postgres --concurrent
PYTHONPATH=src python3 -m agentledger blob conformance --backend s3
```

For selected recovered runs, export evidence and replay:

```bash
PYTHONPATH=src python3 -m agentledger backup check <run_id>
PYTHONPATH=src python3 -m agentledger evidence <run_id> --dir ./recovered-evidence/<run_id>
PYTHONPATH=src python3 -m agentledger replay <run_id>
PYTHONPATH=src python3 -m agentledger timetravel <run_id> --include-states
```

`backup check` is read-only. It verifies that run metadata exists, schema migration version is recorded, blob payload refs resolve, media/stream evidence shape is valid, nested `blob://` refs inside artifact metadata resolve, and an evidence bundle can be constructed. It does not create, delete, truncate, or restore database objects.

## Recovery Point Rules

Use one of these strategies:

```text
consistent pair snapshot:
  capture StateStore and BlobStore at one coordinated point in time

metadata after blobs:
  ensure blobs are durable before committing metadata refs that point to them

retention overlap:
  keep blob objects longer than the database recovery window
  include media/stream nested blob refs in protected retention windows
```

Because AgentLedger blob refs are content-addressed and immutable, restoring an older database against a superset of blob objects is usually safe. Restoring a newer database against an older or pruned blob prefix can break replay/evidence for refs that no longer exist.

## What Runtime Core Does Not Do

Runtime core intentionally does not:

```text
drop schemas
delete real production data
create cloud buckets
manage PITR or WAL archive settings
manage IAM, KMS, TLS, or secrets
orchestrate cross-region restore
```

Those operations belong to DBA, SRE, or deployment runbooks. AgentLedger provides conformance checks, evidence export, replay, and deterministic refs so the restore can be verified without running real tools.
