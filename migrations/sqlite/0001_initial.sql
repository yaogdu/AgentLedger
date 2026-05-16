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
