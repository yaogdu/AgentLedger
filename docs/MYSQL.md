# MySQL Adapter

AgentLedger `1.2.2` adds MySQL as an official optional StateStore adapter boundary.

This is not a runtime-core dependency. Install it only when the application wants MySQL-backed durable state:

```bash
pip install "agentledger-runtime[mysql]"
# or
pip install agentledger-mysql
```

## Configuration

```bash
export AGENTLEDGER_MYSQL_DSN="mysql://agentledger:password@127.0.0.1:3306/agentledger"
python3 -m agentledger migrate status --dialect mysql
python3 -m agentledger migrate up --dialect mysql
```

When the DSN does not include a database name, set:

```bash
export AGENTLEDGER_MYSQL_DATABASE="agentledger"
```

Python code:

```python
from agentledger_mysql import MySQLStore, MySQLStoreConfig

store = MySQLStore(MySQLStoreConfig.from_env())
store.init()
```

## Scope

The adapter provides DDL, migration metadata, CLI migration/status wiring, Python `pymysql` connectivity, and injected-client adapter contracts for Go, TypeScript, and Rust.

Production readiness still requires external validation: real MySQL service tests, least-privilege credentials, concurrency/load checks, backup/restore drills, schema rollout procedures, and operational monitoring.
