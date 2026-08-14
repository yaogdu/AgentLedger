use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use rusqlite::{params, Connection, OpenFlags, OptionalExtension, TransactionBehavior};

use super::{stable_hash, Result, RuntimeError, State, Value};

const BUNDLE_SCHEMA: &str = "agentledger.sqlite.evidence.bundle.v1";
const MAX_PAYLOAD_BYTES: usize = 64 * 1024;
const RETENTION_INDEX: &str =
    "CREATE INDEX IF NOT EXISTS idx_events_event_day ON events(event_day);";
type DerivedStep = (String, String, i64, i64, String);

const SCHEMA: &str = r#"
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
    step_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
    session_id TEXT NOT NULL, status TEXT NOT NULL, owner TEXT, lease_token TEXT,
    lease_until REAL, attempt INTEGER NOT NULL, state_version INTEGER NOT NULL,
    checkpoint_id TEXT, next_wake_condition TEXT, created_at REAL NOT NULL,
    updated_at REAL NOT NULL, last_heartbeat_at REAL, retry_policy_json TEXT,
    last_error_type TEXT, last_error TEXT, cancelled_at REAL
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT,
    seq INTEGER NOT NULL, type TEXT NOT NULL, timestamp REAL NOT NULL, agent_role TEXT,
    state_version INTEGER, causal_token TEXT, payload_hash TEXT, payload_ref TEXT,
    event_day INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq);
