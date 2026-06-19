from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import runpy
import sqlite3
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any

from agentledger.adapters import PythonFunctionAdapter, python_agent
from agentledger.adapter_certification import build_adapter_certification_bundle
from agentledger.adapters_frameworks import AutoGenAdapter, CrewAIAdapter, LangChainRunnableAdapter, LlamaIndexAdapter, OpenAIAgentsSDKAdapter, SemanticKernelAdapter
from agentledger.adapters_langgraph import LangGraphCheckpointerAdapter, LangGraphNodeAdapter
from agentledger.adapters_mcp import InMemoryMCPContextServer, InMemoryMCPToolServer, MCPContextAdapter, MCPToolAdapter
from agentledger.backup import BackupReadinessChecker
from agentledger.blobstore_s3 import S3BlobStore, S3BlobStoreConfig
from agentledger.conformance import BlobStoreConformanceRunner, FrameworkAdapterConformanceRunner, MediaRuntimeConformanceRunner, StateStoreConformanceRunner, WorkerConformanceRunner
from agentledger.contract import contract_json, runtime_contract
from agentledger.approval import ApprovalRequired
from agentledger.cli import build_parser, cmd_adapter_certify, cmd_adapter_conformance, cmd_backup_check, cmd_blob_conformance, cmd_conformance, cmd_corpus_add, cmd_corpus_eval, cmd_corpus_list, cmd_corpus_seed, cmd_cost_report, cmd_debug, cmd_divergence, cmd_evidence, cmd_evidence_regression, cmd_failure_export, cmd_failure_inject, cmd_failure_regress, cmd_failure_report, cmd_inspector_evidence, cmd_inspector_run, cmd_inspector_runs, cmd_lint_boundary, cmd_migrate_status, cmd_migrate_up, cmd_review_checklist, cmd_state_conformance, cmd_timetravel, cmd_tools_manifest, cmd_worker_conformance, cmd_worker_plan, cmd_worker_serve, create_blob_store, create_state_store, main
from agentledger.cost import BudgetController, BudgetExceeded, BudgetLimits, CostAttributionReporter
from agentledger.failure import FAILURE_ENVELOPE_SCHEMA_VERSION, FAILURE_EXPORT_SCHEMA_VERSION, FAILURE_LIFECYCLE_SCHEMA_VERSION, FailureAttributionReporter, FailureRegressionAnalyzer, RetryableAgentError
from agentledger.failure_injection import FailureInjectionSuite
from agentledger.inspector import INSPECTOR_RUN_INDEX_SCHEMA_VERSION, INSPECTOR_SCHEMA_VERSION, InspectorDataSource, InspectorRedactionPolicy, InspectorReportBuilder, ReadOnlyLocalBlobStore, ReadOnlyMySQLStore, ReadOnlyPostgresStore, ReadOnlySQLiteStore
from agentledger.lint import RuntimeBoundaryLinter, load_boundary_rules
from agentledger.media import ArtifactLineage, EventStreamCheckpoint, MediaArtifact, MediaMetadata, StreamChunkRef
from agentledger.media_tools import media_tool_specs, register_media_tool_conventions
from agentledger.policy import PolicyEngine, PolicyRequest
from agentledger.protocol import BlobStoreProtocol, StateStoreProtocol
from agentledger.repro import GoldenCorpus
from agentledger.eval import EvidenceRegressionRunner
from agentledger.diff import DivergenceReporter, EvidenceDiffer, load_evidence_path
from agentledger.evidence import EvidenceExporter
from agentledger.examples import crash_once_agent, recovery_agent, register_fake_github
from agentledger.replay import ReplayEngine
from agentledger.retention import RetentionPlanner
from agentledger.review import AdversarialReviewRunner
from agentledger.sandbox import SandboxConfig, SandboxRouter, create_sandbox_executor
from agentledger.runtime import Runtime, SimulatedCrash
from agentledger.scheduler import RuntimeScheduler
from agentledger.shadow import ShadowRunner
from agentledger.storage_schema import ddl_for, latest_schema_version, migrations_for
from agentledger.storage_mysql import MySQLStore, MySQLStoreConfig
from agentledger.storage_postgres import PostgresStore, PostgresStoreConfig
from agentledger.store import SQLiteStore
from agentledger.trace import OTLPTraceExporter, TraceExporter
from agentledger.timetravel import TimeTravelDebugger
from agentledger.simple import agent, arun, run
from agentledger.tools import PermissionDenied, ToolSpec, ToolValidationError, validate_tool_schema
from agentledger.worker import LocalWorker, WorkerService, build_worker_deployment_plan

from agentledger import __version__ as AGENTLEDGER_VERSION


