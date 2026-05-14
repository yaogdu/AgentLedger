from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ids import new_id, now_ts
from .jsonutil import merge_patch


@dataclass
class StepClaim:
    run_id: str
    session_id: str
    step_id: str
    attempt: int
    lease_token: str
    state_version: int


class SQLiteStore:
    """SQLite WAL implementation for v0.1 durable state, events, and tool ledger."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=30000")

    def init(self) -> None:
        self.conn.executescript(
            """
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
                updated_at REAL NOT NULL
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
            """
        )
        self.conn.commit()

    def create_run(self, *, session_id: str | None = None, initial_state: dict[str, Any] | None = None) -> tuple[str, str]:
        run_id = new_id("run")
        session_id = session_id or new_id("sess")
        step_id = new_id("step")
        ts = now_ts()
        state = initial_state or {}
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs(run_id, session_id, status, state_json, state_version, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (run_id, session_id, "pending", json.dumps(state, ensure_ascii=False), 0, ts, ts),
            )
            self.conn.execute(
                "INSERT INTO steps(step_id, run_id, session_id, status, attempt, state_version, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (step_id, run_id, session_id, "pending", 0, 0, ts, ts),
            )
            self._append_event_in_tx(run_id=run_id, session_id=session_id, step_id=None, event_type="run_created", payload={"initial_state": state})
            self._append_event_in_tx(run_id=run_id, session_id=session_id, step_id=step_id, event_type="step_created", payload={"step_id": step_id})
        return run_id, step_id

    def claim_step(self, *, worker_id: str, run_id: str | None = None, lease_seconds: int = 60) -> StepClaim | None:
        now = now_ts()
        clauses = "status IN ('pending','retry_scheduled')"
        params: list[Any] = []
        if run_id:
            clauses += " AND run_id = ?"
            params.append(run_id)
        row = self.conn.execute(
            f"SELECT * FROM steps WHERE {clauses} ORDER BY created_at LIMIT 1",
            params,
        ).fetchone()
        if row is None:
            return None
        lease_token = new_id("lease")
        attempt = int(row["attempt"]) + 1
        with self.conn:
            updated = self.conn.execute(
                """
                UPDATE steps
                   SET status='running', owner=?, lease_token=?, lease_until=?, attempt=?, updated_at=?
                 WHERE step_id=? AND status IN ('pending','retry_scheduled')
                """,
                (worker_id, lease_token, now + lease_seconds, attempt, now, row["step_id"]),
            )
            if updated.rowcount != 1:
                return None
            self.conn.execute("UPDATE runs SET status='running', updated_at=? WHERE run_id=?", (now, row["run_id"]))
            self._append_event_in_tx(
                run_id=row["run_id"],
                session_id=row["session_id"],
                step_id=row["step_id"],
                event_type="step_claimed",
                payload={"worker_id": worker_id, "lease_token": lease_token, "attempt": attempt},
            )
        return StepClaim(row["run_id"], row["session_id"], row["step_id"], attempt, lease_token, int(row["state_version"]))

    def load_state(self, run_id: str) -> tuple[dict[str, Any], int, str]:
        row = self.conn.execute("SELECT state_json, state_version, session_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"run not found: {run_id}")
        return json.loads(row["state_json"]), int(row["state_version"]), row["session_id"]

    def validate_lease(self, step_id: str, lease_token: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM steps WHERE step_id=?", (step_id,)).fetchone()
        if row is None:
            raise KeyError(f"step not found: {step_id}")
        if row["lease_token"] != lease_token or row["status"] != "running":
            raise RuntimeError("invalid or stale lease token")
        if row["lease_until"] is not None and float(row["lease_until"]) < now_ts():
            raise RuntimeError("lease expired")
        return row

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
            new_state = merge_patch(json.loads(run["state_json"]), patch)
            new_version = current_version + 1
            self.conn.execute(
                "UPDATE runs SET state_json=?, state_version=?, status='completed', updated_at=? WHERE run_id=? AND state_version=?",
                (json.dumps(new_state, ensure_ascii=False), new_version, ts, run_id, base_version),
            )
            self.conn.execute(
                "UPDATE steps SET status='completed', state_version=?, checkpoint_id=?, updated_at=? WHERE step_id=?",
                (new_version, checkpoint_id, ts, step_id),
            )
            self._append_event_in_tx(run_id=run_id, session_id=step["session_id"], step_id=step_id, event_type="state_committed", payload={"patch": patch, "state_version": new_version}, state_version=new_version)
            self._append_event_in_tx(run_id=run_id, session_id=step["session_id"], step_id=step_id, event_type="step_completed", payload={"step_id": step_id}, state_version=new_version)
        return new_version

    def apply_system_state_patch(self, *, run_id: str, patch: dict[str, Any], reason: str) -> int:
        """Apply runtime-owned recovery metadata while preserving the event timeline."""
        ts = now_ts()
        with self.conn:
            run = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise KeyError(f"run not found: {run_id}")
            current_version = int(run["state_version"])
            new_state = merge_patch(json.loads(run["state_json"]), patch)
            new_version = current_version + 1
            self.conn.execute(
                "UPDATE runs SET state_json=?, state_version=?, updated_at=? WHERE run_id=? AND state_version=?",
                (json.dumps(new_state, ensure_ascii=False), new_version, ts, run_id, current_version),
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

    def mark_retry(self, *, run_id: str, step_id: str, error: str) -> None:
        ts = now_ts()
        with self.conn:
            row = self.conn.execute("SELECT * FROM steps WHERE step_id=?", (step_id,)).fetchone()
            if row is None:
                raise KeyError(step_id)
            self.conn.execute(
                "UPDATE steps SET status='retry_scheduled', owner=NULL, lease_token=NULL, lease_until=NULL, updated_at=? WHERE step_id=?",
                (ts, step_id),
            )
            self.conn.execute("UPDATE runs SET status='retry_scheduled', updated_at=? WHERE run_id=?", (ts, run_id))
            self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="error_raised", payload={"error": error})
            self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="step_retry_scheduled", payload={"step_id": step_id})

    def mark_failed(self, *, run_id: str, step_id: str, error: str, error_type: str) -> None:
        ts = now_ts()
        with self.conn:
            row = self.conn.execute("SELECT * FROM steps WHERE step_id=?", (step_id,)).fetchone()
            if row is None:
                raise KeyError(step_id)
            self.conn.execute(
                "UPDATE steps SET status='failed', owner=NULL, lease_token=NULL, lease_until=NULL, updated_at=? WHERE step_id=?",
                (ts, step_id),
            )
            self.conn.execute("UPDATE runs SET status='failed', updated_at=? WHERE run_id=?", (ts, run_id))
            self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="error_raised", payload={"error": error, "error_type": error_type})
            self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="step_failed", payload={"step_id": step_id, "error_type": error_type})

    def append_event(self, *, run_id: str, event_type: str, payload: dict[str, Any], session_id: str | None = None, step_id: str | None = None, agent_role: str | None = None, state_version: int | None = None, causal_token: str | None = None, payload_hash: str | None = None, payload_ref: str | None = None) -> tuple[str, int]:
        with self.conn:
            return self._append_event_in_tx(
                run_id=run_id,
                event_type=event_type,
                payload=payload,
                session_id=session_id,
                step_id=step_id,
                agent_role=agent_role,
                state_version=state_version,
                causal_token=causal_token,
                payload_hash=payload_hash,
                payload_ref=payload_ref,
            )

    def _append_event_in_tx(self, *, run_id: str, event_type: str, payload: dict[str, Any], session_id: str | None = None, step_id: str | None = None, agent_role: str | None = None, state_version: int | None = None, causal_token: str | None = None, payload_hash: str | None = None, payload_ref: str | None = None) -> tuple[str, int]:
        seq_row = self.conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM events WHERE run_id=?", (run_id,)).fetchone()
        seq = int(seq_row["next_seq"])
        event_id = new_id("evt")
        if payload_ref is None:
            payload_ref = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.conn.execute(
            "INSERT INTO events(event_id, run_id, session_id, step_id, seq, type, timestamp, agent_role, state_version, causal_token, payload_hash, payload_ref) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, run_id, session_id, step_id, seq, event_type, now_ts(), agent_role, state_version, causal_token, payload_hash, payload_ref),
        )
        return event_id, seq

    def reserve_ledger(self, **kwargs: Any) -> sqlite3.Row | None:
        existing = self.conn.execute("SELECT * FROM tool_ledger WHERE idempotency_key=?", (kwargs["idempotency_key"],)).fetchone()
        if existing is not None:
            return existing
        ts = now_ts()
        try:
            with self.conn:
                self.conn.execute(
                    """INSERT INTO tool_ledger(ledger_id, run_id, session_id, step_id, tool_name, tool_version, tool_call_id, idempotency_key, causal_token, request_hash, request_ref, status, created_at, updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        new_id("ledger"), kwargs["run_id"], kwargs.get("session_id"), kwargs["step_id"], kwargs["tool_name"], kwargs["tool_version"], kwargs["tool_call_id"], kwargs["idempotency_key"], kwargs["causal_token"], kwargs["request_hash"], kwargs["request_ref"], "RESERVED", ts, ts,
                    ),
                )
        except sqlite3.IntegrityError:
            return self.conn.execute("SELECT * FROM tool_ledger WHERE idempotency_key=?", (kwargs["idempotency_key"],)).fetchone()
        return None

    def update_ledger(self, *, idempotency_key: str, status: str, external_id: str | None = None, response_hash: str | None = None, response_ref: str | None = None, error_type: str | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE tool_ledger SET status=?, external_id=?, response_hash=?, response_ref=?, error_type=?, updated_at=? WHERE idempotency_key=?",
                (status, external_id, response_hash, response_ref, error_type, now_ts(), idempotency_key),
            )

    def events(self, run_id: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,)))

    def ledger(self, run_id: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM tool_ledger WHERE run_id=? ORDER BY created_at", (run_id,)))

    def final_state(self, run_id: str) -> dict[str, Any]:
        return self.load_state(run_id)[0]
