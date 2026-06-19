# 查询示例

AgentLedger 存储的是 runtime metadata、状态变更、Tool Ledger、events、approvals、artifacts、costs 和 evidence refs。业务系统可能有几百张业务表，但 AgentLedger 不应该直接扫描这些业务表。推荐用稳定关联 ID 串起来：

- `run_id`：AgentLedger runtime run id。
- `session_id`：长会话或长期任务中的逻辑 session id。
- `step_id`：runtime 管理的 step id。
- `correlation_id`：业务 ID，例如订单、案件、workflow、request 或 task id。
- `artifact_id` / `blob_ref`：大对象、证据包和 artifact 的不可变引用。

推荐模式：

```text
业务表
  -> 保留自己的领域 schema 和索引
  -> 只存 agentledger_run_id 或 correlation_id

AgentLedger 表
  -> 存 runtime facts、events、Tool Ledger、approvals、artifacts、costs 和 evidence refs
  -> 不复制大业务行
```

## 单表查询

查询一个 run 的当前 durable state：

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

查询最近失败的 runs：

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

查看某个 run 的 Tool Ledger：

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

查看某个 run 的 runtime events：

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

查询 artifact 引用，不直接加载大 payload：

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

## 多表查询

把 events、tool calls 和 artifacts 合成一条 run timeline：

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

关联 run 和 cost attribution：

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

查询等待人工审批的 runs：

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

业务表关联 AgentLedger：

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

如果业务库有很多表，不要把所有表都 join 到 AgentLedger。更稳的做法是维护一张窄投影表：

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

然后通过投影表查询：

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

## 几百张业务表的场景

如果应用有几百张业务表，要把 AgentLedger 当成 runtime ledger，而不是业务数仓：

- 只有直接启动、拥有或汇总 agent run 的少数业务表需要存 `agentledger_run_id`。
- 其它业务对象通过 `agent_run_links` 这种投影表关联。
- 大型领域 payload 放在应用存储或 BlobStore artifact 中，AgentLedger 只记录 `blob_ref`、hash 和 metadata。
- 业务搜索留在业务库，runtime 搜索留在 AgentLedger。
- 跨系统分析优先导出 evidence bundle，不要对几百张表做大范围 ad hoc join。

推荐索引：

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

如果 Postgres 部署里经常查 JSON metadata，建议加业务定制的 expression index，不要给每个 JSON 字段都加通用索引：

```sql
CREATE INDEX agentledger_artifacts_kind_idx
  ON agentledger.artifacts ((metadata_json->>'kind'));
```

## 安全说明

- conformance 和查询实验不要指向生产业务库。
- dashboard、notebook、临时分析优先使用只读数据库账号。
- runtime-facing tool 不提供 destructive reset/drop helper。
- retention 必须通过 replay-aware retention plan；不要删除 evidence bundle 仍需要的 blob refs 或 events。

---

generated by codex cli