class FakePostgresConnection:
    """SQLite-backed stand-in for psycopg's small connection surface."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return self.conn.execute(sql.replace("%s", "?"), params)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()

    def transaction(self) -> "FakePostgresConnection":
        return self

    def __enter__(self) -> "FakePostgresConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.conn.commit() if exc_type is None else self.conn.rollback()


class FakeS3Body:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        bucket = kwargs["Bucket"]
        key = kwargs["Key"]
        body = kwargs["Body"]
        self.objects[(bucket, key)] = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.puts.append(kwargs)

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        return {"Body": FakeS3Body(self.objects[(kwargs["Bucket"], kwargs["Key"])])}


class RuntimeTests(unittest.TestCase):
    def _run_side_effect_demo(self, root: Path) -> tuple[Runtime, str, Path]:
        rt = Runtime.local(root)
        external = root / "external_issues.json"
        register_fake_github(rt, external)
        run_id, _ = rt.create_run(initial_state={"crashed_once": False})
        first_ok = asyncio.run(rt.run_once(crash_once_agent, run_id=run_id, agent_role="ExecutorAgent"))
        self.assertFalse(first_ok)
        rt.store.apply_system_state_patch(
            run_id=run_id,
            patch={"crashed_once": True},
            reason="test recovery marker after simulated worker crash",
        )
        second_ok = asyncio.run(rt.run_once(recovery_agent, run_id=run_id, agent_role="ExecutorAgent"))
        self.assertTrue(second_ok)
        return rt, run_id, external

    def test_cli_parser_accepts_documented_commands(self) -> None:
        parser = build_parser()
        command_cases = [
            ["init"],
            ["doctor"],
            ["version"],
            ["run", "examples/side_effect_idempotency"],
            ["debug", "run-1"],
            ["debug", "run-1", "--json", "--include-diffs"],
            ["replay", "run-1"],
            ["ledger", "run-1"],
            ["evidence", "run-1"],
            ["evidence", "run-1", "--dir", "./evidence/run-1"],
            ["evidence", "run-1", "--html", "./evidence.html"],
            ["inspector", "run", "run-1", "--backend", "sqlite", "--html", "./inspector.html"],
            ["inspector", "run", "run-1", "--root", ".agentledger-demo", "--html", "./inspector.html"],
            ["inspector", "run", "run-1", "--backend", "postgres", "--dsn", "postgresql://user:pass@localhost/db", "--schema", "agentledger", "--out", "./inspector.json"],
            ["inspector", "run", "run-1", "--backend", "mysql", "--dsn", "mysql://user:pass@localhost/db", "--database", "agentledger", "--out", "./inspector.json"],
            ["inspector", "evidence", "./evidence/run-1", "--out", "./inspector.json"],
            ["evidence-check", "run-1"],
            ["review", "checklist", "run-1", "--fail-on-risk"],
            ["cost", "report", "run-1"],
            ["trace", "run-1", "--out", "./trace.jsonl"],
            ["trace", "run-1", "--format", "otlp", "--out", "./trace.otlp.json"],
            ["timetravel", "run-1", "--at-seq", "5"],
            ["timetravel", "run-1", "--include-diffs", "--include-states", "--html", "./time-travel.html"],
            ["approvals", "run-1"],
            ["approve", "approval-1", "--approver", "alice", "--reason", "reviewed"],
            ["backup", "check", "run-1"],
            ["retention", "plan", "run-1"],
            ["retention", "mark-compacted", "run-1"],
            ["sandbox", "inspect", "examples/sandbox/sandbox.yaml"],
            ["lint", "boundary", "./examples", "./src", "--exclude", "src/agentledger"],
            ["lint", "boundary", "./examples", "--rules", "examples/lint/boundary_rules.json", "--replace-defaults", "--no-fail"],
            ["migrate", "status"],
            ["migrate", "up", "--dialect", "postgres"],
            ["migrate", "status", "--dialect", "mysql"],
            ["migrate", "ddl", "--dialect", "mysql"],
            ["migrate", "ddl", "--dialect", "postgres"],
            ["contract", "export"],
            ["diff", "left-run", "right-run"],
            ["divergence", "left-run", "right-run"],
            ["evidence-regression", "./golden-bundle.json", "./current-bundle-dir"],
            ["corpus", "seed", "minimal-success"],
            ["corpus", "seed", "tool-ledger-success"],
            ["corpus", "seed", "media-stream-checkpoint"],
            ["corpus", "seed", "--list-builtins"],
            ["corpus", "add", "side-effect", "./golden-bundle.json"],
            ["corpus", "check", "side-effect", "./current-bundle-dir"],
            ["shadow", "run-1", "examples/side_effect_idempotency"],
            ["status", "run-1"],
            ["cancel", "run-1", "--reason", "operator requested"],
            ["recover-expired"],
            ["failure", "inject", "--scenario", "all"],
            ["failure", "report", "run-1"],
            ["conformance"],
            ["adapter", "conformance", "--kind", "langchain"],
            ["adapter", "certify", "--kind", "postgres", "--adapter-version", "1.2.0"],
            ["state", "conformance", "--backend", "sqlite"],
            ["blob", "conformance", "--backend", "local"],
            ["worker", "conformance", "--backend", "sqlite", "--concurrent"],
            ["worker", "plan", "examples/transient_retry", "--replicas", "2", "--daemon"],
            ["worker", "serve", "examples/transient_retry", "--max-loops", "5"],
            ["worker-run", "examples/transient_retry"],
            ["postgres", "ddl"],
            ["postgres", "conformance"],
            ["mysql", "ddl"],
            ["policy", "check", "examples/policy/local.policy.yaml", "ExecutorAgent", "github.create_issue", "medium"],
            ["tools", "manifest", "--format", "agentledger", "--example", "examples/docs"],
            ["--policy", "examples/policy/local.policy.yaml", "run", "examples/side_effect_idempotency"],
        ]
        for argv in command_cases:
            with self.subTest(argv=argv):
                parsed = parser.parse_args(argv)
                self.assertTrue(callable(parsed.func))
        for argv in (["eval", "run-1"], ["eval-regression", "golden.json", "current.json"], ["corpus", "eval", "case", "current.json"]):
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    parser.parse_args(argv)

    def test_pyproject_declares_package_entrypoint_and_supported_python(self) -> None:
        metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        project = metadata["project"]
        self.assertEqual(project["name"], "agentledger-runtime")
        self.assertEqual(project["requires-python"], ">=3.11")
        self.assertEqual(project["scripts"]["agentledger"], "agentledger.cli:main")
        self.assertEqual(project["urls"]["Repository"], "https://github.com/yaogdu/AgentLedger")
        self.assertIn("README.md", project["readme"])
        self.assertIn("postgres", project["optional-dependencies"])
        self.assertIn("s3", project["optional-dependencies"])
        self.assertIn("inspector", project["optional-dependencies"])
        self.assertIn("Programming Language :: Python :: 3.11", project["classifiers"])
        self.assertIn("Programming Language :: Python :: 3.12", project["classifiers"])
        self.assertEqual(project["version"], AGENTLEDGER_VERSION)

        inspector_metadata = tomllib.loads(Path("packages/agentledger-inspector/pyproject.toml").read_text(encoding="utf-8"))
        inspector_project = inspector_metadata["project"]
        inspector_module = runpy.run_path("packages/agentledger-inspector/src/agentledger_inspector/__init__.py")
        self.assertEqual(inspector_project["version"], inspector_module["__version__"])
        self.assertEqual(inspector_project["dependencies"], [f"agentledger-runtime>={AGENTLEDGER_VERSION},<2"])
        self.assertIn(f"agentledger-inspector>={inspector_module['__version__']},<2", project["optional-dependencies"]["inspector"])

    def test_cli_version_prints_package_version(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main(["version"])
        self.assertEqual(stdout.getvalue().strip(), f"agentledger {AGENTLEDGER_VERSION}")

    def test_cli_help_points_to_github_docs(self) -> None:
        stdout = io.StringIO()
        parser = build_parser()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit):
            parser.parse_args(["--help"])
        help_text = stdout.getvalue()
        self.assertIn("https://github.com/yaogdu/AgentLedger", help_text)
        self.assertIn("pipx install agentledger-runtime", help_text)

    def test_side_effect_not_duplicated_after_crash_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agentledger"
            rt, run_id, external = self._run_side_effect_demo(root)
            issues = json.loads(external.read_text())
            self.assertEqual(len(issues), 1)
            final_state = rt.store.final_state(run_id)
            self.assertTrue(final_state["recovered"])
            self.assertEqual(final_state["issue"]["external_id"], "ISSUE-1")

    def test_replay_does_not_execute_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agentledger"
            rt, run_id, external = self._run_side_effect_demo(root)

            before = json.loads(external.read_text())
            summary = ReplayEngine(store=rt.store, blobs=rt.blobs).replay(run_id)
            after = json.loads(external.read_text())
            self.assertEqual(before, after)
            self.assertGreater(summary.event_count, 0)
            self.assertGreater(summary.tool_call_count, 0)
            self.assertTrue(summary.replay_safe)
            self.assertTrue(summary.event_hash.startswith("sha256:"))

    def test_low_risk_stateless_tool_can_commit_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(ToolSpec(name="math.add", func=lambda args: {"sum": args["a"] + args["b"]}))
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, state: dict[str, Any]) -> None:
                result = await ctx.call_tool("math.add", {"a": 2, "b": 3})
                ctx.write_state_patch("sum", result["sum"])

            ok = asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertTrue(ok)
            self.assertEqual(rt.store.final_state(run_id)["sum"], 5)
            self.assertEqual(rt.store.cost_summary(run_id)["tool_calls"], 1.0)

    def test_high_risk_tool_is_default_denied_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(ToolSpec(name="shell.exec", func=lambda args: {"ok": True}, risk_level="high"))
            run_id, step_id = rt.create_run(initial_state={})

            async def agent(ctx: Any, state: dict[str, Any]) -> None:
                await ctx.call_tool("shell.exec", {"cmd": "echo unsafe"})

            with self.assertRaises(PermissionDenied):
                asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ExecutorAgent"))
            event_types = [row["type"] for row in rt.store.events(run_id)]
            self.assertIn("step_failed", event_types)
            step = rt.store.conn.execute("SELECT status FROM steps WHERE step_id=?", (step_id,)).fetchone()
            self.assertEqual(step["status"], "failed")

    def test_required_tool_args_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(ToolSpec(name="docs.read", func=lambda args: {"ok": True}, input_schema={"required": ["path"]}))
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, state: dict[str, Any]) -> None:
                await ctx.call_tool("docs.read", {})

            with self.assertRaises(ValueError):
                asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ReaderAgent"))

    def test_tool_schema_subset_validates_input_and_output(self) -> None:
        validate_tool_schema(
            {
                "type": "object",
                "required": ["path", "limit"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                },
                "additionalProperties": False,
            },
            {"path": "README.md", "limit": 2, "tags": ["docs"]},
            path="args",
        )
        with self.assertRaises(ToolValidationError):
            validate_tool_schema({"type": "object", "properties": {"limit": {"type": "integer"}}, "additionalProperties": False}, {"limit": "2", "extra": True})

    def test_tool_schema_subset_supports_portable_composition_and_constraints(self) -> None:
        schema = {
            "type": "object",
            "required": ["mode", "name", "scores", "metadata"],
            "properties": {
                "mode": {"oneOf": [{"const": "fast"}, {"const": "safe"}]},
                "name": {"type": "string", "pattern": "^[a-z][a-z0-9_-]+$"},
                "scores": {"type": "array", "items": {"type": "number", "multipleOf": 0.5}, "uniqueItems": True},
                "metadata": {
                    "type": "object",
                    "properties": {"kind": {"enum": ["demo", "prod"]}},
                    "additionalProperties": {"type": "string"},
                },
                "limit": {"anyOf": [{"type": "integer", "exclusiveMinimum": 0}, {"type": "null"}]},
            },
            "allOf": [{"type": "object", "minProperties": 4}],
            "not": {"required": ["forbidden"]},
        }
        validate_tool_schema(
            schema,
            {"mode": "safe", "name": "agent_1", "scores": [1, 1.5], "metadata": {"kind": "demo", "owner": "qa"}, "limit": None},
            path="args",
        )
        invalid_cases = [
            {"mode": "fast", "name": "Bad", "scores": [1], "metadata": {"kind": "demo"}},
            {"mode": "safe", "name": "agent", "scores": [1, 1], "metadata": {"kind": "demo"}},
            {"mode": "safe", "name": "agent", "scores": [1.25], "metadata": {"kind": "demo"}},
            {"mode": "safe", "name": "agent", "scores": [1], "metadata": {"kind": "demo", "count": 1}},
            {"mode": "safe", "name": "agent", "scores": [1], "metadata": {"kind": "demo"}, "limit": 0},
            {"mode": "safe", "name": "agent", "scores": [1], "metadata": {"kind": "demo"}, "forbidden": True},
        ]
        for value in invalid_cases:
            with self.subTest(value=value):
                with self.assertRaises(ToolValidationError):
                    validate_tool_schema(schema, value, path="args")

    def test_tool_output_schema_failure_is_a_failed_tool_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(
                ToolSpec(
                    name="docs.bad_read",
                    func=lambda _args: {"content": 123},
                    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                    output_schema={"type": "object", "required": ["content"], "properties": {"content": {"type": "string"}}},
                )
            )
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, _state: dict[str, Any]) -> None:
                await ctx.call_tool("docs.bad_read", {})

            with self.assertRaises(ToolValidationError):
                asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ReaderAgent"))
            event_types = [row["type"] for row in rt.store.events(run_id)]
            self.assertIn("tool_call_failed", event_types)

    def test_stale_lease_cannot_commit_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, step_id = rt.create_run(initial_state={})
            claim = rt.store.claim_step(worker_id="worker-a", run_id=run_id)
            self.assertIsNotNone(claim)
            assert claim is not None
            with self.assertRaises(RuntimeError):
                rt.store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token="bad-token", base_version=0, patch={"x": 1})

    def test_evidence_bundle_and_eval_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).to_dict()
            self.assertEqual(bundle["schema_version"], "agentledger.evidence.v1")
            self.assertTrue(bundle["bundle_hash"].startswith("sha256:"))
            self.assertEqual(bundle["summary"]["tool_ledger_count"], 1)
            self.assertEqual(bundle["summary"]["cost_summary"]["tool_calls"], 2.0)
            report = EvidenceRegressionRunner().evaluate(bundle)
            self.assertTrue(report.passed)

    def test_inspector_reads_sqlite_runtime_and_evidence_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agentledger"
            rt, run_id, _ = self._run_side_effect_demo(root)
            source = InspectorDataSource()

            runtime_report = source.from_sqlite(db_path=root / "state.db", blob_root=root / "blobs", run_id=run_id)
            data = runtime_report.to_dict()
            self.assertEqual(data["schema_version"], INSPECTOR_SCHEMA_VERSION)
            self.assertEqual(data["run"]["run_id"], run_id)
            self.assertGreater(data["summary"]["event_count"], 0)
            self.assertEqual(len(data["tool_ledger"]), 1)
            self.assertTrue(data["evidence"]["bundle_hash"].startswith("sha256:"))
            html = runtime_report.to_html()
            self.assertIn("AgentLedger Inspector", html)
            self.assertIn(run_id, html)

            evidence_dir = Path(tmp) / "evidence" / run_id
            EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).write_dir(evidence_dir)
            evidence_report = source.from_evidence_path(evidence_dir)
            self.assertEqual(evidence_report.to_dict()["run"]["run_id"], run_id)
            self.assertEqual(evidence_report.to_dict()["evidence"]["bundle_hash"], data["evidence"]["bundle_hash"])

    def test_inspector_cli_outputs_json_and_static_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agentledger"
            rt, run_id, _ = self._run_side_effect_demo(root)
            json_path = Path(tmp) / "inspector.json"
            html_path = Path(tmp) / "inspector.html"

            args = type(
                "Args",
                (),
                {
                    "root": str(root),
                    "run_id": run_id,
                    "backend": "sqlite",
                    "db": None,
                    "blob_root": None,
                    "dsn": None,
                    "schema": "agentledger",
                    "database": None,
                    "include_payloads": False,
                    "out": str(json_path),
                    "html": None,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_inspector_run(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["run_id"], run_id)
            written = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(written["schema_version"], INSPECTOR_SCHEMA_VERSION)

            evidence_dir = Path(tmp) / "evidence" / run_id
            EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).write_dir(evidence_dir)
            args = type("Args", (), {"path": str(evidence_dir), "include_payloads": False, "out": None, "html": str(html_path)})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_inspector_evidence(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["inspector_html"], str(html_path))
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("AgentLedger Inspector", html)
            self.assertIn(run_id, html)

    def test_inspector_run_index_outputs_json_and_static_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agentledger"
            rt, run_id, _ = self._run_side_effect_demo(root)
            pending_run_id, _ = rt.create_run(initial_state={"agent_run_id": "agent-run-index-2"})
            source = InspectorDataSource()

            index = source.runs_from_sqlite(
                db_path=root / "state.db",
                blob_root=root / "blobs",
                limit=10,
                run_link_template="/runs/{run_id}/inspector.html",
            )
            data = index.to_dict()
            self.assertEqual(data["schema_version"], INSPECTOR_RUN_INDEX_SCHEMA_VERSION)
            self.assertEqual(data["summary"]["run_count"], 2)
            rows = {row["run_id"]: row for row in data["runs"]}
            self.assertIn(run_id, rows)
            self.assertEqual(rows[pending_run_id]["agent_run_id"], "agent-run-index-2")
            self.assertEqual(rows[pending_run_id]["status"], "pending")
            self.assertIn({"kind": "inspector", "value": "open", "href": f"/runs/{pending_run_id}/inspector.html"}, rows[pending_run_id]["related_links"])

            html = index.to_html()
            self.assertIn("AgentLedger Inspector Runs", html)
            self.assertIn('href="#runs"', html)
            self.assertIn('class="run-list"', html)
            self.assertIn('class="run-item', html)
            self.assertIn(".run-list { display: grid; gap: 28px; }", html)
            self.assertIn(".metadata-panel { margin-top: 36px; }", html)
            self.assertIn('class="panel metadata-panel"', html)
            self.assertIn("data-run-pager", html)
            self.assertIn('data-page-size="20"', html)
            self.assertIn('data-run-index="1"', html)
            self.assertIn("Open Inspector", html)
            self.assertIn(f"/runs/{pending_run_id}/inspector.html", html)
            self.assertIn("run/session", Path("docs/ROADMAP.md").read_text(encoding="utf-8"))

            json_path = Path(tmp) / "runs.json"
            html_path = Path(tmp) / "runs.html"
            args = type(
                "Args",
                (),
                {
                    "root": str(root),
                    "backend": "sqlite",
                    "db": None,
                    "blob_root": None,
                    "dsn": None,
                    "schema": "agentledger",
                    "database": None,
                    "limit": 10,
                    "status": None,
                    "run_link_template": "/runs/{run_id}/inspector.html",
                    "out": str(json_path),
                    "html": None,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_inspector_runs(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema_version"], INSPECTOR_RUN_INDEX_SCHEMA_VERSION)
            self.assertEqual(payload["run_count"], 2)
            written = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(written["summary"]["run_count"], 2)

            args.out = None
            args.html = str(html_path)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_inspector_runs(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["inspector_html"], str(html_path))
            generated_html = html_path.read_text(encoding="utf-8")
            self.assertIn("AgentLedger Inspector Runs", generated_html)
            self.assertIn('class="run-list"', generated_html)
            self.assertIn("data-run-pager", generated_html)

    def test_inspector_read_only_sources_do_not_create_or_write_runtime_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_db = Path(tmp) / "missing.db"
            missing_blobs = Path(tmp) / "missing-blobs"
            with self.assertRaises(FileNotFoundError):
                ReadOnlySQLiteStore(missing_db)
            with self.assertRaises(FileNotFoundError):
                ReadOnlyLocalBlobStore(missing_blobs)

            root = Path(tmp) / ".agentledger"
            Runtime.local(root)
            store = ReadOnlySQLiteStore(root / "state.db")
            try:
                store.init()
                with self.assertRaises(sqlite3.OperationalError):
                    store.conn.execute("CREATE TABLE inspector_write_probe(id TEXT)")
            finally:
                store.close()

            blobs = ReadOnlyLocalBlobStore(root / "blobs")
            with self.assertRaises(RuntimeError):
                blobs.put_json({"should": "not write"})

            pg_store = ReadOnlyPostgresStore(PostgresStoreConfig("postgres://fake/agentledger"), connection=FakePostgresConnection(), owns_connection=True)
            try:
                pg_store.init()
                with self.assertRaises(RuntimeError):
                    pg_store.create_run(initial_state={})
                with self.assertRaises(RuntimeError):
                    pg_store.append_event(run_id="run-1", event_type="probe", payload={})
                with self.assertRaises(RuntimeError):
                    pg_store.migration_status()
            finally:
                pg_store.close()

            mysql_store = ReadOnlyMySQLStore(MySQLStoreConfig("mysql://fake/agentledger"), connection=FakePostgresConnection(), owns_connection=True)
            try:
                mysql_store.init()
                with self.assertRaises(RuntimeError):
                    mysql_store.create_artifact(run_id="run-1", step_id=None, name="probe", blob_hash="sha256:x", blob_ref="blob://x")
                with self.assertRaises(RuntimeError):
                    mysql_store.record_cost(run_id="run-1", session_id=None, step_id=None, category="tool", name="probe", amount=1, unit="call")
            finally:
                mysql_store.close()

    def test_inspector_extension_api_accepts_custom_read_store_and_escapes_html(self) -> None:
        class CustomBlobStore:
            def get_json(self, ref: str) -> Any:
                self.last_ref = ref
                return {"tool_name": "<script>alert(1)</script>", "reason": "needs <approval>"}

        class CustomStateStore:
            def run(self, run_id: str) -> dict[str, Any]:
                return {
                    "run_id": run_id,
                    "session_id": "sess-custom",
                    "status": "completed",
                    "state_version": 1,
                    "created_at": 1.0,
                    "updated_at": 2.0,
                }

            def steps(self, run_id: str) -> list[dict[str, Any]]:
                return [{"step_id": "step-1", "run_id": run_id, "status": "completed", "attempt": 1, "state_version": 1}]

            def events(self, run_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "seq": 1,
                        "event_id": "evt-1",
                        "run_id": run_id,
                        "step_id": "step-1",
                        "agent_role": "Reviewer",
                        "state_version": 1,
                        "type": "tool_permission_decided",
                        "timestamp": 1.1,
                        "payload_ref": "blob://payload-danger",
                    }
                ]

            def ledger(self, run_id: str) -> list[dict[str, Any]]:
                return [{"tool_name": "<b>danger</b>", "status": "SUCCEEDED", "external_id": "ext-1"}]

            def approval_requests(self, run_id: str | None = None) -> list[dict[str, Any]]:
                return []

            def artifacts(self, run_id: str) -> list[dict[str, Any]]:
                return [{"name": "<img src=x onerror=alert(1)>", "blob_hash": "sha256:x", "blob_ref": "blob://artifact", "metadata_json": "{}"}]

            def cost_records(self, run_id: str) -> list[dict[str, Any]]:
                return [{"category": "tool", "name": "custom", "amount": 1, "unit": "call"}]

            def cost_summary(self, run_id: str) -> dict[str, Any]:
                return {"tool_calls": 1.0}

            def final_state(self, run_id: str) -> dict[str, Any]:
                return {"done": True}

        report = InspectorDataSource().from_runtime_store(store=CustomStateStore(), blobs=CustomBlobStore(), run_id="run-<unsafe>")
        data = report.to_dict()
        self.assertEqual(data["schema_version"], INSPECTOR_SCHEMA_VERSION)
        self.assertEqual(data["source"], {"kind": "runtime_store", "run_id": "run-<unsafe>"})
        self.assertEqual(data["run"]["run_id"], "run-<unsafe>")
        self.assertEqual(data["timeline"][0]["summary"], "tool_name=<script>alert(1)</script>, reason=needs <approval>")
        self.assertEqual(data["tool_ledger"][0]["tool_name"], "<b>danger</b>")

        html = report.to_html()
        self.assertIn("run-&lt;unsafe&gt;", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;danger&lt;/b&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<b>danger</b>", html)
        self.assertNotIn('<img src=x onerror=alert(1)>', html)

        evidence_report = InspectorReportBuilder().from_evidence(
            {
                "schema_version": "agentledger.evidence.v1",
                "bundle_hash": "sha256:custom",
                "run": {"run_id": "run-from-evidence", "status": "completed", "state_version": 1},
                "steps": [],
                "events": [],
                "tool_ledger": [],
                "approval_requests": [],
                "artifacts": [],
                "media_artifacts": [],
                "stream_checkpoints": [],
                "cost_records": [],
                "summary": {"event_count": 0},
                "final_state": {},
            }
        )
        self.assertEqual(evidence_report.to_dict()["schema_version"], INSPECTOR_SCHEMA_VERSION)
        self.assertEqual(evidence_report.to_dict()["run"]["run_id"], "run-from-evidence")

    def test_inspector_report_adds_navigation_anchors_and_related_links(self) -> None:
        evidence = {
            "schema_version": "agentledger.evidence.v1",
            "bundle_hash": "sha256:links",
            "run": {"run_id": "run-links", "status": "completed", "state_version": 1},
            "steps": [{"step_id": "step-1", "run_id": "run-links", "status": "completed", "attempt": 1}],
            "events": [
                {
                    "seq": 1,
                    "event_id": "evt-1",
                    "type": "tool_permission_decided",
                    "step_id": "step-1",
                    "timestamp": 2.0,
                    "payload": {"tool_name": "email.send", "approval_id": "approval-1", "artifact_id": "art-1", "legal_agent_run_id": "agent-run-1"},
                },
                {
                    "seq": 2,
                    "event_id": "evt-2",
                    "type": "step_created",
                    "step_id": "step-1",
                    "timestamp": "1970-01-01T00:00:01Z",
                    "payload": {"step_id": "step-1"},
                }
            ],
            "tool_ledger": [{"tool_name": "email.send", "status": "SUCCEEDED", "external_id": "msg-1", "response_ref": "blob://response"}],
            "approval_requests": [{"approval_id": "approval-1", "step_id": "step-1", "tool_name": "email.send", "risk_level": "high", "status": "PENDING"}],
            "artifacts": [{"artifact_id": "art-1", "name": "receipt", "blob_hash": "sha256:x", "blob_ref": "blob://artifact", "metadata_json": json.dumps({"kind": "receipt", "content_ref": "s3://bucket/receipt.json"})}],
            "media_artifacts": [],
            "stream_checkpoints": [],
            "cost_records": [],
            "summary": {"event_count": 1},
            "final_state": {},
        }
        report = InspectorReportBuilder().from_evidence(evidence)
        data = report.to_dict()

        self.assertEqual(data["timeline"][0]["anchor"], "event-1")
        self.assertEqual(data["steps"][0]["anchor"], "step-step-1")
        self.assertEqual(data["tool_ledger"][0]["anchor"], "tool-email-send")
        self.assertEqual(data["approvals"][0]["anchor"], "approval-approval-1")
        self.assertEqual(data["artifacts"][0]["anchor"], "artifact-art-1")
        self.assertIn({"kind": "step", "value": "step-1", "href": "#step-step-1"}, data["timeline"][0]["related_links"])
        self.assertIn({"kind": "tool", "value": "email.send", "href": "#tool-email-send"}, data["timeline"][0]["related_links"])
        self.assertIn({"kind": "approval", "value": "approval-1", "href": "#approval-approval-1"}, data["timeline"][0]["related_links"])
        self.assertIn({"kind": "artifact", "value": "art-1", "href": "#artifact-art-1"}, data["timeline"][0]["related_links"])
        self.assertEqual(data["agent_run_id"], "agent-run-1")
        self.assertEqual([row["seq"] for row in data["event_stream"]], [2, 1])
        self.assertEqual(data["event_stream"][0]["time"], "1970-01-01 00:00:01 UTC")
        self.assertEqual(data["event_stream"][0]["runtime_run_id"], "run-links")
        self.assertEqual(data["event_stream"][0]["agent_run_id"], "agent-run-1")
        self.assertIn({"kind": "event", "value": "2", "href": "#event-2"}, data["event_stream"][0]["related_links"])

        html = report.to_html()
        self.assertIn('href="#event-stream"', html)
        self.assertIn('class="event-list"', html)
        self.assertIn('class="event-item', html)
        self.assertIn('href="#timeline"', html)
        self.assertIn('class="table-wrap"', html)
        self.assertIn('class="details-row', html)
        self.assertIn('class="record-details"', html)
        self.assertNotIn("<th>Details</th>", html)
        self.assertIn('table-layout: fixed', html)
        self.assertIn('white-space: pre-wrap', html)
        self.assertIn('id="event-1"', html)
        self.assertIn('href="#step-step-1"', html)
        self.assertIn('href="#tool-email-send"', html)
        self.assertIn('href="#approval-approval-1"', html)
        self.assertIn('href="#artifact-art-1"', html)

    def test_inspector_failure_envelopes_cover_non_happy_path_evidence(self) -> None:
        evidence = {
            "schema_version": "agentledger.evidence.v1",
            "bundle_hash": "sha256:failure-read-model",
            "run": {"run_id": "run-failure", "status": "failed", "state_version": 3},
            "steps": [
                {
                    "step_id": "step-retry",
                    "run_id": "run-failure",
                    "status": "retry_scheduled",
                    "attempt": 1,
                    "last_error_type": "TimeoutError",
                    "last_error": "provider timeout",
                    "updated_at": 1.0,
                },
                {
                    "step_id": "step-denied",
                    "run_id": "run-failure",
                    "status": "failed",
                    "attempt": 1,
                    "last_error_type": "ApprovalDenied",
                    "last_error": "operator denied",
                    "updated_at": 4.0,
                },
            ],
            "events": [
                {"seq": 1, "event_id": "evt-1", "type": "step_retry_scheduled", "step_id": "step-retry", "timestamp": 1.0, "payload": {"step_id": "step-retry", "attempt": 1}},
                {"seq": 2, "event_id": "evt-2", "type": "tool_call_failed", "step_id": "step-retry", "timestamp": 2.0},
                {"seq": 3, "event_id": "evt-3", "type": "tool_call_blocked", "step_id": "step-denied", "timestamp": 3.0, "payload": {"tool": "payments.refund", "reason": "policy denied"}},
            ],
            "tool_ledger": [
                {
                    "ledger_id": "ledger-1",
                    "step_id": "step-retry",
                    "tool_name": "payments.charge",
                    "status": "PENDING_VERIFICATION",
                    "idempotency_key": "idem-1",
                    "response_ref": "blob://unknown-response",
                    "updated_at": 2.5,
                }
            ],
            "approval_requests": [
                {
                    "approval_id": "approval-1",
                    "step_id": "step-denied",
                    "tool_name": "payments.refund",
                    "risk_level": "high",
                    "status": "PENDING",
                    "reason": "needs human review",
                    "updated_at": 3.5,
                }
            ],
            "artifacts": [],
            "media_artifacts": [],
            "stream_checkpoints": [],
            "cost_records": [],
            "summary": {"event_count": 3},
            "final_state": {},
        }
        report = InspectorReportBuilder().from_evidence(evidence)
        data = report.to_dict()
        envelopes = data["failure_envelopes"]

        self.assertGreaterEqual(data["summary"]["failure_envelope_count"], 6)
        self.assertTrue(all(row["schema_version"] == FAILURE_ENVELOPE_SCHEMA_VERSION for row in envelopes))
        self.assertIn("unknown_side_effect", {row["status"] for row in envelopes})
        self.assertIn("manual_verification", {row["recoverability"] for row in envelopes})
        self.assertIn("recovery_scheduled", {row["status"] for row in envelopes})
        self.assertIn("blocked", {row["status"] for row in envelopes})
        self.assertIn("waiting_human", {row["status"] for row in envelopes})
        self.assertEqual(data["failure_lifecycle"]["schema_version"], FAILURE_LIFECYCLE_SCHEMA_VERSION)
        self.assertIn("failure_detected", {row["stage"] for row in data["failure_lifecycle"]["events"]})
        self.assertIn("failure_recovery_scheduled", {row["stage"] for row in data["failure_lifecycle"]["events"]})
        self.assertIn("failure_terminal", {row["stage"] for row in data["failure_lifecycle"]["events"]})
        self.assertGreater(data["failure_causal_graph"]["summary"]["failure_node_count"], 0)
        self.assertFalse(data["failure_replay_plan"]["safe_to_replay"])
        self.assertGreaterEqual(data["failure_replay_plan"]["manual_verification_count"], 1)
        self.assertTrue(any(row["kind"] == "unknown_side_effect" for row in data["failure_alerts"]["alerts"]))
        self.assertEqual(data["failure_export"]["schema_version"], FAILURE_EXPORT_SCHEMA_VERSION)
        self.assertIn("langfuse", data["failure_export"]["external_mappings"])
        self.assertIn("opentelemetry", data["failure_export"]["external_mappings"])
        self.assertTrue(any(row.get("source_kind") == "event" and row.get("message") == "tool_call_failed" for row in envelopes))
        self.assertTrue(any({"kind": "step", "value": "step-retry", "href": "#step-step-retry"} in row.get("related_links", []) for row in envelopes))
        self.assertTrue(any({"kind": "event", "value": "3", "href": "#event-3"} in row.get("related_links", []) for row in envelopes))

        html = report.to_html()
        self.assertIn("Failure Envelopes", html)
        self.assertIn("Failure Lifecycle", html)
        self.assertIn("Failure Replay Plan", html)
        self.assertIn("Failure Alerts", html)
        self.assertIn("Failure Causal Nodes", html)
        self.assertIn("unknown_side_effect", html)
        self.assertIn("manual_verification", html)
        self.assertIn('href="#failures"', html)

    def test_inspector_redaction_policy_applies_to_json_and_html(self) -> None:
        evidence = {
            "schema_version": "agentledger.evidence.v1",
            "bundle_hash": "sha256:redaction",
            "run": {"run_id": "run-redaction", "status": "completed", "initial_state": {"password": "secret-password"}},
            "steps": [],
            "events": [
                {
                    "seq": 1,
                    "event_id": "evt-1",
                    "type": "tool_permission_decided",
                    "step_id": "step-1",
                    "payload": {
                        "tool_name": "crm.update",
                        "password": "secret-password",
                        "decision": {
                            "allowed": True,
                            "action_tier": "write_external",
                            "api_token": "secret-token",
                            "findings": [{"evidence": {"password": "nested-secret"}}],
                        },
                    },
                }
            ],
            "tool_ledger": [{"tool_name": "crm.update", "status": "SUCCEEDED", "external_id": "ticket-1", "request": {"api_token": "secret-token"}}],
            "approval_requests": [],
            "artifacts": [{"name": "artifact", "metadata_json": json.dumps({"password": "secret-password"})}],
            "media_artifacts": [],
            "stream_checkpoints": [],
            "cost_records": [],
            "summary": {"event_count": 1, "secret_note": "not matched by key"},
            "final_state": {},
        }
        report = InspectorReportBuilder().from_evidence(
            evidence,
            include_payloads=True,
            redaction_policy=InspectorRedactionPolicy(keys=("password", "api_token")),
        )
        data = report.to_dict()
        serialized = json.dumps(data, ensure_ascii=False)
        html = report.to_html()

        self.assertEqual(data["redaction"]["enabled"], True)
        self.assertIn("password", data["redaction"]["redacted_keys"])
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("nested-secret", serialized)
        self.assertNotIn("secret-password", html)
        self.assertNotIn("secret-token", html)
        self.assertIn("&lt;redacted&gt;", html)
        self.assertIn("secret_note", serialized)

    def test_inspector_cli_accepts_redaction_policy_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agentledger"
            rt, run_id, _ = self._run_side_effect_demo(root)
            evidence_dir = Path(tmp) / "evidence" / run_id
            EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).write_dir(evidence_dir)
            policy_path = Path(tmp) / "redaction.json"
            policy_path.write_text(json.dumps({"keys": ["external_id"], "replacement": "[hidden]"}), encoding="utf-8")
            out_path = Path(tmp) / "inspector.json"

            args = type(
                "Args",
                (),
                {
                    "path": str(evidence_dir),
                    "include_payloads": True,
                    "redact_key": ["request_hash"],
                    "redaction_policy": str(policy_path),
                    "redaction_replacement": "<ignored>",
                    "out": str(out_path),
                    "html": None,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_inspector_evidence(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["inspector_report"], str(out_path))
            written = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(written["schema_version"], INSPECTOR_SCHEMA_VERSION)
            self.assertEqual(written["redaction"]["replacement"], "[hidden]")
            self.assertIn("external_id", written["redaction"]["redacted_keys"])
            self.assertIn("request_hash", written["redaction"]["redacted_keys"])
            self.assertTrue(all(row.get("external_id") == "[hidden]" for row in written["tool_ledger"]))
            self.assertTrue(all(row.get("request_hash") == "[hidden]" for row in written["tool_ledger"]))

    def test_shadow_mode_replays_side_effect_without_external_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agentledger"
            rt, source_run_id, external = self._run_side_effect_demo(root)
            before = json.loads(external.read_text())
            report = asyncio.run(ShadowRunner(rt).run(recovery_agent, source_run_id=source_run_id, agent_role="ShadowAgent"))
            after = json.loads(external.read_text())
            self.assertTrue(report.ok)
            self.assertNotEqual(report.shadow_run_id, source_run_id)
            self.assertEqual(before, after)
            self.assertEqual(len(after), 1)
            self.assertEqual(rt.store.cost_summary(report.shadow_run_id)["tool_calls"], 1.0)

    def test_budget_blocks_extra_tool_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls = {"count": 0}
            rt = Runtime.local(Path(tmp) / ".agentledger", budget=BudgetController(BudgetLimits(max_tool_calls=1)))

            def add(args: dict[str, Any]) -> dict[str, Any]:
                calls["count"] += 1
                return {"sum": args["a"] + args["b"]}

            rt.registry.register(ToolSpec(name="math.add", func=add))
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, state: dict[str, Any]) -> None:
                await ctx.call_tool("math.add", {"a": 1, "b": 2})
                await ctx.call_tool("math.add", {"a": 3, "b": 4})

            with self.assertRaises(BudgetExceeded):
                asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertEqual(calls["count"], 1)
            self.assertEqual(rt.store.cost_summary(run_id)["tool_calls"], 1.0)

    def test_cost_attribution_report_groups_by_agent_step_category_and_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(ToolSpec(name="math.add", func=lambda args: {"sum": args["a"] + args["b"]}))
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                await ctx.call_tool("math.add", {"a": 1, "b": 2})
                await ctx.call_model(
                    {
                        "provider": "mock-llm",
                        "mock_response": "ok",
                        "mock_usage": {"total_tokens": 17},
                        "mock_cost_usd": 0.03,
                    }
                )

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="CostAgent")))
            report = CostAttributionReporter(rt.store).report(run_id).to_dict()
            self.assertEqual(report["total"]["tool_calls"], 1.0)
            self.assertEqual(report["total"]["model_tokens"], 17.0)
            self.assertEqual(report["total"]["total_usd"], 0.03)
            self.assertEqual(report["by_agent"]["CostAgent"]["tool_calls"], 1.0)
            self.assertEqual(report["by_agent"]["CostAgent"]["model_tokens"], 17.0)
            self.assertEqual(report["by_category"]["tool"]["tool:call"], 1.0)
            self.assertEqual(report["by_name"]["math.add"]["tool_calls"], 1.0)
            self.assertEqual(report["by_name"]["mock-llm"]["model_tokens"], 17.0)

            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "policy": None, "sandbox_config": None, "run_id": run_id})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_cost_report(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["run_id"], run_id)
            self.assertEqual(payload["by_agent"]["CostAgent"]["total_usd"], 0.03)

    def test_model_evidence_boundary_records_failure_and_tool_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                ctx.record_model_failure(
                    provider="deepseek",
                    model="deepseek-chat",
                    error_type="RateLimitError",
                    message="rate limited",
                    retryable=True,
                    request={"messages": ["hello"]},
                )
                ctx.record_tool_call_proposal(
                    tool_name="search_contract_clause",
                    arguments={"clause": "payment"},
                    provider="deepseek",
                    model="deepseek-chat",
                    reason="model requested clause search",
                )

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="Researcher")))
            events = [dict(row) for row in rt.store.events(run_id)]
            self.assertTrue(any(event["type"] == "model_call_failed" for event in events))
            self.assertTrue(any(event["type"] == "tool_call_proposed" for event in events))
            failure = FailureAttributionReporter(rt.store).report(run_id).to_dict()
            self.assertTrue(any(item["category"] == "model" for item in failure["failure_envelopes"]))
            report = InspectorDataSource().from_runtime_store(store=rt.store, blobs=rt.blobs, run_id=run_id).to_dict()
            self.assertTrue(any(event["type"] == "model_call_failed" for event in report["timeline"]))

    def test_python_function_adapter_and_decorator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            @python_agent(role="DecoratedAgent")
            async def decorated(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("decorated", True)

            adapter = PythonFunctionAdapter(decorated.as_agent(), role="WrappedAgent")
            ok = asyncio.run(rt.run_once(adapter.as_agent(), run_id=run_id, agent_role="WrappedAgent"))
            self.assertTrue(ok)
            self.assertTrue(rt.store.final_state(run_id)["decorated"])
            self.assertEqual(adapter.map_run_spec()["adapter"], "python-function")

    def test_dependency_free_framework_facades(self) -> None:
        class FakeLangChainRunnable:
            def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
                return {"framework": "langchain", "topic": payload["topic"]}

        class FakeCrew:
            async def akickoff(self, payload: dict[str, Any]) -> dict[str, Any]:
                return {"framework": "crewai", "topic": payload["topic"]}

        class FakeAutoGen:
            def generate_reply(self, payload: dict[str, Any]) -> dict[str, Any]:
                return {"framework": "autogen", "topic": payload["topic"]}

        class FakeOpenAIAgent:
            async def arun(self, payload: dict[str, Any]) -> dict[str, Any]:
                return {"framework": "openai", "topic": payload["topic"]}

        class FakeLlamaIndexQueryEngine:
            def query(self, payload: dict[str, Any]) -> dict[str, Any]:
                return {"framework": "llamaindex", "topic": payload["topic"]}

        class FakeSemanticKernel:
            async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
                return {"framework": "semantic-kernel", "topic": payload["topic"]}

        adapters = [
            LangChainRunnableAdapter(FakeLangChainRunnable()),
            CrewAIAdapter(FakeCrew()),
            AutoGenAdapter(FakeAutoGen()),
            OpenAIAgentsSDKAdapter(FakeOpenAIAgent()),
            LlamaIndexAdapter(FakeLlamaIndexQueryEngine()),
            SemanticKernelAdapter(FakeSemanticKernel()),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            for adapter in adapters:
                run_id, _ = rt.create_run(initial_state={"topic": adapter.name})
                self.assertTrue(asyncio.run(rt.run_once(adapter.as_agent(), run_id=run_id, agent_role=adapter.role)))
                final_state = rt.store.final_state(run_id)
                output_key = adapter.output_key
                self.assertIsNotNone(output_key)
                self.assertEqual(final_state[output_key]["topic"], adapter.name)

    def test_framework_adapter_conformance_runner_passes_for_facade(self) -> None:
        class FakeLangChainRunnable:
            def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
                return {"framework": "langchain", "topic": payload["topic"]}

        report = FrameworkAdapterConformanceRunner(
            lambda: LangChainRunnableAdapter(FakeLangChainRunnable(), output_key="adapter_output"),
            name="langchain-adapter",
        ).run()
        self.assertTrue(report.passed, report.to_dict())
        self.assertEqual(
            {check.name for check in report.checks},
            {"run_spec_maps_adapter", "runtime_run_once_completes", "evidence_export_works"},
        )

    def test_cli_adapter_conformance_outputs_certification_report(self) -> None:
        args = type("Args", (), {"kind": "semantic-kernel"})()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cmd_adapter_conformance(args)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["passed"], payload)
        self.assertEqual(payload["kind"], "semantic-kernel")
        self.assertEqual(payload["report"]["name"], "semantic-kernel-adapter")

    def test_adapter_certification_bundle_marks_external_validation(self) -> None:
        bundle = build_adapter_certification_bundle("postgres", adapter_version="1.2.0").to_dict()
        self.assertEqual(bundle["schema"], "agentledger.adapter_certification.v1")
        self.assertEqual(bundle["adapter"], "postgres")
        self.assertEqual(bundle["package_name"], "agentledger-postgres")
        self.assertEqual(bundle["agentledger_contract_version"], "1.0")
        self.assertIn("postgres", bundle["required_external_services"])
        self.assertTrue(bundle["production_validation"]["required"])
        self.assertEqual(bundle["production_validation"]["status"], "external-required")

        langgraph = build_adapter_certification_bundle("langgraph", adapter_version="1.2.0", package_name="custom-langgraph").to_dict()
        self.assertEqual(langgraph["package_name"], "custom-langgraph")
        self.assertFalse(langgraph["production_validation"]["required"])
        self.assertEqual(langgraph["production_validation"]["status"], "local-contract-verified")

    def test_cli_adapter_certify_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "postgres-certification.json"
            args = type("Args", (), {"kind": "postgres", "adapter_version": "1.2.0", "package_name": None, "out": str(out)})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_adapter_certify(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["certification_bundle"], str(out))
            bundle = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(bundle["adapter_version"], "1.2.0")
            self.assertEqual(bundle["production_validation"]["status"], "external-required")

    def test_policy_yaml_allows_and_denies_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                """version: 1
