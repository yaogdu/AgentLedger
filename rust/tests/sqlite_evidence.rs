#![cfg(feature = "sqlite-evidence")]

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use agentledger::{EvidenceEventInput, SqliteEvidenceStore, State, Value};
use rusqlite::Connection;

static NEXT_TEMP_DIR: AtomicU64 = AtomicU64::new(1);

struct TestDir(PathBuf);

impl TestDir {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "agentledger-sqlite-evidence-{}-{}",
            std::process::id(),
            NEXT_TEMP_DIR.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TestDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn event(id: &str, run_id: &str, day: i64) -> EvidenceEventInput {
    let mut payload = State::new();
    payload.insert(
        "outcome".to_string(),
        Value::String("completed".to_string()),
    );
    EvidenceEventInput {
        event_id: id.to_string(),
        run_id: run_id.to_string(),
        session_id: "session-1".to_string(),
        step_id: Some(format!("step-{id}")),
        event_type: "turn.completed".to_string(),
        occurred_at_ms: day * 86_400_000 + 1,
        payload,
    }
}

#[test]
fn durable_queue_survives_reopen_and_projects_in_order() {
    let temp = TestDir::new();
    let path = temp.path().join("evidence.db");
    {
        let store = SqliteEvidenceStore::open(&path).unwrap();
        assert!(store.enqueue(&event("event-1", "run-1", 1)).unwrap());
        assert!(store.enqueue(&event("event-2", "run-1", 1)).unwrap());
        assert!(!store.enqueue(&event("event-2", "run-1", 1)).unwrap());
        assert_eq!(store.pending_count().unwrap(), 2);
    }

    let store = SqliteEvidenceStore::open(&path).unwrap();
    assert_eq!(store.pending_count().unwrap(), 2);
    let first = store.project_batch(1).unwrap();
    assert_eq!(first.projected, 1);
    assert_eq!(first.acked, 1);
    assert_eq!(store.pending_count().unwrap(), 1);
    let second = store.project_batch(10).unwrap();
    assert_eq!(second.projected, 1);
    assert_eq!(second.acked, 1);
    assert_eq!(store.pending_count().unwrap(), 0);

    let events = store.events("run-1").unwrap();
    assert_eq!(
        events.iter().map(|item| item.seq).collect::<Vec<_>>(),
        vec![1, 2]
    );
    assert_eq!(
        events[0].payload.get("outcome"),
        Some(&Value::String("completed".to_string()))
    );
}

#[test]
fn opens_existing_standard_schema_before_creating_retention_index() {
    let temp = TestDir::new();
    let path = temp.path().join("evidence.db");
    let connection = Connection::open(&path).unwrap();
    connection
        .execute_batch(
            "CREATE TABLE events (
                event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT,
                seq INTEGER NOT NULL, type TEXT NOT NULL, timestamp REAL NOT NULL, agent_role TEXT,
                state_version INTEGER, causal_token TEXT, payload_hash TEXT, payload_ref TEXT
             );
             CREATE TABLE evidence_ingest_queue (
                queue_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL, session_id TEXT NOT NULL, event_type TEXT NOT NULL,
                occurred_at_ms INTEGER NOT NULL, event_day INTEGER NOT NULL, payload_json TEXT NOT NULL
             );",
        )
        .unwrap();
    drop(connection);

    SqliteEvidenceStore::open(&path).unwrap();
    let connection = Connection::open(path).unwrap();
    for (table, column) in [
        ("events", "event_day"),
        ("evidence_ingest_queue", "step_id"),
    ] {
        let count: i64 = connection
            .query_row(
                &format!(
                    "SELECT COUNT(*) FROM pragma_table_info('{table}') WHERE name = '{column}'"
                ),
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 1);
    }
}

