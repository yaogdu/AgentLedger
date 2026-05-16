# Distributed Worker Deployment

AgentLedger workers are stateless execution processes over durable runtime state. Correctness lives in the StateStore:

```text
claim_step -> lease_token -> heartbeat -> commit_state_patch
recover_expired_leases -> fence old lease tokens
cancel_run -> fence running workers and block new claims
```

`WorkerService` is the process-shaped reference loop. Production deployments can run many replicas as long as the backing StateStore passes `WorkerConformanceRunner`.

## Reference Topology

```text
Agent code package
  -> N worker processes / pods
  -> shared StateStore, e.g. Postgres
  -> shared BlobStore, e.g. S3/MinIO
  -> optional sandbox executor
  -> optional observability exporter
```

Workers should not coordinate through local memory. They should coordinate only through store leases, fencing tokens, run/step status, and the Tool Ledger.

## Process Shape

Local process smoke:

```bash
PYTHONPATH=src python3 -m agentledger worker serve examples/transient_retry --max-loops 5
```

Generate a deployment recipe without creating any external resources:

```bash
PYTHONPATH=src python3 -m agentledger worker plan examples/transient_retry --replicas 2
PYTHONPATH=src python3 -m agentledger worker plan examples/transient_retry --backend postgres --replicas 4 --daemon
```

`worker plan` emits process commands, readiness checks, graceful shutdown notes, and lease/fencing reminders. It is intentionally read-only: it does not create queues, pods, services, credentials, or cloud resources.

Important knobs:

```text
--worker-id                stable process identity for logs/traces
--lease-seconds            claim lease duration
--max-idle-polls           stop after repeated idle polls; 0 disables idle stop
--idle-sleep-seconds       backoff between idle polls
--install-signal-handlers  graceful SIGINT/SIGTERM stop for local process mode
```

Production supervisors such as systemd, Kubernetes, Nomad, or ECS should restart failed workers. Runtime recovery is based on lease expiry, not on the supervisor knowing why a worker stopped.

## Postgres Worker Pool

The experimental Postgres adapter uses `FOR UPDATE SKIP LOCKED` for concurrent claims. Before scaling replicas, run:

```bash
PYTHONPATH=src python3 -m agentledger state conformance --backend postgres
PYTHONPATH=src python3 -m agentledger worker conformance --backend postgres --concurrent
```

Operational requirements:

```text
connection pool size >= expected worker concurrency
statement timeout and lock timeout are deployment-defined
lease_seconds > expected normal step duration or heartbeat interval is configured
recover_expired_leases runs in every worker loop or via a separate scheduler
all high-risk side effects are idempotency-keyed through Tool Ledger
```

## Kubernetes Pattern

Recommended initial deployment:

```text
Deployment:
  replicas: N
  command: agentledger worker serve <agent-entrypoint>
  env: StateStore, BlobStore, policy, sandbox config

PreStop:
  allow graceful SIGTERM handling

Readiness:
  check config and store connectivity outside runtime-core

Liveness:
  supervisor-level process health, not run correctness
```

Kubernetes should not be the source of run state. A pod restart must be safe because another worker can recover the expired lease and continue from the durable checkpoint.

## Shutdown and Cancellation

Graceful stop:

```text
worker receives SIGTERM
WorkerService.request_stop marks stop requested
current step finishes or fails according to runtime semantics
process exits after loop summary
```

Run cancellation:

```bash
PYTHONPATH=src python3 -m agentledger cancel <run_id> --reason "operator requested"
```

Cancellation is persisted in the event log and fences old lease tokens. A stale worker commit after cancellation must fail.

## Observability

Every worker should report:

```text
worker_id
run_id
step_id
lease_token hash or redacted token
attempt
stopped_reason
recovered_leases
idle_polls
cost summary
failure classification
```

Local exporters:

```bash
PYTHONPATH=src python3 -m agentledger trace <run_id> --out trace.jsonl
PYTHONPATH=src python3 -m agentledger trace <run_id> --format otlp --out trace.otlp.json
PYTHONPATH=src python3 -m agentledger evidence <run_id> --dir evidence/<run_id>
```

## Failure Drills

Run before a production pilot:

```bash
PYTHONPATH=src python3 -m agentledger failure inject --scenario all
```

Minimum drill coverage:

```text
worker crash after side effect does not duplicate external write
retry exhaustion fails the step/run with events
expired lease recovery fences stale owner
cancelled run fences stale owner and blocks new claims
```

## Non-goals

Runtime core does not create deployments, queues, clusters, connection pools, secrets, or cloud resources. It defines worker semantics and provides a reference loop plus conformance tests. Deployment adapters and operations teams own the actual orchestration environment.
