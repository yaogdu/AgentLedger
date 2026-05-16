from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .ids import new_id, now_ts
from .jsonutil import merge_patch
from .storage_schema import MigrationStatus, ddl_for, migrations_for
from .store import SQLiteStore, StepClaim

POSTGRES_SCHEMA_SQL = ddl_for("postgres")


class PostgresDependencyMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class PostgresStoreConfig:
    dsn: str
    schema: str = "public"

    @classmethod
    def from_env(
        cls,
        environ: dict[str, str] | None = None,
        *,
        dsn: str | None = None,
        schema: str | None = None,
    ) -> "PostgresStoreConfig":
        env = environ if environ is not None else os.environ
        resolved_dsn = dsn or env.get("AGENTLEDGER_POSTGRES_DSN")
        if not resolved_dsn:
            raise ValueError("Postgres DSN is required; pass --dsn or set AGENTLEDGER_POSTGRES_DSN")
        return cls(dsn=resolved_dsn, schema=schema if schema is not None else env.get("AGENTLEDGER_POSTGRES_SCHEMA", "agentledger"))

    def to_dict(self) -> dict[str, str]:
        return {"dsn": self.redacted_dsn(), "schema": self.schema}

    def redacted_dsn(self) -> str:
        return re.sub(r"(://[^:/@]+:)([^@]+)(@)", r"\1***\3", self.dsn)


class _PostgresCompatConnection:
    """Small compatibility layer so Postgres can reuse StateStore semantics.

    SQLiteStore is the reference implementation. This wrapper adapts the small
    subset of DB-API calls used by that store from `?` placeholders to psycopg's
    `%s` placeholders and provides transaction context management.
    """

    def __init__(self, raw: Any):
        self.raw = raw
        self._active_tx: Any = None
        self._closed = False

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        return self.raw.execute(self._translate(sql), tuple(params or ()))

    def executescript(self, sql: str) -> None:
        for statement in self._statements(sql):
            self.execute(statement)

    def commit(self) -> None:
        self.raw.commit()

    def close(self) -> None:
        if self._closed:
            return
        close = getattr(self.raw, "close", None)
        if callable(close):
            close()
        else:
            # Some injected test doubles wrap a DB-API connection instead of
            # exposing close() directly. Close the wrapped handle when present.
            wrapped = getattr(self.raw, "conn", None)
            wrapped_close = getattr(wrapped, "close", None)
            if callable(wrapped_close):
                wrapped_close()
        self._closed = True

    def __enter__(self) -> "_PostgresCompatConnection":
        tx_factory = getattr(self.raw, "transaction", None)
        if callable(tx_factory):
            self._active_tx = tx_factory()
            self._active_tx.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        if self._active_tx is not None:
            tx = self._active_tx
            self._active_tx = None
            return tx.__exit__(exc_type, exc, tb)
        if exc_type is None:
            self.raw.commit()
            return None
        rollback = getattr(self.raw, "rollback", None)
        if callable(rollback):
            rollback()
        return None

    def _translate(self, sql: str) -> str:
        return sql.replace("?", "%s")

    def _statements(self, sql: str) -> list[str]:
        return [part.strip() for part in sql.split(";") if part.strip()]


