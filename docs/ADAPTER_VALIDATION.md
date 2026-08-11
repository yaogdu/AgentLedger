# Adapter Validation

This page documents the local real-service validation path for official production-pilot adapters. It is stronger than injected-client conformance and weaker than a production hardening claim.

## What It Covers

The local validation stack starts disposable Docker services and runs existing AgentLedger conformance commands against them:

- Postgres StateStore conformance
- Postgres worker concurrency conformance
- S3-compatible BlobStore conformance against MinIO

It does not validate cloud IAM, KMS, lifecycle rules, database backup/restore, Docker daemon hardening, OTLP collectors, Langfuse server ingestion, or production network policy.

## Run

Install the optional client dependencies in your Python environment:

```bash
python3 -m pip install "psycopg[binary]" boto3
```

Then run:

```bash
bash scripts/validate_adapters_local.sh --output-dir /tmp/agentledger-adapter-validation
```

Or run with temporary dependencies and no project virtualenv:

```bash
UV_CACHE_DIR=/tmp/agentledger-uv-cache uv run --no-project --with "psycopg[binary]" --with boto3 --python python3 python scripts/validate_adapters_local.py --output-dir /tmp/agentledger-adapter-validation
```

The script uses:

- `examples/adapter_validation/docker-compose.yml`
- Postgres on `127.0.0.1:15432`
- MinIO S3 API on `127.0.0.1:19000`
- bucket `agentledger-runs`
- a unique S3 prefix for each run

By default it tears services down with `docker compose down -v`. Use `--keep-services` when debugging.

## Output

The script writes:

```text
/tmp/agentledger-adapter-validation/adapter-validation.json
/tmp/agentledger-adapter-validation/adapter-validation.md
```

`adapter-validation.json` uses schema `agentledger.adapter_validation.v1` and includes:

- redacted service configuration
- each check name, command, status, return code, and duration
- parsed conformance JSON where available
- output file paths for stdout and stderr
- remaining `external-required` validation areas

## Interpreting Results

`ok=true` means the local disposable services passed the adapter conformance paths. It is acceptable release evidence for moving Postgres/S3 from "contract only" to "local real-service validated".

It is not enough to claim production hardening. Production claims still require:

- Postgres backup/restore or rollback drill
- expected-concurrency worker tests against the target database
- database role and schema isolation review
- S3/MinIO lifecycle, encryption, and restore checks
- cloud S3 IAM/KMS policy review if using AWS or another cloud
- Docker daemon or sandbox infrastructure hardening if executing untrusted code

## Environment Overrides

You can override defaults with CLI flags or environment variables:

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://agentledger:agentledger@127.0.0.1:15432/agentledger
AGENTLEDGER_POSTGRES_SCHEMA=agentledger
AGENTLEDGER_S3_BUCKET=agentledger-runs
AGENTLEDGER_S3_PREFIX=agentledger/validation
AGENTLEDGER_S3_ENDPOINT_URL=http://127.0.0.1:19000
AGENTLEDGER_S3_REGION=us-east-1
```

Docker images and host ports are controlled by the compose file variables:

```bash
AGENTLEDGER_POSTGRES_IMAGE=postgres:16-alpine
AGENTLEDGER_POSTGRES_PORT=15432
AGENTLEDGER_MINIO_IMAGE=minio/minio:latest
AGENTLEDGER_MINIO_PORT=19000
AGENTLEDGER_MINIO_CONSOLE_PORT=19001
```

Do not point this script at real application data.