CREATE TABLE IF NOT EXISTS tool_ledger (
    ledger_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT NOT NULL,
    tool_name TEXT NOT NULL, tool_version TEXT NOT NULL, tool_call_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE, causal_token TEXT NOT NULL, request_hash TEXT NOT NULL,
    request_ref TEXT NOT NULL, status TEXT NOT NULL, external_id TEXT, response_hash TEXT,
    response_ref TEXT, error_type TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step_id TEXT, name TEXT,
    blob_hash TEXT NOT NULL, blob_ref TEXT NOT NULL, metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cost_records (
    cost_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT,
    category TEXT NOT NULL, name TEXT NOT NULL, amount REAL NOT NULL, unit TEXT NOT NULL,
    metadata_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS approval_requests (
    approval_id TEXT PRIMARY KEY, approval_key TEXT NOT NULL UNIQUE, run_id TEXT NOT NULL,
    session_id TEXT, step_id TEXT NOT NULL, tool_name TEXT NOT NULL, risk_level TEXT NOT NULL,
    status TEXT NOT NULL, reason TEXT, request_hash TEXT NOT NULL, request_ref TEXT NOT NULL,
    requested_by TEXT, approved_by TEXT, decision_reason TEXT, created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_ingest_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL, session_id TEXT NOT NULL, step_id TEXT, event_type TEXT NOT NULL,
    occurred_at_ms INTEGER NOT NULL, event_day INTEGER NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_bundle_metadata (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
"#;

#[derive(Clone, Debug, PartialEq)]
pub struct EvidenceEventInput {
    pub event_id: String,
    pub run_id: String,
    pub session_id: String,
    pub step_id: Option<String>,
    pub event_type: String,
    pub occurred_at_ms: i64,
    pub payload: State,
}

#[derive(Clone, Debug, PartialEq)]
pub struct EvidenceEventRecord {
    pub event_id: String,
    pub run_id: String,
    pub session_id: String,
    pub step_id: Option<String>,
    pub seq: u64,
    pub event_type: String,
    pub occurred_at_ms: i64,
    pub payload_hash: String,
    pub payload: State,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ProjectionReceipt {
    pub projected: usize,
    pub acked: usize,
    pub dropped_invalid: usize,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EvidenceBundleReceipt {
    pub run_id: String,
    pub event_count: usize,
    pub event_hash: String,
    pub retention_cutoff_event_day: Option<i64>,
    pub removed_turn_count: usize,
    pub path: PathBuf,
}

#[derive(Clone, Debug, PartialEq)]
pub struct EvidenceReplaySummary {
    pub run_id: String,
    pub event_count: usize,
    pub event_hash: String,
    pub event_types: Vec<String>,
    pub timeline: Vec<EvidenceEventRecord>,
    pub reconstructed_state: State,
    pub failure_attributions: Vec<State>,
    pub retention_cutoff_event_day: Option<i64>,
    pub removed_turn_count: usize,
    pub replay_safe: bool,
}

#[derive(Clone, Debug)]
pub struct SqliteEvidenceStore {
    path: PathBuf,
}

impl SqliteEvidenceStore {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref().to_path_buf();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(runtime_error)?;
        }
        let store = Self { path };
        let connection = store.connection()?;
        connection.execute_batch(SCHEMA).map_err(runtime_error)?;
        ensure_column(&connection, "events", "event_day", "INTEGER")?;
        ensure_column(&connection, "evidence_ingest_queue", "step_id", "TEXT")?;
        connection
            .execute_batch(RETENTION_INDEX)
            .map_err(runtime_error)?;
        Ok(store)
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn enqueue(&self, event: &EvidenceEventInput) -> Result<bool> {
        validate_event(event)?;
        let payload_json = state_to_json(&event.payload)?;
        if payload_json.len() > MAX_PAYLOAD_BYTES {
            return Err(RuntimeError(format!(
                "evidence payload exceeds {MAX_PAYLOAD_BYTES} bytes"
            )));
        }
        let mut connection = self.connection()?;
        let transaction = connection
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(runtime_error)?;
        let run_session_id = transaction
            .query_row(
                "SELECT session_id FROM runs WHERE run_id = ?
                 UNION ALL
                 SELECT session_id FROM evidence_ingest_queue WHERE run_id = ?
                 LIMIT 1",
                params![event.run_id, event.run_id],
                |row| row.get::<_, String>(0),
            )
            .optional()
            .map_err(runtime_error)?;
        if run_session_id
            .as_ref()
            .is_some_and(|session_id| session_id != &event.session_id)
        {
            return Err(RuntimeError(format!(
                "run_id belongs to another session: {}",
                event.run_id
            )));
        }
        if let Some(step_id) = &event.step_id {
            let owner = transaction
                .query_row(
                    "SELECT run_id, session_id FROM steps WHERE step_id = ?
                     UNION ALL
                     SELECT run_id, session_id FROM evidence_ingest_queue WHERE step_id = ?
                     LIMIT 1",
                    params![step_id, step_id],
                    |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
                )
                .optional()
                .map_err(runtime_error)?;
            if owner
                .as_ref()
                .is_some_and(|owner| owner.0 != event.run_id || owner.1 != event.session_id)
            {
                return Err(RuntimeError(format!(
                    "step_id belongs to another run or session: {step_id}"
                )));
            }
        }
        let changed = transaction
            .execute(
                "INSERT OR IGNORE INTO evidence_ingest_queue
                 (event_id, run_id, session_id, step_id, event_type, occurred_at_ms, event_day, payload_json)
                 SELECT ?, ?, ?, ?, ?, ?, ?, ?
                 WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_id = ?)",
                params![
                    event.event_id,
                    event.run_id,
                    event.session_id,
                    event.step_id,
                    event.event_type,
                    event.occurred_at_ms,
                    event.occurred_at_ms / 86_400_000,
                    payload_json,
                    event.event_id
                ],
            )
            .map_err(runtime_error)?;
        let result = if changed == 1 {
            Ok(true)
        } else {
            let existing: Option<(String, String, Option<String>, String, i64, String)> = transaction
                .query_row(
                "SELECT run_id, session_id, step_id, event_type, occurred_at_ms, payload_json
                   FROM evidence_ingest_queue WHERE event_id = ?
                 UNION ALL
                 SELECT run_id, COALESCE(session_id, ''), step_id, type,
                        CAST(ROUND(timestamp * 1000) AS INTEGER), payload_ref
                   FROM events WHERE event_id = ?
                 LIMIT 1",
                params![event.event_id, event.event_id],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                    ))
                },
            )
                .optional()
                .map_err(runtime_error)?;
            match existing {
                Some((run_id, session_id, step_id, event_type, occurred_at_ms, stored_payload))
                    if run_id == event.run_id
                        && session_id == event.session_id
                        && step_id == event.step_id
                        && event_type == event.event_type
                        && occurred_at_ms == event.occurred_at_ms
                        && stored_payload == payload_json =>
                {
                    Ok(false)
                }
                Some(_) => Err(RuntimeError(format!(
                    "conflicting evidence event_id: {}",
                    event.event_id
                ))),
                None => Err(RuntimeError(format!(
                    "evidence event_id was not inserted: {}",
                    event.event_id
                ))),
            }
        };
        transaction.commit().map_err(runtime_error)?;
        result
    }

    pub fn pending_count(&self) -> Result<usize> {
        let count: i64 = self
            .connection()?
            .query_row("SELECT COUNT(*) FROM evidence_ingest_queue", [], |row| {
                row.get(0)
            })
            .map_err(runtime_error)?;
        usize::try_from(count).map_err(runtime_error)
    }

    pub fn project_batch(&self, limit: usize) -> Result<ProjectionReceipt> {
        if limit == 0 {
            return Err(RuntimeError(
                "projection limit must be positive".to_string(),
            ));
        }
        let mut connection = self.connection()?;
        let transaction = connection
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(runtime_error)?;
        let queued = {
            let mut statement = transaction
                .prepare(
                    "SELECT queue_id, event_id, run_id, session_id, step_id, event_type,
                            occurred_at_ms, event_day, payload_json
                       FROM evidence_ingest_queue ORDER BY queue_id LIMIT ?",
                )
                .map_err(runtime_error)?;
            let limit = i64::try_from(limit).map_err(runtime_error)?;
            let rows = statement
                .query_map([limit], |row| {
                    Ok(QueuedEvent {
                        queue_id: row.get(0)?,
                        event_id: row.get(1)?,
                        run_id: row.get(2)?,
                        session_id: row.get(3)?,
                        step_id: row.get(4)?,
                        event_type: row.get(5)?,
                        occurred_at_ms: row.get(6)?,
                        event_day: row.get(7)?,
                        payload_json: row.get(8)?,
                    })
                })
                .map_err(runtime_error)?;
            rows.collect::<std::result::Result<Vec<_>, _>>()
                .map_err(runtime_error)?
        };

        let mut receipt = ProjectionReceipt::default();
        for event in queued {
            if event.payload_json.len() > MAX_PAYLOAD_BYTES {
                ack_queued_event(&transaction, &mut receipt, event.queue_id, true)?;
                continue;
            }
            let payload = match json_to_state(&event.payload_json) {
                Ok(payload) => payload,
                Err(_) => {
                    ack_queued_event(&transaction, &mut receipt, event.queue_id, true)?;
                    continue;
                }
            };
            let input = EvidenceEventInput {
                event_id: event.event_id.clone(),
                run_id: event.run_id.clone(),
                session_id: event.session_id.clone(),
                step_id: event.step_id.clone(),
                event_type: event.event_type.clone(),
                occurred_at_ms: event.occurred_at_ms,
                payload,
            };
            let payload_json = state_to_json(&input.payload)?;
            if validate_event(&input).is_err()
                || event.event_day != event.occurred_at_ms / 86_400_000
                || payload_json.len() > MAX_PAYLOAD_BYTES
            {
                ack_queued_event(&transaction, &mut receipt, event.queue_id, true)?;
                continue;
            }
            let existing = transaction
                .query_row(
                    "SELECT run_id, COALESCE(session_id, ''), step_id, type,
                            CAST(ROUND(timestamp * 1000) AS INTEGER), payload_hash, payload_ref
                       FROM events WHERE event_id = ?",
                    [&event.event_id],
                    |row| {
                        Ok((
                            row.get::<_, String>(0)?,
                            row.get::<_, String>(1)?,
                            row.get::<_, Option<String>>(2)?,
                            row.get::<_, String>(3)?,
                            row.get::<_, i64>(4)?,
                            row.get::<_, String>(5)?,
                            row.get::<_, String>(6)?,
                        ))
                    },
                )
                .optional()
                .map_err(runtime_error)?;
            if let Some((
                run_id,
                session_id,
                step_id,
                event_type,
                occurred_at_ms,
                payload_hash,
                stored_payload,
            )) = existing
            {
                let matches = run_id == event.run_id
                    && session_id == event.session_id
                    && step_id == event.step_id
                    && event_type == event.event_type
                    && occurred_at_ms == event.occurred_at_ms
                    && payload_hash == stable_hash(&payload_json)
                    && stored_payload == payload_json;
                ack_queued_event(&transaction, &mut receipt, event.queue_id, !matches)?;
                continue;
            }
            let run_owner = transaction
                .query_row(
                    "SELECT session_id FROM runs WHERE run_id = ?",
                    [&event.run_id],
                    |row| row.get::<_, String>(0),
                )
                .optional()
                .map_err(runtime_error)?;
            let step_owner = if let Some(step_id) = &event.step_id {
                transaction
                    .query_row(
                        "SELECT run_id, session_id FROM steps WHERE step_id = ?",
                        [step_id],
                        |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
                    )
                    .optional()
                    .map_err(runtime_error)?
            } else {
                None
            };
            let invalid_owner = run_owner
                .as_ref()
                .is_some_and(|session_id| session_id != &event.session_id)
                || step_owner
                    .as_ref()
                    .is_some_and(|owner| owner.0 != event.run_id || owner.1 != event.session_id);
            if invalid_owner {
                ack_queued_event(&transaction, &mut receipt, event.queue_id, true)?;
                continue;
            }
            let occurred_at = event.occurred_at_ms as f64 / 1000.0;
            transaction
                .execute(
                    "INSERT OR IGNORE INTO runs
                     (run_id, session_id, status, state_json, state_version, created_at, updated_at)
                     VALUES (?, ?, 'active', '{}', 0, ?, ?)",
                    params![event.run_id, event.session_id, occurred_at, occurred_at],
                )
                .map_err(runtime_error)?;
            if let Some(step_id) = &event.step_id {
                let status = terminal_step_status(&event.event_type).unwrap_or("running");
                transaction
                    .execute(
                        "INSERT OR IGNORE INTO steps
                         (step_id, run_id, session_id, status, owner, lease_token, lease_until,
                          attempt, state_version, checkpoint_id, next_wake_condition, created_at,
                          updated_at, last_heartbeat_at, retry_policy_json, last_error_type,
                          last_error, cancelled_at)
                         VALUES (?, ?, ?, ?, NULL, NULL, NULL, 1, 0, NULL, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL)",
                        params![step_id, event.run_id, event.session_id, status, occurred_at, occurred_at],
                    )
                    .map_err(runtime_error)?;
                transaction
                    .execute(
                        "UPDATE steps SET status = COALESCE(?, status), updated_at = ? WHERE step_id = ?",
                        params![terminal_step_status(&event.event_type), occurred_at, step_id],
                    )
                    .map_err(runtime_error)?;
            }
            let seq: i64 = transaction
                .query_row(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE run_id = ?",
                    [&event.run_id],
                    |row| row.get(0),
                )
                .map_err(runtime_error)?;
            let inserted = transaction
                .execute(
                    "INSERT OR IGNORE INTO events
                     (event_id, run_id, session_id, step_id, seq, type, timestamp, agent_role,
                      state_version, causal_token, payload_hash, payload_ref, event_day)
                     VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)",
                    params![
                        event.event_id,
                        event.run_id,
                        event.session_id,
                        event.step_id,
                        seq,
                        event.event_type,
                        occurred_at,
                        stable_hash(&payload_json),
                        payload_json,
                        event.event_day
                    ],
                )
                .map_err(runtime_error)?;
            if inserted == 1 {
                let status = terminal_run_status(&event.event_type);
                transaction
                    .execute(
                        "UPDATE runs SET status = COALESCE(?, status), updated_at = ? WHERE run_id = ?",
                        params![status, occurred_at, event.run_id],
                    )
                    .map_err(runtime_error)?;
                receipt.projected += 1;
            }
            receipt.acked += transaction
                .execute(
                    "DELETE FROM evidence_ingest_queue WHERE queue_id = ?",
                    [event.queue_id],
                )
                .map_err(runtime_error)?;
        }
        transaction.commit().map_err(runtime_error)?;
        Ok(receipt)
    }

    pub fn events(&self, run_id: &str) -> Result<Vec<EvidenceEventRecord>> {
        if run_id.trim().is_empty() {
            return Err(RuntimeError("run_id must not be empty".to_string()));
        }
        read_events(&self.connection()?, run_id)
    }

    pub fn prune_to_active_event_days(&self, keep_days: usize) -> Result<usize> {
        if keep_days == 0 {
            return Err(RuntimeError(
                "active event day retention must be positive".to_string(),
            ));
        }
        let mut connection = self.connection()?;
        let transaction = connection.transaction().map_err(runtime_error)?;
        let days = {
            let mut statement = transaction
                .prepare(
                    "SELECT DISTINCT event_day FROM events
                     WHERE event_day IS NOT NULL ORDER BY event_day DESC",
                )
                .map_err(runtime_error)?;
            let rows = statement
                .query_map([], |row| row.get::<_, i64>(0))
                .map_err(runtime_error)?;
            rows.collect::<std::result::Result<Vec<_>, _>>()
                .map_err(runtime_error)?
        };
        if days.len() <= keep_days {
            transaction.commit().map_err(runtime_error)?;
            return Ok(0);
        }
        let cutoff = days[keep_days - 1];
        let removable_steps = {
            let mut statement = transaction
                .prepare(
                    "SELECT s.step_id, s.run_id FROM steps s
                     WHERE s.status IN ('completed', 'failed', 'cancelled')
                       AND EXISTS (SELECT 1 FROM events e WHERE e.step_id = s.step_id)
                       AND NOT EXISTS (
                           SELECT 1 FROM events e
                           WHERE e.step_id = s.step_id AND e.event_day >= ?
                       )",
                )
                .map_err(runtime_error)?;
            let rows = statement
                .query_map([cutoff], |row| {
                    Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
                })
                .map_err(runtime_error)?;
            rows.collect::<std::result::Result<Vec<_>, _>>()
                .map_err(runtime_error)?
        };
        let mut deleted = 0;
        let mut removed_by_run = BTreeMap::<String, usize>::new();
        for (step_id, run_id) in &removable_steps {
            deleted += transaction
                .execute("DELETE FROM events WHERE step_id = ?", [step_id])
                .map_err(runtime_error)?;
            transaction
                .execute("DELETE FROM steps WHERE step_id = ?", [step_id])
                .map_err(runtime_error)?;
            *removed_by_run.entry(run_id.clone()).or_default() += 1;
        }
        deleted += transaction
            .execute(
                "DELETE FROM events WHERE step_id IS NULL AND event_day < ?",
                [cutoff],
            )
            .map_err(runtime_error)?;
        transaction
            .execute(
                "INSERT INTO evidence_bundle_metadata(key, value) VALUES (?, ?)
                 ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                params!["retention_cutoff_event_day", cutoff.to_string()],
            )
            .map_err(runtime_error)?;
        for (run_id, removed) in removed_by_run {
            let key = retention_removed_key(&run_id);
            let previous_removed: usize = optional_bundle_metadata(&transaction, &key)?
                .unwrap_or_else(|| "0".to_string())
                .parse()
                .map_err(runtime_error)?;
            transaction
                .execute(
                    "INSERT INTO evidence_bundle_metadata(key, value) VALUES (?, ?)
                     ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    params![key, (previous_removed + removed).to_string()],
                )
                .map_err(runtime_error)?;
        }
        transaction.commit().map_err(runtime_error)?;
        Ok(deleted)
    }

    pub fn export_bundle(
        &self,
        run_id: &str,
        path: impl AsRef<Path>,
    ) -> Result<EvidenceBundleReceipt> {
        let mut connection = self.connection()?;
        let transaction = connection.transaction().map_err(runtime_error)?;
        let events = read_events(&transaction, run_id)?;
        if events.is_empty() {
            return Err(RuntimeError(format!(
                "run has no evidence events: {run_id}"
            )));
        }
        let target = path.as_ref();
        if target.exists() {
            return Err(RuntimeError(format!(
                "evidence bundle already exists: {}",
                target.display()
            )));
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(runtime_error)?;
        }
        let retention_cutoff_event_day =
            optional_bundle_metadata(&transaction, "retention_cutoff_event_day")?
                .map(|value| value.parse())
                .transpose()
                .map_err(runtime_error)?;
        let removed_turn_count =
            optional_bundle_metadata(&transaction, &retention_removed_key(run_id))?
                .unwrap_or_else(|| "0".to_string())
                .parse()
                .map_err(runtime_error)?;
        transaction.commit().map_err(runtime_error)?;
        let result = export_bundle_file(
            run_id,
            &events,
            target,
            retention_cutoff_event_day,
            removed_turn_count,
        );
        if result.is_err() {
            let _ = fs::remove_file(target);
        }
        result
    }

    pub fn replay_bundle(path: impl AsRef<Path>) -> Result<EvidenceReplaySummary> {
        let connection =
            Connection::open_with_flags(path.as_ref(), OpenFlags::SQLITE_OPEN_READ_ONLY)
                .map_err(runtime_error)?;
        connection
            .busy_timeout(Duration::from_secs(30))
            .map_err(runtime_error)?;
        let integrity: String = connection
            .query_row("PRAGMA quick_check", [], |row| row.get(0))
            .map_err(runtime_error)?;
        if integrity != "ok" {
            return Err(RuntimeError(format!(
                "evidence bundle integrity failed: {integrity}"
            )));
        }
        let schema = bundle_metadata(&connection, "schema_version")?;
        if schema != BUNDLE_SCHEMA {
            return Err(RuntimeError(format!(
                "unsupported evidence bundle schema: {schema}"
            )));
        }
        let run_id = bundle_metadata(&connection, "run_id")?;
        let expected_hash = bundle_metadata(&connection, "event_hash")?;
        let expected_count: usize = bundle_metadata(&connection, "event_count")?
            .parse()
            .map_err(runtime_error)?;
        let events = read_events(&connection, &run_id)?;
        let actual_hash = event_hash(&events);
        let total_event_count: i64 = connection
            .query_row("SELECT COUNT(*) FROM events", [], |row| row.get(0))
            .map_err(runtime_error)?;
        let total_run_count: i64 = connection
            .query_row("SELECT COUNT(*) FROM runs", [], |row| row.get(0))
            .map_err(runtime_error)?;
        if events.len() != expected_count
            || usize::try_from(total_event_count).map_err(runtime_error)? != expected_count
            || total_run_count != 1
            || actual_hash != expected_hash
        {
            return Err(RuntimeError("evidence bundle receipt mismatch".to_string()));
        }
        if read_steps(&connection)? != derive_steps(&events)? {
            return Err(RuntimeError(
                "evidence bundle step structure mismatch".to_string(),
            ));
        }
        let (session_id, run_status, state_json): (String, String, String) = connection
            .query_row(
                "SELECT session_id, status, state_json FROM runs WHERE run_id = ?",
                [&run_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .map_err(runtime_error)?;
        let expected_session_id = &events[0].session_id;
        let expected_run_status = events
            .iter()
            .filter_map(|event| terminal_run_status(&event.event_type))
            .next_back()
            .unwrap_or("evidence");
        if session_id != *expected_session_id
            || run_status != expected_run_status
            || !json_to_state(&state_json)?.is_empty()
        {
            return Err(RuntimeError(
                "evidence bundle run structure mismatch".to_string(),
            ));
        }
        let step_count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM steps WHERE run_id = ?",
                [&run_id],
                |row| row.get(0),
            )
            .map_err(runtime_error)?;
        let mut reconstructed_state = State::new();
        reconstructed_state.insert("session_id".to_string(), Value::String(session_id));
        reconstructed_state.insert("run_status".to_string(), Value::String(run_status));
        reconstructed_state.insert("step_count".to_string(), Value::Number(step_count as f64));
        if let Some(last) = events.last() {
            reconstructed_state.insert(
                "last_event_type".to_string(),
                Value::String(last.event_type.clone()),
            );
            reconstructed_state.insert(
                "last_occurred_at_ms".to_string(),
                Value::Number(last.occurred_at_ms as f64),
            );
        }
        let failure_attributions = events
            .iter()
            .filter(|event| event.event_type == "failure.attributed")
            .map(|event| event.payload.clone())
            .collect();
        let retention_cutoff_event_day =
            optional_bundle_metadata(&connection, "retention_cutoff_event_day")?
                .map(|value| value.parse())
                .transpose()
                .map_err(runtime_error)?;
        let removed_turn_count =
            optional_bundle_metadata(&connection, "retention_removed_turn_count")?
                .unwrap_or_else(|| "0".to_string())
                .parse()
                .map_err(runtime_error)?;
        Ok(EvidenceReplaySummary {
            run_id,
            event_count: events.len(),
            event_hash: actual_hash,
            event_types: events
                .iter()
                .map(|event| event.event_type.clone())
                .collect(),
            timeline: events,
            reconstructed_state,
            failure_attributions,
            retention_cutoff_event_day,
            removed_turn_count,
            replay_safe: true,
        })
    }

    fn connection(&self) -> Result<Connection> {
        let connection = Connection::open(&self.path).map_err(runtime_error)?;
        connection
            .busy_timeout(Duration::from_secs(30))
            .map_err(runtime_error)?;
        connection
            .execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")
            .map_err(runtime_error)?;
        Ok(connection)
    }
}

fn ack_queued_event(
    connection: &Connection,
    receipt: &mut ProjectionReceipt,
    queue_id: i64,
    invalid: bool,
) -> Result<()> {
    let acked = connection
        .execute(
            "DELETE FROM evidence_ingest_queue WHERE queue_id = ?",
            [queue_id],
        )
        .map_err(runtime_error)?;
    receipt.acked += acked;
    if invalid {
        receipt.dropped_invalid += acked;
    }
    Ok(())
}

#[derive(Debug)]
struct QueuedEvent {
    queue_id: i64,
    event_id: String,
    run_id: String,
    session_id: String,
    step_id: Option<String>,
    event_type: String,
    occurred_at_ms: i64,
    event_day: i64,
    payload_json: String,
}

fn export_bundle_file(
    run_id: &str,
    events: &[EvidenceEventRecord],
    target: &Path,
    retention_cutoff_event_day: Option<i64>,
    removed_turn_count: usize,
) -> Result<EvidenceBundleReceipt> {
    let mut connection = Connection::open(target).map_err(runtime_error)?;
    connection
        .execute_batch("PRAGMA journal_mode=DELETE; PRAGMA foreign_keys=ON;")
        .map_err(runtime_error)?;
    connection.execute_batch(SCHEMA).map_err(runtime_error)?;
    connection
        .execute_batch(RETENTION_INDEX)
        .map_err(runtime_error)?;
    let transaction = connection.transaction().map_err(runtime_error)?;
    let first = &events[0];
    let last = events.last().unwrap();
    let run_status = events
        .iter()
        .filter_map(|event| terminal_run_status(&event.event_type))
        .next_back()
        .unwrap_or("evidence");
    transaction
        .execute(
            "INSERT INTO runs
             (run_id, session_id, status, state_json, state_version, created_at, updated_at)
             VALUES (?, ?, ?, '{}', 0, ?, ?)",
            params![
                run_id,
                first.session_id,
                run_status,
                first.occurred_at_ms as f64 / 1000.0,
                last.occurred_at_ms as f64 / 1000.0
            ],
        )
        .map_err(runtime_error)?;
    for (step_id, (step_run_id, session_id, created_at_ms, updated_at_ms, status)) in
        &derive_steps(events)?
    {
        transaction
            .execute(
                "INSERT INTO steps
                 (step_id, run_id, session_id, status, owner, lease_token, lease_until,
                  attempt, state_version, checkpoint_id, next_wake_condition, created_at,
                  updated_at, last_heartbeat_at, retry_policy_json, last_error_type,
                  last_error, cancelled_at)
                 VALUES (?, ?, ?, ?, NULL, NULL, NULL, 1, 0, NULL, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL)",
                params![
                    step_id,
                    step_run_id,
                    session_id,
                    status,
                    *created_at_ms as f64 / 1000.0,
                    *updated_at_ms as f64 / 1000.0
                ],
            )
            .map_err(runtime_error)?;
    }
    for event in events {
        let payload_json = state_to_json(&event.payload)?;
        transaction
            .execute(
                "INSERT INTO events
                 (event_id, run_id, session_id, step_id, seq, type, timestamp, agent_role,
                  state_version, causal_token, payload_hash, payload_ref, event_day)
                 VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)",
                params![
                    event.event_id,
                    event.run_id,
                    event.session_id,
                    event.step_id,
                    i64::try_from(event.seq).map_err(runtime_error)?,
                    event.event_type,
                    event.occurred_at_ms as f64 / 1000.0,
                    event.payload_hash,
                    payload_json,
                    event.occurred_at_ms / 86_400_000
                ],
            )
            .map_err(runtime_error)?;
    }
    let hash = event_hash(events);
    for (key, value) in [
        ("schema_version", BUNDLE_SCHEMA.to_string()),
        ("run_id", run_id.to_string()),
        ("event_count", events.len().to_string()),
        ("event_hash", hash.clone()),
        (
            "retention_removed_turn_count",
            removed_turn_count.to_string(),
        ),
    ] {
        transaction
            .execute(
                "INSERT INTO evidence_bundle_metadata(key, value) VALUES (?, ?)",
                params![key, value],
            )
            .map_err(runtime_error)?;
    }
    if let Some(cutoff) = retention_cutoff_event_day {
        transaction
            .execute(
                "INSERT INTO evidence_bundle_metadata(key, value)
                 VALUES ('retention_cutoff_event_day', ?)",
                [cutoff.to_string()],
            )
            .map_err(runtime_error)?;
    }
    transaction.commit().map_err(runtime_error)?;
    connection
        .execute_batch("PRAGMA wal_checkpoint(TRUNCATE); PRAGMA journal_mode=DELETE;")
        .map_err(runtime_error)?;
    drop(connection);
    Ok(EvidenceBundleReceipt {
        run_id: run_id.to_string(),
        event_count: events.len(),
        event_hash: hash,
        retention_cutoff_event_day,
        removed_turn_count,
        path: target.to_path_buf(),
    })
}

