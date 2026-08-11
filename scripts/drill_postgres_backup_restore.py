#!/usr/bin/env python3
"""Run a local Postgres backup/restore drill for AgentLedger metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from local_validation_common import CommandResult, dsn_database, dsn_user, prepend_path, read_version as read_project_version, redact_dsn, run_check as run_command_check, run_python_step  # noqa: E402

DEFAULT_DOCKER_INFRA_DIR = ROOT.parent / "docker-infra"
LOCAL_COMPOSE_FILE = ROOT / "examples" / "adapter_validation" / "docker-compose.yml"


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = args.suffix or time.strftime("%Y%m%d%H%M%S", time.gmtime())
    source_schema = args.source_schema or f"agentledger_backup_src_{suffix}"
    target_database = args.target_database or f"agentledger_restore_{suffix}"
    validate_identifier(source_schema, "source schema")
    validate_identifier(target_database, "target database")

    compose = shlex.split(os.environ.get("AGENTLEDGER_DOCKER_COMPOSE", "docker compose"))
    compose_file = args.compose_file.resolve()
    compose_base = docker_compose_base(compose, compose_file)
    project = args.compose_project
    source_database = dsn_database(args.postgres_dsn)
    postgres_user = dsn_user(args.postgres_dsn) or "agentledger"
    target_dsn = replace_dsn_database(args.postgres_dsn, target_database)
    marker = f"backup-restore-drill-{suffix}"
    env = build_env(args, source_schema, target_dsn)
    env["AGENTLEDGER_POSTGRES_DRILL_COMPOSE_FILE"] = str(compose_file)
    env["AGENTLEDGER_POSTGRES_DRILL_COMPOSE_PROJECT"] = project
    results: list[CommandResult] = []
    started = False
    backup_sql_path: str | None = None

    def append(result: CommandResult) -> bool:
        results.append(result)
        return result.status == "passed"

    def cleanup() -> list[CommandResult]:
        return cleanup_drill_objects(compose_base, project, output_dir, args, postgres_user, source_database, source_schema, target_database)

    def finish(status: int | None = None) -> int:
        cleanup_required = started and not args.keep_services
        cleanup_results = cleanup() if cleanup_required else []
        report_status = write_outputs(
            args,
            output_dir,
            env,
            results,
            cleanup=cleanup_results,
            cleanup_required=cleanup_required,
            backup_sql_path=backup_sql_path,
        )
        return status if status is not None else report_status

    try:
        if not append(run_check("python_postgres_dependency", [args.python, "-c", "import psycopg"], output_dir, env=env)):
            return finish()

        if not append(run_check("docker_compose_config", compose_base + ["config", "--quiet"], output_dir)):
            return finish()

        if not append(run_check("docker_compose_up", compose_base + ["-p", project, "up", "-d", "postgres"], output_dir, timeout=args.command_timeout)):
            return finish()
        started = True

        if not append(wait_for_postgres(compose_base, project, output_dir, args.command_timeout, postgres_user, source_database)):
            return finish()

        seed = run_python_step(
            "seed_source_run",
            output_dir,
            lambda: seed_source_run(args.postgres_dsn, source_schema, marker),
        )
        if not append(seed):
            return finish()

        dump = run_check(
            "pg_dump_source_schema",
            compose_base
            + [
                "-p",
                project,
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                postgres_user,
                "-d",
                source_database,
                "--schema",
                source_schema,
                "--format=plain",
                "--no-owner",
                "--no-privileges",
            ],
            output_dir,
            timeout=args.command_timeout,
        )
        backup_sql_path = dump.stdout_path
        if not append(dump):
            return finish()

        if not append(run_check("drop_existing_restore_database", compose_base + ["-p", project, "exec", "-T", "postgres", "dropdb", "--force", "--if-exists", "-U", postgres_user, target_database], output_dir, timeout=args.command_timeout)):
            return finish()

        if not append(run_check("create_restore_database", compose_base + ["-p", project, "exec", "-T", "postgres", "createdb", "-U", postgres_user, target_database], output_dir, timeout=args.command_timeout)):
            return finish()

        if not append(run_check("restore_dump_to_target_database", compose_base + ["-p", project, "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", postgres_user, "-d", target_database], output_dir, stdin_path=Path(backup_sql_path), timeout=args.command_timeout)):
            return finish()

        restored = run_python_step(
            "verify_restored_run",
            output_dir,
            lambda: verify_restored_run(target_dsn, source_schema, seed.parsed_stdout),
        )
        if not append(restored):
            return finish()

        for conformance in run_post_restore_conformance(args, output_dir, env, target_dsn, source_schema):
            if not append(conformance):
                return finish()
        return finish()
    except KeyboardInterrupt:
        results.append(CommandResult("interrupted", [], 130, 0.0))
        return finish(130)
    except Exception as exc:
        stderr_path = output_dir / "unexpected_error.err"
        stderr_path.write_text(repr(exc), encoding="utf-8")
        results.append(CommandResult("unexpected_error", [], 1, 0.0, stderr_path=str(stderr_path)))
        return finish()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local Postgres pg_dump/restore drill for AgentLedger metadata.")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/agentledger-postgres-backup-restore-drill"))
    parser.add_argument("--compose-file", type=Path, default=default_compose_file())
    parser.add_argument("--compose-project", default=os.environ.get("AGENTLEDGER_POSTGRES_DRILL_COMPOSE_PROJECT", default_compose_project()))
    parser.add_argument("--python", default=os.environ.get("PYTHON", sys.executable))
    parser.add_argument("--command-timeout", type=int, default=180)
    parser.add_argument("--keep-services", action="store_true", help="Leave generated drill schema/database in place for debugging.")
    parser.add_argument("--postgres-dsn", default=os.environ.get("AGENTLEDGER_POSTGRES_DSN", default_postgres_dsn()))
    parser.add_argument("--source-schema", default=os.environ.get("AGENTLEDGER_POSTGRES_DRILL_SOURCE_SCHEMA"))
    parser.add_argument("--target-database", default=os.environ.get("AGENTLEDGER_POSTGRES_DRILL_TARGET_DATABASE"))
    parser.add_argument("--suffix", default=os.environ.get("AGENTLEDGER_POSTGRES_DRILL_SUFFIX"))
    return parser.parse_args()


def default_compose_file() -> Path:
    docker_infra_compose = DEFAULT_DOCKER_INFRA_DIR / "docker-compose.yml"
    return docker_infra_compose if docker_infra_compose.exists() else LOCAL_COMPOSE_FILE


def default_compose_project() -> str:
    return "docker-infra" if (DEFAULT_DOCKER_INFRA_DIR / "docker-compose.yml").exists() else "agentledger-postgres-backup-restore-drill"


def default_postgres_dsn() -> str:
    env = read_dotenv(DEFAULT_DOCKER_INFRA_DIR / ".env")
    if not env:
        env = read_dotenv(DEFAULT_DOCKER_INFRA_DIR / ".env.example")
    if env:
        user = env.get("POSTGRES_USER", "infra")
        password = env.get("POSTGRES_PASSWORD", "infra")
        port = env.get("POSTGRES_PORT", "15440")
        database = "agentledger"
        return f"postgresql://{user}:{password}@127.0.0.1:{port}/{database}"
    return "postgresql://agentledger:agentledger@127.0.0.1:15432/agentledger"


def read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def docker_compose_base(compose: list[str], compose_file: Path) -> list[str]:
    env_file = compose_file.parent / ".env"
    command = list(compose)
    if env_file.exists():
        command.extend(["--env-file", str(env_file)])
    command.extend(["-f", str(compose_file)])
    return command


def build_env(args: argparse.Namespace, source_schema: str, target_dsn: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = prepend_path(str(ROOT / "src"), env.get("PYTHONPATH"))
    env["AGENTLEDGER_POSTGRES_DSN"] = args.postgres_dsn
    env["AGENTLEDGER_POSTGRES_DRILL_SOURCE_SCHEMA"] = source_schema
    env["AGENTLEDGER_POSTGRES_DRILL_TARGET_DSN"] = target_dsn
    return env


def wait_for_postgres(compose_base: list[str], project: str, output_dir: Path, timeout: int, user: str, database: str) -> CommandResult:
    start = time.monotonic()
    attempts = 0
    command = compose_base + ["-p", project, "exec", "-T", "postgres", "pg_isready", "-U", user, "-d", database]
    last = CommandResult("postgres_ready", command, 1, 0.0)
    while time.monotonic() - start < timeout:
        attempts += 1
        last = run_check("postgres_ready", command, output_dir, timeout=10, output_suffix=f"attempt-{attempts}")
        if last.status == "passed":
            return last
        time.sleep(2)
    return last


def cleanup_drill_objects(
    compose_base: list[str],
    project: str,
    output_dir: Path,
    args: argparse.Namespace,
    user: str,
    source_database: str,
    source_schema: str,
    target_database: str,
) -> list[CommandResult]:
    if args.keep_services:
        return []
    return [
        run_check(
            "drop_source_schema",
            compose_base + ["-p", project, "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", source_database, "-c", f'DROP SCHEMA IF EXISTS "{source_schema}" CASCADE'],
            output_dir,
            timeout=args.command_timeout,
        ),
        run_check(
            "drop_restore_database",
            compose_base + ["-p", project, "exec", "-T", "postgres", "dropdb", "--force", "--if-exists", "-U", user, target_database],
            output_dir,
            timeout=args.command_timeout,
        ),
    ]


def run_post_restore_conformance(args: argparse.Namespace, output_dir: Path, env: dict[str, str], target_dsn: str, schema: str) -> list[CommandResult]:
    commands = [
        (
            "restored_postgres_state_conformance",
            [
                args.python,
                "-m",
                "agentledger",
                "state",
                "conformance",
                "--backend",
                "postgres",
                "--dsn",
                target_dsn,
                "--schema",
                schema,
            ],
        ),
        (
            "restored_postgres_worker_concurrency",
            [
                args.python,
                "-m",
                "agentledger",
                "worker",
                "conformance",
                "--backend",
                "postgres",
                "--dsn",
                target_dsn,
                "--schema",
                schema,
                "--concurrent",
            ],
        ),
    ]
    return [run_check(name, command, output_dir, env=env, timeout=args.command_timeout, parse_json=True) for name, command in commands]


def run_check(
    name: str,
    command: list[str],
    output_dir: Path,
    *,
    env: dict[str, str] | None = None,
    stdin_path: Path | None = None,
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
        stdin_path=stdin_path,
        timeout=timeout,
        parse_json=parse_json,
        output_suffix=output_suffix,
    )


def seed_source_run(dsn: str, schema: str, marker: str) -> dict[str, Any]:
    from agentledger.storage_postgres import PostgresStore, PostgresStoreConfig

    store = PostgresStore(PostgresStoreConfig(dsn=dsn, schema=schema))
    try:
        store.init()
        run_id, step_id = store.create_run(initial_state={"marker": marker, "phase": "source"})
        claim = store.claim_step(worker_id="backup-restore-drill", run_id=run_id)
        if claim is None:
            raise RuntimeError("source step was not claimable")
        store.commit_state_patch(
            run_id=run_id,
            step_id=step_id,
            lease_token=claim.lease_token,
            base_version=claim.state_version,
            patch={"restored_expected": True, "marker": marker},
            checkpoint_id="backup-restore-drill",
        )
        idempotency_key = f"{run_id}:backup.restore.drill"
        store.reserve_ledger(
            run_id=run_id,
            session_id=claim.session_id,
            step_id=step_id,
            tool_name="backup.restore.drill",
            tool_version="v1",
            tool_call_id="backup-restore-drill",
            idempotency_key=idempotency_key,
            causal_token="backup-restore-drill",
            request_hash="sha256:backup-restore-request",
            request_ref="inline://backup-restore-request",
        )
        store.update_ledger(
            idempotency_key=idempotency_key,
            status="SUCCEEDED",
            external_id="backup-restore-drill",
            response_hash="sha256:backup-restore-response",
            response_ref="inline://backup-restore-response",
        )
        store.create_artifact(
            run_id=run_id,
            step_id=step_id,
            name="backup-restore-drill-artifact",
            blob_hash="sha256:backup-restore-artifact",
            blob_ref="inline://backup-restore-artifact",
            metadata={"marker": marker, "purpose": "postgres_backup_restore_drill"},
        )
        store.record_cost(
            run_id=run_id,
            session_id=claim.session_id,
            step_id=step_id,
            category="tool",
            name="backup.restore.drill",
            amount=1,
            unit="call",
            metadata={"marker": marker},
        )
        store.append_event(
            run_id=run_id,
            session_id=claim.session_id,
            step_id=step_id,
            event_type="backup_restore_drill_marker",
            payload={"marker": marker},
        )
        return summarize_store(store, run_id, marker)
    finally:
        store.close()


def verify_restored_run(target_dsn: str, schema: str, source_summary: Any) -> dict[str, Any]:
    if not isinstance(source_summary, dict):
        raise RuntimeError("source summary is missing")

    from agentledger.storage_postgres import PostgresStore, PostgresStoreConfig

    store = PostgresStore(PostgresStoreConfig(dsn=target_dsn, schema=schema))
    try:
        store.init()
        restored = summarize_store(store, source_summary["run_id"], source_summary["marker"])
        checks = compare_summaries(source_summary, restored)
        return {
            "passed": all(check["passed"] for check in checks),
            "checks": checks,
            "source": source_summary,
            "restored": restored,
        }
    finally:
        store.close()


def summarize_store(store: Any, run_id: str, marker: str) -> dict[str, Any]:
    state, state_version, session_id = store.load_state(run_id)
    events = store.events(run_id)
    ledger = store.ledger(run_id)
    artifacts = store.artifacts(run_id)
    costs = store.cost_records(run_id)
    run = store.run(run_id)
    return {
        "run_id": run_id,
        "session_id": session_id,
        "marker": marker,
        "run_status": run["status"],
        "schema_version": store.schema_version(),
        "state_version": state_version,
        "state": state,
        "event_count": len(events),
        "event_types": [row["type"] for row in events],
        "ledger_count": len(ledger),
        "ledger_statuses": [row["status"] for row in ledger],
        "artifact_count": len(artifacts),
        "artifact_names": [row["name"] for row in artifacts],
        "cost_count": len(costs),
        "cost_summary": store.cost_summary(run_id),
    }


def compare_summaries(source: dict[str, Any], restored: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        check("run_id_preserved", restored["run_id"] == source["run_id"], restored["run_id"]),
        check("schema_version_present", bool(restored["schema_version"]), restored["schema_version"]),
        check("final_state_preserved", restored["state"] == source["state"], restored["state"]),
        check("events_preserved", restored["event_count"] == source["event_count"], restored["event_count"]),
        check("drill_marker_event_present", "backup_restore_drill_marker" in restored["event_types"], restored["event_types"]),
        check("ledger_preserved", restored["ledger_count"] == 1 and restored["ledger_statuses"] == ["SUCCEEDED"], restored["ledger_statuses"]),
        check("artifact_preserved", restored["artifact_count"] == 1 and restored["artifact_names"] == ["backup-restore-drill-artifact"], restored["artifact_names"]),
        check("cost_preserved", restored["cost_count"] == 1 and restored["cost_summary"].get("tool_calls") == 1.0, restored["cost_summary"]),
    ]


def check(name: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def validate_identifier(value: str, label: str) -> None:
    if len(value) > 63 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"invalid Postgres {label}: {value!r}")


def replace_dsn_database(value: str, database: str) -> str:
    validate_identifier(database, "database")
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.netloc, f"/{quote(database)}", parts.query, parts.fragment))


def write_outputs(
    args: argparse.Namespace,
    output_dir: Path,
    env: dict[str, str],
    results: list[CommandResult],
    *,
    cleanup: list[CommandResult],
    cleanup_required: bool,
    backup_sql_path: str | None,
) -> int:
    report = build_report(
        version=read_project_version(ROOT),
        output_dir=output_dir,
        env=env,
        checks=results,
        cleanup=cleanup,
        cleanup_required=cleanup_required,
        keep_services=args.keep_services,
        backup_sql_path=backup_sql_path,
    )
    json_path = output_dir / "postgres-backup-restore-drill.json"
    md_path = output_dir / "postgres-backup-restore-drill.md"
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
    cleanup: list[CommandResult],
    cleanup_required: bool,
    keep_services: bool,
    backup_sql_path: str | None,
) -> dict[str, Any]:
    check_dicts = [check.to_dict() for check in checks]
    check_dicts.extend(check.to_dict() for check in cleanup)
    validation_ok = all(check.status == "passed" for check in checks)
    cleanup_ok = keep_services or not cleanup_required or (bool(cleanup) and all(check.status == "passed" for check in cleanup))
    cleanup_status = "skipped" if keep_services else ("passed" if cleanup_ok and cleanup else ("failed" if cleanup else "not_run"))
    ok = validation_ok and cleanup_ok
    return {
        "schema": "agentledger.postgres_backup_restore_drill.v1",
        "version": version,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ok": ok,
        "output_dir": str(output_dir),
        "backup_sql_path": backup_sql_path,
        "services": {
            "compose": {
                "file": env["AGENTLEDGER_POSTGRES_DRILL_COMPOSE_FILE"],
                "project": env["AGENTLEDGER_POSTGRES_DRILL_COMPOSE_PROJECT"],
            },
            "source": {
                "dsn": redact_dsn(env["AGENTLEDGER_POSTGRES_DSN"]),
                "database": dsn_database(env["AGENTLEDGER_POSTGRES_DSN"]),
                "schema": env["AGENTLEDGER_POSTGRES_DRILL_SOURCE_SCHEMA"],
            },
            "restore_target": {
                "dsn": redact_dsn(env["AGENTLEDGER_POSTGRES_DRILL_TARGET_DSN"]),
                "database": dsn_database(env["AGENTLEDGER_POSTGRES_DRILL_TARGET_DSN"]),
                "schema": env["AGENTLEDGER_POSTGRES_DRILL_SOURCE_SCHEMA"],
            },
        },
        "checks": check_dicts,
        "remaining_external_required": [
            "production_backup_schedule",
            "pitr_or_wal_archive",
            "rto_rpo_timing",
            "least_privilege_restore_role",
            "s3_blob_prefix_restore_pairing",
        ],
        "cleanup": cleanup_status,
        "cleanup_ok": cleanup_ok,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# AgentLedger Postgres Backup/Restore Drill {report['version']}",
        "",
        f"- Status: {'passed' if report['ok'] else 'failed'}",
        f"- Generated: {report['generated_at']}",
        f"- Output: `{report['output_dir']}`",
        f"- Backup SQL: `{report['backup_sql_path']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Duration |",
        "| --- | --- | ---: |",
    ]
    for check_result in report["checks"]:
        lines.append(f"| `{check_result['name']}` | {check_result['status']} | {check_result['duration_seconds']}s |")
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
