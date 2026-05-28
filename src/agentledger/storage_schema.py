from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Iterable


SCHEMA_MIGRATIONS_SQLITE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at REAL NOT NULL
);
""".strip()

SCHEMA_MIGRATIONS_POSTGRES = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at DOUBLE PRECISION NOT NULL
);
""".strip()

SCHEMA_MIGRATIONS_MYSQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version VARCHAR(32) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  checksum VARCHAR(128) NOT NULL,
  applied_at DOUBLE NOT NULL
);
""".strip()

SQLITE_0001_INITIAL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    state_json TEXT NOT NULL,
    state_version INTEGER NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    owner TEXT,
    lease_token TEXT,
    lease_until REAL,
    attempt INTEGER NOT NULL,
    state_version INTEGER NOT NULL,
    checkpoint_id TEXT,
    next_wake_condition TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_heartbeat_at REAL,
    retry_policy_json TEXT,
    last_error_type TEXT,
    last_error TEXT,
    cancelled_at REAL
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT,
    step_id TEXT,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    agent_role TEXT,
    state_version INTEGER,
    causal_token TEXT,
    payload_hash TEXT,
    payload_ref TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_steps_run_status ON steps(run_id, status);
CREATE INDEX IF NOT EXISTS idx_steps_status_lease ON steps(status, lease_until);
CREATE TABLE IF NOT EXISTS tool_ledger (
    ledger_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT,
    step_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    causal_token TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    request_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    external_id TEXT,
    response_hash TEXT,
    response_ref TEXT,
    error_type TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_ledger_run_tool ON tool_ledger(run_id, tool_name);
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT,
    name TEXT,
    blob_hash TEXT NOT NULL,
    blob_ref TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_step ON artifacts(run_id, step_id);
CREATE TABLE IF NOT EXISTS cost_records (
    cost_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT,
    step_id TEXT,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    unit TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cost_records_run_step ON cost_records(run_id, step_id);
CREATE TABLE IF NOT EXISTS approval_requests (
    approval_id TEXT PRIMARY KEY,
    approval_key TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    session_id TEXT,
    step_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    request_hash TEXT NOT NULL,
    request_ref TEXT NOT NULL,
    requested_by TEXT,
    approved_by TEXT,
    decision_reason TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approval_requests_run_status ON approval_requests(run_id, status);
""".strip()

POSTGRES_0001_INITIAL = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  status TEXT NOT NULL,
  state_json JSONB NOT NULL,
  state_version BIGINT NOT NULL,
  created_at DOUBLE PRECISION NOT NULL,
  updated_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS steps (
  step_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  session_id TEXT NOT NULL,
  status TEXT NOT NULL,
  owner TEXT,
  lease_token TEXT,
  lease_until DOUBLE PRECISION,
  attempt BIGINT NOT NULL,
  state_version BIGINT NOT NULL,
  checkpoint_id TEXT,
  next_wake_condition TEXT,
  created_at DOUBLE PRECISION NOT NULL,
  updated_at DOUBLE PRECISION NOT NULL,
  last_heartbeat_at DOUBLE PRECISION,
  retry_policy_json JSONB,
  last_error_type TEXT,
  last_error TEXT,
  cancelled_at DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_steps_run_status ON steps(run_id, status);
CREATE INDEX IF NOT EXISTS idx_steps_status_lease ON steps(status, lease_until);

CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  session_id TEXT,
  step_id TEXT,
  seq BIGINT NOT NULL,
  type TEXT NOT NULL,
  timestamp DOUBLE PRECISION NOT NULL,
  agent_role TEXT,
  state_version BIGINT,
  causal_token TEXT,
  payload_hash TEXT,
  payload_ref TEXT,
  UNIQUE(run_id, seq)
);