fn derive_steps(events: &[EvidenceEventRecord]) -> Result<BTreeMap<String, DerivedStep>> {
    let mut steps = BTreeMap::new();
    for event in events {
        let Some(step_id) = &event.step_id else {
            continue;
        };
        let entry = steps.entry(step_id.clone()).or_insert_with(|| {
            (
                event.run_id.clone(),
                event.session_id.clone(),
                event.occurred_at_ms,
                event.occurred_at_ms,
                "running".to_string(),
            )
        });
        if entry.0 != event.run_id || entry.1 != event.session_id {
            return Err(RuntimeError(format!(
                "step_id belongs to another run or session: {step_id}"
            )));
        }
        entry.3 = event.occurred_at_ms;
        if let Some(status) = terminal_step_status(&event.event_type) {
            entry.4 = status.to_string();
        }
    }
    Ok(steps)
}

fn read_steps(connection: &Connection) -> Result<BTreeMap<String, DerivedStep>> {
    let mut statement = connection
        .prepare(
            "SELECT step_id, run_id, session_id,
                    CAST(ROUND(created_at * 1000) AS INTEGER),
                    CAST(ROUND(updated_at * 1000) AS INTEGER), status
               FROM steps ORDER BY step_id",
        )
        .map_err(runtime_error)?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                (
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, i64>(3)?,
                    row.get::<_, i64>(4)?,
                    row.get::<_, String>(5)?,
                ),
            ))
        })
        .map_err(runtime_error)?;
    rows.collect::<std::result::Result<BTreeMap<_, _>, _>>()
        .map_err(runtime_error)
}

