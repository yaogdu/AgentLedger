# Query Examples

AgentLedger stores runtime metadata, state transitions, Tool Ledger rows, events, approvals, artifacts, costs, and evidence references. Application databases can contain hundreds of business tables, but AgentLedger should not scan those tables directly. Use stable correlation IDs instead:

- `run_id`: the AgentLedger runtime run id.
- `session_id`: the logical session id when a run belongs to a longer conversation or task.
- `step_id`: the runtime-managed step id.
- `correlation_id`: an application id such as order id, case id, workflow id, request id, or task id.
- `artifact_id` / `blob_ref`: immutable payload references for large objects.

The recommended pattern is:

```text
application tables
  -> keep their own domain schema and indexes
  -> store agentledger_run_id or correlation_id

AgentLedger tables
  -> keep runtime facts, events, Tool Ledger, approvals, artifacts, costs, and evidence refs
  -> do not duplicate large business rows
```

## Single-Table Queries

Find one run and its current durable state:

```sql
SELECT
  run_id,
  session_id,
  status,
  state_version,
  state_json,
  created_at,
  updated_at
FROM agentledger.runs
WHERE run_id = $1;
```

List recent failed runs:

```sql
SELECT
  run_id,
  session_id,
  status,
  state_version,
  updated_at
FROM agentledger.runs
WHERE status IN ('failed', 'cancelled')
ORDER BY updated_at DESC
LIMIT 50;
```

Inspect Tool Ledger rows for one run:

```sql
SELECT
  tool_name,
  status,
  idempotency_key,
  request_hash,
  response_hash,
  error_json,
  created_at,
  updated_at
FROM agentledger.tool_ledger
WHERE run_id = $1
ORDER BY created_at ASC;
```

Inspect runtime events for one run:

```sql
SELECT
  event_id,
  event_type,
  step_id,
  payload_json,
  created_at
FROM agentledger.events
WHERE run_id = $1
ORDER BY event_id ASC;
```

Find artifacts without loading large payloads:

```sql
SELECT
  artifact_id,
  run_id,
  step_id,
  name,
  blob_hash,
  blob_ref,
  metadata_json,
  created_at
FROM agentledger.artifacts
WHERE run_id = $1
ORDER BY created_at ASC;
```

## Multi-Table Queries

Build a run timeline from events, tool calls, and artifacts:

```sql
SELECT
  'event' AS item_type,
  e.created_at,
  e.step_id,
  e.event_type AS name,
  e.payload_json AS payload
FROM agentledger.events e
WHERE e.run_id = $1

UNION ALL

SELECT
  'tool' AS item_type,
  t.created_at,
  t.step_id,
  t.tool_name AS name,
  jsonb_build_object(
    'status', t.status,
    'idempotency_key', t.idempotency_key,
    'request_hash', t.request_hash,
    'response_hash', t.response_hash,
    'error', t.error_json
  ) AS payload
FROM agentledger.tool_ledger t
WHERE t.run_id = $1

UNION ALL

SELECT
  'artifact' AS item_type,
  a.created_at,
  a.step_id,
  a.name,
  jsonb_build_object(
    'artifact_id', a.artifact_id,
    'blob_ref', a.blob_ref,
    'metadata', a.metadata_json
  ) AS payload
FROM agentledger.artifacts a
WHERE a.run_id = $1

ORDER BY created_at ASC;
```

Join run metadata with cost attribution:

```sql
SELECT
  r.run_id,
  r.session_id,
  r.status,
  c.category,
  c.name,
  COUNT(*) AS records,
  SUM(c.amount) AS total_amount
FROM agentledger.runs r
JOIN agentledger.cost_records c ON c.run_id = r.run_id
WHERE r.run_id = $1
GROUP BY r.run_id, r.session_id, r.status, c.category, c.name
ORDER BY c.category, c.name;
```

Find runs blocked by pending approvals:

```sql
SELECT
  r.run_id,
  r.session_id,
  r.status AS run_status,
  a.approval_id,
  a.tool_name,
  a.risk_level,
  a.reason,
  a.created_at
FROM agentledger.approvals a
JOIN agentledger.runs r ON r.run_id = a.run_id
WHERE a.status = 'pending'
ORDER BY a.created_at ASC;
```

Connect an application table to AgentLedger:

```sql
SELECT
  cases.case_id,
  cases.status AS case_status,
  cases.owner_id,
  r.run_id,
  r.status AS runtime_status,
  r.state_version,
  r.updated_at
FROM legal_cases cases
JOIN agentledger.runs r
  ON r.run_id = cases.agentledger_run_id
WHERE cases.case_id = $1;
```

When the application has many tables, do not join all of them to AgentLedger. Create a narrow projection table:

```sql
CREATE TABLE agent_run_links (
  domain_type text NOT NULL,
  domain_id text NOT NULL,
  agentledger_run_id text NOT NULL,
  correlation_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (domain_type, domain_id)
);

CREATE INDEX agent_run_links_run_idx
  ON agent_run_links(agentledger_run_id);
```

Then query through the projection:

```sql
SELECT
  l.domain_type,
  l.domain_id,
  l.correlation_id,
  r.status,
  r.state_version,
  r.updated_at
FROM agent_run_links l
JOIN agentledger.runs r ON r.run_id = l.agentledger_run_id
WHERE l.domain_type = $1
  AND l.domain_id = $2;
```

## Hundreds Of Business Tables

For applications with hundreds of tables, treat AgentLedger as the runtime ledger, not the business warehouse:

- Put `agentledger_run_id` on the small number of tables that directly start, own, or summarize an agent run.
- For everything else, use a projection table such as `agent_run_links`.
- Store large domain payloads in application storage or BlobStore artifacts, then record `blob_ref`, hashes, and metadata in AgentLedger.
- Keep business search in the application database. Keep runtime search in AgentLedger.
- Export evidence bundles for cross-system analysis instead of issuing large ad hoc joins across every table.

Recommended indexes:

```sql
CREATE INDEX agentledger_events_run_created_idx
  ON agentledger.events(run_id, created_at);

CREATE INDEX agentledger_tool_ledger_run_created_idx
  ON agentledger.tool_ledger(run_id, created_at);

CREATE INDEX agentledger_artifacts_run_created_idx
  ON agentledger.artifacts(run_id, created_at);

CREATE INDEX agentledger_cost_records_run_category_idx
  ON agentledger.cost_records(run_id, category, name);
```

For Postgres deployments that query JSON metadata heavily, add application-specific expression indexes instead of generic indexes on every JSON field:

```sql
CREATE INDEX agentledger_artifacts_kind_idx
  ON agentledger.artifacts ((metadata_json->>'kind'));
```

## Safety Notes

- Run conformance and query experiments against test databases, not production data.
- Prefer read-only database credentials for dashboards, notebooks, and ad hoc analysis.
- Do not add destructive reset/drop helpers to runtime-facing tools.
- Apply retention only through a replay-aware retention plan; never delete blob refs or events that are still needed by evidence bundles.
