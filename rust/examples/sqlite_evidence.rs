use std::error::Error;
use std::path::PathBuf;

use agentledger::{EvidenceEventInput, SqliteEvidenceStore, State, Value};

fn main() -> Result<(), Box<dyn Error>> {
    let root = std::env::args()
        .nth(1)
        .map(PathBuf::from)
        .ok_or("usage: sqlite_evidence <output-directory>")?;
    let store = SqliteEvidenceStore::open(root.join("state.db"))?;
    for (index, event_type) in ["session.started", "turn.completed"]
        .into_iter()
        .enumerate()
    {
        let mut payload = State::new();
        payload.insert(
            "outcome".to_string(),
            Value::String("completed".to_string()),
        );
        store.enqueue(&EvidenceEventInput {
            event_id: format!("interop-event-{index}"),
            run_id: "interop-run".to_string(),
            session_id: "interop-session".to_string(),
            step_id: Some("interop-turn".to_string()),
            event_type: event_type.to_string(),
            occurred_at_ms: 1_700_000_000_000 + index as i64,
            payload,
        })?;
    }
    store.project_batch(100)?;
    let bundle = root.join("interop.agentledger.db");
    let receipt = store.export_bundle("interop-run", &bundle)?;
    let replay = SqliteEvidenceStore::replay_bundle(&bundle)?;
    assert_eq!(receipt.event_hash, replay.event_hash);
    println!("{}", bundle.display());
    Ok(())
}