fn read_events(connection: &Connection, run_id: &str) -> Result<Vec<EvidenceEventRecord>> {
    let mut statement = connection
        .prepare(
            "SELECT event_id, run_id, session_id, step_id, seq, type,
                    CAST(ROUND(timestamp * 1000) AS INTEGER), payload_hash, payload_ref
               FROM events WHERE run_id = ? ORDER BY seq",
        )
        .map_err(runtime_error)?;
    let rows = statement
        .query_map([run_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, Option<String>>(3)?,
                row.get::<_, i64>(4)?,
                row.get::<_, String>(5)?,
                row.get::<_, i64>(6)?,
                row.get::<_, String>(7)?,
                row.get::<_, String>(8)?,
            ))
        })
        .map_err(runtime_error)?;
    rows.map(|row| {
        let (
            event_id,
            run_id,
            session_id,
            step_id,
            seq,
            event_type,
            occurred_at_ms,
            payload_hash,
            payload_json,
        ) = row.map_err(runtime_error)?;
        let payload = json_to_state(&payload_json)?;
        if stable_hash(&state_to_json(&payload)?) != payload_hash {
            return Err(RuntimeError(format!(
                "evidence payload hash mismatch: {event_id}"
            )));
        }
        Ok(EvidenceEventRecord {
            event_id,
            run_id,
            session_id,
            step_id,
            seq: u64::try_from(seq).map_err(runtime_error)?,
            event_type,
            occurred_at_ms,
            payload_hash,
            payload,
        })
    })
    .collect()
}

