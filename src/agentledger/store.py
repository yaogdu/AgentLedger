from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .failure import RetryPolicy
from .ids import new_id, now_ts
from .jsonutil import merge_patch
from .storage_schema import MigrationStatus, SQLiteMigrationRunner


@dataclass
class StepClaim:
    run_id: str
    session_id: str
    step_id: str
    attempt: int
    lease_token: str
    state_version: int
    lease_until: float


class SQLiteStore:
    """SQLite WAL implementation for local durable state, events, and tool ledger."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30)
        self._closed = False
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=30000")

    def init(self) -> None:
        SQLiteMigrationRunner(self.conn).apply_all()
        self._ensure_column("steps", "last_heartbeat_at", "REAL")
        self._ensure_column("steps", "retry_policy_json", "TEXT")
        self._ensure_column("steps", "last_error_type", "TEXT")
        self._ensure_column("steps", "last_error", "TEXT")
        self._ensure_column("steps", "cancelled_at", "REAL")
        self.conn.commit()

    def close(self) -> None:
        if not self._closed:
            self.conn.close()
            self._closed = True

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def migration_status(self) -> MigrationStatus:
        return SQLiteMigrationRunner(self.conn).status()

    def schema_version(self) -> str | None:
        return self.migration_status().current_version

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_run(
        self,
        *,
        session_id: str | None = None,
        initial_state: dict[str, Any] | None = None,
        retry_policy: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        run_id = new_id("run")
        session_id = session_id or new_id("sess")
        step_id = new_id("step")
        ts = now_ts()
        state = initial_state or {}
        retry_policy_json = json.dumps(RetryPolicy.from_dict(retry_policy).to_dict(), sort_keys=True)
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs(run_id, session_id, status, state_json, state_version, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (run_id, session_id, "pending", json.dumps(state, ensure_ascii=False), 0, ts, ts),
            )
            self.conn.execute(
                """
                INSERT INTO steps(step_id, run_id, session_id, status, attempt, state_version, retry_policy_json, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (step_id, run_id, session_id, "pending", 0, 0, retry_policy_json, ts, ts),
            )
            self._append_event_in_tx(run_id=run_id, session_id=session_id, step_id=None, event_type="run_created", payload={"initial_state": state, "retry_policy": json.loads(retry_policy_json)})
            self._append_event_in_tx(run_id=run_id, session_id=session_id, step_id=step_id, event_type="step_created", payload={"step_id": step_id, "retry_policy": json.loads(retry_policy_json)})
        return run_id, step_id

    def claim_step(self, *, worker_id: str, run_id: str | None = None, lease_seconds: int = 60) -> StepClaim | None:
        clauses = "status IN ('pending','retry_scheduled')"
        params: list[Any] = []
        if run_id:
            clauses += " AND run_id = ?"
            params.append(run_id)
        for _ in range(64):
            now = now_ts()
            row = self.conn.execute(
                f"SELECT * FROM steps WHERE {clauses} ORDER BY created_at LIMIT 1",
                params,
            ).fetchone()
            if row is None:
                return None
            lease_token = new_id("lease")
            attempt = int(row["attempt"]) + 1
            lease_until = now + lease_seconds
            with self.conn:
                updated = self.conn.execute(
                    """
                    UPDATE steps
                       SET status='running', owner=?, lease_token=?, lease_until=?, last_heartbeat_at=?, attempt=?, updated_at=?
                     WHERE step_id=? AND status IN ('pending','retry_scheduled')
                    """,
                    (worker_id, lease_token, lease_until, now, attempt, now, row["step_id"]),
                )
                if updated.rowcount != 1:
                    continue
                self.conn.execute("UPDATE runs SET status='running', updated_at=? WHERE run_id=?", (now, row["run_id"]))
                self._append_event_in_tx(
                    run_id=row["run_id"],
                    session_id=row["session_id"],
                    step_id=row["step_id"],
                    event_type="step_claimed",
                    payload={"worker_id": worker_id, "lease_token": lease_token, "attempt": attempt, "lease_until": lease_until},
                )
            return StepClaim(row["run_id"], row["session_id"], row["step_id"], attempt, lease_token, int(row["state_version"]), lease_until)
        return None

    def heartbeat(self, *, step_id: str, lease_token: str, lease_seconds: int = 60) -> float:
        row = self.validate_lease(step_id, lease_token)
        now = now_ts()
        lease_until = now + lease_seconds
        with self.conn:
            self.conn.execute(
                "UPDATE steps SET lease_until=?, last_heartbeat_at=?, updated_at=? WHERE step_id=? AND lease_token=? AND status='running'",
                (lease_until, now, now, step_id, lease_token),
            )
            self._append_event_in_tx(
                run_id=row["run_id"],
                session_id=row["session_id"],
                step_id=step_id,
                event_type="worker_heartbeat",
                payload={"lease_token": lease_token, "lease_until": lease_until},
            )
        return lease_until

    def recover_expired_leases(self) -> int:
        now = now_ts()
        rows = list(self.conn.execute("SELECT * FROM steps WHERE status='running' AND lease_until IS NOT NULL AND lease_until < ?", (now,)))
        recovered = 0
        with self.conn:
            for row in rows:
                updated = self.conn.execute(
                    "UPDATE steps SET status='retry_scheduled', owner=NULL, lease_token=NULL, lease_until=NULL, updated_at=? WHERE step_id=? AND status='running'",
                    (now, row["step_id"]),
                )
                if updated.rowcount != 1:
                    continue
                recovered += 1
                self.conn.execute("UPDATE runs SET status='retry_scheduled', updated_at=? WHERE run_id=?", (now, row["run_id"]))
                self._append_event_in_tx(run_id=row["run_id"], session_id=row["session_id"], step_id=row["step_id"], event_type="lease_expired", payload={"previous_owner": row["owner"], "attempt": row["attempt"]})
                self._append_event_in_tx(run_id=row["run_id"], session_id=row["session_id"], step_id=row["step_id"], event_type="step_retry_scheduled", payload={"step_id": row["step_id"], "reason": "lease_expired"})
        return recovered

    def cancel_run(self, *, run_id: str, reason: str) -> int:
        ts = now_ts()
        rows = list(self.conn.execute("SELECT * FROM steps WHERE run_id=? AND status NOT IN ('completed','failed','cancelled')", (run_id,)))
        run = self.run(run_id)
        if run["status"] in {"completed", "failed", "cancelled"}:
            return 0
        with self.conn:
            self._append_event_in_tx(run_id=run_id, session_id=run["session_id"], step_id=None, event_type="run_cancel_requested", payload={"reason": reason})
            for row in rows:
                self.conn.execute(
                    "UPDATE steps SET status='cancelled', owner=NULL, lease_token=NULL, lease_until=NULL, cancelled_at=?, updated_at=? WHERE step_id=?",
                    (ts, ts, row["step_id"]),
                )
                self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=row["step_id"], event_type="step_cancelled", payload={"reason": reason})
            self.conn.execute("UPDATE runs SET status='cancelled', updated_at=? WHERE run_id=?", (ts, run_id))
            self._append_event_in_tx(run_id=run_id, session_id=run["session_id"], step_id=None, event_type="run_cancelled", payload={"reason": reason, "cancelled_steps": len(rows)})
        return len(rows)


    def mark_waiting_human(self, *, run_id: str, step_id: str, reason: str, approval_id: str | None = None) -> None:
        ts = now_ts()
        with self.conn:
            row = self.conn.execute("SELECT * FROM steps WHERE step_id=?", (step_id,)).fetchone()
            if row is None:
                raise KeyError(step_id)
            self.conn.execute(
                "UPDATE steps SET status='waiting_human', owner=NULL, lease_token=NULL, lease_until=NULL, last_error_type=?, last_error=?, updated_at=? WHERE step_id=?",
                ("ApprovalRequired", reason, ts, step_id),
            )
            self.conn.execute("UPDATE runs SET status='waiting_human', updated_at=? WHERE run_id=?", (ts, run_id))
            self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="step_waiting_human", payload={"reason": reason, "approval_id": approval_id})

    def request_approval(self, **kwargs: Any) -> sqlite3.Row:
        existing = self.conn.execute("SELECT * FROM approval_requests WHERE approval_key=?", (kwargs["approval_key"],)).fetchone()
        if existing is not None:
            return existing
        ts = now_ts()
        approval_id = new_id("approval")
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO approval_requests(approval_id, approval_key, run_id, session_id, step_id, tool_name, risk_level, status, reason, request_hash, request_ref, requested_by, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        approval_id,
                        kwargs["approval_key"],
                        kwargs["run_id"],
                        kwargs.get("session_id"),
                        kwargs["step_id"],
                        kwargs["tool_name"],
                        kwargs["risk_level"],
                        "PENDING",
                        kwargs.get("reason"),
                        kwargs["request_hash"],
                        kwargs["request_ref"],
                        kwargs.get("requested_by"),
                        ts,
                        ts,
                    ),
                )
        except sqlite3.IntegrityError:
            pass
        row = self.conn.execute("SELECT * FROM approval_requests WHERE approval_key=?", (kwargs["approval_key"],)).fetchone()
        if row is None:
            raise RuntimeError("approval request was not created")
        return row

    def approval_for_key(self, approval_key: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM approval_requests WHERE approval_key=?", (approval_key,)).fetchone()

    def approval_requests(self, run_id: str | None = None) -> list[sqlite3.Row]:
        if run_id is None:
            return list(self.conn.execute("SELECT * FROM approval_requests ORDER BY created_at"))
        return list(self.conn.execute("SELECT * FROM approval_requests WHERE run_id=? ORDER BY created_at", (run_id,)))

    def approve_request(self, approval_id: str, *, approver: str = "operator", reason: str = "") -> sqlite3.Row:
        return self._decide_approval(approval_id, status="APPROVED", approver=approver, reason=reason)

    def deny_request(self, approval_id: str, *, approver: str = "operator", reason: str = "") -> sqlite3.Row:
        return self._decide_approval(approval_id, status="DENIED", approver=approver, reason=reason)

    def _decide_approval(self, approval_id: str, *, status: str, approver: str, reason: str) -> sqlite3.Row:
        ts = now_ts()
        with self.conn:
            row = self.conn.execute("SELECT * FROM approval_requests WHERE approval_id=?", (approval_id,)).fetchone()
            if row is None:
                raise KeyError(f"approval not found: {approval_id}")
            self.conn.execute(
                "UPDATE approval_requests SET status=?, approved_by=?, decision_reason=?, updated_at=? WHERE approval_id=?",
                (status, approver, reason, ts, approval_id),
            )
            self._append_event_in_tx(
                run_id=row["run_id"],
                session_id=row["session_id"],
                step_id=row["step_id"],
                event_type="tool_approval_decided",
                payload={"approval_id": approval_id, "tool": row["tool_name"], "status": status, "approver": approver, "reason": reason},
            )
            step = self.conn.execute("SELECT * FROM steps WHERE step_id=?", (row["step_id"],)).fetchone()
            if step is not None and step["status"] == "waiting_human":
                if status == "APPROVED":
                    self.conn.execute(
                        "UPDATE steps SET status='pending', owner=NULL, lease_token=NULL, lease_until=NULL, updated_at=? WHERE step_id=?",
                        (ts, row["step_id"]),
                    )
                    self.conn.execute("UPDATE runs SET status='pending', updated_at=? WHERE run_id=?", (ts, row["run_id"]))
                    self._append_event_in_tx(run_id=row["run_id"], session_id=row["session_id"], step_id=row["step_id"], event_type="step_retry_scheduled", payload={"step_id": row["step_id"], "reason": "approval_granted"})
                elif status == "DENIED":
                    self.conn.execute(
                        "UPDATE steps SET status='failed', owner=NULL, lease_token=NULL, lease_until=NULL, last_error_type=?, last_error=?, updated_at=? WHERE step_id=?",
                        ("ApprovalDenied", reason, ts, row["step_id"]),
                    )
                    self.conn.execute("UPDATE runs SET status='failed', updated_at=? WHERE run_id=?", (ts, row["run_id"]))
                    self._append_event_in_tx(run_id=row["run_id"], session_id=row["session_id"], step_id=row["step_id"], event_type="step_failed", payload={"step_id": row["step_id"], "error_type": "ApprovalDenied"})
        decided = self.conn.execute("SELECT * FROM approval_requests WHERE approval_id=?", (approval_id,)).fetchone()
        if decided is None:
            raise KeyError(f"approval not found: {approval_id}")
        return decided


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

    def _retry_policy_for_step(self, row: sqlite3.Row) -> RetryPolicy:
        raw = row["retry_policy_json"] if "retry_policy_json" in row.keys() else None
        return RetryPolicy.from_dict(json.loads(raw) if raw else None)

    def mark_retry(self, *, run_id: str, step_id: str, error: str, error_type: str = "RetryableError") -> bool:
        ts = now_ts()
        with self.conn:
            row = self.conn.execute("SELECT * FROM steps WHERE step_id=?", (step_id,)).fetchone()
            if row is None:
                raise KeyError(step_id)
            retry_policy = self._retry_policy_for_step(row)
            retryable = retry_policy.allows_retry_after_attempt(int(row["attempt"]))
            self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="failure_classified", payload={"error": error, "error_type": error_type, "retryable": retryable, "attempt": row["attempt"], "max_attempts": retry_policy.max_attempts})
            if not retryable:
                self.conn.execute(
                    "UPDATE steps SET status='failed', owner=NULL, lease_token=NULL, lease_until=NULL, last_error_type=?, last_error=?, updated_at=? WHERE step_id=?",
                    (error_type, error, ts, step_id),
                )
                self.conn.execute("UPDATE runs SET status='failed', updated_at=? WHERE run_id=?", (ts, run_id))
                self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="error_raised", payload={"error": error, "error_type": error_type})
                self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="step_failed", payload={"step_id": step_id, "error_type": error_type, "reason": "retry_exhausted"})
                return False
            self.conn.execute(
                "UPDATE steps SET status='retry_scheduled', owner=NULL, lease_token=NULL, lease_until=NULL, last_error_type=?, last_error=?, updated_at=? WHERE step_id=?",
                (error_type, error, ts, step_id),
            )
            self.conn.execute("UPDATE runs SET status='retry_scheduled', updated_at=? WHERE run_id=?", (ts, run_id))
            self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="error_raised", payload={"error": error, "error_type": error_type})
            self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="step_retry_scheduled", payload={"step_id": step_id, "attempt": row["attempt"], "max_attempts": retry_policy.max_attempts})
            return True

    def mark_failed(self, *, run_id: str, step_id: str, error: str, error_type: str) -> None:
        ts = now_ts()
        with self.conn:
            row = self.conn.execute("SELECT * FROM steps WHERE step_id=?", (step_id,)).fetchone()
            if row is None:
                raise KeyError(step_id)
            self.conn.execute(
                "UPDATE steps SET status='failed', owner=NULL, lease_token=NULL, lease_until=NULL, last_error_type=?, last_error=?, updated_at=? WHERE step_id=?",
                (error_type, error, ts, step_id),
            )
            self.conn.execute("UPDATE runs SET status='failed', updated_at=? WHERE run_id=?", (ts, run_id))
            self._append_event_in_tx(run_id=run_id, session_id=row["session_id"], step_id=step_id, event_type="failure_classified", payload={"error": error, "error_type": error_type, "retryable": False})
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

    def run(self, run_id: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"run not found: {run_id}")
        return row

    def runs(self, *, limit: int = 100, status: str | None = None) -> list[sqlite3.Row]:
        safe_limit = max(1, min(int(limit), 1000))
        if status:
            return list(self.conn.execute("SELECT * FROM runs WHERE status=? ORDER BY updated_at DESC, created_at DESC LIMIT ?", (status, safe_limit)))
        return list(self.conn.execute("SELECT * FROM runs ORDER BY updated_at DESC, created_at DESC LIMIT ?", (safe_limit,)))

    def steps(self, run_id: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM steps WHERE run_id=? ORDER BY created_at", (run_id,)))

    def events(self, run_id: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,)))

    def ledger(self, run_id: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM tool_ledger WHERE run_id=? ORDER BY created_at", (run_id,)))

    def artifacts(self, run_id: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at", (run_id,)))

    def cost_records(self, run_id: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM cost_records WHERE run_id=? ORDER BY created_at", (run_id,)))

    def create_artifact(self, *, run_id: str, step_id: str | None, name: str, blob_hash: str, blob_ref: str, metadata: dict[str, Any] | None = None) -> str:
        artifact_id = new_id("art")
        with self.conn:
            self.conn.execute(
                "INSERT INTO artifacts(artifact_id, run_id, step_id, name, blob_hash, blob_ref, metadata_json, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (artifact_id, run_id, step_id, name, blob_hash, blob_ref, json.dumps(metadata or {}, ensure_ascii=False), now_ts()),
            )
        return artifact_id

    def record_cost(self, *, run_id: str, session_id: str | None, step_id: str | None, category: str, name: str, amount: float, unit: str, metadata: dict[str, Any] | None = None) -> str:
        cost_id = new_id("cost")
        ts = now_ts()
        payload = {"cost_id": cost_id, "category": category, "name": name, "amount": amount, "unit": unit, "metadata": metadata or {}}
        with self.conn:
            self.conn.execute(
                "INSERT INTO cost_records(cost_id, run_id, session_id, step_id, category, name, amount, unit, metadata_json, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (cost_id, run_id, session_id, step_id, category, name, float(amount), unit, json.dumps(metadata or {}, ensure_ascii=False), ts),
            )
            self._append_event_in_tx(run_id=run_id, session_id=session_id, step_id=step_id, event_type="cost_recorded", payload=payload)
        return cost_id

    def cost_summary(self, run_id: str) -> dict[str, Any]:
        records = self.cost_records(run_id)
        tool_calls = sum(float(row["amount"]) for row in records if row["category"] in {"tool", "tool_shadow"} and row["unit"] == "call")
        model_tokens = sum(float(row["amount"]) for row in records if row["category"] == "model" and row["unit"] == "token")
        total_usd = sum(float(row["amount"]) for row in records if row["unit"] == "usd")
        by_category: dict[str, float] = {}
        for row in records:
            key = f"{row['category']}:{row['unit']}"
            by_category[key] = by_category.get(key, 0.0) + float(row["amount"])
        return {"tool_calls": tool_calls, "model_tokens": model_tokens, "total_usd": total_usd, "by_category": by_category}

    def find_succeeded_ledger_response(self, *, run_id: str, tool_name: str, logical_operation: str | None, request_hash: str) -> sqlite3.Row | None:
        if logical_operation:
            suffix = f":{tool_name}:{logical_operation}"
            row = self.conn.execute(
                "SELECT * FROM tool_ledger WHERE run_id=? AND tool_name=? AND status='SUCCEEDED' AND idempotency_key LIKE ? ORDER BY created_at DESC LIMIT 1",
                (run_id, tool_name, f"%{suffix}"),
            ).fetchone()
            if row is not None:
                return row
        return self.conn.execute(
            "SELECT * FROM tool_ledger WHERE run_id=? AND tool_name=? AND status='SUCCEEDED' AND request_hash=? ORDER BY created_at DESC LIMIT 1",
            (run_id, tool_name, request_hash),
        ).fetchone()

    def final_state(self, run_id: str) -> dict[str, Any]:
        return self.load_state(run_id)[0]