defaults:
  low: allow
  high: deny
roles:
  ExecutorAgent:
    allow_tools:
      - github.create_issue
    deny_tools:
      - shell.exec
  ReaderAgent:
    allow_risk:
      - low
    deny_risk:
      - sensitive
""",
                encoding="utf-8",
            )
            policy = PolicyEngine.from_file(policy_path)
            self.assertTrue(policy.check_tool("ExecutorAgent", "github.create_issue", "medium")[0])
            self.assertFalse(policy.check_tool("ExecutorAgent", "shell.exec", "high")[0])
            self.assertTrue(policy.check_tool("ReaderAgent", "docs.read", "low")[0])
            self.assertFalse(policy.check_tool("ReaderAgent", "secrets.read", "sensitive")[0])

    def test_policy_engine_evaluates_normalized_decision_contract(self) -> None:
        policy = PolicyEngine()
        policy.allow_tool("TravelPlanner", "video.extract_frames")
        request = PolicyRequest.for_tool(
            role="TravelPlanner",
            tool_name="video.extract_frames",
            risk_level="medium",
            side_effect="external_read",
            sandbox_required=True,
            subject={"kind": "sub_agent", "id": "agent_child_1"},
            resource={"kind": "media_artifact", "media_kind": "video", "ref": "blob://video-1"},
            context={"run_id": "run_1", "step_id": "step_1", "parent_run_id": "run_parent", "delegated_by": "PlannerAgent"},
        )
        decision = policy.evaluate(request)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.action_tier, "L5")
        self.assertEqual(decision.subject_scope, "TravelPlanner")
        self.assertIn("sandbox", {control.kind for control in decision.controls})
        self.assertIn("media_resource_boundary", {finding.id for finding in decision.findings})
        self.assertIn("delegation_context_present", {finding.id for finding in decision.findings})

    def test_tool_gateway_records_policy_decision_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(ToolSpec(name="docs.read", func=lambda args: {"ok": True}, side_effect="none", risk_level="low"))
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("read", await ctx.call_tool("docs.read", {"path": "README.md"}))

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ReaderAgent")))
            permission_events = [json.loads(row["payload_ref"]) for row in rt.store.events(run_id) if row["type"] == "tool_permission_decided"]
            self.assertEqual(len(permission_events), 1)
            decision = permission_events[0]["decision"]
            self.assertEqual(decision["effect"], "allow")
            self.assertEqual(decision["action_tier"], "L2")
            self.assertEqual(decision["risk_level"], "low")
            self.assertIn("audit", {control["kind"] for control in decision["controls"]})

    def test_mcp_tool_adapter_registers_runtime_managed_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[tuple[str, dict[str, Any]]] = []
            rt = Runtime.local(Path(tmp) / ".agentledger")

            def client_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
                calls.append((name, args))
                return {"external_id": "DOC-1", "content": "ok"}

            descriptor = {
                "name": "mcp.docs.write",
                "inputSchema": {"required": ["path"]},
                "annotations": {"side_effect": "external_write", "risk_level": "medium", "idempotency_required": True},
            }
            MCPToolAdapter(client_call).register(rt.registry, descriptor)
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, state: dict[str, Any]) -> None:
                result = await ctx.call_tool("mcp.docs.write", {"path": "README.md", "_logical_operation": "write-doc"})
                ctx.write_state_patch("doc", result)

            ok = asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertTrue(ok)
            self.assertEqual(calls, [("mcp.docs.write", {"path": "README.md", "_logical_operation": "write-doc"})])
            self.assertEqual(rt.store.ledger(run_id)[0]["status"], "SUCCEEDED")

    def test_mcp_tool_adapter_maps_governance_annotations(self) -> None:
        descriptor = {
            "name": "mcp.github.create_pr",
            "inputSchema": {"type": "object", "required": ["title"]},
            "annotations": {
                "side_effect": "external_write",
                "risk_level": "high",
                "idempotency_required": True,
                "approval_required": True,
                "sandbox_required": True,
                "sandbox_executor": "docker",
                "sandbox_policy": {"network": "deny", "filesystem": "read-only"},
            },
        }
        spec = MCPToolAdapter(lambda _name, _args: {"ok": True}).tool_spec_from_descriptor(descriptor)
        self.assertEqual(spec.side_effect, "external_write")
        self.assertEqual(spec.risk_level, "high")
        self.assertTrue(spec.idempotency_required)
        self.assertTrue(spec.approval_required)
        self.assertTrue(spec.sandbox_required)
        self.assertEqual(spec.sandbox_executor, "docker")
        self.assertEqual(spec.sandbox_policy["network"], "deny")

    def test_mcp_context_adapter_routes_resource_reads_through_tool_gateway(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            context_server = InMemoryMCPContextServer()
            context_server.add_resource(uri="agentledger://notes/one", name="Note One", reader=lambda uri: {"uri": uri, "body": "hello"})
            MCPContextAdapter(context_server.read_resource).register_read_tool(rt.registry)

            tool_server = InMemoryMCPToolServer()
            tool_server.add_tool(
                {"name": "mcp.echo", "inputSchema": {"type": "object", "required": ["text"]}, "annotations": {"side_effect": "none", "risk_level": "low"}},
                lambda name, args: {"tool": name, "text": args["text"]},
            )
            MCPToolAdapter(tool_server.call_tool).register_all(rt.registry, tool_server.list_tools())
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                resource = await ctx.call_tool("mcp.context.read", {"uri": "agentledger://notes/one"})
                echo = await ctx.call_tool("mcp.echo", {"text": "ok"})
                ctx.write_state_patch("resource", resource)
                ctx.write_state_patch("echo", echo)

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="MCPAgent")))
            final_state = rt.store.final_state(run_id)
            self.assertEqual(final_state["resource"]["content"]["body"], "hello")
            self.assertEqual(final_state["echo"]["text"], "ok")
            self.assertEqual(context_server.list_resources()[0]["uri"], "agentledger://notes/one")
            self.assertEqual({spec.name for spec in rt.registry.list()}, {"mcp.context.read", "mcp.echo"})

    def test_langgraph_adapter_skeleton_checkpoint_and_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={"x": 1})
            checkpointer = LangGraphCheckpointerAdapter(rt)
            checkpoint = checkpointer.checkpoint_from_run(run_id)
            self.assertEqual(checkpoint["state"], {"x": 1})
            checkpointer.persist_checkpoint(run_id, {"node": "plan", "value": 42})
            self.assertEqual(rt.store.final_state(run_id)["langgraph_checkpoint"]["value"], 42)
            config = checkpointer.config_for_run(run_id, thread_id="thread-1")
            next_config = checkpointer.put(config, {"channel_values": {"x": 2}}, {"source": "unit"}, {"x": 2})
            self.assertIn("checkpoint_id", next_config["configurable"])
            checkpointer.put_writes(next_config, [("messages", ["hello"])], task_id="task-1", task_path="planner")
            item = checkpointer.get_tuple(next_config)
            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(item["checkpoint"]["channel_values"]["x"], 2)
            self.assertEqual(item["metadata"]["source"], "unit")
            self.assertEqual(item["pending_writes"][0]["task_id"], "task-1")
            self.assertEqual(checkpointer.get(next_config)["channel_values"]["x"], 2)
            self.assertEqual(len(checkpointer.list(next_config)), 1)

            async def node(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("node_ok", True)

            node_run_id, _ = rt.create_run(initial_state={})
            ok = asyncio.run(rt.run_once(LangGraphNodeAdapter(node).as_agent(), run_id=node_run_id, agent_role="LangGraphAgent"))
            self.assertTrue(ok)
            self.assertTrue(rt.store.final_state(node_run_id)["node_ok"])

    def test_protocols_match_local_implementations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            self.assertIsInstance(rt.store, StateStoreProtocol)
            self.assertIsInstance(rt.blobs, BlobStoreProtocol)

    def test_blob_store_conformance_passes_for_local_and_s3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local_report = BlobStoreConformanceRunner(lambda: __import__("agentledger").LocalBlobStore(Path(tmp) / "blobs"), name="local").run()
            self.assertTrue(local_report.passed, local_report.to_dict())

        def s3_factory() -> S3BlobStore:
            return S3BlobStore(S3BlobStoreConfig(bucket="agentledger-test", prefix="runs"), client=FakeS3Client())

        s3_report = BlobStoreConformanceRunner(s3_factory, name="s3-fake").run()
        self.assertTrue(s3_report.passed, s3_report.to_dict())

    def test_media_runtime_conformance_runner_passes_for_local_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            report = MediaRuntimeConformanceRunner(lambda: rt).run()
            self.assertTrue(report.passed, report.to_dict())
            self.assertEqual({check.name for check in report.checks}, {"media_evidence_replay_chain", "media_tool_ledger_chain"})

    def test_cli_conformance_reports_state_and_blob_stores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "policy": None, "sandbox_config": None})()
            with contextlib.redirect_stdout(stdout):
                cmd_conformance(args)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["passed"], payload)
            self.assertTrue(payload["reports"]["state_store"]["passed"], payload)
            self.assertTrue(payload["reports"]["blob_store"]["passed"], payload)
            self.assertTrue(payload["reports"]["media_runtime"]["passed"], payload)

    def test_cli_blob_conformance_supports_local_and_injected_s3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local_args = type(
                "Args",
                (),
                {"root": str(Path(tmp) / ".agentledger"), "backend": "local", "path": None},
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_blob_conformance(local_args)
            local_payload = json.loads(stdout.getvalue())
            self.assertTrue(local_payload["passed"], local_payload)
            self.assertEqual(local_payload["backend"], "local")

        s3_args = type(
            "Args",
            (),
            {
                "root": ".agentledger",
                "backend": "s3",
                "bucket": "agentledger-test",
                "prefix": "cli/blobs",
                "endpoint_url": "http://minio.local:9000",
                "region": None,
                "profile": None,
            },
        )()
        self.assertIsInstance(create_blob_store(s3_args, s3_client=FakeS3Client()), S3BlobStore)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cmd_blob_conformance(s3_args, s3_client=FakeS3Client())
        s3_payload = json.loads(stdout.getvalue())
        self.assertTrue(s3_payload["passed"], s3_payload)
        self.assertEqual(s3_payload["backend"], "s3")

    def test_s3_config_from_env_supports_minio_and_requires_bucket(self) -> None:
        config = S3BlobStoreConfig.from_env(
            {
                "AGENTLEDGER_S3_BUCKET": "agentledger-runs",
                "AGENTLEDGER_S3_PREFIX": "team/blobs",
                "AGENTLEDGER_S3_ENDPOINT_URL": "http://localhost:9000",
                "AGENTLEDGER_S3_REGION": "us-east-1",
                "AGENTLEDGER_S3_PROFILE": "dev",
            }
        )
        self.assertEqual(config.bucket, "agentledger-runs")
        self.assertEqual(config.prefix, "team/blobs")
        self.assertEqual(config.endpoint_url, "http://localhost:9000")
        self.assertEqual(config.region_name, "us-east-1")
        self.assertEqual(config.profile_name, "dev")
        self.assertEqual(config.to_dict()["bucket"], "agentledger-runs")
        with self.assertRaises(ValueError):
            S3BlobStoreConfig.from_env({})

    def test_s3_blob_store_uses_content_addressed_s3_refs(self) -> None:
        client = FakeS3Client()
        blobs = S3BlobStore(S3BlobStoreConfig(bucket="agentledger-test", prefix="runtime/blobs", endpoint_url="http://minio.local:9000"), client=client)
        digest, ref = blobs.put_json({"answer": 42})
        self.assertTrue(digest.startswith("sha256:"))
        self.assertTrue(ref.startswith("s3://agentledger-test/runtime/blobs/sha256/"))
        self.assertEqual(blobs.get_json(ref), {"answer": 42})
        self.assertEqual(client.puts[0]["ContentType"], "application/json")
        self.assertEqual(client.puts[0]["Metadata"]["agentledger-digest"], digest)
        with self.assertRaises(ValueError):
            blobs.get_json("s3://other-bucket/runtime/blobs/sha256/nope.json")
        with self.assertRaises(ValueError):
            blobs.get_json("s3://agentledger-test/")

    def test_context_heartbeat_extends_lease_and_records_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, state: dict[str, Any]) -> None:
                lease_until = ctx.heartbeat(lease_seconds=120)
                ctx.write_state_patch("lease_until", lease_until)

            ok = asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="ExecutorAgent", lease_seconds=60))
            self.assertTrue(ok)
            event_types = [row["type"] for row in rt.store.events(run_id)]
            self.assertIn("worker_heartbeat", event_types)
            self.assertGreater(rt.store.final_state(run_id)["lease_until"], 0)

    def test_expired_lease_recovery_fences_old_worker_and_allows_new_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, step_id = rt.create_run(initial_state={})
            old_claim = rt.store.claim_step(worker_id="worker-a", run_id=run_id, lease_seconds=0)
            self.assertIsNotNone(old_claim)
            assert old_claim is not None

            recovered = RuntimeScheduler(rt.store).recover_expired_leases()
            self.assertEqual(recovered.recovered_steps, 1)
            with self.assertRaises(RuntimeError):
                rt.store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token=old_claim.lease_token, base_version=0, patch={"stale": True})
            new_claim = rt.store.claim_step(worker_id="worker-b", run_id=run_id)
            self.assertIsNotNone(new_claim)
            assert new_claim is not None
            self.assertEqual(new_claim.attempt, 2)

    def test_cancel_run_fences_running_worker_and_blocks_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, step_id = rt.create_run(initial_state={})
            claim = rt.store.claim_step(worker_id="worker-a", run_id=run_id)
            self.assertIsNotNone(claim)
            assert claim is not None
            cancelled = RuntimeScheduler(rt.store).cancel_run(run_id, reason="test cancel")
            self.assertEqual(cancelled, 1)
            self.assertEqual(rt.store.run(run_id)["status"], "cancelled")
            with self.assertRaises(RuntimeError):
                rt.store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token=claim.lease_token, base_version=0, patch={"late": True})
            self.assertIsNone(rt.store.claim_step(worker_id="worker-b", run_id=run_id))

    def test_retry_policy_exhaustion_marks_step_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, step_id = rt.create_run(initial_state={}, retry_policy={"max_attempts": 1})

            async def flaky(ctx: Any, state: dict[str, Any]) -> None:
                raise SimulatedCrash("retry budget exhausted")

            ok = asyncio.run(rt.run_once(flaky, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertFalse(ok)
            self.assertEqual(rt.store.run(run_id)["status"], "failed")
            step = rt.store.conn.execute("SELECT status, last_error_type FROM steps WHERE step_id=?", (step_id,)).fetchone()
            self.assertEqual(step["status"], "failed")
            self.assertEqual(step["last_error_type"], "SimulatedCrash")
            event_types = [row["type"] for row in rt.store.events(run_id)]
            self.assertIn("failure_classified", event_types)

    def test_failure_injection_suite_exercises_reliability_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = FailureInjectionSuite(Path(tmp)).run()
            self.assertTrue(report.passed, report.to_dict())
            names = {check.name for check in report.checks}
            self.assertEqual(names, {"side_effect_crash", "retry_exhaustion", "lease_fencing", "cancellation_fencing"})

    def test_cli_failure_inject_outputs_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "scenario": "lease_fencing"})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_failure_inject(args)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["passed"], payload)
            self.assertEqual(payload["checks"][0]["name"], "lease_fencing")

    def test_failure_attribution_report_summarizes_failed_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={}, retry_policy={"max_attempts": 1})

            async def flaky(ctx: Any, state: dict[str, Any]) -> None:
                raise RetryableAgentError("failure attribution smoke")

            self.assertFalse(asyncio.run(rt.run_once(flaky, run_id=run_id, agent_role="FailureAgent")))
            report = FailureAttributionReporter(rt.store).report(run_id).to_dict()
            self.assertEqual(report["run_status"], "failed")
            self.assertEqual(report["summary"]["failed_step_count"], 1)
            self.assertGreaterEqual(report["summary"]["failure_envelope_count"], 3)
            self.assertGreaterEqual(report["summary"]["terminal_failure_count"], 1)
            self.assertEqual(report["root_causes"][0]["kind"], "failed_step")
            self.assertEqual(report["root_causes"][0]["error_type"], "RetryableAgentError")
            self.assertTrue(any(event["type"] == "failure_classified" for event in report["failure_events"]))
            self.assertTrue(any(row["schema_version"] == FAILURE_ENVELOPE_SCHEMA_VERSION for row in report["failure_envelopes"]))
            self.assertTrue(any(row["status"] == "terminal" and row["step_id"] for row in report["failure_envelopes"]))
            self.assertEqual(report["failure_lifecycle"]["schema_version"], FAILURE_LIFECYCLE_SCHEMA_VERSION)
            self.assertIn("failure_terminal", {row["stage"] for row in report["failure_lifecycle"]["events"]})
            self.assertGreater(report["failure_causal_graph"]["summary"]["failure_node_count"], 0)
            self.assertTrue(report["failure_replay_plan"]["safe_to_replay"])
            self.assertGreaterEqual(report["failure_alerts"]["alert_count"], 1)
            self.assertEqual(report["failure_export"]["schema_version"], FAILURE_EXPORT_SCHEMA_VERSION)
            self.assertIn("temporal", report["failure_export"]["external_mappings"])

            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "policy": None, "sandbox_config": None, "run_id": run_id})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_failure_report(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["run_id"], run_id)
            self.assertEqual(payload["summary"]["root_cause_count"], 1)
            self.assertEqual(payload["summary"]["failure_envelope_count"], report["summary"]["failure_envelope_count"])

            export_path = Path(tmp) / "failure-export.json"
            export_args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "policy": None, "sandbox_config": None, "run_id": run_id, "out": str(export_path)})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_failure_export(export_args)
            export_payload = json.loads(stdout.getvalue())
            self.assertEqual(export_payload["schema_version"], FAILURE_EXPORT_SCHEMA_VERSION)
            self.assertTrue(export_path.exists())

    def test_failure_regression_analyzer_classifies_new_fixed_and_recurring_failures(self) -> None:
        baseline = {
            "failure_envelopes": [
                {"failure_id": "old", "category": "tool", "status": "terminal", "owner": "tool", "message": "timeout", "tool_name": "search"},
                {"failure_id": "fixed", "category": "policy", "status": "blocked", "owner": "policy", "message": "denied", "tool_name": "refund"},
            ]
        }
        current = {
            "failure_envelopes": [
                {"failure_id": "new-id", "category": "tool", "status": "terminal", "owner": "tool", "message": "timeout", "tool_name": "search"},
                {"failure_id": "new", "category": "model", "status": "terminal", "owner": "model", "message": "rate limit", "tool_name": None},
            ]
        }
        report = FailureRegressionAnalyzer().compare(baseline, current)
        self.assertFalse(report["same"])
        self.assertEqual(report["summary"]["recurring_failure_count"], 1)
        self.assertEqual(report["summary"]["fixed_failure_count"], 1)
        self.assertEqual(report["summary"]["new_failure_count"], 1)

        with tempfile.TemporaryDirectory() as tmp:
            baseline_path = Path(tmp) / "baseline.json"
            current_path = Path(tmp) / "current.json"
            out_path = Path(tmp) / "regression.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            current_path.write_text(json.dumps(current), encoding="utf-8")
            args = type("Args", (), {"baseline": str(baseline_path), "current": str(current_path), "out": str(out_path), "fail_on_regression": False})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_failure_regress(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_regression"], str(out_path))
            written = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(written["summary"]["new_failure_count"], 1)

    def test_scheduler_status_reports_runtime_control_plane_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})
            status = RuntimeScheduler(rt.store).status(run_id)
            self.assertEqual(status["run_id"], run_id)
            self.assertEqual(status["run_status"], "pending")
            self.assertEqual(len(status["steps"]), 1)

    def test_evidence_bundle_can_write_directory_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            target = Path(tmp) / "evidence"
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
            path = bundle.write_dir(target)
            self.assertEqual(path, target)
            for name in ["manifest.json", "bundle.json", "events.jsonl", "summary.json", "steps.json", "tool_ledger.json", "cost_records.json", "artifacts.json", "media_artifacts.json", "stream_checkpoints.json", "final_state.json"]:
                self.assertTrue((target / name).exists(), name)
            manifest = json.loads((target / "manifest.json").read_text())
            self.assertEqual(manifest["run_id"], run_id)
            event_lines = (target / "events.jsonl").read_text().strip().splitlines()
            self.assertEqual(len(event_lines), bundle.to_dict()["summary"]["event_count"])

    def test_evidence_bundle_can_write_static_html_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            html_path = Path(tmp) / "evidence.html"
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
            self.assertEqual(bundle.write_html(html_path), html_path)
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("AgentLedger Evidence Report", html)
            self.assertIn(run_id, html)
            self.assertIn("Tool Ledger", html)
            self.assertIn("Media Artifacts", html)
            self.assertIn('class="details-row', html)
            self.assertIn('class="record-details"', html)
            self.assertNotIn("<th>Details</th>", html)

            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "policy": None, "sandbox_config": None, "run_id": run_id, "html": str(Path(tmp) / "cli-evidence.html"), "dir": None, "out": None})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_evidence(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["evidence_html"], str(Path(tmp) / "cli-evidence.html"))
            self.assertTrue(Path(payload["evidence_html"]).exists())

    def test_backup_readiness_check_is_read_only_and_verifies_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            report = BackupReadinessChecker(store=rt.store, blobs=rt.blobs).check_run(run_id)
            self.assertTrue(report.passed, report.to_dict())
            self.assertGreater(report.refs_checked, 0)
            self.assertEqual(report.missing_refs, [])

            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "policy": None, "sandbox_config": None, "run_id": run_id})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_backup_check(args)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["passed"], payload)
            self.assertEqual(payload["run_id"], run_id)

    def test_local_worker_retries_until_idle_and_completes_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={}, retry_policy={"max_attempts": 3})
            attempts = {"count": 0}

            async def transient(ctx: Any, state: dict[str, Any]) -> None:
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise RetryableAgentError("first attempt fails")
                ctx.write_state_patch("attempts", attempts["count"])

            summary = asyncio.run(LocalWorker(rt, transient, worker_id="worker-test", agent_role="WorkerAgent").run_until_idle(run_id=run_id, max_iterations=5))
            self.assertEqual(summary.attempts, 2)
            self.assertEqual(summary.succeeded_attempts, 1)
            self.assertEqual(summary.final_status, "completed")
            self.assertEqual(rt.store.final_state(run_id)["attempts"], 2)

    def test_worker_service_loops_until_terminal_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={}, retry_policy={"max_attempts": 3})
            attempts = {"count": 0}

            async def transient(ctx: Any, state: dict[str, Any]) -> None:
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise RetryableAgentError("first service attempt fails")
                ctx.write_state_patch("attempts", attempts["count"])
                ctx.write_state_patch("worker_service", True)

            summary = asyncio.run(
                WorkerService(rt, transient, worker_id="worker-service-test", agent_role="WorkerAgent").serve(
                    run_id=run_id,
                    max_loops=5,
                    max_idle_polls=1,
                    idle_sleep_seconds=0,
                )
            )
            self.assertEqual(summary.attempts, 2)
            self.assertEqual(summary.succeeded_attempts, 1)
            self.assertEqual(summary.stopped_reason, "terminal_status")
            self.assertEqual(summary.final_status, "completed")
            self.assertTrue(rt.store.final_state(run_id)["worker_service"])

    def test_worker_service_can_stop_before_next_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            async def idle_agent(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("done", True)

            service = WorkerService(rt, idle_agent, worker_id="worker-stop-test")
            service.request_stop("unit_stop")
            summary = asyncio.run(service.serve(run_id=run_id, max_loops=5, idle_sleep_seconds=0))
            self.assertEqual(summary.attempts, 0)
            self.assertEqual(summary.stopped_reason, "unit_stop")
            self.assertEqual(rt.store.run(run_id)["status"], "pending")

    def test_worker_deployment_plan_builds_supervision_recipe(self) -> None:
        plan = build_worker_deployment_plan(
            agent_entrypoint="examples/transient_retry",
            root=".agentledger-worker",
            backend="postgres",
            replicas=2,
            worker_id_prefix="agent-worker",
            lease_seconds=90,
            max_idle_polls=None,
            idle_sleep_seconds=0.5,
        )
        payload = plan.to_dict()
        self.assertEqual(payload["replicas"], 2)
        self.assertEqual(payload["commands"][0][:5], ["agentledger", "--root", ".agentledger-worker", "worker", "serve"])
        self.assertIn("--install-signal-handlers", payload["commands"][0])
        self.assertEqual(payload["commands"][0][-2:], ["--max-idle-polls", "0"])
        self.assertIn(["agentledger", "--root", ".agentledger-worker", "migrate", "status", "--dialect", "postgres"], payload["readiness_checks"])
        self.assertIn("lease fencing", payload["shutdown"]["safe_restart"])

    def test_cli_worker_plan_outputs_json_recipe(self) -> None:
        args = type(
            "Args",
            (),
            {
                "root": ".agentledger-plan",
                "example": "examples/transient_retry",
                "backend": "sqlite",
                "replicas": 2,
                "worker_id_prefix": "worker",
                "lease_seconds": 60,
                "max_idle_polls": 3,
                "idle_sleep_seconds": 0.1,
                "daemon": False,
            },
        )()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cmd_worker_plan(args)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["replicas"], 2)
        self.assertEqual(payload["commands"][1][7], "worker-2")
        self.assertEqual(payload["max_idle_polls"], 3)

    def test_cli_worker_serve_runs_transient_retry_example(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = type(
                "Args",
                (),
                {
                    "root": str(Path(tmp) / ".agentledger"),
                    "policy": None,
                    "sandbox_config": None,
                    "example": "examples/transient_retry",
                    "run_id": None,
                    "worker_id": "worker-cli-service",
                    "lease_seconds": 60,
                    "max_loops": 5,
                    "max_idle_polls": 1,
                    "idle_sleep_seconds": 0,
                    "max_attempts": 3,
                    "install_signal_handlers": False,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_worker_serve(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["summary"]["stopped_reason"], "terminal_status")
            self.assertTrue(payload["final_state"]["worker_service"])

    def test_state_store_conformance_runner_passes_for_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            report = StateStoreConformanceRunner(lambda: rt.store, name="sqlite-local").run()
            self.assertTrue(report.passed, report.to_dict())
            self.assertEqual({check.name for check in report.checks}, {"create_claim_commit", "stale_lease_rejected", "expired_lease_recovered", "cancel_fences_worker"})

    def test_worker_conformance_runner_passes_for_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"

            def factory() -> SQLiteStore:
                store = SQLiteStore(db_path)
                store.init()
                return store

            report = WorkerConformanceRunner(factory, name="sqlite-worker", workers=4, concurrent=True).run()
            self.assertTrue(report.passed, report.to_dict())
            self.assertEqual(
                {check.name for check in report.checks},
                {"multi_worker_claims_distinct_steps", "heartbeat_fences_wrong_owner", "recovery_fences_previous_owner"},
            )

    def test_evidence_diff_detects_state_and_event_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")

            async def agent_a(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("value", "a")

            async def agent_b(ctx: Any, state: dict[str, Any]) -> None:
                await ctx.create_artifact("note", {"value": "b"})
                ctx.write_state_patch("value", "b")

            left_id, _ = rt.create_run(initial_state={})
            right_id, _ = rt.create_run(initial_state={})
            asyncio.run(rt.run_once(agent_a, run_id=left_id, agent_role="DiffAgent"))
            asyncio.run(rt.run_once(agent_b, run_id=right_id, agent_role="DiffAgent"))
            left = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(left_id)
            right = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(right_id)
            report = EvidenceDiffer().compare(left, right)
            self.assertFalse(report.same)
            self.assertIn("value", report.changes["final_state"]["changed"])
            self.assertGreater(report.changes["event_types"]["changed_count"], 0)

    def test_evidence_diff_can_load_bundle_file_or_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
            file_path = bundle.write(Path(tmp) / "bundle.json")
            dir_path = bundle.write_dir(Path(tmp) / "bundle-dir")
            file_data = load_evidence_path(file_path)
            dir_data = load_evidence_path(dir_path)
            self.assertEqual(file_data["bundle_hash"], dir_data["bundle_hash"])
            self.assertTrue(EvidenceDiffer().compare(file_data, dir_data).same)

    def test_divergence_report_compares_runtime_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")

            async def agent_a(ctx: Any, state: dict[str, Any]) -> None:
                response = await ctx.call_model({"provider": "mock", "mock_response": "alpha", "mock_usage": {"total_tokens": 3}, "mock_cost_usd": 0.01})
                await ctx.create_artifact("note", {"value": "alpha"})
                ctx.write_state_patch("answer", response["content"])

            async def agent_b(ctx: Any, state: dict[str, Any]) -> None:
                response = await ctx.call_model({"provider": "mock", "mock_response": "beta", "mock_usage": {"total_tokens": 5}, "mock_cost_usd": 0.02})
                await ctx.create_artifact("note", {"value": "beta"})
                ctx.write_state_patch("answer", response["content"])

            left_id, _ = rt.create_run(initial_state={})
            right_id, _ = rt.create_run(initial_state={})
            self.assertTrue(asyncio.run(rt.run_once(agent_a, run_id=left_id, agent_role="DivergenceAgent")))
            self.assertTrue(asyncio.run(rt.run_once(agent_b, run_id=right_id, agent_role="DivergenceAgent")))
            left = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(left_id).to_dict()
            right = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(right_id).to_dict()
            report = DivergenceReporter().compare(left, right).to_dict()
            self.assertFalse(report["same"])
            self.assertIn("state", report["changed_dimensions"])
            self.assertIn("artifacts", report["changed_dimensions"])
            self.assertIn("cost", report["changed_dimensions"])
            self.assertIn("model_outputs", report["changed_dimensions"])

            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "policy": None, "sandbox_config": None, "left": left_id, "right": right_id, "evidence_paths": False, "fail_on_divergence": False})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_divergence(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["left_run_id"], left_id)
            self.assertIn("model_outputs", payload["changed_dimensions"])

    def test_media_stream_divergence_reports_specific_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")

            async def media_agent(ctx: Any, state: dict[str, Any]) -> None:
                index = int(state["index"])
                await ctx.create_media_artifact(
                    "frame",
                    "frame",
                    uri=f"s3://media/run/frame-{index:04d}.jpg",
                    media_metadata=MediaMetadata(kind="frame", mime_type="image/jpeg", frame_index=index, timestamp_start_seconds=float(index)),
                    lineage=ArtifactLineage(source_blob_refs=["s3://media/run/video.mp4"], tool_call_ids=["video.extract_frames"]),
                )
                await ctx.create_stream_checkpoint(
                    "camera-checkpoint",
                    stream_id="camera-1",
                    consumer_id="vision-agent",
                    offset=index,
                    watermark=float(index),
                    chunk=StreamChunkRef(stream_id="camera-1", chunk_id=f"chunk-{index}", offset=index, content_ref=f"blob://sha256/chunk-{index}.json", sequence=index),
                )
                ctx.write_state_patch("index", index)

            left_id, _ = rt.create_run(initial_state={"index": 1})
            right_id, _ = rt.create_run(initial_state={"index": 2})
            self.assertTrue(asyncio.run(rt.run_once(media_agent, run_id=left_id, agent_role="MediaAgent")))
            self.assertTrue(asyncio.run(rt.run_once(media_agent, run_id=right_id, agent_role="MediaAgent")))
            left = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(left_id).to_dict()
            right = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(right_id).to_dict()

            diff = EvidenceDiffer().compare(left, right).to_dict()
            self.assertGreater(diff["changes"]["media_artifacts"]["changed_count"], 0)
            self.assertGreater(diff["changes"]["stream_checkpoints"]["changed_count"], 0)

            report = DivergenceReporter().compare(left, right).to_dict()
            self.assertIn("media_artifacts", report["changed_dimensions"])
            self.assertIn("stream_checkpoints", report["changed_dimensions"])

            regression = EvidenceRegressionRunner().evaluate_regression(left, right, require_same_final_state=False)
            regression_checks = {check.name: check for check in regression.checks}
            self.assertFalse(regression_checks["media_artifact_regression"].passed)
            self.assertFalse(regression_checks["stream_checkpoint_regression"].passed)
            allowed = EvidenceRegressionRunner().evaluate_regression(
                left,
                right,
                require_same_final_state=False,
                require_same_media_artifacts=False,
                require_same_stream_checkpoints=False,
            )
            self.assertTrue(allowed.passed)

    def test_cli_regression_flags_allow_media_stream_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")

            def media_agent(index: int) -> Any:
                async def agent(ctx: Any, _state: dict[str, Any]) -> None:
                    await ctx.create_media_artifact(
                        "frame",
                        "frame",
                        uri=f"s3://media/run/frame-{index:04d}.jpg",
                        media_metadata=MediaMetadata(kind="frame", mime_type="image/jpeg", frame_index=index),
                    )
                    await ctx.create_stream_checkpoint(
                        "camera-checkpoint",
                        stream_id="camera-1",
                        consumer_id="vision-agent",
                        offset=index,
                    )
                    ctx.write_state_patch("done", True)

                return agent

            left_id, _ = rt.create_run(initial_state={})
            right_id, _ = rt.create_run(initial_state={})
            self.assertTrue(asyncio.run(rt.run_once(media_agent(1), run_id=left_id, agent_role="MediaAgent")))
            self.assertTrue(asyncio.run(rt.run_once(media_agent(2), run_id=right_id, agent_role="MediaAgent")))
            golden = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(left_id).write(Path(tmp) / "golden.json")
            current = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(right_id).write_dir(Path(tmp) / "current")

            args = type(
                "Args",
                (),
                {
                    "golden": str(golden),
                    "current": str(current),
                    "allow_final_state_changes": False,
                    "allow_event_type_changes": False,
                    "allow_tool_ledger_status_changes": False,
                    "allow_media_artifact_changes": False,
                    "allow_stream_checkpoint_changes": False,
                    "max_total_usd_delta": None,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit):
                    cmd_evidence_regression(args)
            failed = json.loads(stdout.getvalue())
            checks = {check["name"]: check for check in failed["checks"]}
            self.assertFalse(checks["media_artifact_regression"]["passed"])
            self.assertFalse(checks["stream_checkpoint_regression"]["passed"])

            args.allow_media_artifact_changes = True
            args.allow_stream_checkpoint_changes = True
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_evidence_regression(args)
            self.assertTrue(json.loads(stdout.getvalue())["passed"])

            corpus_dir = str(Path(tmp) / "corpus")
            add_args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "corpus_dir": corpus_dir, "name": "media", "evidence": str(golden), "metadata": None})()
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_corpus_add(add_args)
            eval_args = type(
                "Args",
                (),
                {
                    "root": str(Path(tmp) / ".agentledger"),
                    "corpus_dir": corpus_dir,
                    "name": "media",
                    "current": str(current),
                    "allow_final_state_changes": False,
                    "allow_event_type_changes": False,
                    "allow_tool_ledger_status_changes": False,
                    "allow_media_artifact_changes": False,
                    "allow_stream_checkpoint_changes": False,
                    "max_total_usd_delta": None,
                },
            )()
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cmd_corpus_eval(eval_args)
            eval_args.allow_media_artifact_changes = True
            eval_args.allow_stream_checkpoint_changes = True
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_corpus_eval(eval_args)
            self.assertTrue(json.loads(stdout.getvalue())["passed"])

    def test_golden_corpus_add_list_and_eval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
            evidence_file = bundle.write(Path(tmp) / "bundle.json")
            corpus = GoldenCorpus(Path(tmp) / "corpus")
            case = corpus.add("side-effect", evidence_file, metadata={"suite": "runtime"})
            self.assertEqual(case.name, "side-effect")
            self.assertEqual(corpus.list()[0].metadata["suite"], "runtime")
            report = corpus.evaluate("side-effect", evidence_file)
            self.assertTrue(report.passed, report.to_dict())

    def test_golden_corpus_can_seed_builtin_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_dir = Path(tmp) / "corpus"
            corpus = GoldenCorpus(corpus_dir)
            expected_builtins = ["media-stream-checkpoint", "minimal-success", "tool-ledger-success"]
            self.assertEqual(corpus.builtin_names(), expected_builtins)

            for name in expected_builtins:
                with self.subTest(name=name):
                    case = corpus.seed_builtin(name)
                    self.assertEqual(case.name, name)
                    self.assertTrue(case.bundle_hash.startswith("sha256:"))
                    report = corpus.evaluate(name, case.path)
                    self.assertTrue(report.passed, report.to_dict())

            tool_case = json.loads((corpus_dir / "tool-ledger-success" / "bundle.json").read_text(encoding="utf-8"))
            self.assertEqual(tool_case["summary"]["tool_ledger_count"], 1)
            self.assertEqual(tool_case["tool_ledger"][0]["status"], "SUCCEEDED")
            media_case = json.loads((corpus_dir / "media-stream-checkpoint" / "bundle.json").read_text(encoding="utf-8"))
            self.assertEqual(media_case["summary"]["media_artifact_count"], 1)
            self.assertEqual(media_case["summary"]["stream_checkpoint_count"], 1)

            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "corpus_dir": str(corpus_dir), "name": "tool-ledger-success", "list_builtins": False})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_corpus_seed(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["name"], "tool-ledger-success")

            args.list_builtins = True
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_corpus_seed(args)
            self.assertEqual(json.loads(stdout.getvalue())["builtins"], expected_builtins)

    def test_cli_corpus_commands_support_repro_harness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            evidence_file = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).write(Path(tmp) / "bundle.json")
            corpus_dir = str(Path(tmp) / "corpus")
            add_args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "corpus_dir": corpus_dir, "name": "demo", "evidence": str(evidence_file), "metadata": '{"suite":"demo"}'})()
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_corpus_add(add_args)
            list_args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "corpus_dir": corpus_dir})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_corpus_list(list_args)
            self.assertEqual(json.loads(stdout.getvalue())["count"], 1)
            eval_args = type(
                "Args",
                (),
                {
                    "root": str(Path(tmp) / ".agentledger"),
                    "corpus_dir": corpus_dir,
                    "name": "demo",
                    "current": str(evidence_file),
                    "allow_final_state_changes": False,
                    "allow_event_type_changes": False,
                    "allow_tool_ledger_status_changes": False,
                    "max_total_usd_delta": None,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_corpus_eval(eval_args)
            self.assertTrue(json.loads(stdout.getvalue())["passed"])

    def test_evidence_regression_detects_final_state_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")

            async def agent_a(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("value", "a")

            async def agent_b(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("value", "b")

            left_id, _ = rt.create_run(initial_state={})
            right_id, _ = rt.create_run(initial_state={})
            self.assertTrue(asyncio.run(rt.run_once(agent_a, run_id=left_id, agent_role="EvalAgent")))
            self.assertTrue(asyncio.run(rt.run_once(agent_b, run_id=right_id, agent_role="EvalAgent")))
            left = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(left_id).to_dict()
            right = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(right_id).to_dict()
            report = EvidenceRegressionRunner().evaluate_regression(left, right, require_same_event_types=False)
            self.assertFalse(report.passed)
            self.assertFalse(next(check for check in report.checks if check.name == "final_state_regression").passed)
            summary = report.metadata["regression_summary"]
            self.assertEqual(summary["failed_checks"], ["final_state_regression"])
            self.assertIn("final_state", summary["changed_dimensions"])
            self.assertEqual(summary["changed_counts"]["final_state"], 1)
            self.assertEqual(summary["cost_delta_usd"], 0.0)
            allowed = EvidenceRegressionRunner().evaluate_regression(left, right, require_same_final_state=False, require_same_event_types=False)
            self.assertTrue(allowed.passed)
            self.assertEqual(allowed.metadata["regression_summary"]["failed_checks"], [])

    def test_cli_evidence_regression_supports_evidence_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
            left = bundle.write(Path(tmp) / "golden.json")
            right = bundle.write_dir(Path(tmp) / "current")
            args = type(
                "Args",
                (),
                {
                    "golden": str(left),
                    "current": str(right),
                    "allow_final_state_changes": False,
                    "allow_event_type_changes": False,
                    "allow_tool_ledger_status_changes": False,
                    "max_total_usd_delta": 0.0,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_evidence_regression(args)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["passed"], payload)
            self.assertIn("diff", payload["metadata"])
            self.assertIn("regression_summary", payload["metadata"])
            self.assertEqual(payload["metadata"]["regression_summary"]["failed_checks"], [])

    def test_adversarial_review_checklist_can_gate_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                await ctx.call_model({"provider": "mock", "mock_response": "ok", "mock_usage": {"total_tokens": 10}, "mock_cost_usd": 0.02})
                ctx.write_state_patch("ok", True)

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ReviewAgent")))
            evidence = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).to_dict()
            passed = AdversarialReviewRunner().evaluate(evidence, max_total_usd=0.05).to_dict()
            self.assertTrue(passed["passed"], passed)
            failed = AdversarialReviewRunner().evaluate(evidence, max_total_usd=0.01).to_dict()
            self.assertFalse(failed["passed"], failed)
            self.assertFalse(next(check for check in failed["checks"] if check["name"] == "max_total_usd")["passed"])

            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "policy": None, "sandbox_config": None, "run_id": run_id, "max_total_usd": 0.05, "fail_on_risk": True})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_review_checklist(args)
            self.assertTrue(json.loads(stdout.getvalue())["passed"])

            args.max_total_usd = 0.01
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cmd_review_checklist(args)

    def test_trace_exporter_writes_event_spans_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
            exporter = TraceExporter()
            spans = exporter.spans(bundle)
            self.assertEqual(len(spans), bundle.to_dict()["summary"]["event_count"])
            self.assertEqual(spans[0].trace_id, run_id)
            path = exporter.write_jsonl(bundle, Path(tmp) / "trace.jsonl")
            lines = path.read_text().strip().splitlines()
            self.assertEqual(len(lines), len(spans))
            first = json.loads(lines[0])
            self.assertEqual(first["trace_id"], run_id)
            self.assertIn("agentledger.seq", first["attributes"])

    def test_trace_exporter_includes_media_stream_spans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, _state: dict[str, Any]) -> None:
                await ctx.create_media_artifact("frame", "frame", uri="s3://media/frame.jpg", media_metadata=MediaMetadata(kind="frame", frame_index=1))
                await ctx.create_stream_checkpoint("checkpoint", stream_id="camera-1", consumer_id="vision-agent", offset=1)

            self.assertTrue(asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="MediaAgent")))
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
            spans = TraceExporter().spans(bundle)
            names = [span.name for span in spans]
            self.assertIn("media_artifact", names)
            self.assertIn("stream_checkpoint", names)
            media_span = next(span for span in spans if span.name == "media_artifact")
            stream_span = next(span for span in spans if span.name == "stream_checkpoint")
            self.assertEqual(media_span.attributes["agentledger.media_kind"], "frame")
            self.assertEqual(stream_span.attributes["agentledger.stream_offset"], 1)

    def test_otlp_trace_exporter_writes_otlp_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
            exporter = OTLPTraceExporter()
            payload = exporter.to_otlp_json(bundle)
            spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
            self.assertGreater(len(spans), 0)
            self.assertEqual(len(spans[0]["traceId"]), 32)
            self.assertEqual(len(spans[0]["spanId"]), 16)
            attrs = {item["key"]: item["value"] for item in spans[0]["attributes"]}
            self.assertEqual(attrs["agentledger.original_trace_id"]["stringValue"], run_id)
            path = exporter.write_json(bundle, Path(tmp) / "trace.otlp.json")
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("resourceSpans", written)

    def test_otlp_trace_exporter_can_post_with_injected_transport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt, run_id, _ = self._run_side_effect_demo(Path(tmp) / ".agentledger")
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id)
            captured: dict[str, Any] = {}

            class FakeResponse:
                status = 200

                def read(self) -> bytes:
                    return b"ok"

            def fake_opener(request: Any, timeout: float) -> FakeResponse:
                captured["url"] = request.full_url
                captured["body"] = request.data
                captured["content_type"] = request.headers["Content-type"]
                captured["timeout"] = timeout
                return FakeResponse()

            result = OTLPTraceExporter().post_json(bundle, "http://collector/v1/traces", timeout=1.5, opener=fake_opener)
            self.assertEqual(result["status"], 200)
            self.assertEqual(result["response"], "ok")
            self.assertEqual(captured["url"], "http://collector/v1/traces")
            self.assertEqual(captured["content_type"], "application/json")
            self.assertEqual(captured["timeout"], 1.5)
            self.assertIn(b"resourceSpans", captured["body"])

    def test_time_travel_debugger_reconstructs_state_by_seq(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={"count": 0})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("count", state["count"] + 1)
                ctx.write_state_patch("nested", {"ok": True})

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="TimeTravelAgent")))
            report = TimeTravelDebugger(store=rt.store, blobs=rt.blobs).inspect(run_id, include_states=True, include_diffs=True)
            self.assertEqual(report.state_at_seq["count"], 1)
            self.assertTrue(report.state_at_seq["nested"]["ok"])
            changed_frames = [frame for frame in report.timeline if frame.state_changed]
            self.assertGreaterEqual(len(changed_frames), 2)
            self.assertEqual(changed_frames[0].event_type, "run_created")
            self.assertIn("count", changed_frames[-1].changed_keys)
            self.assertIn("count", changed_frames[-1].state_diff["changed"])

            first_state = TimeTravelDebugger(store=rt.store, blobs=rt.blobs).inspect(run_id, at_seq=1)
            self.assertEqual(first_state.state_at_seq, {"count": 0})
            self.assertEqual(first_state.selected_event.event_type, "run_created")

    def test_cli_timetravel_outputs_timeline_and_state_at_seq(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={"x": 1})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("x", 2)

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="TimeTravelAgent")))
            args = type(
                "Args",
                (),
                {
                    "root": str(Path(tmp) / ".agentledger"),
                    "policy": None,
                    "sandbox_config": None,
                    "run_id": run_id,
                    "at_seq": 1,
                    "include_states": False,
                    "include_diffs": True,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_timetravel(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["state_at_seq"], {"x": 1})
            self.assertGreater(payload["event_count"], 0)
            self.assertEqual(payload["selected_event"]["type"], "run_created")
            self.assertIn("state_diff", payload["timeline"][0])

    def test_cli_timetravel_can_write_static_html_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={"x": 1})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("x", 2)

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="DebugAgent")))
            html_path = Path(tmp) / "time-travel.html"
            args = type(
                "Args",
                (),
                {
                    "root": str(Path(tmp) / ".agentledger"),
                    "policy": None,
                    "sandbox_config": None,
                    "run_id": run_id,
                    "at_seq": None,
                    "include_states": True,
                    "include_diffs": True,
                    "html": str(html_path),
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_timetravel(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["html_report"], str(html_path))
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("AgentLedger Time Travel Report", html)
            self.assertIn(run_id, html)
            self.assertIn("state_committed", html)
            self.assertIn("&quot;x&quot;", html)
            self.assertIn('class="details-row', html)
            self.assertIn('class="record-details"', html)
            self.assertNotIn("<th>Details</th>", html)

    def test_cli_debug_can_emit_state_diff_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={"x": 1})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("x", 2)

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="DebugAgent")))
            args = type(
                "Args",
                (),
                {
                    "root": str(Path(tmp) / ".agentledger"),
                    "policy": None,
                    "sandbox_config": None,
                    "run_id": run_id,
                    "json": True,
                    "at_seq": None,
                    "include_states": False,
                    "include_diffs": True,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_debug(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["run_id"], run_id)
            changed = [frame for frame in payload["timeline"] if "x" in frame["changed_keys"]]
            self.assertTrue(changed)
            self.assertIn("state_diff", changed[-1])

    def test_postgres_store_skeleton_exposes_schema_ddl(self) -> None:
        ddl = PostgresStore.ddl()
        self.assertIn("CREATE TABLE IF NOT EXISTS schema_migrations", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS runs", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS steps", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS tool_ledger", ddl)
        self.assertIn("approval_requests", ddl)
        self.assertIn("JSONB", ddl)

    def test_mysql_store_skeleton_exposes_schema_ddl_and_config(self) -> None:
        ddl = MySQLStore.ddl()
        self.assertIn("CREATE TABLE IF NOT EXISTS schema_migrations", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS runs", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS steps", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS tool_ledger", ddl)
        self.assertIn("JSON", ddl)
        config = MySQLStoreConfig.from_env(
            {
                "AGENTLEDGER_MYSQL_DSN": "mysql://agentledger:secret@localhost:3306/agentledger",
                "AGENTLEDGER_MYSQL_DATABASE": "agentledger_test",
            }
        )
        self.assertEqual(config.database, "agentledger_test")
        self.assertEqual(config.to_dict()["dsn"], "mysql://agentledger:***@localhost:3306/agentledger")
        with self.assertRaises(ValueError):
            MySQLStoreConfig.from_env({})

    def test_postgres_store_connection_injection_passes_state_conformance(self) -> None:
        def factory() -> PostgresStore:
            store = PostgresStore(PostgresStoreConfig("postgres://fake/agentledger"), connection=FakePostgresConnection(), owns_connection=True)
            store.init()
            return store

        report = StateStoreConformanceRunner(factory, name="postgres-fake", close_stores=True).run()
        self.assertTrue(report.passed, report.to_dict())

    def test_postgres_config_from_env_redacts_password_and_validates_schema(self) -> None:
        config = PostgresStoreConfig.from_env(
            {
                "AGENTLEDGER_POSTGRES_DSN": "postgresql://agentledger:secret@localhost:5432/agentledger",
                "AGENTLEDGER_POSTGRES_SCHEMA": "agentledger_test",
            }
        )
        self.assertEqual(config.schema, "agentledger_test")
        self.assertEqual(config.to_dict()["dsn"], "postgresql://agentledger:***@localhost:5432/agentledger")
        with self.assertRaises(ValueError):
            PostgresStoreConfig.from_env({})
        with self.assertRaises(ValueError):
            PostgresStore(PostgresStoreConfig("postgres://fake/db", schema="bad-schema"), connection=FakePostgresConnection(), owns_connection=True).init()

    def test_cli_state_conformance_supports_sqlite_and_injected_postgres(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "backend": "sqlite"})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_state_conformance(sqlite_args)
            sqlite_payload = json.loads(stdout.getvalue())
            self.assertTrue(sqlite_payload["passed"], sqlite_payload)
            self.assertEqual(sqlite_payload["backend"], "sqlite")

        pg_args = type(
            "Args",
            (),
            {
                "root": ".agentledger",
                "backend": "postgres",
                "dsn": "postgres://fake/agentledger",
                "schema": "public",
            },
        )()
        store = create_state_store(pg_args, postgres_connection=FakePostgresConnection)
        try:
            self.assertIsInstance(store, PostgresStore)
        finally:
            store.close()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cmd_state_conformance(pg_args, postgres_connection=FakePostgresConnection)
        pg_payload = json.loads(stdout.getvalue())
        self.assertTrue(pg_payload["passed"], pg_payload)
        self.assertEqual(pg_payload["backend"], "postgres")

    def test_cli_worker_conformance_supports_sqlite_and_injected_postgres(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_args = type(
                "Args",
                (),
                {"root": str(Path(tmp) / ".agentledger"), "backend": "sqlite", "workers": 3, "concurrent": True},
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_worker_conformance(sqlite_args)
            sqlite_payload = json.loads(stdout.getvalue())
            self.assertTrue(sqlite_payload["passed"], sqlite_payload)
            self.assertEqual(sqlite_payload["backend"], "sqlite")

        pg_args = type(
            "Args",
            (),
            {
                "root": ".agentledger",
                "backend": "postgres",
                "dsn": "postgres://fake/agentledger",
                "schema": "public",
                "workers": 3,
                "concurrent": False,
            },
        )()
        stdout = io.StringIO()
        shared_connection = FakePostgresConnection()
        try:
            with contextlib.redirect_stdout(stdout):
                cmd_worker_conformance(pg_args, postgres_connection=shared_connection)
        finally:
            shared_connection.close()
        pg_payload = json.loads(stdout.getvalue())
        self.assertTrue(pg_payload["passed"], pg_payload)
        self.assertEqual(pg_payload["backend"], "postgres")

    def test_agent_context_artifacts_use_store_boundary(self) -> None:
        source = Path("src/agentledger/context.py").read_text(encoding="utf-8")
        self.assertIn("self.store.create_artifact", source)
        self.assertNotIn("self.store.conn.execute", source)

    def test_media_and_stream_contracts_are_artifact_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, _state: dict[str, Any]) -> None:
                frame_id = await ctx.create_media_artifact(
                    "frame-0001",
                    "frame",
                    uri="s3://media/run-1/frame-0001.jpg",
                    media_metadata=MediaMetadata(kind="frame", mime_type="image/jpeg", width=1920, height=1080, timestamp_start_seconds=2.5, frame_index=1),
                    lineage=ArtifactLineage(source_blob_refs=["s3://media/run-1/video.mp4"], tool_call_ids=["tool_extract_frames"]),
                )
                checkpoint_id = await ctx.create_stream_checkpoint(
                    "camera-stream-checkpoint",
                    stream_id="camera-1",
                    consumer_id="vision-agent",
                    offset=42,
                    watermark=12.5,
                    chunk=StreamChunkRef(stream_id="camera-1", chunk_id="chunk-42", offset=42, content_ref="blob://sha256/chunk-42.json", sequence=42),
                    partial_result_ref="blob://sha256/partial-result.json",
                    backpressure={"recommended_pause_ms": 250},
                )
                ctx.write_state_patch("media_refs", {"frame": frame_id, "checkpoint": checkpoint_id})

            self.assertTrue(asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="MediaAgent")))
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).to_dict()
            self.assertEqual(bundle["summary"]["media_artifact_count"], 1)
            self.assertEqual(bundle["summary"]["stream_checkpoint_count"], 1)
            self.assertEqual(bundle["media_artifacts"][0]["kind"], "frame")
            self.assertEqual(bundle["stream_checkpoints"][0]["stream_id"], "camera-1")
            artifacts = {row["name"]: row for row in bundle["artifacts"]}

            frame = artifacts["frame-0001"]
            self.assertEqual(frame["metadata"]["agentledger_media"]["kind"], "frame")
            frame_manifest = rt.blobs.get_json(frame["blob_ref"])
            self.assertEqual(frame_manifest["uri"], "s3://media/run-1/frame-0001.jpg")
            self.assertEqual(frame_manifest["metadata"]["width"], 1920)
            self.assertEqual(frame_manifest["lineage"]["source_blob_refs"], ["s3://media/run-1/video.mp4"])
            self.assertNotIn("raw_bytes", frame_manifest)

            checkpoint = artifacts["camera-stream-checkpoint"]
            self.assertEqual(checkpoint["metadata"]["agentledger_stream"]["offset"], 42)
            checkpoint_manifest = rt.blobs.get_json(checkpoint["blob_ref"])
            self.assertEqual(checkpoint_manifest["chunk"]["content_ref"], "blob://sha256/chunk-42.json")
            self.assertEqual(checkpoint_manifest["backpressure"]["recommended_pause_ms"], 250)
            replay = ReplayEngine(store=rt.store, blobs=rt.blobs).replay(run_id)
            self.assertEqual(replay.artifact_count, 2)
            self.assertEqual(replay.media_artifact_count, 1)
            self.assertEqual(replay.stream_checkpoint_count, 1)
            review = AdversarialReviewRunner().evaluate(bundle).to_dict()
            checks = {check["name"]: check for check in review["checks"]}
            self.assertTrue(checks["media_artifacts_have_refs"]["passed"])
            self.assertTrue(checks["stream_checkpoints_have_offsets"]["passed"])
            malformed = dict(bundle)
            malformed["stream_checkpoints"] = [{**bundle["stream_checkpoints"][0], "offset": None}]
            malformed_review = AdversarialReviewRunner().evaluate(malformed).to_dict()
            malformed_checks = {check["name"]: check for check in malformed_review["checks"]}
            self.assertFalse(malformed_checks["stream_checkpoints_have_offsets"]["passed"])
            self.assertFalse(malformed_review["passed"])

            with self.assertRaises(ValueError):
                MediaArtifact(kind="unsupported")
            with self.assertRaises(ValueError):
                EventStreamCheckpoint(stream_id="s", consumer_id="c", offset=-1)

    def test_media_tool_conventions_export_runtime_managed_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            specs = register_media_tool_conventions(rt.registry)
            names = [spec.name for spec in specs]
            self.assertEqual(
                names,
                [
                    "audio.transcribe",
                    "video.extract_frames",
                    "frame.describe",
                    "video.summarize",
                    "stream.consume",
                    "stream.emit",
                ],
            )
            manifest = rt.registry.manifest()
            self.assertTrue(all(tool["idempotency_required"] for tool in manifest["tools"]))
            self.assertIn("source_ref", manifest["tools"][0]["input_schema"]["required"])
            openai_names = [tool["function"]["name"] for tool in rt.registry.openai_tools()]
            self.assertIn("video.extract_frames", openai_names)

            validate_tool_schema(media_tool_specs()[0].input_schema, {"source_ref": "s3://media/audio.wav"}, path="args")
            with self.assertRaises(ToolValidationError):
                validate_tool_schema(media_tool_specs()[1].input_schema, {"source_ref": "s3://media/video.mp4", "max_frames": 0}, path="args")

            args = type("Args", (), {"root": str(Path(tmp) / ".agentledger"), "policy": None, "sandbox_config": None, "format": "agentledger", "example": "examples/media_stream", "out": None})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_tools_manifest(args)
            payload = json.loads(stdout.getvalue())
            cli_names = [tool["name"] for tool in payload["tools"]]
            self.assertIn("stream.consume", cli_names)

    def test_media_tool_convention_runs_through_tool_ledger_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            calls: list[dict[str, Any]] = []

            def extract_frames(args: dict[str, Any]) -> dict[str, Any]:
                calls.append(args)
                return {
                    "frame_refs": [
                        {
                            "uri": "s3://media/run-1/frame-0001.jpg",
                            "frame_index": 1,
                            "timestamp_start_seconds": 2.5,
                        }
                    ],
                    "timeline_ref": "blob://sha256/timeline.json",
                    "metadata": {"source_ref": args["source_ref"]},
                }

            register_media_tool_conventions(rt.registry, {"video.extract_frames": extract_frames})
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, _state: dict[str, Any]) -> None:
                result = await ctx.call_tool(
                    "video.extract_frames",
                    {
                        "source_ref": "s3://media/run-1/video.mp4",
                        "max_frames": 1,
                        "_logical_operation": "extract-demo-frames",
                    },
                )
                frame = result["frame_refs"][0]
                artifact_id = await ctx.create_media_artifact(
                    "frame-0001",
                    "frame",
                    uri=frame["uri"],
                    media_metadata=MediaMetadata(kind="frame", mime_type="image/jpeg", frame_index=frame["frame_index"], timestamp_start_seconds=frame["timestamp_start_seconds"]),
                    lineage=ArtifactLineage(source_blob_refs=["s3://media/run-1/video.mp4"], tool_call_ids=["video.extract_frames"]),
                )
                ctx.write_state_patch("frame_artifact", artifact_id)

            self.assertTrue(asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="MediaAgent")))
            self.assertEqual(len(calls), 1)
            ledger = rt.store.ledger(run_id)
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["tool_name"], "video.extract_frames")
            self.assertEqual(ledger[0]["status"], "SUCCEEDED")
            bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).to_dict()
            self.assertEqual(bundle["summary"]["tool_ledger_count"], 1)
            self.assertEqual(bundle["summary"]["media_artifact_count"], 1)
            self.assertEqual(bundle["media_artifacts"][0]["lineage"]["tool_call_ids"], ["video.extract_frames"])

    def test_backup_readiness_checks_media_stream_nested_blob_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, _state: dict[str, Any]) -> None:
                _digest, chunk_ref = ctx.blobs.put_json({"chunk": "frame-bytes-placeholder"})
                media_id = await ctx.create_media_artifact(
                    "frame-from-blob",
                    "frame",
                    content_ref=chunk_ref,
                    media_metadata=MediaMetadata(kind="frame", mime_type="image/jpeg", frame_index=1),
                )
                checkpoint_id = await ctx.create_stream_checkpoint(
                    "stream-checkpoint",
                    stream_id="camera-1",
                    consumer_id="vision-agent",
                    offset=1,
                    chunk=StreamChunkRef(stream_id="camera-1", chunk_id="chunk-1", offset=1, content_ref=chunk_ref, sequence=1),
                    partial_result_ref=chunk_ref,
                )
                ctx.write_state_patch("refs", {"media": media_id, "checkpoint": checkpoint_id})

            self.assertTrue(asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="MediaAgent")))
            report = BackupReadinessChecker(store=rt.store, blobs=rt.blobs).check_run(run_id).to_dict()
            self.assertTrue(report["passed"], report)
            self.assertGreaterEqual(report["refs_checked"], 5)
            checks = {check["name"]: check for check in report["checks"]}
            self.assertTrue(checks["media_stream_evidence_shape"]["passed"])

    def test_sqlite_store_records_schema_migration_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "state.db")
            store.init()
            status = store.migration_status().to_dict()
            self.assertEqual(status["current_version"], latest_schema_version("sqlite"))
            self.assertTrue(status["up_to_date"])
            self.assertEqual(status["applied"][0]["version"], "0001")
            self.assertEqual(store.schema_version(), "0001")

    def test_storage_schema_catalog_exposes_sqlite_and_postgres_ddl(self) -> None:
        sqlite_ddl = ddl_for("sqlite")
        postgres_ddl = ddl_for("postgres")
        self.assertIn("schema_migrations", sqlite_ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS runs", sqlite_ddl)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS idx_events_run_seq", sqlite_ddl)
        self.assertIn("JSONB", postgres_ddl)
        self.assertEqual(migrations_for("sqlite")[0].version, "0001")
        self.assertTrue(migrations_for("postgres")[0].checksum.startswith("sha256:"))

    def test_cli_migrate_supports_injected_postgres_without_destructive_cleanup(self) -> None:
        args = type(
            "Args",
            (),
            {
                "root": ".agentledger",
                "dialect": "postgres",
                "dsn": "postgres://fake/agentledger",
                "schema": "public",
            },
        )()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cmd_migrate_up(args, postgres_connection=FakePostgresConnection)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["migration_status"]["current_version"], "0001")
        self.assertEqual(payload["migration_status"]["latest_version"], "0001")
        self.assertEqual(payload["config"]["dsn"], "postgres://fake/agentledger")

        old_dsn = os.environ.pop("AGENTLEDGER_POSTGRES_DSN", None)
        old_schema = os.environ.pop("AGENTLEDGER_POSTGRES_SCHEMA", None)
        try:
            no_dsn_args = type("Args", (), {"root": ".agentledger", "dialect": "postgres", "dsn": None, "schema": None})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_migrate_status(no_dsn_args)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "dsn-not-configured")
        finally:
            if old_dsn is not None:
                os.environ["AGENTLEDGER_POSTGRES_DSN"] = old_dsn
            if old_schema is not None:
                os.environ["AGENTLEDGER_POSTGRES_SCHEMA"] = old_schema

    def test_runtime_contract_declares_python_reference_and_preview_languages(self) -> None:
        contract = runtime_contract()
        languages = {entry["language"]: entry for entry in contract["language_targets"]}
        self.assertEqual(contract["reference_implementation"]["language"], "python")
        self.assertEqual(languages["python"]["status"], "active")
        self.assertEqual(languages["typescript"]["status"], "preview")
        self.assertEqual(languages["rust"]["status"], "preview")
        self.assertEqual(languages["go"]["status"], "preview")
        self.assertIn("state commits require a valid lease token", contract["invariants"])
        self.assertIn("tool_call_completed", contract["event_types"])
        self.assertIn("model_call_failed", contract["event_types"])
        self.assertIn("tool_call_proposed", contract["event_types"])
        self.assertEqual(contract["artifact_contracts"]["model_evidence_schema_version"], "agentledger.model.evidence.v1")
        self.assertEqual(contract["conformance"]["runtime_semantics_manifest_path"], "contracts/conformance/runtime_semantics.v1.json")
        self.assertIn("contracts/conformance/local_persistence.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/local_blob_store.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/tool_schema_validation.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/worker_service.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/media_stream_artifacts.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/evidence_consumers.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/static_debug_html.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/ops_readiness.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/storage_schema.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/mcp_adapters.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/framework_adapters.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/otlp_trace_export.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn("contracts/conformance/simple_api.v1.json", contract["conformance"]["runtime_core_fixture_paths"])
        self.assertIn('"contract_version": "1.0"', contract_json())

    def test_runtime_contract_matches_checked_in_golden_fixture(self) -> None:
        golden = Path("contracts/agentledger.runtime.v1.json").read_text(encoding="utf-8").strip()
        self.assertEqual(contract_json().strip(), golden)

    def test_release_readiness_docs_and_ci_exist(self) -> None:
        required_paths = [
            "README.md",
            "README.zh-CN.md",
            "docs/README.md",
            "docs/zh/README.md",
            "docs/assets/agentledger-runtime-architecture.svg",
            "docs/ARCHITECTURE.md",
            "docs/COMPARISONS.md",
            "docs/MATURITY_MODEL.md",
            "docs/ROADMAP.md",
            "docs/MULTI_LANGUAGE.md",
            "docs/LANGUAGE_PARITY_MATRIX.md",
            "docs/LANGUAGE_PARITY_AUDIT.md",
            "docs/EXECUTION_BACKENDS.md",
            "docs/STORAGE.md",
            "docs/POSTGRES.md",
            "docs/S3_MINIO.md",
            "docs/BACKUP_RESTORE.md",
            "docs/DISTRIBUTED_WORKERS.md",
            "docs/VERSIONING.md",
            "docs/ADAPTER_CERTIFICATION.md",
            "docs/zh/LANGUAGE_PARITY_MATRIX.md",
            "docs/zh/LANGUAGE_PARITY_AUDIT.md",
            "docs/zh/EXECUTION_BACKENDS.md",
            "docs/zh/COMPARISONS.md",
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            "CHANGELOG.md",
            "SECURITY.md",
            ".github/workflows/ci.yml",
            "scripts/check_language_parity.py",
            "contracts/conformance/runtime_semantics.v1.json",
            "contracts/conformance/local_persistence.v1.json",
            "contracts/conformance/local_blob_store.v1.json",
            "contracts/conformance/tool_schema_validation.v1.json",
            "contracts/conformance/worker_service.v1.json",
            "contracts/conformance/evidence_consumers.v1.json",
            "contracts/conformance/static_debug_html.v1.json",
            "contracts/conformance/ops_readiness.v1.json",
            "contracts/conformance/storage_schema.v1.json",
            "contracts/conformance/mcp_adapters.v1.json",
            "contracts/conformance/framework_adapters.v1.json",
            "contracts/conformance/otlp_trace_export.v1.json",
            "contracts/conformance/simple_api.v1.json",
            "go/cmd/agentledger-go/main.go",
            "typescript/src/cli.js",
            "rust/src/main.rs",
            "docs/assets/langgraph-agentledger-relationship.svg",
            "docs/POLICY_ENGINE.md",
            "docs/zh/POLICY_ENGINE.md",
            "docs/assets/agent-policy-engine-relationship-map.svg",
            "docs/assets/agent-policy-engine-evaluate-detail.svg",
        ]
        for path in required_paths:
            self.assertTrue(Path(path).exists(), path)
        readme = Path("README.md").read_text(encoding="utf-8")
        zh_readme = Path("README.zh-CN.md").read_text(encoding="utf-8")
        maturity = Path("docs/MATURITY_MODEL.md").read_text(encoding="utf-8")
        roadmap = Path("docs/ROADMAP.md").read_text(encoding="utf-8")
        ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        parity_script = Path("scripts/check_language_parity.py").read_text(encoding="utf-8")
        release_family = ".".join(AGENTLEDGER_VERSION.split(".")[:2]) + ".x"
        self.assertIn("[English](README.md) | [中文](README.zh-CN.md)", readme)
        self.assertIn(f"![Version {release_family} stable]", readme)
        self.assertIn(f"current runtime-core release is {AGENTLEDGER_VERSION}", readme)
        self.assertIn("python3 -m pip install agentledger-runtime", readme)
        self.assertIn("https://github.com/yaogdu/AgentLedger", readme)
        self.assertIn("docs/assets/agentledger-runtime-architecture.svg", readme)
        self.assertIn("Relationship to adjacent tools", readme)
        self.assertIn("LangSmith, Langfuse, OpenTelemetry", readme)
        self.assertIn("In-path enforcement", readme)
        self.assertIn("not try to become a full trace store", readme)
        self.assertIn("[English](README.md) | [中文](README.zh-CN.md)", zh_readme)
        self.assertIn("适合什么场景", zh_readme)
        self.assertIn("和相邻工具的关系", zh_readme)
        self.assertIn("相对重点和优势", zh_readme)
        self.assertIn("Capability Matrix", maturity)
        self.assertIn("v1.0 - Stable Runtime Contract", roadmap)
        self.assertIn("Execution backend positioning", roadmap)
        self.assertIn("unittest discover", ci)
        self.assertIn("lint boundary", ci)
        self.assertIn("Go runtime preview", ci)
        self.assertIn("SEMANTIC_MANIFEST_PATH", parity_script)
        self.assertIn("load_semantic_manifest", parity_script)
        self.assertIn("language_conformance", parity_script)
        semantic_manifest = json.loads(Path("contracts/conformance/runtime_semantics.v1.json").read_text(encoding="utf-8"))
        semantic_ids = {entry["id"] for entry in semantic_manifest["required_semantic_checks"]}
        self.assertIn("local_persistence_smoke", semantic_ids)
        self.assertIn("local_blob_store_smoke", semantic_ids)
        self.assertIn("tool_schema_validation_smoke", semantic_ids)
        self.assertIn("worker_service_smoke", semantic_ids)
        self.assertIn("tool_ledger_idempotent_retry", semantic_ids)
        self.assertIn("policy_approval_sandbox_smoke", semantic_ids)
        self.assertIn("media_stream_artifacts_smoke", semantic_ids)

    def test_runtime_boundary_linter_detects_direct_tool_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            unsafe = Path(tmp) / "unsafe_agent.py"
            unsafe.write_text(
                """