fn bundle_metadata(connection: &Connection, key: &str) -> Result<String> {
    optional_bundle_metadata(connection, key)?
        .ok_or_else(|| RuntimeError(format!("evidence bundle metadata missing: {key}")))
}

fn optional_bundle_metadata(connection: &Connection, key: &str) -> Result<Option<String>> {
    connection
        .query_row(
            "SELECT value FROM evidence_bundle_metadata WHERE key = ?",
            [key],
            |row| row.get(0),
        )
        .optional()
        .map_err(runtime_error)
}

fn retention_removed_key(run_id: &str) -> String {
    format!("retention_removed_turn_count:{run_id}")
}

fn event_hash(events: &[EvidenceEventRecord]) -> String {
    let mut canonical = String::new();
    for event in events {
        for field in [
            event.event_id.as_str(),
            event.run_id.as_str(),
            event.session_id.as_str(),
            event.step_id.as_deref().unwrap_or("<none>"),
            event.event_type.as_str(),
            event.payload_hash.as_str(),
        ] {
            canonical.push_str(&field.len().to_string());
            canonical.push(':');
            canonical.push_str(field);
            canonical.push(';');
        }
        canonical.push_str(&format!("{}:{};", event.seq, event.occurred_at_ms));
    }
    stable_hash(&canonical)
}

