// Package mysql exposes the AgentLedger MySQL adapter boundary for Go.
package mysql

import runtime "github.com/yaogdu/AgentLedger/go"

type Adapter = runtime.MySQLAdapter
type DatabaseSQLExecutor = runtime.DatabaseSQLExecutor
type Migration = runtime.Migration
type SQLExecutor = runtime.SQLExecutor
type SQLTxExecutor = runtime.SQLTxExecutor

func New(database string, client SQLExecutor) Adapter {
	return runtime.NewMySQLAdapter(database, client)
}

func MigrationPlan() ([]Migration, error) {
	return runtime.MigrationsFor("mysql")
}