import os
import subprocess as sp
import requests as rq
import urllib.request
from openai import OpenAI
from litellm import completion as llm_completion
from google import genai
import google.generativeai as palm
from mistralai import Mistral
import cohere
import groq
import ollama
import vertexai


async def agent(ctx, state):
    await ctx.call_tool("docs.read", {"path": "README.md"})
    os.system("echo bypass")
    sp.run(["echo", "bypass"])
    rq.get("https://example.com")
    urllib.request.urlopen("https://example.com")
    client = OpenAI()
    client.responses.create(model="demo", input="hello")
    llm_completion(model="demo", messages=[])
    google_client = genai.Client()
    google_client.models.generate_content(model="demo", contents="hello")
    palm_model = palm.GenerativeModel("demo")
    palm_model.generate_content("hello")
    mistral_client = Mistral(api_key="demo")
    mistral_client.chat.complete(model="demo", messages=[])
    cohere_client = cohere.Client("demo")
    cohere_client.chat(model="demo", message="hello")
    groq_client = groq.Groq(api_key="demo")
    groq_client.chat.completions.create(model="demo", messages=[])
    ollama_client = ollama.Client()
    ollama_client.chat(model="demo", messages=[])
    vertexai.init(project="demo")
    # agentledger: ignore-next-line
    os.system("ignored")
