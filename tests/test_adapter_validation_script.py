from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_adapters_local.py"
    spec = importlib.util.spec_from_file_location("validate_adapters_local", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AdapterValidationScriptTests(unittest.TestCase):
    def test_redacts_postgres_dsn_password(self) -> None:
        module = load_module()
        self.assertEqual(
            module.redact_dsn("postgresql://agentledger:secret@localhost:15432/agentledger"),
            "postgresql://agentledger:***@localhost:15432/agentledger",
        )
        self.assertEqual(
            module.redact_dsn("postgresql://localhost:15432/agentledger?user=agentledger&password=secret&sslmode=require"),
            "postgresql://localhost:15432/agentledger?user=agentledger&password=***&sslmode=require",
        )
        self.assertEqual(
            module.redact_command(["python", "--dsn=postgresql://localhost/db?password=secret"]),
            ["python", "--dsn=postgresql://localhost/db?password=***"],
        )

    def test_report_fails_when_validation_check_fails(self) -> None:
        module = load_module()
        check = module.CommandResult(
            name="postgres_state_conformance",
            command=[
                "python",
                "-m",
                "agentledger",
                "--dsn",
                "postgresql://agentledger:secret@localhost:15432/agentledger",
            ],
            returncode=1,
            duration_seconds=0.1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = module.build_report(
                version="1.5.2",
                output_dir=Path(tmp),
                env={
                    "AGENTLEDGER_POSTGRES_DSN": "postgresql://agentledger:secret@localhost:15432/agentledger",
                    "AGENTLEDGER_POSTGRES_SCHEMA": "agentledger",
                    "AGENTLEDGER_S3_BUCKET": "agentledger-runs",
                    "AGENTLEDGER_S3_PREFIX": "agentledger/validation/test",
                    "AGENTLEDGER_S3_ENDPOINT_URL": "http://127.0.0.1:19000",
                    "AGENTLEDGER_S3_REGION": "us-east-1",
                },
                checks=[check],
                cleanup=None,
                keep_services=False,
            )
        self.assertFalse(report["ok"])
        self.assertEqual(
            report["services"]["postgres"]["dsn"],
            "postgresql://agentledger:***@localhost:15432/agentledger",
        )
        self.assertNotIn("secret", json.dumps(report))

    def test_report_fails_when_cleanup_fails(self) -> None:
        module = load_module()
        passed = module.CommandResult(
            name="postgres_state_conformance",
            command=["python", "-m", "agentledger"],
            returncode=0,
            duration_seconds=0.1,
        )
        cleanup = module.CommandResult(
            name="docker_compose_down",
            command=["docker", "compose", "down", "-v"],
            returncode=1,
            duration_seconds=0.1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = module.build_report(
                version="1.5.2",
                output_dir=Path(tmp),
                env={
                    "AGENTLEDGER_POSTGRES_DSN": "postgresql://agentledger:secret@localhost:15432/agentledger",
                    "AGENTLEDGER_POSTGRES_SCHEMA": "agentledger",
                    "AGENTLEDGER_S3_BUCKET": "agentledger-runs",
                    "AGENTLEDGER_S3_PREFIX": "agentledger/validation/test",
                    "AGENTLEDGER_S3_ENDPOINT_URL": "http://127.0.0.1:19000",
                    "AGENTLEDGER_S3_REGION": "us-east-1",
                },
                checks=[passed],
                cleanup=cleanup,
                keep_services=False,
            )
        self.assertFalse(report["ok"])
        self.assertFalse(report["cleanup_ok"])


if __name__ == "__main__":
    unittest.main()
