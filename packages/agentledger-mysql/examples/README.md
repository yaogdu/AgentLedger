# agentledger-mysql examples

Set a MySQL DSN and run migration/status commands:

```bash
export AGENTLEDGER_MYSQL_DSN="mysql://agentledger:agentledger@127.0.0.1:3306/agentledger"
python3 -m agentledger migrate status --dialect mysql
python3 -m agentledger migrate up --dialect mysql
```

Use `AGENTLEDGER_MYSQL_DATABASE` or `--database` when the DSN does not include a database name.
