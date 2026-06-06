# Inspector Example

This example shows how to build a read-only internal viewer on top of AgentLedger Inspector.

It creates a temporary local runtime, runs one tool-using agent, then reads the run through:

- SQLite runtime metadata
- an exported evidence bundle
- the stable `agentledger.inspector.v1` read model for custom UI/API code

Run from the repository root:

```bash
PYTHONPATH=src python3 examples/inspector/custom_viewer.py
```

The script writes a JSON report and a static HTML report under a temporary directory and prints their paths.

## Production Notes

- Use read-only database credentials for Postgres/MySQL Inspector connections.
- Keep authentication, authorization, and network exposure outside AgentLedger Inspector.
- Build custom pages or API endpoints from `InspectorReport.to_dict()`, not undocumented SQL tables.
- Keep custom viewers read-only. Approve, deny, cancel, and recover actions should use runtime APIs, not Inspector data sources.