class PostgresStore(SQLiteStore):
    """psycopg-backed StateStore adapter.

    Runtime core does not depend on psycopg. A real connection can be injected
    for tests or enterprise wiring; otherwise `psycopg` is imported lazily.
    """

    dialect = "postgres"

    def __init__(self, config: PostgresStoreConfig, *, connection: Any | None = None, owns_connection: bool | None = None):
        self.config = config
        self.path = config.dsn
        self._jsonb_factory = self._load_jsonb_factory() if connection is None else None
        self._schema_configured = False
        self._owns_connection = connection is None if owns_connection is None else owns_connection
        raw_connection = connection if connection is not None else self._connect()
        self._native_postgres_claim = self._is_native_postgres_connection(raw_connection)
        self.conn = _PostgresCompatConnection(raw_connection)
        self._closed = False

    @staticmethod
    def ddl() -> str:
        return POSTGRES_SCHEMA_SQL

    def init(self) -> None:
        self._configure_schema()
        self._apply_migrations()

    def close(self) -> None:
        if not self._closed and self._owns_connection:
            self.conn.close()
        self._closed = True

    def _load_jsonb_factory(self) -> Any | None:
        try:
            from psycopg.types.json import Jsonb  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            return None
        return Jsonb

    def _is_native_postgres_connection(self, raw_connection: Any) -> bool:
        module = type(raw_connection).__module__
        return module.startswith("psycopg") or hasattr(raw_connection, "info")

    def _json_param(self, value: Any) -> Any:
        if self._jsonb_factory is None:
            return json.dumps(value, ensure_ascii=False)
        return self._jsonb_factory(value)

    def _quote_identifier(self, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError(f"invalid Postgres identifier: {value!r}")
        return f'"{value}"'

    def _configure_schema(self) -> None:
        if self._schema_configured:
            return
        schema = self.config.schema or "public"
        if schema != "public":
            quoted = self._quote_identifier(schema)
            self.conn.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted}")
            self.conn.execute(f"SET search_path TO {quoted}")
            self.conn.commit()
        self._schema_configured = True

    def migration_status(self) -> MigrationStatus:
        self._ensure_migration_table()
        applied = self._applied_migrations()
        current_version = applied[-1]["version"] if applied else None
        pending = [migration.to_dict() for migration in migrations_for("postgres") if migration.version not in {row["version"] for row in applied}]
        latest = migrations_for("postgres")[-1].version
        return MigrationStatus(dialect="postgres", current_version=current_version, latest_version=latest, applied=applied, pending=pending)

    def schema_version(self) -> str | None:
        return self.migration_status().current_version

    def _connect(self) -> Any:
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise PostgresDependencyMissing("psycopg is not installed; install a postgres adapter extra to use PostgresStore") from exc
        return psycopg.connect(self.config.dsn, row_factory=dict_row, autocommit=True)

    def _ensure_migration_table(self) -> None:
        self._configure_schema()
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              checksum TEXT NOT NULL,
              applied_at DOUBLE PRECISION NOT NULL
            )
            """
        )
        self.conn.commit()

    def _applied_migrations(self) -> list[dict[str, Any]]:
        self._ensure_migration_table()
        cursor = self.conn.execute("SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version")
        rows = cursor.fetchall()
        self.conn.commit()
        return [self._row_to_dict(row) for row in rows]

    def _apply_migrations(self) -> None:
        self._ensure_migration_table()
        applied = {row["version"] for row in self._applied_migrations()}
        with self.conn:
            for migration in migrations_for("postgres"):
                if migration.version in applied:
                    continue
                self.conn.executescript(migration.sql)
                self.conn.execute(
                    "INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES(?,?,?,?)",
                    (migration.version, migration.name, migration.checksum, now_ts()),
                )

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return dict(row)
        if hasattr(row, "keys"):
            return {key: row[key] for key in row.keys()}
        raise TypeError(f"expected mapping row, got {type(row)!r}")

    def _json_value(self, value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    def _retry_policy_for_step(self, row: Any) -> Any:
        raw = row.get("retry_policy_json") if isinstance(row, dict) else row["retry_policy_json"]
        if isinstance(raw, dict):
            from .failure import RetryPolicy

            return RetryPolicy.from_dict(raw)
        return super()._retry_policy_for_step(row)

    def create_run(
        self,
        *,
        session_id: str | None = None,
        initial_state: dict[str, Any] | None = None,
        retry_policy: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        from .failure import RetryPolicy
        from .ids import new_id

        run_id = new_id("run")
        session_id = session_id or new_id("sess")
        step_id = new_id("step")
        ts = now_ts()
        state = initial_state or {}
        retry_policy_payload = RetryPolicy.from_dict(retry_policy).to_dict()
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs(run_id, session_id, status, state_json, state_version, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (run_id, session_id, "pending", self._json_param(state), 0, ts, ts),
            )
            self.conn.execute(
                """
                INSERT INTO steps(step_id, run_id, session_id, status, attempt, state_version, retry_policy_json, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (step_id, run_id, session_id, "pending", 0, 0, self._json_param(retry_policy_payload), ts, ts),
            )
            self._append_event_in_tx(run_id=run_id, session_id=session_id, step_id=None, event_type="run_created", payload={"initial_state": state, "retry_policy": retry_policy_payload})
            self._append_event_in_tx(run_id=run_id, session_id=session_id, step_id=step_id, event_type="step_created", payload={"step_id": step_id, "retry_policy": retry_policy_payload})
        return run_id, step_id

    def claim_step(self, *, worker_id: str, run_id: str | None = None, lease_seconds: int = 60) -> StepClaim | None:
        if not self._native_postgres_claim:
            return super().claim_step(worker_id=worker_id, run_id=run_id, lease_seconds=lease_seconds)

        now = now_ts()
        lease_token = new_id("lease")
        lease_until = now + lease_seconds
        run_filter = "AND run_id = ?" if run_id else ""
        params: list[Any] = []
        if run_id:
            params.append(run_id)
        params.extend([worker_id, lease_token, lease_until, now, now])
        with self.conn:
            row = self.conn.execute(
                f"""
                WITH candidate AS (
                    SELECT step_id
                      FROM steps
                     WHERE status IN ('pending','retry_scheduled') {run_filter}
                     ORDER BY created_at
                     LIMIT 1
                       FOR UPDATE SKIP LOCKED
                )
                UPDATE steps AS s
                   SET status='running',
                       owner=?,
                       lease_token=?,
                       lease_until=?,
                       last_heartbeat_at=?,
                       attempt=s.attempt + 1,
                       updated_at=?
                  FROM candidate
                 WHERE s.step_id = candidate.step_id
                RETURNING s.*
                """,
                params,
            ).fetchone()
            if row is None:
                return None
            claimed = self._row_to_dict(row)
            attempt = int(claimed["attempt"])
            self.conn.execute("UPDATE runs SET status='running', updated_at=? WHERE run_id=?", (now, claimed["run_id"]))
            self._append_event_in_tx(
                run_id=claimed["run_id"],
                session_id=claimed["session_id"],
                step_id=claimed["step_id"],
                event_type="step_claimed",
                payload={"worker_id": worker_id, "lease_token": lease_token, "attempt": attempt, "lease_until": lease_until},
            )
        return StepClaim(claimed["run_id"], claimed["session_id"], claimed["step_id"], attempt, lease_token, int(claimed["state_version"]), lease_until)

    def load_state(self, run_id: str) -> tuple[dict[str, Any], int, str]:
        row = self.conn.execute("SELECT state_json, state_version, session_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"run not found: {run_id}")
        return self._json_value(row["state_json"]), int(row["state_version"]), row["session_id"]

    def commit_state_patch(self, *, run_id: str, step_id: str, lease_token: str, base_version: int, patch: dict[str, Any], checkpoint_id: str | None = None) -> int:
        ts = now_ts()
        with self.conn:
            step = self.validate_lease(step_id, lease_token)
            run = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise KeyError(f"run not found: {run_id}")
            current_version = int(run["state_version"])
            if current_version != base_version:
                raise RuntimeError(f"state version conflict: expected {base_version}, got {current_version}")
            new_state = merge_patch(self._json_value(run["state_json"]), patch)
            new_version = current_version + 1
            self.conn.execute(
                "UPDATE runs SET state_json=?, state_version=?, status='completed', updated_at=? WHERE run_id=? AND state_version=?",
                (self._json_param(new_state), new_version, ts, run_id, base_version),
            )
            self.conn.execute(
                "UPDATE steps SET status='completed', state_version=?, checkpoint_id=?, updated_at=? WHERE step_id=?",
                (new_version, checkpoint_id, ts, step_id),
            )
            self._append_event_in_tx(run_id=run_id, session_id=step["session_id"], step_id=step_id, event_type="state_committed", payload={"patch": patch, "state_version": new_version}, state_version=new_version)
            self._append_event_in_tx(run_id=run_id, session_id=step["session_id"], step_id=step_id, event_type="step_completed", payload={"step_id": step_id}, state_version=new_version)
        return new_version

    def apply_system_state_patch(self, *, run_id: str, patch: dict[str, Any], reason: str) -> int:
        ts = now_ts()
        with self.conn:
            run = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise KeyError(f"run not found: {run_id}")
            current_version = int(run["state_version"])
            new_state = merge_patch(self._json_value(run["state_json"]), patch)
            new_version = current_version + 1
            self.conn.execute(
                "UPDATE runs SET state_json=?, state_version=?, updated_at=? WHERE run_id=? AND state_version=?",
                (self._json_param(new_state), new_version, ts, run_id, current_version),
            )
            self._append_event_in_tx(
                run_id=run_id,
                session_id=run["session_id"],
                step_id=None,
                event_type="system_state_patch_applied",
                payload={"patch": patch, "reason": reason, "state_version": new_version},
                state_version=new_version,
            )
        return new_version

    def reserve_ledger(self, **kwargs: Any) -> Any | None:
        existing = self.conn.execute("SELECT * FROM tool_ledger WHERE idempotency_key=?", (kwargs["idempotency_key"],)).fetchone()
        if existing is not None:
            return existing
        try:
            return super().reserve_ledger(**kwargs)
        except Exception:
            row = self.conn.execute("SELECT * FROM tool_ledger WHERE idempotency_key=?", (kwargs["idempotency_key"],)).fetchone()
            if row is not None:
                return row
            raise

    def request_approval(self, **kwargs: Any) -> Any:
        existing = self.conn.execute("SELECT * FROM approval_requests WHERE approval_key=?", (kwargs["approval_key"],)).fetchone()
        if existing is not None:
            return existing
        try:
            return super().request_approval(**kwargs)
        except Exception:
            row = self.conn.execute("SELECT * FROM approval_requests WHERE approval_key=?", (kwargs["approval_key"],)).fetchone()
            if row is not None:
                return row
            raise

    def cost_summary(self, run_id: str) -> dict[str, Any]:
        # PostgreSQL JSONB fields may already be decoded by psycopg; the rest of
        # the implementation stores JSON as strings and remains compatible.
        return super().cost_summary(run_id)

    def final_state(self, run_id: str) -> dict[str, Any]:
        return self.load_state(run_id)[0]

    def create_artifact(self, *, run_id: str, step_id: str | None, name: str, blob_hash: str, blob_ref: str, metadata: dict[str, Any] | None = None) -> str:
        from .ids import new_id

        artifact_id = new_id("art")
        with self.conn:
            self.conn.execute(
                "INSERT INTO artifacts(artifact_id, run_id, step_id, name, blob_hash, blob_ref, metadata_json, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (artifact_id, run_id, step_id, name, blob_hash, blob_ref, self._json_param(metadata or {}), now_ts()),
            )
        return artifact_id

    def record_cost(self, *, run_id: str, session_id: str | None, step_id: str | None, category: str, name: str, amount: float, unit: str, metadata: dict[str, Any] | None = None) -> str:
        from .ids import new_id

        cost_id = new_id("cost")
        ts = now_ts()
        payload = {"cost_id": cost_id, "category": category, "name": name, "amount": amount, "unit": unit, "metadata": metadata or {}}
        with self.conn:
            self.conn.execute(
                "INSERT INTO cost_records(cost_id, run_id, session_id, step_id, category, name, amount, unit, metadata_json, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (cost_id, run_id, session_id, step_id, category, name, float(amount), unit, self._json_param(metadata or {}), ts),
            )
            self._append_event_in_tx(run_id=run_id, session_id=session_id, step_id=step_id, event_type="cost_recorded", payload=payload)
        return cost_id
