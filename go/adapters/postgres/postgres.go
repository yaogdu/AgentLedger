// Package postgres exposes the AgentLedger Postgres adapter boundary for Go.
package postgres

import runtime "github.com/yaogdu/AgentLedger/go"

type Adapter = runtime.PostgresAdapter
type Migration = runtime.Migration
type SQLExecutor = runtime.SQLExecutor

func New(schema string, client SQLExecutor) Adapter {
	return runtime.NewPostgresAdapter(schema, client)
}

func MigrationPlan() ([]Migration, error) {
	return runtime.MigrationsFor("postgres")
}