CREATE TABLE IF NOT EXISTS tool_ledger (
  ledger_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  session_id TEXT,
  step_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  tool_version TEXT NOT NULL,
  tool_call_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  causal_token TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  request_ref TEXT NOT NULL,
  status TEXT NOT NULL,
  external_id TEXT,
  response_hash TEXT,
  response_ref TEXT,
  error_type TEXT,
  created_at DOUBLE PRECISION NOT NULL,
  updated_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_ledger_run_tool ON tool_ledger(run_id, tool_name);

CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT,
  name TEXT,
  blob_hash TEXT NOT NULL,
  blob_ref TEXT NOT NULL,
  metadata_json JSONB NOT NULL,
  created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_step ON artifacts(run_id, step_id);

CREATE TABLE IF NOT EXISTS cost_records (
  cost_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  session_id TEXT,
  step_id TEXT,
  category TEXT NOT NULL,
  name TEXT NOT NULL,
  amount DOUBLE PRECISION NOT NULL,
  unit TEXT NOT NULL,
  metadata_json JSONB NOT NULL,
  created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cost_records_run_step ON cost_records(run_id, step_id);

CREATE TABLE IF NOT EXISTS approval_requests (
  approval_id TEXT PRIMARY KEY,
  approval_key TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  session_id TEXT,
  step_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  risk_level TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT,
  request_hash TEXT NOT NULL,
  request_ref TEXT NOT NULL,
  requested_by TEXT,
  approved_by TEXT,
  decision_reason TEXT,
  created_at DOUBLE PRECISION NOT NULL,
  updated_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approval_requests_run_status ON approval_requests(run_id, status);
""".strip()

MYSQL_0001_INITIAL = """
CREATE TABLE IF NOT EXISTS runs (
  run_id VARCHAR(128) PRIMARY KEY,
  session_id VARCHAR(128) NOT NULL,
  status VARCHAR(64) NOT NULL,
  state_json JSON NOT NULL,
  state_version BIGINT NOT NULL,
  created_at DOUBLE NOT NULL,
  updated_at DOUBLE NOT NULL
);

CREATE TABLE IF NOT EXISTS steps (
  step_id VARCHAR(128) PRIMARY KEY,
  run_id VARCHAR(128) NOT NULL,
  session_id VARCHAR(128) NOT NULL,
  status VARCHAR(64) NOT NULL,
  owner VARCHAR(255),
  lease_token VARCHAR(128),
  lease_until DOUBLE,
  attempt BIGINT NOT NULL,
  state_version BIGINT NOT NULL,
  checkpoint_id VARCHAR(255),
  next_wake_condition TEXT,
  created_at DOUBLE NOT NULL,
  updated_at DOUBLE NOT NULL,
  last_heartbeat_at DOUBLE,
  retry_policy_json JSON,
  last_error_type VARCHAR(255),
  last_error TEXT,
  cancelled_at DOUBLE,
  INDEX idx_steps_run_status (run_id, status),
  INDEX idx_steps_status_lease (status, lease_until)
);

CREATE TABLE IF NOT EXISTS events (
  event_id VARCHAR(128) PRIMARY KEY,
  run_id VARCHAR(128) NOT NULL,
  session_id VARCHAR(128),
  step_id VARCHAR(128),
  seq BIGINT NOT NULL,
  type VARCHAR(255) NOT NULL,
  timestamp DOUBLE NOT NULL,
  agent_role VARCHAR(255),
  state_version BIGINT,
  causal_token TEXT,
  payload_hash VARCHAR(128),
  payload_ref TEXT,
  UNIQUE KEY idx_events_run_seq (run_id, seq)
);

CREATE TABLE IF NOT EXISTS tool_ledger (
  ledger_id VARCHAR(128) PRIMARY KEY,
  run_id VARCHAR(128) NOT NULL,
  session_id VARCHAR(128),
  step_id VARCHAR(128) NOT NULL,
  tool_name VARCHAR(255) NOT NULL,
  tool_version VARCHAR(64) NOT NULL,
  tool_call_id VARCHAR(128) NOT NULL,
  idempotency_key VARCHAR(255) NOT NULL UNIQUE,
  causal_token TEXT NOT NULL,
  request_hash VARCHAR(128) NOT NULL,
  request_ref TEXT NOT NULL,
  status VARCHAR(64) NOT NULL,
  external_id VARCHAR(255),
  response_hash VARCHAR(128),
  response_ref TEXT,
  error_type VARCHAR(255),
  created_at DOUBLE NOT NULL,
  updated_at DOUBLE NOT NULL,
  INDEX idx_tool_ledger_run_tool (run_id, tool_name)
);

CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id VARCHAR(128) PRIMARY KEY,
  run_id VARCHAR(128) NOT NULL,
  step_id VARCHAR(128),
  name VARCHAR(255),
  blob_hash VARCHAR(128) NOT NULL,
  blob_ref TEXT NOT NULL,
  metadata_json JSON NOT NULL,
  created_at DOUBLE NOT NULL,
  INDEX idx_artifacts_run_step (run_id, step_id)
);

CREATE TABLE IF NOT EXISTS cost_records (
  cost_id VARCHAR(128) PRIMARY KEY,
  run_id VARCHAR(128) NOT NULL,
  session_id VARCHAR(128),
  step_id VARCHAR(128),
  category VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  amount DOUBLE NOT NULL,
  unit VARCHAR(64) NOT NULL,
  metadata_json JSON NOT NULL,
  created_at DOUBLE NOT NULL,
  INDEX idx_cost_records_run_step (run_id, step_id)
);

CREATE TABLE IF NOT EXISTS approval_requests (
  approval_id VARCHAR(128) PRIMARY KEY,
  approval_key VARCHAR(255) NOT NULL UNIQUE,
  run_id VARCHAR(128) NOT NULL,
  session_id VARCHAR(128),
  step_id VARCHAR(128) NOT NULL,
  tool_name VARCHAR(255) NOT NULL,
  risk_level VARCHAR(64) NOT NULL,
  status VARCHAR(64) NOT NULL,
  reason TEXT,
  request_hash VARCHAR(128) NOT NULL,
  request_ref TEXT NOT NULL,
  requested_by VARCHAR(255),
  approved_by VARCHAR(255),
  decision_reason TEXT,
  created_at DOUBLE NOT NULL,
  updated_at DOUBLE NOT NULL,
  INDEX idx_approval_requests_run_status (run_id, status)
);
""".strip()


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    dialect: str
    sql: str

    @property
    def checksum(self) -> str:
        return "sha256:" + hashlib.sha256(self.sql.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "name": self.name, "dialect": self.dialect, "checksum": self.checksum}


@dataclass(frozen=True)
class MigrationStatus:
    dialect: str
    current_version: str | None
    latest_version: str | None
    applied: list[dict[str, Any]]
    pending: list[dict[str, Any]]

    @property
    def up_to_date(self) -> bool:
        return not self.pending

    def to_dict(self) -> dict[str, Any]:
        return {
            "dialect": self.dialect,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "up_to_date": self.up_to_date,
            "applied": self.applied,
            "pending": self.pending,
        }


SQLITE_MIGRATIONS = (Migration("0001", "initial_runtime_metadata", "sqlite", SQLITE_0001_INITIAL),)
POSTGRES_MIGRATIONS = (Migration("0001", "initial_runtime_metadata", "postgres", POSTGRES_0001_INITIAL),)
MYSQL_MIGRATIONS = (Migration("0001", "initial_runtime_metadata", "mysql", MYSQL_0001_INITIAL),)


def migrations_for(dialect: str) -> tuple[Migration, ...]:
    normalized = dialect.lower()
    if normalized == "sqlite":
        return SQLITE_MIGRATIONS
    if normalized in {"postgres", "postgresql"}:
        return POSTGRES_MIGRATIONS
    if normalized == "mysql":
        return MYSQL_MIGRATIONS
    raise ValueError(f"unsupported storage dialect: {dialect}")


def latest_schema_version(dialect: str) -> str | None:
    migrations = migrations_for(dialect)
    return migrations[-1].version if migrations else None


def ddl_for(dialect: str) -> str:
    normalized = dialect.lower()
    if normalized in {"postgres", "postgresql"}:
        header = SCHEMA_MIGRATIONS_POSTGRES
    elif normalized == "mysql":
        header = SCHEMA_MIGRATIONS_MYSQL
    else:
        header = SCHEMA_MIGRATIONS_SQLITE
    return "\n\n".join([header, *[migration.sql for migration in migrations_for(dialect)]])


class SQLiteMigrationRunner:
    """Small migration runner for the built-in local SQLite backend."""

    def __init__(self, conn: sqlite3.Connection, migrations: Iterable[Migration] = SQLITE_MIGRATIONS):
        self.conn = conn
        self.migrations = tuple(migrations)

    def ensure_table(self) -> None:
        self.conn.executescript(SCHEMA_MIGRATIONS_SQLITE)

    def applied(self) -> list[dict[str, Any]]:
        self.ensure_table()
        cursor = self.conn.execute("SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version")
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        return [dict(row) if hasattr(row, "keys") else dict(zip(columns, row)) for row in rows]

    def applied_versions(self) -> set[str]:
        return {row["version"] for row in self.applied()}

    def pending(self) -> list[Migration]:
        applied = self.applied_versions()
        return [migration for migration in self.migrations if migration.version not in applied]

    def apply_all(self) -> list[dict[str, Any]]:
        self.ensure_table()
        applied_versions = self.applied_versions()
        applied_now: list[dict[str, Any]] = []
        for migration in self.migrations:
            if migration.version in applied_versions:
                continue
            self.conn.executescript(migration.sql)
            self.conn.execute(
                "INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES(?,?,?,?)",
                (migration.version, migration.name, migration.checksum, time.time()),
            )
            applied_now.append(migration.to_dict())
        self.conn.commit()
        return applied_now

    def status(self) -> MigrationStatus:
        applied = self.applied()
        pending = [migration.to_dict() for migration in self.pending()]
        current_version = applied[-1]["version"] if applied else None
        latest_version = self.migrations[-1].version if self.migrations else None
        return MigrationStatus(dialect="sqlite", current_version=current_version, latest_version=latest_version, applied=applied, pending=pending)
