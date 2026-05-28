# agentledger-postgres

Postgres StateStore adapter package for AgentLedger.

```bash
pip install agentledger-postgres
pip install "agentledger-runtime[postgres]"
```

```python
from agentledger_postgres import PostgresStore, PostgresStoreConfig

store = PostgresStore(PostgresStoreConfig.from_env())
store.init()
```

This package keeps the runtime core dependency-light while making Postgres an explicit opt-in. It re-exports the stable adapter classes from `agentledger.storage_postgres` in the `1.2.x` line.

Certification:

```bash
python3 -m agentledger adapter certify --kind postgres --adapter-version 1.2.2
```

