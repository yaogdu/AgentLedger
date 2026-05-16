# Postgres StateStore

`PostgresStore` is the experimental production-pilot path for durable AgentLedger runtime metadata. It is intended for teams that need a real database boundary for runs, steps, events, leases, approvals, cost records, and Tool Ledger rows.

## Status

```text
status: Experimental
hard dependency: none
optional runtime SDK: psycopg, only when no connection is injected
local tests: SQLite-backed fake connection
real-service tests: opt-in via environment variables
```

## Configuration

`PostgresStoreConfig` can be constructed directly or loaded from environment variables.

```text
AGENTLEDGER_POSTGRES_DSN     required for env/CLI Postgres mode
AGENTLEDGER_POSTGRES_SCHEMA  default: agentledger
```

Python wiring with an injected enterprise connection:

```python
from agentledger import PostgresStore, PostgresStoreConfig

store = PostgresStore(
    PostgresStoreConfig.from_env(),
    connection=my_psycopg_connection,
)
store.init()
```

Python wiring with psycopg discovery:

```python
from agentledger import PostgresStore, PostgresStoreConfig

store = PostgresStore(PostgresStoreConfig.from_env())
store.init()
```

## Docker Example

If a local container exposes Postgres on `localhost:15432`:

```bash
export AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database
export AGENTLEDGER_POSTGRES_SCHEMA=agentledger
```

Do not commit real database credentials. Prefer environment variables, secret managers, or local-only shell profiles.

## Local State Conformance

SQLite state conformance does not require Postgres:

```bash
PYTHONPATH=src python3 -m agentledger state conformance --backend sqlite
PYTHONPATH=src python3 -m agentledger worker conformance --backend sqlite --concurrent
```

## Postgres CLI Conformance

Run this only when the database exists and `psycopg` is installed in the Python environment:

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
AGENTLEDGER_POSTGRES_SCHEMA=agentledger \
PYTHONPATH=src python3 -m agentledger state conformance --backend postgres
```

Worker-pool semantics use the same StateStore backend and can be checked separately. The native psycopg path uses `FOR UPDATE SKIP LOCKED` for concurrent claims:

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
AGENTLEDGER_POSTGRES_SCHEMA=agentledger \
PYTHONPATH=src python3 -m agentledger worker conformance --backend postgres --concurrent
```

Equivalent command through the Postgres namespace:

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
AGENTLEDGER_POSTGRES_SCHEMA=agentledger \
PYTHONPATH=src python3 -m agentledger postgres conformance
```

## Migrations

Runtime-core can apply AgentLedger-owned Postgres migrations when a DSN is configured. This path creates schemas/tables/indexes and records `schema_migrations`; it does not drop, truncate, or clean real data:

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
AGENTLEDGER_POSTGRES_SCHEMA=agentledger \
PYTHONPATH=src python3 -m agentledger migrate up --dialect postgres

AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
AGENTLEDGER_POSTGRES_SCHEMA=agentledger \
PYTHONPATH=src python3 -m agentledger migrate status --dialect postgres
```

## Opt-in Integration Test

The normal unit suite skips real Postgres. To run the real-service conformance check:

```bash
AGENTLEDGER_RUN_POSTGRES_INTEGRATION=1 \
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
AGENTLEDGER_POSTGRES_SCHEMA=agentledger \
PYTHONPATH=src python3 -m unittest tests.test_postgres_integration -v
```

The test creates a unique child schema such as `agentledger_it_<uuid>`. It does not drop schemas automatically. Runtime core intentionally does not provide schema cleanup or destructive database maintenance commands; cleanup belongs to DBA/infra runbooks.

CI includes a dedicated Postgres service job that installs the optional `postgres` extra and runs the same real-service conformance suite against PostgreSQL 16.

## Production-pilot Checklist

Before using this adapter for serious pilot workloads, verify:

```text
schema name is isolated per deployment environment
migration rollout and rollback process is documented
backup/restore can recover run, step, event, ledger, approval, cost, and artifact refs
connection pool sizing and transaction timeout policy are defined
statement timeout and lock timeout are configured by deployment policy
least-privilege database role owns only AgentLedger schema objects
StateStoreConformanceRunner passes against the target database
WorkerConformanceRunner passes against the target database
multi-worker claim/recovery behavior is tested under expected concurrency
```

## Non-goals

The runtime core does not manage database provisioning, credentials, connection pools, TLS certificates, backups, PITR, or migration orchestration. Those remain deployment responsibilities or optional adapter-package concerns.