#[test]
fn bundle_is_one_sqlite_file_and_replay_is_read_only() {
    let temp = TestDir::new();
    let store = SqliteEvidenceStore::open(temp.path().join("evidence.db")).unwrap();
    store.enqueue(&event("event-1", "run-1", 1)).unwrap();
    store.enqueue(&event("event-2", "run-1", 2)).unwrap();
    let mut failure = event("event-3", "run-1", 2);
    failure.step_id = Some("step-event-2".to_string());
    failure.event_type = "failure.attributed".to_string();
    store.enqueue(&failure).unwrap();
    store.project_batch(10).unwrap();

    let bundle = temp.path().join("run-1.agentledger.db");
    let receipt = store.export_bundle("run-1", &bundle).unwrap();
    assert_eq!(receipt.event_count, 3);
    assert!(bundle.is_file());
    assert!(!bundle.with_extension("db-wal").exists());
    assert!(!bundle.with_extension("db-shm").exists());

    let before = fs::read(&bundle).unwrap();
    let replay = SqliteEvidenceStore::replay_bundle(&bundle).unwrap();
    assert_eq!(replay.run_id, "run-1");
    assert_eq!(replay.event_count, 3);
    assert_eq!(replay.event_hash, receipt.event_hash);
    assert_eq!(replay.timeline.len(), 3);
    assert_eq!(replay.failure_attributions.len(), 1);
    assert_eq!(fs::read(&bundle).unwrap(), before);

    let output = Command::new(env!("CARGO_BIN_EXE_agentledger-runtime"))
        .args(["replay", bundle.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let cli: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(cli["schema_version"], "agentledger.sqlite.replay.v1");
    assert_eq!(cli["run_id"], "run-1");
    assert_eq!(cli["timeline"].as_array().unwrap().len(), 3);
    assert_eq!(cli["failure_attributions"].as_array().unwrap().len(), 1);

    let mut connection = Connection::open(&bundle).unwrap();
    connection
        .execute(
            "UPDATE events SET session_id = 'tampered' WHERE event_id = 'event-1'",
            [],
        )
        .unwrap();
    drop(connection);
    assert!(SqliteEvidenceStore::replay_bundle(&bundle).is_err());
    connection = Connection::open(&bundle).unwrap();
    connection
        .execute(
            "UPDATE events SET session_id = 'session-1' WHERE event_id = 'event-1'",
            [],
        )
        .unwrap();
    connection
        .execute(
            "UPDATE steps SET status = 'tampered' WHERE step_id = 'step-event-1'",
            [],
        )
        .unwrap();
    drop(connection);
    assert!(SqliteEvidenceStore::replay_bundle(&bundle).is_err());
    connection = Connection::open(&bundle).unwrap();
    connection
        .execute(
            "UPDATE steps SET status = 'completed' WHERE step_id = 'step-event-1'",
            [],
        )
        .unwrap();
    connection
        .execute(
            "UPDATE events SET timestamp = timestamp + 1 WHERE event_id = 'event-1'",
            [],
        )
        .unwrap();
    drop(connection);
    assert!(SqliteEvidenceStore::replay_bundle(&bundle).is_err());
    connection = Connection::open(&bundle).unwrap();
    connection
        .execute(
            "UPDATE events SET timestamp = timestamp - 1 WHERE event_id = 'event-1'",
            [],
        )
        .unwrap();
    connection
        .execute(
            "UPDATE events SET payload_ref = '{\"outcome\":\"tampered\"}' WHERE event_id = 'event-1'",
            [],
        )
        .unwrap();
    drop(connection);
    assert!(SqliteEvidenceStore::replay_bundle(&bundle).is_err());
}

#[test]
fn retention_keeps_seven_active_event_days() {
    let temp = TestDir::new();
    let store = SqliteEvidenceStore::open(temp.path().join("evidence.db")).unwrap();
    for (index, day) in (1..=9).enumerate() {
        store
            .enqueue(&event(&format!("event-{index}"), "run-1", day))
            .unwrap();
    }
    let mut cross_start = event("cross-start", "run-1", 1);
    cross_start.step_id = Some("step-cross".to_string());
    cross_start.event_type = "turn.started".to_string();
    let mut cross_end = event("cross-end", "run-1", 3);
    cross_end.step_id = Some("step-cross".to_string());
    let mut open = event("open-start", "run-1", 1);
    open.step_id = Some("step-open".to_string());
    open.event_type = "turn.started".to_string();
    let mut open_attempt = event("open-attempt", "run-1", 2);
    open_attempt.step_id = Some("step-open".to_string());
    open_attempt.event_type = "attempt.completed".to_string();
    store.enqueue(&cross_start).unwrap();
    store.enqueue(&cross_end).unwrap();
    store.enqueue(&open).unwrap();
    store.enqueue(&open_attempt).unwrap();
    store.enqueue(&event("run-2-old", "run-2", 1)).unwrap();
    store.enqueue(&event("run-2-new", "run-2", 9)).unwrap();
    store.project_batch(20).unwrap();

    assert_eq!(store.prune_to_active_event_days(7).unwrap(), 3);
    let retained = store.events("run-1").unwrap();
    assert_eq!(retained.len(), 11);
    assert!(retained.iter().any(|item| item.event_id == "cross-start"));
    assert!(retained.iter().any(|item| item.event_id == "cross-end"));
    assert!(retained.iter().any(|item| item.event_id == "open-start"));
    assert!(retained.iter().any(|item| item.event_id == "open-attempt"));
    assert_eq!(store.events("run-2").unwrap().len(), 1);
    assert_eq!(store.prune_to_active_event_days(7).unwrap(), 0);

    let bundle = temp.path().join("retained.agentledger.db");
    let receipt = store.export_bundle("run-1", &bundle).unwrap();
    assert_eq!(receipt.retention_cutoff_event_day, Some(3));
    assert_eq!(receipt.removed_turn_count, 2);
    let replay = SqliteEvidenceStore::replay_bundle(bundle).unwrap();
    assert_eq!(replay.retention_cutoff_event_day, Some(3));
    assert_eq!(replay.removed_turn_count, 2);

    let bundle = temp.path().join("retained-run-2.agentledger.db");
    let receipt = store.export_bundle("run-2", &bundle).unwrap();
    assert_eq!(receipt.removed_turn_count, 1);
}

#[test]
fn malformed_events_and_corrupt_bundles_fail_closed() {
    let temp = TestDir::new();
    let store = SqliteEvidenceStore::open(temp.path().join("evidence.db")).unwrap();
    let mut invalid = event("", "run-1", 1);
    assert!(store.enqueue(&invalid).is_err());
    invalid.event_id = "event-1".to_string();
    invalid.occurred_at_ms = -1;
    assert!(store.enqueue(&invalid).is_err());

    let corrupt = temp.path().join("corrupt.db");
    fs::write(&corrupt, b"not sqlite").unwrap();
    assert!(SqliteEvidenceStore::replay_bundle(&corrupt).is_err());
}

#[test]
fn duplicate_event_id_rejects_conflicting_content() {
    let temp = TestDir::new();
    let store = SqliteEvidenceStore::open(temp.path().join("evidence.db")).unwrap();
    let original = event("event-1", "run-1", 1);
    assert!(store.enqueue(&original).unwrap());
    assert!(!store.enqueue(&original).unwrap());

    let mut conflict = original.clone();
    conflict.event_type = "turn.failed".to_string();
    assert!(store.enqueue(&conflict).is_err());

    store.project_batch(10).unwrap();
    assert!(!store.enqueue(&original).unwrap());
    conflict.event_type = "turn.completed".to_string();
    conflict
        .payload
        .insert("changed".to_string(), Value::Bool(true));
    assert!(store.enqueue(&conflict).is_err());
}

#[test]
fn terminal_run_status_is_not_reopened_by_later_evidence() {
    let temp = TestDir::new();
    let path = temp.path().join("evidence.db");
    let store = SqliteEvidenceStore::open(&path).unwrap();
    let mut deleted = event("event-1", "run-1", 1);
    deleted.event_type = "session.deleted".to_string();
    store.enqueue(&deleted).unwrap();
    store.enqueue(&event("event-2", "run-1", 2)).unwrap();
    store.project_batch(10).unwrap();

    let connection = Connection::open(path).unwrap();
    let status: String = connection
        .query_row(
            "SELECT status FROM runs WHERE run_id = 'run-1'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(status, "deleted");
}

#[test]
fn run_id_cannot_cross_sessions() {
    let temp = TestDir::new();
    let store = SqliteEvidenceStore::open(temp.path().join("evidence.db")).unwrap();
    store.enqueue(&event("event-1", "run-1", 1)).unwrap();
    let mut conflict = event("event-2", "run-1", 1);
    conflict.session_id = "session-2".to_string();
    assert!(store.enqueue(&conflict).is_err());
    store.enqueue(&event("event-3", "run-1", 1)).unwrap();
    let receipt = store.project_batch(10).unwrap();
    assert_eq!(receipt.projected, 2);
    assert_eq!(receipt.dropped_invalid, 0);
}

#[test]
fn corrupt_queue_row_does_not_block_later_evidence() {
    let temp = TestDir::new();
    let path = temp.path().join("evidence.db");
    let store = SqliteEvidenceStore::open(&path).unwrap();
    let mut started = event("event-1", "run-1", 1);
    started.event_type = "turn.started".to_string();
    store.enqueue(&started).unwrap();
    store.project_batch(10).unwrap();
    let connection = Connection::open(&path).unwrap();
    connection
        .execute_batch(
            "INSERT INTO evidence_ingest_queue
             (event_id, run_id, session_id, step_id, event_type, occurred_at_ms, event_day, payload_json)
             VALUES ('poison', 'run-1', 'session-2', 'poison-step', 'turn.completed', 2, 0, '{}');
             INSERT INTO evidence_ingest_queue
             (event_id, run_id, session_id, step_id, event_type, occurred_at_ms, event_day, payload_json)
             VALUES ('bad-json', 'run-1', 'session-1', 'step-event-1', 'turn.completed', 3, 0, '{');
             INSERT INTO evidence_ingest_queue
             (event_id, run_id, session_id, step_id, event_type, occurred_at_ms, event_day, payload_json)
             VALUES ('bad-day', 'run-1', 'session-1', 'step-event-1', 'turn.completed', 86400001, 0, '{}');
             INSERT INTO evidence_ingest_queue
             (event_id, run_id, session_id, step_id, event_type, occurred_at_ms, event_day, payload_json)
             VALUES ('event-1', 'run-1', 'session-1', 'step-event-1', 'turn.completed', 4, 0, '{}');",
        )
        .unwrap();
    drop(connection);
    let mut attempt = event("event-2", "run-1", 1);
    attempt.step_id = Some("step-event-1".to_string());
    attempt.event_type = "attempt.completed".to_string();
    store.enqueue(&attempt).unwrap();

    let receipt = store.project_batch(10).unwrap();
    assert_eq!(receipt.projected, 1);
    assert_eq!(receipt.acked, 5);
    assert_eq!(receipt.dropped_invalid, 4);
    assert_eq!(store.pending_count().unwrap(), 0);
    assert_eq!(store.events("run-1").unwrap().len(), 2);
    let connection = Connection::open(path).unwrap();
    let status: String = connection
        .query_row(
            "SELECT status FROM steps WHERE step_id = 'step-event-1'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(status, "running");
}