fn validate_event(event: &EvidenceEventInput) -> Result<()> {
    for (name, value) in [
        ("event_id", &event.event_id),
        ("run_id", &event.run_id),
        ("session_id", &event.session_id),
        ("event_type", &event.event_type),
    ] {
        if value.trim().is_empty() {
            return Err(RuntimeError(format!("{name} must not be empty")));
        }
        if value.len() > 256 {
            return Err(RuntimeError(format!("{name} exceeds 256 bytes")));
        }
    }
    if let Some(step_id) = &event.step_id {
        if step_id.trim().is_empty() {
            return Err(RuntimeError("step_id must not be empty".to_string()));
        }
        if step_id.len() > 256 {
            return Err(RuntimeError("step_id exceeds 256 bytes".to_string()));
        }
    }
    if event.occurred_at_ms < 0 {
        return Err(RuntimeError(
            "occurred_at_ms must not be negative".to_string(),
        ));
    }
    Ok(())
}

fn terminal_step_status(event_type: &str) -> Option<&'static str> {
    match event_type {
        "turn.completed" => Some("completed"),
        "turn.failed" => Some("failed"),
        "turn.cancelled" | "turn.canceled" => Some("cancelled"),
        _ => None,
    }
}

fn ensure_column(
    connection: &Connection,
    table: &str,
    column: &str,
    definition: &str,
) -> Result<()> {
    if ![table, column, definition].iter().all(|value| {
        value
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == '_')
    }) {
        return Err(RuntimeError("invalid SQLite schema identifier".to_string()));
    }
    let mut statement = connection
        .prepare(&format!("PRAGMA table_info({table})"))
        .map_err(runtime_error)?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(runtime_error)?;
    let columns = rows
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(runtime_error)?;
    if !columns.iter().any(|name| name == column) {
        connection
            .execute_batch(&format!(
                "ALTER TABLE {table} ADD COLUMN {column} {definition}"
            ))
            .map_err(runtime_error)?;
    }
    Ok(())
}

