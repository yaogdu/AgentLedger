package agentledger

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
)

type Migration struct {
	Version string `json:"version"`
	Name    string `json:"name"`
	Dialect string `json:"dialect"`
	SQL     string `json:"sql"`
}

func (m Migration) Checksum() string {
	sum := sha256.Sum256([]byte(m.SQL))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func MigrationsFor(dialect string) ([]Migration, error) {
	normalized := strings.ToLower(dialect)
	if normalized == "sqlite" {
		return []Migration{{Version: "0001", Name: "initial_runtime_metadata", Dialect: "sqlite", SQL: sqliteInitialDDL}}, nil
	}
	if normalized == "postgres" || normalized == "postgresql" {
		return []Migration{{Version: "0001", Name: "initial_runtime_metadata", Dialect: "postgres", SQL: postgresInitialDDL}}, nil
	}
	return nil, fmt.Errorf("unsupported storage dialect: %s", dialect)
}

func LatestSchemaVersion(dialect string) (string, error) {
	migrations, err := MigrationsFor(dialect)
	if err != nil || len(migrations) == 0 {
		return "", err
	}
	return migrations[len(migrations)-1].Version, nil
}

func DDLFor(dialect string) (string, error) {
	normalized := strings.ToLower(dialect)
	migrations, err := MigrationsFor(dialect)
	if err != nil {
		return "", err
	}
	header := schemaMigrationsSQLite
	if normalized == "postgres" || normalized == "postgresql" {
		header = schemaMigrationsPostgres
	}
	parts := []string{header}
	for _, migration := range migrations {
		parts = append(parts, migration.SQL)
	}
	return strings.Join(parts, "\n\n"), nil
}

const schemaMigrationsSQLite = `CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at REAL NOT NULL
);`

const schemaMigrationsPostgres = `CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at DOUBLE PRECISION NOT NULL
);`

const sqliteInitialDDL = `CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL, state_json TEXT NOT NULL, state_version INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS steps (step_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT NOT NULL, status TEXT NOT NULL, owner TEXT, lease_token TEXT, lease_until REAL, attempt INTEGER NOT NULL, state_version INTEGER NOT NULL, checkpoint_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT, seq INTEGER NOT NULL, type TEXT NOT NULL, timestamp REAL NOT NULL, agent_role TEXT, state_version INTEGER, causal_token TEXT, payload_hash TEXT, payload_ref TEXT);
CREATE TABLE IF NOT EXISTS tool_ledger (ledger_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT NOT NULL, tool_name TEXT NOT NULL, tool_version TEXT NOT NULL, tool_call_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, causal_token TEXT NOT NULL, request_hash TEXT NOT NULL, request_ref TEXT NOT NULL, status TEXT NOT NULL, external_id TEXT, response_hash TEXT, response_ref TEXT, error_type TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts (artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step_id TEXT, name TEXT, blob_hash TEXT NOT NULL, blob_ref TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at REAL NOT NULL);`

const postgresInitialDDL = `CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL, state_json JSONB NOT NULL, state_version BIGINT NOT NULL, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS steps (step_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id), session_id TEXT NOT NULL, status TEXT NOT NULL, owner TEXT, lease_token TEXT, lease_until DOUBLE PRECISION, attempt BIGINT NOT NULL, state_version BIGINT NOT NULL, checkpoint_id TEXT, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT, seq BIGINT NOT NULL, type TEXT NOT NULL, timestamp DOUBLE PRECISION NOT NULL, agent_role TEXT, state_version BIGINT, causal_token TEXT, payload_hash TEXT, payload_ref TEXT, UNIQUE(run_id, seq));
CREATE TABLE IF NOT EXISTS tool_ledger (ledger_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT NOT NULL, tool_name TEXT NOT NULL, tool_version TEXT NOT NULL, tool_call_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, causal_token TEXT NOT NULL, request_hash TEXT NOT NULL, request_ref TEXT NOT NULL, status TEXT NOT NULL, external_id TEXT, response_hash TEXT, response_ref TEXT, error_type TEXT, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts (artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step_id TEXT, name TEXT, blob_hash TEXT NOT NULL, blob_ref TEXT NOT NULL, metadata_json JSONB NOT NULL, created_at DOUBLE PRECISION NOT NULL);`
