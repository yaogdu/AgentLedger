from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .ids import now_ts
from .storage_schema import MigrationStatus, ddl_for, migrations_for
from .storage_postgres import _PostgresCompatConnection, PostgresStore

MYSQL_SCHEMA_SQL = ddl_for("mysql")


class MySQLDependencyMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class MySQLStoreConfig:
    dsn: str
    database: str | None = None

    @classmethod
    def from_env(
        cls,
        environ: dict[str, str] | None = None,
        *,
        dsn: str | None = None,
        database: str | None = None,
    ) -> "MySQLStoreConfig":
        env = environ if environ is not None else os.environ
        resolved_dsn = dsn or env.get("AGENTLEDGER_MYSQL_DSN")
        if not resolved_dsn:
            raise ValueError("MySQL DSN is required; pass --dsn or set AGENTLEDGER_MYSQL_DSN")
        return cls(dsn=resolved_dsn, database=database if database is not None else env.get("AGENTLEDGER_MYSQL_DATABASE"))

    def to_dict(self) -> dict[str, str | None]:
        return {"dsn": self.redacted_dsn(), "database": self.database}

    def redacted_dsn(self) -> str:
        return re.sub(r"(://[^:/@]+:)([^@]+)(@)", r"\1***\3", self.dsn)


class _MySQLCompatConnection(_PostgresCompatConnection):
    """Compatibility layer for DB-API-like MySQL clients.

    The runtime uses SQLite-style `?` placeholders. MySQL drivers such as
    PyMySQL/mysqlclient use `%s`, so this wrapper translates placeholders and
    splits migration scripts into individual statements.
    """

    def execute(self, sql: str, params: Any | None = None) -> Any:
        if hasattr(self.raw, "execute"):
            return self.raw.execute(self._translate(sql), tuple(params or ()))
        cursor = self.raw.cursor()
        cursor.execute(self._translate(sql), tuple(params or ()))
        return cursor

    def __enter__(self) -> "_MySQLCompatConnection":
        begin = getattr(self.raw, "begin", None)
        if callable(begin):
            begin()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        if exc_type is None:
            self.raw.commit()
            return None
        rollback = getattr(self.raw, "rollback", None)
        if callable(rollback):
            rollback()
        return None

    def _translate(self, sql: str) -> str:
        return sql.replace("?", "%s")


class MySQLStore(PostgresStore):
    """MySQL-backed StateStore adapter.

    Runtime core does not depend on a MySQL driver. A DB-API-like connection can
    be injected for tests or app wiring; otherwise `pymysql` is imported lazily.
    Live MySQL production hardening remains an adapter validation concern.
    """

    dialect = "mysql"

    def __init__(self, config: MySQLStoreConfig, *, connection: Any | None = None, owns_connection: bool | None = None):
        self.config = config
        self.path = config.dsn
        self._jsonb_factory = None
        self._schema_configured = False
        self._owns_connection = connection is None if owns_connection is None else owns_connection
        raw_connection = connection if connection is not None else self._connect()
        self._native_postgres_claim = False
        self.conn = _MySQLCompatConnection(raw_connection)
        self._closed = False

    @staticmethod
    def ddl() -> str:
        return MYSQL_SCHEMA_SQL

    def _connect(self) -> Any:
        try:
            import pymysql  # type: ignore
            from pymysql.cursors import DictCursor  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise MySQLDependencyMissing("pymysql is not installed; install agentledger-mysql or agentledger-runtime[mysql] to use MySQLStore") from exc
        parsed = urlparse(self.config.dsn)
        if parsed.scheme not in {"mysql", "mysql+pymysql"}:
            raise ValueError("MySQL DSN must use mysql:// or mysql+pymysql://")
        query = parse_qs(parsed.query)
        return pymysql.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            database=self.config.database or parsed.path.lstrip("/") or None,
            charset=query.get("charset", ["utf8mb4"])[0],
            autocommit=True,
            cursorclass=DictCursor,
        )

    def _ensure_migration_table(self) -> None:
        self._configure_schema()
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version VARCHAR(32) PRIMARY KEY,
              name VARCHAR(255) NOT NULL,
              checksum VARCHAR(128) NOT NULL,
              applied_at DOUBLE NOT NULL
            )
            """
        )
        self.conn.commit()

    def _configure_schema(self) -> None:
        if self._schema_configured:
            return
        database = self.config.database
        if database:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
                raise ValueError(f"invalid MySQL database identifier: {database!r}")
            self.conn.execute(f"USE `{database}`")
            self.conn.commit()
        self._schema_configured = True

    def migration_status(self) -> MigrationStatus:
        self._ensure_migration_table()
        applied = self._applied_migrations()
        current_version = applied[-1]["version"] if applied else None
        pending = [migration.to_dict() for migration in migrations_for("mysql") if migration.version not in {row["version"] for row in applied}]
        latest = migrations_for("mysql")[-1].version
        return MigrationStatus(dialect="mysql", current_version=current_version, latest_version=latest, applied=applied, pending=pending)

    def _apply_migrations(self) -> None:
        self._ensure_migration_table()
        applied = {row["version"] for row in self._applied_migrations()}
        with self.conn:
            for migration in migrations_for("mysql"):
                if migration.version in applied:
                    continue
                self.conn.executescript(migration.sql)
                self.conn.execute(
                    "INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES(?,?,?,?)",
                    (migration.version, migration.name, migration.checksum, now_ts()),
                )

    def _json_param(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _json_value(self, value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    def commit_state_patch(self, *, run_id: str, step_id: str, lease_token: str, base_version: int, patch: dict[str, Any], checkpoint_id: str | None = None) -> int:
        # MySQL JSON columns require JSON strings from DB-API drivers. Keep the
        # same optimistic version and lease semantics as the reference store.
        return super().commit_state_patch(run_id=run_id, step_id=step_id, lease_token=lease_token, base_version=base_version, patch=patch, checkpoint_id=checkpoint_id)

    def apply_system_state_patch(self, *, run_id: str, patch: dict[str, Any], reason: str) -> int:
        return super().apply_system_state_patch(run_id=run_id, patch=patch, reason=reason)