fn terminal_run_status(event_type: &str) -> Option<&'static str> {
    match event_type {
        "session.deleted" => Some("deleted"),
        "session.closed" => Some("completed"),
        "session.failed" => Some("failed"),
        _ => None,
    }
}

fn state_to_json(state: &State) -> Result<String> {
    let value = value_to_json(&Value::Object(state.clone()))?;
    serde_json::to_string(&value).map_err(runtime_error)
}

fn value_to_json(value: &Value) -> Result<serde_json::Value> {
    Ok(match value {
        Value::Null => serde_json::Value::Null,
        Value::Bool(value) => serde_json::Value::Bool(*value),
        Value::Number(value) => serde_json::Number::from_f64(*value)
            .map(serde_json::Value::Number)
            .ok_or_else(|| RuntimeError("evidence payload number must be finite".to_string()))?,
        Value::String(value) => serde_json::Value::String(value.clone()),
        Value::Array(values) => serde_json::Value::Array(
            values
                .iter()
                .map(value_to_json)
                .collect::<Result<Vec<_>>>()?,
        ),
        Value::Object(values) => {
            let mut object = serde_json::Map::new();
            let mut keys = values.keys().collect::<Vec<_>>();
            keys.sort();
            for key in keys {
                object.insert(key.clone(), value_to_json(&values[key])?);
            }
            serde_json::Value::Object(object)
        }
    })
}

fn json_to_state(encoded: &str) -> Result<State> {
    match json_to_value(serde_json::from_str(encoded).map_err(runtime_error)?)? {
        Value::Object(state) => Ok(state),
        _ => Err(RuntimeError(
            "evidence payload must be a JSON object".to_string(),
        )),
    }
}

fn json_to_value(value: serde_json::Value) -> Result<Value> {
    Ok(match value {
        serde_json::Value::Null => Value::Null,
        serde_json::Value::Bool(value) => Value::Bool(value),
        serde_json::Value::Number(value) => Value::Number(
            value
                .as_f64()
                .ok_or_else(|| RuntimeError("invalid JSON number".to_string()))?,
        ),
        serde_json::Value::String(value) => Value::String(value),
        serde_json::Value::Array(values) => Value::Array(
            values
                .into_iter()
                .map(json_to_value)
                .collect::<Result<Vec<_>>>()?,
        ),
        serde_json::Value::Object(values) => Value::Object(
            values
                .into_iter()
                .map(|(key, value)| Ok((key, json_to_value(value)?)))
                .collect::<Result<State>>()?,
        ),
    })
}

fn runtime_error(error: impl std::fmt::Display) -> RuntimeError {
    RuntimeError(error.to_string())
}
