from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "drill_postgres_backup_restore.py"
    spec = importlib.util.spec_from_file_location("drill_postgres_backup_restore", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PostgresBackupRestoreDrillScriptTests(unittest.TestCase):
    def test_dsn_helpers_redact_and_replace_database(self) -> None:
        module = load_module()
        dsn = "postgresql://agentledger:secret@localhost:15432/agentledger?sslmode=require&password=query-secret"
        self.assertEqual(module.dsn_database(dsn), "agentledger")
        self.assertEqual(module.dsn_user(dsn), "agentledger")
        self.assertEqual(
            module.replace_dsn_database(dsn, "agentledger_restore_test"),
            "postgresql://agentledger:secret@localhost:15432/agentledger_restore_test?sslmode=require&password=query-secret",
        )
        redacted = module.redact_dsn(dsn)
        self.assertIn("agentledger:***@", redacted)
        self.assertIn("password=***", redacted)
        self.assertNotIn("secret", redacted)

    def test_compare_summaries_requires_restored_rows(self) -> None:
        module = load_module()
        source = {
            "run_id": "run-1",
            "schema_version": "0001",
            "state": {"marker": "x"},
            "event_count": 5,
        }
        restored = {
            "run_id": "run-1",
            "schema_version": "0001",
            "state": {"marker": "x"},
            "event_count": 5,
            "event_types": ["run_created", "backup_restore_drill_marker"],
            "ledger_count": 1,
            "ledger_statuses": ["SUCCEEDED"],
            "artifact_count": 1,
            "artifact_names": ["backup-restore-drill-artifact"],
            "cost_count": 1,
            "cost_summary": {"tool_calls": 1.0},
        }
        self.assertTrue(all(check["passed"] for check in module.compare_summaries(source, restored)))
        restored["ledger_statuses"] = ["RESERVED"]
        self.assertFalse(all(check["passed"] for check in module.compare_summaries(source, restored)))

    def test_report_fails_when_cleanup_fails(self) -> None:
        module = load_module()
        passed = module.CommandResult(
            name="verify_restored_run",
            command=[],
            returncode=0,
            duration_seconds=0.1,
            parsed_stdout={"passed": True},
        )
        cleanup = module.CommandResult(
            name="drop_restore_database",
            command=["docker", "compose", "exec", "postgres", "dropdb", "agentledger_restore_test"],
            returncode=1,
            duration_seconds=0.1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = module.build_report(
                version="1.5.2",
                output_dir=Path(tmp),
                env={
                    "AGENTLEDGER_POSTGRES_DSN": "postgresql://agentledger:secret@localhost:15432/agentledger",
                    "AGENTLEDGER_POSTGRES_DRILL_SOURCE_SCHEMA": "agentledger_backup_src_test",
                    "AGENTLEDGER_POSTGRES_DRILL_TARGET_DSN": "postgresql://agentledger:secret@localhost:15432/agentledger_restore_test",
                    "AGENTLEDGER_POSTGRES_DRILL_COMPOSE_FILE": "/tmp/docker-compose.yml",
                    "AGENTLEDGER_POSTGRES_DRILL_COMPOSE_PROJECT": "docker-infra",
                },
                checks=[passed],
                cleanup=[cleanup],
                cleanup_required=True,
                keep_services=False,
                backup_sql_path="/tmp/drill.sql",
            )
        self.assertFalse(report["ok"])
        self.assertFalse(report["cleanup_ok"])
        self.assertNotIn("secret", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
