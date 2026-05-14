# Side-effect Idempotency Demo

This demo proves the first AgentLedger invariant:

```text
If a worker crashes after an external side effect but before state commit,
retry must not duplicate the external side effect.
```

Run it from the repository root:

```bash
PYTHONPATH=src python3 -m agentledger run examples/side_effect_idempotency
```

Then inspect the run:

```bash
PYTHONPATH=src python3 -m agentledger debug <run_id>
PYTHONPATH=src python3 -m agentledger ledger <run_id>
PYTHONPATH=src python3 -m agentledger replay <run_id>
```