""".strip(),
                encoding="utf-8",
            )

            report = RuntimeBoundaryLinter().scan([unsafe])
            self.assertFalse(report.passed)
            rule_ids = {finding.rule_id for finding in report.findings}
            self.assertIn("direct-shell-os-system", rule_ids)
            self.assertIn("direct-shell-subprocess", rule_ids)
            self.assertIn("direct-http-requests", rule_ids)
            self.assertIn("direct-http-urllib", rule_ids)
            self.assertIn("direct-openai-sdk", rule_ids)
            self.assertIn("direct-litellm-sdk", rule_ids)
            self.assertIn("direct-google-genai-sdk", rule_ids)
            self.assertIn("direct-google-generativeai-sdk", rule_ids)
            self.assertIn("direct-mistral-sdk", rule_ids)
            self.assertIn("direct-cohere-sdk", rule_ids)
            self.assertIn("direct-groq-sdk", rule_ids)
            self.assertIn("direct-ollama-sdk", rule_ids)
            self.assertIn("direct-vertexai-sdk", rule_ids)
            self.assertEqual(sum(1 for finding in report.findings if finding.callee == "os.system"), 1)

    def test_runtime_boundary_linter_loads_project_rule_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_path = root / "boundary_rules.json"
            rules_path.write_text(
                json.dumps(
                    {
                        "rules": [
                            {
                                "rule_id": "project-direct-internal-client",
                                "pattern": "internal_client.",
                                "prefix": True,
                                "category": "project-side-effect",
                                "message": "direct internal client bypass",
                                "suggestion": "wrap it as a runtime-managed tool",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            unsafe = root / "unsafe_agent.py"
            unsafe.write_text(
                "import internal_client\nimport os\ninternal_client.call()\nos.system('echo default')\n",
                encoding="utf-8",
            )

            appended = RuntimeBoundaryLinter(rules=load_boundary_rules(rules_path)).scan([unsafe])
            appended_ids = {finding.rule_id for finding in appended.findings}
            self.assertIn("project-direct-internal-client", appended_ids)
            self.assertIn("direct-shell-os-system", appended_ids)

            replaced = RuntimeBoundaryLinter(rules=load_boundary_rules(rules_path, include_defaults=False)).scan([unsafe])
            replaced_ids = {finding.rule_id for finding in replaced.findings}
            self.assertEqual(replaced_ids, {"project-direct-internal-client"})

    def test_cli_lint_boundary_reports_json_and_fails_on_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            unsafe = Path(tmp) / "unsafe_agent.py"
            unsafe.write_text("import os\nos.system('echo bypass')\n", encoding="utf-8")
            args = type("Args", (), {"paths": [str(unsafe)], "exclude": [], "rules": None, "replace_defaults": False, "no_fail": True})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_lint_boundary(args)
            payload = json.loads(stdout.getvalue())
            self.assertFalse(payload["passed"])
            self.assertEqual(payload["finding_count"], 1)

            args.no_fail = False
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cmd_lint_boundary(args)

    def test_framework_and_tool_examples_run_without_external_dependencies(self) -> None:
        for path in [
            "examples/autogen/basic_agent.py",
            "examples/crewai/basic_crew.py",
            "examples/langchain/basic_runnable.py",
            "examples/langgraph/basic_graph.py",
            "examples/llamaindex/basic_query.py",
            "examples/media_stream/basic_media_stream.py",
            "examples/media_stream/managed_tool.py",
            "examples/mcp_context/basic_context_server.py",
            "examples/mcp_tool/basic_tool.py",
            "examples/openai_agents/basic_agent.py",
            "examples/sandbox/command_tool.py",
            "examples/semantic_kernel/basic_kernel.py",
            "examples/tool_catalog/basic_catalog.py",
        ]:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                runpy.run_path(path, run_name="__main__")
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["ok"], path)

    def test_simple_api_hello_world(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            @agent
            def hello(ctx: Any) -> str:
                return "hello world"

            result = run(hello, root=Path(tmp) / ".agentledger")
            self.assertTrue(result.ok)
            self.assertEqual(result.output, "hello world")
            self.assertEqual(result.state["output"], "hello world")
            event_types = [row["type"] for row in result.runtime.store.events(result.run_id)]
            self.assertIn("agent_result_returned", event_types)

    def test_runtime_tool_decorator_registers_managed_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")

            @rt.tool(
                name="math.add",
                description="Add two integers.",
                input_schema={
                    "type": "object",
                    "required": ["left", "right"],
                    "properties": {"left": {"type": "integer"}, "right": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["sum"], "properties": {"sum": {"type": "integer"}}},
            )
            def add(args: dict[str, Any]) -> dict[str, Any]:
                return {"sum": args["left"] + args["right"]}

            async def agent_fn(ctx: Any, _state: dict[str, Any]) -> None:
                result = await ctx.call_tool("math.add", {"left": 2, "right": 3})
                ctx.write_state_patch("sum", result["sum"])

            run_id, _ = rt.create_run(initial_state={})
            self.assertEqual(add.name, "math.add")
            self.assertEqual(rt.registry.manifest()["tools"][0]["description"], "Add two integers.")
            self.assertEqual(rt.registry.openai_tools()[0]["function"]["name"], "math.add")
            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ToolAgent")))
            self.assertEqual(rt.store.final_state(run_id)["sum"], 5)
            self.assertEqual(rt.store.cost_summary(run_id)["tool_calls"], 1.0)

    def test_cli_tools_manifest_exports_agentledger_and_openai_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = type(
                "Args",
                (),
                {
                    "root": str(Path(tmp) / ".agentledger"),
                    "policy": None,
                    "sandbox_config": None,
                    "format": "agentledger",
                    "example": "examples/docs",
                    "out": None,
                },
            )()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_tools_manifest(args)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["tools"][0]["name"], "docs.read")
            self.assertEqual(payload["tools"][0]["input_schema"]["required"], ["path"])

            args.format = "openai"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cmd_tools_manifest(args)
            openai_payload = json.loads(stdout.getvalue())
            self.assertEqual(openai_payload["tools"][0]["type"], "function")
            self.assertEqual(openai_payload["tools"][0]["function"]["name"], "docs.read")

    def test_simple_api_async_agent_and_evidence_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def hello(ctx: Any, state: dict[str, Any]) -> dict[str, Any]:
                ctx.write_state_patch("seen", state.get("name"))
                return {"message": f"hello {state['name']}"}

            result = asyncio.run(arun(hello, root=Path(tmp) / ".agentledger", initial_state={"name": "runtime"}, evidence_dir=Path(tmp) / "evidence"))
            self.assertTrue(result.ok)
            self.assertEqual(result.output, {"message": "hello runtime"})
            self.assertEqual(result.state["seen"], "runtime")
            self.assertIsNotNone(result.evidence_path)
            assert result.evidence_path is not None
            self.assertTrue((result.evidence_path / "manifest.json").exists())

    def test_tool_approval_gate_waits_then_resumes_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls = {"count": 0}
            rt = Runtime.local(Path(tmp) / ".agentledger")

            def send_email(args: dict[str, Any]) -> dict[str, Any]:
                calls["count"] += 1
                return {"external_id": "email-1", "sent": True}

            rt.registry.register(ToolSpec(name="email.send", func=send_email, side_effect="external_write", idempotency_required=True, approval_required=True))
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                result = await ctx.call_tool("email.send", {"to": "ops@example.com", "_logical_operation": "welcome"})
                ctx.write_state_patch("email", result)

            first_ok = asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertFalse(first_ok)
            self.assertEqual(rt.store.run(run_id)["status"], "waiting_human")
            approvals = rt.store.approval_requests(run_id)
            self.assertEqual(len(approvals), 1)
            self.assertEqual(approvals[0]["status"], "PENDING")
            rt.store.approve_request(approvals[0]["approval_id"], approver="alice", reason="safe test")

            second_ok = asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertTrue(second_ok)
            self.assertEqual(calls["count"], 1)
            self.assertEqual(rt.store.final_state(run_id)["email"]["external_id"], "email-1")
            self.assertEqual(rt.store.approval_requests(run_id)[0]["status"], "APPROVED")

    def test_sandbox_required_tool_records_boundary_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            rt.registry.register(ToolSpec(name="code.eval", func=lambda args: {"value": args["value"] + 1}, sandbox_required=True, input_schema={"required": ["value"]}))
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                result = await ctx.call_tool("code.eval", {"value": 41})
                ctx.write_state_patch("answer", result["value"])

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ExecutorAgent")))
            self.assertEqual(rt.store.final_state(run_id)["answer"], 42)
            event_types = [row["type"] for row in rt.store.events(run_id)]
            self.assertIn("sandbox_started", event_types)
            self.assertIn("sandbox_completed", event_types)



    def test_sandbox_config_routes_tool_override_to_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = create_sandbox_executor({
                "default_executor": "none",
                "fail_closed": True,
                "tools": {"code.eval": {"executor": "local", "network": "deny", "timeout_seconds": 5}},
            })
            rt = Runtime.local(Path(tmp) / ".agentledger", sandbox=sandbox)
            rt.registry.register(ToolSpec(name="code.eval", func=lambda args: {"value": args["value"] + 1}, sandbox_required=True))
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                result = await ctx.call_tool("code.eval", {"value": 41})
                ctx.write_state_patch("answer", result["value"])

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ExecutorAgent")))
            started = [json.loads(row["payload_ref"]) for row in rt.store.events(run_id) if row["type"] == "sandbox_started"]
            self.assertEqual(started[0]["executor"], "local")
            self.assertEqual(started[0]["timeout_seconds"], 5)
            self.assertEqual(rt.store.final_state(run_id)["answer"], 42)

    def test_sandbox_none_fails_closed_for_required_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = create_sandbox_executor({"default_executor": "none", "fail_closed": True})
            rt = Runtime.local(Path(tmp) / ".agentledger", sandbox=sandbox)
            calls = {"count": 0}

            def unsafe(args: dict[str, Any]) -> dict[str, Any]:
                calls["count"] += 1
                return {"ok": True}

            rt.registry.register(ToolSpec(name="shell.exec", func=unsafe, sandbox_required=True))
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                await ctx.call_tool("shell.exec", {"cmd": "echo nope"})

            with self.assertRaises(RuntimeError):
                asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ExecutorAgent"))
            self.assertEqual(calls["count"], 0)
            completed = [json.loads(row["payload_ref"]) for row in rt.store.events(run_id) if row["type"] == "sandbox_completed"]
            self.assertEqual(completed[0]["error_type"], "SandboxDisabled")
            self.assertEqual(rt.store.run(run_id)["status"], "failed")

    def test_external_sandbox_adapters_are_configurable_without_core_dependencies(self) -> None:
        config = SandboxConfig.from_dict({
            "default_executor": "k8s-gvisor",
            "executors": {
                "bwrap": {"type": "bubblewrap"},
                "docker": {"type": "docker", "image": "python:3.11-slim"},
                "k8s-gvisor": {"type": "kubernetes", "runtime_class": "gvisor", "image": "sandbox:latest"},
                "firecracker": {"type": "firecracker", "endpoint": "https://sandbox.internal"},
                "e2b": {"type": "e2b"},
            },
        })
        router = create_sandbox_executor(config)
        self.assertIsInstance(router, SandboxRouter)
        description = router.describe()
        self.assertIn("k8s-gvisor", description["executors"])
        policy = router.policy_for(__import__("agentledger").SandboxPolicy(tool_name="untrusted_code.run", run_id="run_x", step_id="step_x"))
        self.assertEqual(policy.executor, "k8s-gvisor")
        result = asyncio.run(router.run_tool(lambda args: {"should_not": "run"}, {"code": "print(1)"}, policy))
        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "SandboxAdapterNotInstalled")
        self.assertEqual(result.metadata["manifest"]["kubernetes_job"]["spec"]["template"]["spec"]["runtimeClassName"], "gvisor")


    def test_kubernetes_executor_dry_run_manifest_includes_gvisor_runtime_class(self) -> None:
        sandbox = create_sandbox_executor({
            "default_executor": "k8s-gvisor",
            "executors": {
                "k8s-gvisor": {
                    "type": "kubernetes",
                    "runtime_class": "gvisor",
                    "namespace": "agentledger-sandbox",
                    "image": "python:3.11-slim",
                    "dry_run": True,
                    "resource_limits": {"memory": "128Mi"},
                }
            },
        })
        policy = __import__("agentledger").SandboxPolicy(tool_name="untrusted_code.run", run_id="run_x", step_id="step_x")
        policy = sandbox.policy_for(policy)  # type: ignore[attr-defined]
        result = asyncio.run(sandbox.run_tool(lambda args: {"bad": True}, {"_sandbox_command": ["python", "-c", "print('sandbox-ok')"]}, policy))
        self.assertTrue(result.ok)
        self.assertTrue(result.output["dry_run"])
        job = result.output["kubernetes_job"]
        pod_spec = job["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]
        self.assertEqual(job["metadata"]["namespace"], "agentledger-sandbox")
        self.assertEqual(pod_spec["runtimeClassName"], "gvisor")
        self.assertEqual(container["image"], "python:3.11-slim")
        self.assertEqual(container["command"], ["python"])
        self.assertEqual(container["args"], ["-c", "print('sandbox-ok')"])
        self.assertFalse(result.metadata["executed"])

    def test_kubernetes_dry_run_routes_through_tool_gateway_without_running_callable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = create_sandbox_executor({
                "default_executor": "k8s-gvisor",
                "executors": {
                    "k8s-gvisor": {
                        "type": "kubernetes",
                        "runtime_class": "gvisor",
                        "namespace": "agentledger-sandbox",
                        "image": "python:3.11-slim",
                        "dry_run": True,
                    }
                },
            })
            rt = Runtime.local(Path(tmp) / ".agentledger", sandbox=sandbox)
            calls = {"count": 0}

            def should_not_run(args: dict[str, Any]) -> dict[str, Any]:
                calls["count"] += 1
                return {"bad": True}

            rt.registry.register(ToolSpec(name="untrusted_code.run", func=should_not_run, sandbox_required=True))
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                result = await ctx.call_tool("untrusted_code.run", {"_sandbox_command": ["python", "-c", "print('sandbox-ok')"]})
                runtime_class = result["kubernetes_job"]["spec"]["template"]["spec"]["runtimeClassName"]
                ctx.write_state_patch("runtime_class", runtime_class)

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ExecutorAgent")))
            self.assertEqual(calls["count"], 0)
            self.assertEqual(rt.store.final_state(run_id)["runtime_class"], "gvisor")
            completed = [json.loads(row["payload_ref"]) for row in rt.store.events(run_id) if row["type"] == "sandbox_completed"]
            self.assertTrue(completed[0]["ok"])
            self.assertTrue(completed[0]["metadata"]["dry_run"])

    def test_kubernetes_executor_fails_closed_when_kubectl_missing_and_execution_enabled(self) -> None:
        sandbox = create_sandbox_executor({
            "default_executor": "k8s-real",
            "executors": {
                "k8s-real": {
                    "type": "kubernetes",
                    "runtime_class": "gvisor",
                    "namespace": "agentledger-sandbox",
                    "kubectl": "/definitely/missing/kubectl",
                    "allow_command_execution": True,
                    "dry_run": False,
                }
            },
        })
        policy = __import__("agentledger").SandboxPolicy(tool_name="cmd.echo", run_id="run_x", step_id="step_x")
        policy = sandbox.policy_for(policy)  # type: ignore[attr-defined]
        result = asyncio.run(sandbox.run_tool(lambda args: {"bad": True}, {"_sandbox_command": ["echo", "hello"]}, policy))
        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "SandboxBinaryMissing")
        self.assertIn("kubectl", result.error or "")
        self.assertEqual(result.metadata["manifest"]["kubernetes_job"]["spec"]["template"]["spec"]["runtimeClassName"], "gvisor")

    def test_bubblewrap_command_executor_runs_with_explicit_local_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = create_sandbox_executor({
                "default_executor": "bwrap-dev",
                "executors": {
                    "bwrap-dev": {
                        "type": "bubblewrap",
                        "binary": "/definitely/missing/bwrap",
                        "allow_command_execution": True,
                        "fallback_without_bwrap": True,
                    }
                },
            })
            rt = Runtime.local(Path(tmp) / ".agentledger", sandbox=sandbox)
            calls = {"count": 0}

            def should_not_run(args: dict[str, Any]) -> dict[str, Any]:
                calls["count"] += 1
                return {"bad": True}

            rt.registry.register(ToolSpec(name="cmd.echo", func=should_not_run, sandbox_required=True))
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                result = await ctx.call_tool("cmd.echo", {"_sandbox_command": [sys.executable, "-c", "print('sandbox-ok')"]})
                ctx.write_state_patch("stdout", result["stdout"].strip())

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ExecutorAgent")))
            self.assertEqual(calls["count"], 0)
            self.assertEqual(rt.store.final_state(run_id)["stdout"], "sandbox-ok")
            completed = [json.loads(row["payload_ref"]) for row in rt.store.events(run_id) if row["type"] == "sandbox_completed"]
            self.assertTrue(completed[0]["ok"])
            self.assertEqual(completed[0]["metadata"]["fallback_isolation"], "none")

    def test_docker_command_executor_fails_closed_when_binary_missing(self) -> None:
        sandbox = create_sandbox_executor({
            "default_executor": "docker-missing",
            "executors": {
                "docker-missing": {
                    "type": "docker",
                    "binary": "/definitely/missing/docker",
                    "allow_command_execution": True,
                    "image": "python:3.11-slim",
                }
            },
        })
        policy = __import__("agentledger").SandboxPolicy(tool_name="cmd.echo", run_id="run_x", step_id="step_x")
        policy = sandbox.policy_for(policy)  # type: ignore[attr-defined]
        result = asyncio.run(sandbox.run_tool(lambda args: {"bad": True}, {"_sandbox_command": ["echo", "hello"]}, policy))
        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "SandboxBinaryMissing")
        self.assertIn("docker", " ".join(result.metadata["manifest"]["command"]))

    def test_retention_planner_is_non_destructive_and_marks_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            async def agent_fn(ctx: Any, state: dict[str, Any]) -> None:
                ctx.write_state_patch("done", True)

            self.assertTrue(asyncio.run(rt.run_once(agent_fn, run_id=run_id, agent_role="ExecutorAgent")))
            planner = RetentionPlanner(rt.store, rt.blobs)
            plan = planner.plan(run_id)
            self.assertFalse(plan.destructive)
            self.assertGreater(plan.event_count, 0)
            self.assertEqual(plan.media_artifact_count, 0)
            self.assertEqual(plan.stream_checkpoint_count, 0)
            version = planner.mark_compacted(run_id, reason="unit test")
            self.assertGreater(version, 0)
            retention = rt.store.final_state(run_id)["_agentledger"]["retention"]
            self.assertTrue(retention["compacted"])

    def test_retention_planner_accounts_for_media_stream_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime.local(Path(tmp) / ".agentledger")
            run_id, _ = rt.create_run(initial_state={})

            async def agent(ctx: Any, _state: dict[str, Any]) -> None:
                _digest, blob_ref = ctx.blobs.put_json({"payload": "media-ref"})
                await ctx.create_media_artifact("frame", "frame", content_ref=blob_ref, media_metadata=MediaMetadata(kind="frame", frame_index=1))
                await ctx.create_stream_checkpoint(
                    "checkpoint",
                    stream_id="camera-1",
                    consumer_id="vision-agent",
                    offset=1,
                    chunk=StreamChunkRef(stream_id="camera-1", chunk_id="chunk-1", offset=1, content_ref=blob_ref),
                    partial_result_ref=blob_ref,
                )

            self.assertTrue(asyncio.run(rt.run_once(agent, run_id=run_id, agent_role="MediaAgent")))
            plan = RetentionPlanner(rt.store, rt.blobs).plan(run_id).to_dict()
            self.assertFalse(plan["destructive"])
            self.assertEqual(plan["media_artifact_count"], 1)
            self.assertEqual(plan["stream_checkpoint_count"], 1)
            self.assertEqual(plan["protected_blob_ref_count"], 1)
            self.assertTrue(any("media/stream nested blob refs" in action for action in plan["actions"]))

if __name__ == "__main__":
    unittest.main()
