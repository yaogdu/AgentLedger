#!/usr/bin/env python3
"""Validate service-backed AgentLedger adapters against local Docker services."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from local_validation_common import CommandResult, prepend_path, read_version, redact_command, redact_dsn, run_check as run_command_check  # noqa: E402

DEFAULT_COMPOSE_FILE = ROOT / "examples" / "adapter_validation" / "docker-compose.yml"


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    compose = shlex.split(os.environ.get("AGENTLEDGER_DOCKER_COMPOSE", "docker compose"))
    compose_file = args.compose_file.resolve()
    project = args.compose_project
    python_bin = args.python
    started = False
    results: list[CommandResult] = []

    env = build_env(args, output_dir)
    try:
        results.append(run_check("python_adapter_dependencies", [python_bin, "-c", "import psycopg, boto3"], output_dir, env=env))
        if results[-1].status != "passed":
            return write_outputs(args, output_dir, env, results, cleanup=None)

        results.append(run_check("docker_compose_config", compose + ["-f", str(compose_file), "config", "--quiet"], output_dir))
        if results[-1].status != "passed":
            return write_outputs(args, output_dir, env, results, cleanup=None)

        up = run_check(
            "docker_compose_up",
            compose + ["-f", str(compose_file), "-p", project, "up", "-d", "postgres", "minio"],
            output_dir,
            timeout=args.command_timeout,
        )
        results.append(up)
        if up.status != "passed":
            return write_outputs(args, output_dir, env, results, cleanup=None)
        started = True

        results.append(wait_for_postgres(compose, compose_file, project, output_dir, args.command_timeout))
        if results[-1].status != "passed":
            return write_outputs(args, output_dir, env, results, cleanup_services(compose, compose_file, project, output_dir, args) if started else None)

        results.append(
            run_check(
                "minio_bucket_setup",
                compose + ["-f", str(compose_file), "-p", project, "run", "--rm", "minio-setup"],
                output_dir,
                env=env,
                timeout=args.command_timeout,
            )
        )
        if results[-1].status != "passed":
            return write_outputs(args, output_dir, env, results, cleanup_services(compose, compose_file, project, output_dir, args) if started else None)

        results.extend(run_adapter_checks(args, output_dir, env))
        cleanup = cleanup_services(compose, compose_file, project, output_dir, args)
        return write_outputs(args, output_dir, env, results, cleanup)
    except KeyboardInterrupt:
        cleanup = cleanup_services(compose, compose_file, project, output_dir, args) if started else None
        results.append(CommandResult("interrupted", [], 130, 0.0))
        write_outputs(args, output_dir, env, results, cleanup)
        return 130


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local real-service validation for Postgres and MinIO adapters.")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/agentledger-adapter-validation"))
    parser.add_argument("--compose-file", type=Path, default=DEFAULT_COMPOSE_FILE)
    parser.add_argument("--compose-project", default=os.environ.get("AGENTLEDGER_ADAPTER_COMPOSE_PROJECT", "agentledger-adapter-validation"))
    parser.add_argument("--python", default=os.environ.get("PYTHON", sys.executable))
    parser.add_argument("--command-timeout", type=int, default=180)
    parser.add_argument("--keep-services", action="store_true", help="Leave Docker services running after validation.")
    parser.add_argument("--postgres-dsn", default=os.environ.get("AGENTLEDGER_POSTGRES_DSN", "postgresql://agentledger:agentledger@127.0.0.1:15432/agentledger"))
    parser.add_argument("--postgres-schema", default=os.environ.get("AGENTLEDGER_POSTGRES_SCHEMA", "agentledger"))
    parser.add_argument("--s3-bucket", default=os.environ.get("AGENTLEDGER_S3_BUCKET", "agentledger-runs"))
    parser.add_argument("--s3-prefix", default=os.environ.get("AGENTLEDGER_S3_PREFIX", "agentledger/validation"))
    parser.add_argument("--s3-endpoint-url", default=os.environ.get("AGENTLEDGER_S3_ENDPOINT_URL", "http://127.0.0.1:19000"))
    parser.add_argument("--s3-region", default=os.environ.get("AGENTLEDGER_S3_REGION", "us-east-1"))
    return parser.parse_args()


def build_env(args: argparse.Namespace, output_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = prepend_path(str(ROOT / "src"), env.get("PYTHONPATH"))
    env["AGENTLEDGER_RUN_POSTGRES_INTEGRATION"] = "1"
    env["AGENTLEDGER_POSTGRES_DSN"] = args.postgres_dsn
    env["AGENTLEDGER_POSTGRES_SCHEMA"] = args.postgres_schema
    env["AGENTLEDGER_RUN_S3_INTEGRATION"] = "1"
    env["AGENTLEDGER_S3_BUCKET"] = args.s3_bucket
    env["AGENTLEDGER_S3_PREFIX"] = f"{args.s3_prefix.rstrip('/')}/{int(time.time())}"
    env["AGENTLEDGER_S3_ENDPOINT_URL"] = args.s3_endpoint_url
    env["AGENTLEDGER_S3_REGION"] = args.s3_region
    env.setdefault("AWS_ACCESS_KEY_ID", os.environ.get("AGENTLEDGER_MINIO_ROOT_USER", "minioadmin"))
    env.setdefault("AWS_SECRET_ACCESS_KEY", os.environ.get("AGENTLEDGER_MINIO_ROOT_PASSWORD", "minioadmin"))
    env["AGENTLEDGER_ADAPTER_VALIDATION_DIR"] = str(output_dir)
    return env


def run_adapter_checks(args: argparse.Namespace, output_dir: Path, env: dict[str, str]) -> list[CommandResult]:
    python = args.python
    commands = [
        (
            "postgres_state_conformance",
            [
                python,
                "-m",
                "agentledger",
                "state",
                "conformance",
                "--backend",
                "postgres",
                "--dsn",
                args.postgres_dsn,
                "--schema",
                args.postgres_schema,
            ],
        ),
        (
            "postgres_worker_concurrency",
            [
                python,
                "-m",
                "agentledger",
                "worker",
                "conformance",
                "--backend",
                "postgres",
                "--dsn",
                args.postgres_dsn,
                "--schema",
                args.postgres_schema,
                "--concurrent",
            ],
        ),
        (
            "s3_minio_blob_conformance",
            [
                python,
                "-m",
                "agentledger",
                "blob",
                "conformance",
                "--backend",
                "s3",
                "--bucket",
                args.s3_bucket,
                "--prefix",
                env["AGENTLEDGER_S3_PREFIX"],
                "--endpoint-url",
                args.s3_endpoint_url,
                "--region",
                args.s3_region,
            ],
        ),
    ]
    return [run_check(name, command, output_dir, env=env, timeout=args.command_timeout, parse_json=True) for name, command in commands]


def wait_for_postgres(compose: list[str], compose_file: Path, project: str, output_dir: Path, timeout: int) -> CommandResult:
    start = time.monotonic()
    attempts = 0
    command = compose + ["-f", str(compose_file), "-p", project, "exec", "-T", "postgres", "pg_isready", "-U", "agentledger", "-d", "agentledger"]
    last = CommandResult("postgres_ready", command, 1, 0.0)
    while time.monotonic() - start < timeout:
        attempts += 1
        last = run_check("postgres_ready", command, output_dir, timeout=10, output_suffix=f"attempt-{attempts}")
        if last.status == "passed":
            return last
        time.sleep(2)
    return last


def cleanup_services(compose: list[str], compose_file: Path, project: str, output_dir: Path, args: argparse.Namespace) -> CommandResult | None:
    if args.keep_services:
        return None
    return run_check("docker_compose_down", compose + ["-f", str(compose_file), "-p", project, "down", "-v"], output_dir, timeout=args.command_timeout)


def run_check(
    name: str,
    command: list[str],
    output_dir: Path,
    *,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
    parse_json: bool = False,
    output_suffix: str | None = None,
) -> CommandResult:
    return run_command_check(
        name,
        command,
        output_dir,
        cwd=ROOT,
        env=env,
        timeout=timeout,
        parse_json=parse_json,
        output_suffix=output_suffix,
    )


def write_outputs(
    args: argparse.Namespace,
    output_dir: Path,
    env: dict[str, str],
    results: list[CommandResult],
    cleanup: CommandResult | None,
) -> int:
    report = build_report(
        version=read_version(ROOT),
        output_dir=output_dir,
        env=env,
        checks=results,
        cleanup=cleanup,
        keep_services=args.keep_services,
    )
    json_path = output_dir / "adapter-validation.json"
    md_path = output_dir / "adapter-validation.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0 if report["ok"] else 1


def build_report(
    *,
    version: str,
    output_dir: Path,
    env: dict[str, str],
    checks: list[CommandResult],
    cleanup: CommandResult | None,
    keep_services: bool,
) -> dict[str, Any]:
    check_dicts = [check.to_dict() for check in checks]
    if cleanup is not None:
        check_dicts.append(cleanup.to_dict())
    validation_ok = all(check.status == "passed" for check in checks)
    cleanup_status = "skipped" if keep_services else (cleanup.status if cleanup else "not_run")
    cleanup_ok = keep_services or (cleanup is not None and cleanup.status == "passed")
    ok = validation_ok and cleanup_ok
    return {
        "schema": "agentledger.adapter_validation.v1",
        "version": version,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ok": ok,
        "output_dir": str(output_dir),
        "services": {
            "postgres": {
                "dsn": redact_dsn(env["AGENTLEDGER_POSTGRES_DSN"]),
                "schema": env["AGENTLEDGER_POSTGRES_SCHEMA"],
                "checks": ["state_store_conformance", "worker_concurrency"],
            },
            "s3_minio": {
                "bucket": env["AGENTLEDGER_S3_BUCKET"],
                "prefix": env["AGENTLEDGER_S3_PREFIX"],
                "endpoint_url": env["AGENTLEDGER_S3_ENDPOINT_URL"],
                "region": env["AGENTLEDGER_S3_REGION"],
                "checks": ["blob_store_conformance"],
            },
        },
        "checks": check_dicts,
        "remaining_external_required": [
            "docker_daemon_hardening",
            "otel_collector_transport",
            "langfuse_server_ingestion",
            "cloud_s3_iam_kms_lifecycle",
            "postgres_backup_restore_drill",
        ],
        "cleanup": cleanup_status,
        "cleanup_ok": cleanup_ok,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# AgentLedger Adapter Validation {report['version']}",
        "",
        f"- Status: {'passed' if report['ok'] else 'failed'}",
        f"- Generated: {report['generated_at']}",
        f"- Output: `{report['output_dir']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Duration |",
        "| --- | --- | ---: |",
    ]
    for check in report["checks"]:
        lines.append(f"| `{check['name']}` | {check['status']} | {check['duration_seconds']}s |")
    lines.extend(
        [
            "",
            "## Remaining External-required Areas",
            "",
        ]
    )
    for item in report["remaining_external_required"]:
        lines.append(f"- `{item}`")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
