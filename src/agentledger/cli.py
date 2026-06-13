from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from . import __version__
from .adapter_certification import build_adapter_certification_bundle, supported_adapter_certification_profiles
from .adapters import PythonFunctionAdapter
from .adapters_frameworks import AutoGenAdapter, CrewAIAdapter, LangChainRunnableAdapter, LlamaIndexAdapter, OpenAIAgentsSDKAdapter, SemanticKernelAdapter
from .adapters_langgraph import LangGraphNodeAdapter
from .backup import BackupReadinessChecker
from .blobstore import LocalBlobStore
from .blobstore_s3 import S3BlobStore, S3BlobStoreConfig
from .conformance import BlobStoreConformanceRunner, FrameworkAdapterConformanceRunner, MediaRuntimeConformanceRunner, StateStoreConformanceRunner, WorkerConformanceRunner
from .contract import contract_json
from .cost import CostAttributionReporter
from .eval import EvidenceRegressionRunner
from .diff import DivergenceReporter, EvidenceDiffer, load_evidence_path
from .evidence import EvidenceExporter
from .examples import crash_once_agent, recovery_agent, register_fake_github
from .failure import FailureAttributionReporter, FailureRegressionAnalyzer, RetryableAgentError
from .failure_injection import FailureInjectionSuite
from .inspector import InspectorDataSource, InspectorRedactionPolicy
from .lint import RuntimeBoundaryLinter, load_boundary_rules
from .media_tools import register_media_tool_conventions
from .policy import PolicyEngine
from .repro import GoldenCorpus
from .replay import ReplayEngine
from .retention import RetentionPlanner
from .review import AdversarialReviewRunner
from .runtime import Runtime
from .sandbox import SandboxConfig, create_sandbox_executor
from .scheduler import RuntimeScheduler
from .shadow import ShadowRunner
from .storage_schema import ddl_for, latest_schema_version
from .storage_postgres import PostgresStore, PostgresStoreConfig
from .storage_mysql import MySQLStore, MySQLStoreConfig
from .store import SQLiteStore
from .trace import OTLPResource, OTLPTraceExporter, TraceExporter
from .timetravel import TimeTravelDebugger
from .tools import ToolSpec
from .worker import LocalWorker, WorkerService, build_worker_deployment_plan

PROJECT_URL = "https://github.com/yaogdu/AgentLedger"
HELP_EPILOG = f"""Project: {PROJECT_URL}
Docs:    {PROJECT_URL}#readme
Install: pipx install agentledger-runtime
Package: pip install agentledger-runtime
"""


def runtime_from_root(root: str, policy_path: str | None = None, sandbox_config_path: str | None = None) -> Runtime:
    rt = Runtime.local(root, sandbox_config=sandbox_config_path)
    if policy_path:
        rt.policy = PolicyEngine.from_file(policy_path)
        rt.gateway.policy = rt.policy
    return rt


def cmd_init(args: argparse.Namespace) -> None:
    runtime_from_root(args.root, args.policy)
    print(f"initialized AgentLedger store at {args.root}")


def cmd_doctor(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    print(f"store={rt.store.path}")
    print("status=ok")
    print(f"docs={PROJECT_URL}")


def cmd_version(args: argparse.Namespace) -> None:
    print(f"agentledger {__version__}")


def cmd_run(args: argparse.Namespace) -> None:
    if args.example != "examples/side_effect_idempotency":
        raise SystemExit("this built-in demo runner currently supports examples/side_effect_idempotency")
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    external_path = Path(args.root) / "external_issues.json"
    register_fake_github(rt, external_path)
    run_id, _ = rt.create_run(initial_state={"crashed_once": False})
    first_ok = asyncio.run(rt.run_once(crash_once_agent, run_id=run_id, agent_role="ExecutorAgent"))
    if not first_ok:
        rt.store.apply_system_state_patch(
            run_id=run_id,
            patch={"crashed_once": True},
            reason="demo recovery marker after simulated worker crash",
        )
    second_ok = asyncio.run(rt.run_once(recovery_agent, run_id=run_id, agent_role="ExecutorAgent"))
    issues = json.loads(external_path.read_text(encoding="utf-8"))
    print(json.dumps({"run_id": run_id, "first_attempt_ok": first_ok, "second_attempt_ok": second_ok, "external_issue_count": len(issues), "external_issues_path": str(external_path)}, indent=2))


def cmd_debug(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    if getattr(args, "json", False) or getattr(args, "include_diffs", False) or getattr(args, "include_states", False) or getattr(args, "at_seq", None) is not None or getattr(args, "html", None):
        report = TimeTravelDebugger(store=rt.store, blobs=rt.blobs).inspect(
            args.run_id,
            at_seq=getattr(args, "at_seq", None),
            include_states=getattr(args, "include_states", False),
            include_diffs=getattr(args, "include_diffs", False),
        )
        if getattr(args, "html", None):
            path = report.write_html(args.html)
            print(json.dumps({"run_id": args.run_id, "html_report": str(path), "event_count": report.event_count}, indent=2, ensure_ascii=False))
            return
        if getattr(args, "json", False):
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
            return
        for frame in report.timeline:
            state = frame.state_version if frame.state_version is not None else "-"
            changed = ",".join(frame.changed_keys) if frame.changed_keys else "-"
            print(f"{frame.seq:03d} {frame.event_type} step={frame.step_id or '-'} state={state} changed={changed}")
            if frame.state_diff is not None and frame.state_diff.get("changed_count", 0):
                print(json.dumps({"seq": frame.seq, "state_diff": frame.state_diff}, ensure_ascii=False, sort_keys=True))
        if getattr(args, "at_seq", None) is not None:
            print(json.dumps({"state_at_seq": report.state_at_seq}, ensure_ascii=False, sort_keys=True))
        return
    for event in rt.store.events(args.run_id):
        state = event["state_version"] if event["state_version"] is not None else "-"
        print(f"{event['seq']:03d} {event['type']} step={event['step_id'] or '-'} state={state}")


def cmd_ledger(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    rows = []
    for row in rt.store.ledger(args.run_id):
        rows.append({k: row[k] for k in row.keys() if k in {"tool_name", "status", "idempotency_key", "external_id", "response_ref", "error_type"}})
    print(json.dumps(rows, indent=2))


def cmd_replay(args: argparse.Namespace) -> None:
    root = Path(args.root)
    store = SQLiteStore(root / "state.db")
    blobs = LocalBlobStore(root / "blobs")
    summary = ReplayEngine(store=store, blobs=blobs).replay(args.run_id)
    print(json.dumps(summary.__dict__, indent=2, ensure_ascii=False))


def cmd_evidence(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(args.run_id)
    if getattr(args, "html", None):
        path = bundle.write_html(args.html)
        print(json.dumps({"run_id": args.run_id, "evidence_html": str(path), "bundle_hash": bundle.to_dict()["bundle_hash"]}, indent=2))
        return
    if args.dir:
        path = bundle.write_dir(args.dir)
        print(json.dumps({"run_id": args.run_id, "evidence_dir": str(path), "bundle_hash": bundle.to_dict()["bundle_hash"]}, indent=2))
        return
    if args.out:
        path = bundle.write(args.out)
        print(json.dumps({"run_id": args.run_id, "evidence_path": str(path), "bundle_hash": bundle.to_dict()["bundle_hash"]}, indent=2))
        return
    print(bundle.to_json())


def _write_inspector_report(report, args: argparse.Namespace) -> None:
    if getattr(args, "html", None):
        path = report.write_html(args.html)
        print(json.dumps({"schema_version": report.to_dict()["schema_version"], "run_id": report.to_dict()["run"].get("run_id"), "inspector_html": str(path)}, indent=2, ensure_ascii=False))
        return
    if getattr(args, "out", None):
        path = report.write(args.out)
        print(json.dumps({"schema_version": report.to_dict()["schema_version"], "run_id": report.to_dict()["run"].get("run_id"), "inspector_report": str(path)}, indent=2, ensure_ascii=False))
        return
    print(report.to_json())


def _write_inspector_run_index(index, args: argparse.Namespace) -> None:
    if getattr(args, "html", None):
        path = index.write_html(args.html)
        print(json.dumps({"schema_version": index.to_dict()["schema_version"], "run_count": index.to_dict()["summary"].get("run_count"), "inspector_html": str(path)}, indent=2, ensure_ascii=False))
        return
    if getattr(args, "out", None):
        path = index.write(args.out)
        print(json.dumps({"schema_version": index.to_dict()["schema_version"], "run_count": index.to_dict()["summary"].get("run_count"), "inspector_runs": str(path)}, indent=2, ensure_ascii=False))
        return
    print(index.to_json())


def _inspector_redaction_policy(args: argparse.Namespace) -> InspectorRedactionPolicy | None:
    keys: list[str] = []
    replacement = getattr(args, "redaction_replacement", "<redacted>")
    policy_path = getattr(args, "redaction_policy", None)
    policy = InspectorRedactionPolicy.from_path(policy_path) if policy_path else None
    if policy:
        keys.extend(policy.keys)
        replacement = policy.replacement
    keys.extend(getattr(args, "redact_key", None) or [])
    if not keys:
        return None
    return InspectorRedactionPolicy(keys=tuple(dict.fromkeys(keys)), replacement=replacement)


def cmd_inspector_run(args: argparse.Namespace) -> None:
    source = InspectorDataSource()
    blob_root = args.blob_root or str(Path(args.root) / "blobs")
    redaction_policy = _inspector_redaction_policy(args)
    if args.backend == "sqlite":
        db_path = args.db or str(Path(args.root) / "state.db")
        report = source.from_sqlite(db_path=db_path, blob_root=blob_root, run_id=args.run_id, include_payloads=args.include_payloads, redaction_policy=redaction_policy)
    elif args.backend == "postgres":
        config = PostgresStoreConfig.from_env(dsn=args.dsn, schema=args.schema)
        report = source.from_postgres(dsn=config.dsn, schema=config.schema, blob_root=blob_root, run_id=args.run_id, include_payloads=args.include_payloads, redaction_policy=redaction_policy)
    elif args.backend == "mysql":
        config = MySQLStoreConfig.from_env(dsn=args.dsn, database=args.database)
        report = source.from_mysql(dsn=config.dsn, database=config.database, blob_root=blob_root, run_id=args.run_id, include_payloads=args.include_payloads, redaction_policy=redaction_policy)
    else:
        raise ValueError(f"unsupported inspector backend: {args.backend}")
    _write_inspector_report(report, args)


def cmd_inspector_runs(args: argparse.Namespace) -> None:
    source = InspectorDataSource()
    blob_root = getattr(args, "blob_root", None)
    if args.backend == "sqlite":
        db_path = args.db or str(Path(args.root) / "state.db")
        resolved_blob_root = blob_root if blob_root is not None else str(Path(args.root) / "blobs")
        index = source.runs_from_sqlite(db_path=db_path, blob_root=resolved_blob_root, limit=args.limit, status=args.status, run_link_template=args.run_link_template)
    elif args.backend == "postgres":
        config = PostgresStoreConfig.from_env(dsn=args.dsn, schema=args.schema)
        index = source.runs_from_postgres(dsn=config.dsn, schema=config.schema, blob_root=blob_root, limit=args.limit, status=args.status, run_link_template=args.run_link_template)
    elif args.backend == "mysql":
        config = MySQLStoreConfig.from_env(dsn=args.dsn, database=args.database)
        index = source.runs_from_mysql(dsn=config.dsn, database=config.database, blob_root=blob_root, limit=args.limit, status=args.status, run_link_template=args.run_link_template)
    else:
        raise ValueError(f"unsupported inspector backend: {args.backend}")
    _write_inspector_run_index(index, args)


def cmd_inspector_evidence(args: argparse.Namespace) -> None:
    report = InspectorDataSource().from_evidence_path(args.path, include_payloads=args.include_payloads, redaction_policy=_inspector_redaction_policy(args))
    _write_inspector_report(report, args)


def cmd_evidence_check(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(args.run_id).to_dict()
    report = EvidenceRegressionRunner().evaluate(bundle, max_total_usd=args.max_total_usd)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


def cmd_review_checklist(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    evidence = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(args.run_id).to_dict()
    report = AdversarialReviewRunner().evaluate(evidence, max_total_usd=args.max_total_usd)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if args.fail_on_risk and not report.passed:
        raise SystemExit(1)


def cmd_cost_report(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    report = CostAttributionReporter(rt.store).report(args.run_id)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


def cmd_evidence_regression(args: argparse.Namespace) -> None:
    golden = load_evidence_path(args.golden)
    current = load_evidence_path(args.current)
    report = EvidenceRegressionRunner().evaluate_regression(
        golden,
        current,
        require_same_final_state=not args.allow_final_state_changes,
        require_same_event_types=not args.allow_event_type_changes,
        require_same_tool_ledger_statuses=not args.allow_tool_ledger_status_changes,
        require_same_media_artifacts=not getattr(args, "allow_media_artifact_changes", False),
        require_same_stream_checkpoints=not getattr(args, "allow_stream_checkpoint_changes", False),
        max_total_usd_delta=args.max_total_usd_delta,
    )
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if not report.passed:
        raise SystemExit(1)


def cmd_shadow(args: argparse.Namespace) -> None:
    if args.example != "examples/side_effect_idempotency":
        raise SystemExit("this built-in shadow demo currently supports examples/side_effect_idempotency")
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    external_path = Path(args.root) / "external_issues.json"
    register_fake_github(rt, external_path)
    before = json.loads(external_path.read_text(encoding="utf-8"))
    report = asyncio.run(ShadowRunner(rt).run(recovery_agent, source_run_id=args.run_id, agent_role="ShadowAgent"))
    after = json.loads(external_path.read_text(encoding="utf-8"))
    print(json.dumps({**report.to_dict(), "external_issue_count_before": len(before), "external_issue_count_after": len(after)}, indent=2, ensure_ascii=False))



def cmd_status(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    print(json.dumps(RuntimeScheduler(rt.store).status(args.run_id), indent=2, ensure_ascii=False))


def cmd_cancel(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    cancelled_steps = RuntimeScheduler(rt.store).cancel_run(args.run_id, reason=args.reason)
    print(json.dumps({"run_id": args.run_id, "cancelled_steps": cancelled_steps, "reason": args.reason}, indent=2, ensure_ascii=False))


def cmd_recover_expired(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    summary = RuntimeScheduler(rt.store).recover_expired_leases()
    print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))


def cmd_conformance(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    state_report = StateStoreConformanceRunner(lambda: rt.store, name="sqlite-local").run()
    blob_report = BlobStoreConformanceRunner(lambda: rt.blobs, name="local-blob").run()
    worker_report = WorkerConformanceRunner(lambda: rt.store, name="local-worker", workers=4, close_stores=False).run()
    media_report = MediaRuntimeConformanceRunner(lambda: rt, name="media-runtime").run()
    passed = state_report.passed and blob_report.passed and worker_report.passed and media_report.passed
    print(
        json.dumps(
            {
                "passed": passed,
                "reports": {
                    "state_store": state_report.to_dict(),
                    "blob_store": blob_report.to_dict(),
                    "worker_runtime": worker_report.to_dict(),
                    "media_runtime": media_report.to_dict(),
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if not passed:
        raise SystemExit(1)


def create_blob_store(args: argparse.Namespace, *, s3_client=None):
    backend = getattr(args, "backend", "local")
    if backend == "local":
        path = getattr(args, "path", None) or str(Path(args.root) / "blobs")
        return LocalBlobStore(path)
    if backend == "s3":
        config = S3BlobStoreConfig.from_env(
            bucket=getattr(args, "bucket", None),
            prefix=getattr(args, "prefix", None),
            endpoint_url=getattr(args, "endpoint_url", None),
            region_name=getattr(args, "region", None),
            profile_name=getattr(args, "profile", None),
        )
        return S3BlobStore(config, client=s3_client)
    raise ValueError(f"unsupported blob backend: {backend}")


def _sql_connection_for(value):
    return value() if callable(value) else value


def create_state_store(args: argparse.Namespace, *, postgres_connection=None, mysql_connection=None):
    backend = getattr(args, "backend", "sqlite")
    if backend == "sqlite":
        store = SQLiteStore(Path(args.root) / "state.db")
        store.init()
        return store
    if backend == "postgres":
        config = PostgresStoreConfig.from_env(
            dsn=getattr(args, "dsn", None),
            schema=getattr(args, "schema", None),
        )
        injected_connection = postgres_connection() if callable(postgres_connection) else postgres_connection
        store = PostgresStore(config, connection=injected_connection, owns_connection=postgres_connection is None or callable(postgres_connection))
        store.init()
        return store
    if backend == "mysql":
        config = MySQLStoreConfig.from_env(
            dsn=getattr(args, "dsn", None),
            database=getattr(args, "database", None),
        )
        injected_connection = _sql_connection_for(mysql_connection)
        store = MySQLStore(config, connection=injected_connection, owns_connection=mysql_connection is None or callable(mysql_connection))
        store.init()
        return store
    raise ValueError(f"unsupported state backend: {backend}")


def cmd_state_conformance(args: argparse.Namespace, *, postgres_connection=None, mysql_connection=None) -> None:
    def factory():
        return create_state_store(args, postgres_connection=postgres_connection, mysql_connection=mysql_connection)

    injected = postgres_connection if args.backend == "postgres" else mysql_connection if args.backend == "mysql" else None
    close_stores = not (injected is not None and not callable(injected))
    report = StateStoreConformanceRunner(factory, name=f"{args.backend}-state", close_stores=close_stores).run()
    print(json.dumps({"backend": args.backend, "passed": report.passed, "report": report.to_dict()}, indent=2, ensure_ascii=False))
    if not report.passed:
        raise SystemExit(1)


def cmd_blob_conformance(args: argparse.Namespace, *, s3_client=None) -> None:
    def factory():
        return create_blob_store(args, s3_client=s3_client)

    report = BlobStoreConformanceRunner(factory, name=f"{args.backend}-blob").run()
    print(json.dumps({"backend": args.backend, "passed": report.passed, "report": report.to_dict()}, indent=2, ensure_ascii=False))
    if not report.passed:
        raise SystemExit(1)



def cmd_worker_plan(args: argparse.Namespace) -> None:
    plan = build_worker_deployment_plan(
        agent_entrypoint=args.example,
        root=args.root,
        backend=args.backend,
        replicas=args.replicas,
        worker_id_prefix=args.worker_id_prefix,
        lease_seconds=args.lease_seconds,
        max_idle_polls=None if args.daemon else args.max_idle_polls,
        idle_sleep_seconds=args.idle_sleep_seconds,
    )
    print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))

def cmd_worker_conformance(args: argparse.Namespace, *, postgres_connection=None, mysql_connection=None) -> None:
    def factory():
        return create_state_store(args, postgres_connection=postgres_connection, mysql_connection=mysql_connection)

    injected = postgres_connection if args.backend == "postgres" else mysql_connection if args.backend == "mysql" else None
    close_stores = not (injected is not None and not callable(injected))
    report = WorkerConformanceRunner(
        factory,
        name=f"{args.backend}-worker",
        workers=args.workers,
        concurrent=args.concurrent,
        close_stores=close_stores,
    ).run()
    print(json.dumps({"backend": args.backend, "passed": report.passed, "report": report.to_dict()}, indent=2, ensure_ascii=False))
    if not report.passed:
        raise SystemExit(1)


def create_framework_adapter(kind: str):
    if kind == "python-function":
        async def agent_fn(ctx, state):
            ctx.write_state_patch("adapter_output", {"framework": "python-function", "topic": state.get("topic")})

        return PythonFunctionAdapter(agent_fn, role="PythonFunctionAgent")
    if kind == "langgraph-node":
        async def node(ctx, state):
            ctx.write_state_patch("adapter_output", {"framework": "langgraph-node", "topic": state.get("topic")})

        return LangGraphNodeAdapter(node)
    if kind == "langchain":
        class FakeLangChainRunnable:
            def invoke(self, payload):
                return {"framework": "langchain", "topic": payload.get("topic")}

        return LangChainRunnableAdapter(FakeLangChainRunnable(), output_key="adapter_output")
    if kind == "crewai":
        class FakeCrew:
            async def akickoff(self, payload):
                return {"framework": "crewai", "topic": payload.get("topic")}

        return CrewAIAdapter(FakeCrew(), output_key="adapter_output")
    if kind == "autogen":
        class FakeAutoGenAgent:
            def generate_reply(self, payload):
                return {"framework": "autogen", "topic": payload.get("topic")}

        return AutoGenAdapter(FakeAutoGenAgent(), output_key="adapter_output")
    if kind == "openai-agents":
        class FakeOpenAIAgent:
            async def arun(self, payload):
                return {"framework": "openai-agents", "topic": payload.get("topic")}

        return OpenAIAgentsSDKAdapter(FakeOpenAIAgent(), output_key="adapter_output")
    if kind == "llamaindex":
        class FakeLlamaIndexQueryEngine:
            def query(self, payload):
                return {"framework": "llamaindex", "topic": payload.get("topic")}

        return LlamaIndexAdapter(FakeLlamaIndexQueryEngine(), output_key="adapter_output")
    if kind == "semantic-kernel":
        class FakeSemanticKernel:
            async def invoke(self, payload):
                return {"framework": "semantic-kernel", "topic": payload.get("topic")}

        return SemanticKernelAdapter(FakeSemanticKernel(), output_key="adapter_output")
    raise ValueError(f"unsupported adapter kind: {kind}")


def cmd_adapter_conformance(args: argparse.Namespace) -> None:
    report = FrameworkAdapterConformanceRunner(lambda: create_framework_adapter(args.kind), name=f"{args.kind}-adapter").run()
    print(json.dumps({"kind": args.kind, "passed": report.passed, "report": report.to_dict()}, indent=2, ensure_ascii=False))
    if not report.passed:
        raise SystemExit(1)


def cmd_adapter_certify(args: argparse.Namespace) -> None:
    bundle = build_adapter_certification_bundle(
        args.kind,
        adapter_version=args.adapter_version,
        package_name=args.package_name,
    ).to_dict()
    if args.out:
        path = Path(args.out)
        path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"kind": args.kind, "certification_bundle": str(path)}, indent=2, ensure_ascii=False))
        return
    print(json.dumps(bundle, indent=2, ensure_ascii=False))


def cmd_worker_run(args: argparse.Namespace) -> None:
    if args.example != "examples/transient_retry":
        raise SystemExit("this built-in worker demo currently supports examples/transient_retry")
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    run_id, _ = rt.create_run(initial_state={}, retry_policy={"max_attempts": args.max_attempts})
    attempts = {"count": 0}

    async def transient_agent(ctx, state):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RetryableAgentError("transient worker-loop failure")
        ctx.write_state_patch("attempts", attempts["count"])
        ctx.write_state_patch("worker_loop", True)

    summary = asyncio.run(
        LocalWorker(rt, transient_agent, worker_id=args.worker_id, agent_role="WorkerAgent", lease_seconds=args.lease_seconds).run_until_idle(
            run_id=run_id,
            max_iterations=args.max_iterations,
        )
    )
    print(json.dumps({"run_id": run_id, "summary": summary.to_dict(), "final_state": rt.store.final_state(run_id)}, indent=2, ensure_ascii=False))


def cmd_worker_serve(args: argparse.Namespace) -> None:
    if args.example != "examples/transient_retry":
        raise SystemExit("this built-in worker service demo currently supports examples/transient_retry")
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    run_id = args.run_id
    if run_id is None:
        run_id, _ = rt.create_run(initial_state={}, retry_policy={"max_attempts": args.max_attempts})
    attempts = {"count": 0}

    async def transient_agent(ctx, state):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RetryableAgentError("transient worker-service failure")
        ctx.write_state_patch("attempts", attempts["count"])
        ctx.write_state_patch("worker_service", True)

    service = WorkerService(rt, transient_agent, worker_id=args.worker_id, agent_role="WorkerAgent", lease_seconds=args.lease_seconds)
    if args.install_signal_handlers:
        service.install_signal_handlers()
    max_idle_polls = None if args.max_idle_polls <= 0 else args.max_idle_polls
    summary = asyncio.run(
        service.serve(
            run_id=run_id,
            max_loops=args.max_loops,
            max_idle_polls=max_idle_polls,
            idle_sleep_seconds=args.idle_sleep_seconds,
        )
    )
    print(json.dumps({"run_id": run_id, "summary": summary.to_dict(), "final_state": rt.store.final_state(run_id)}, indent=2, ensure_ascii=False))


def cmd_diff(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    if args.evidence_paths:
        left = load_evidence_path(args.left)
        right = load_evidence_path(args.right)
    else:
        left = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(args.left).to_dict()
        right = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(args.right).to_dict()
    report = EvidenceDiffer().compare(left, right)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


def cmd_divergence(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    if args.evidence_paths:
        left = load_evidence_path(args.left)
        right = load_evidence_path(args.right)
    else:
        left = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(args.left).to_dict()
        right = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(args.right).to_dict()
    report = DivergenceReporter().compare(left, right)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if args.fail_on_divergence and not report.same:
        raise SystemExit(1)


def cmd_trace(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    bundle = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(args.run_id)
    if args.format == "otlp":
        exporter = OTLPTraceExporter(resource=OTLPResource(service_name=args.service_name, service_version=args.service_version))
        result: dict[str, object] = {"run_id": args.run_id, "format": "otlp"}
        if args.out:
            path = exporter.write_json(bundle, args.out)
            result["trace_path"] = str(path)
            result["span_count"] = len(exporter.trace_exporter.spans(bundle))
        if getattr(args, "otlp_endpoint", None):
            result["collector"] = exporter.post_json(bundle, args.otlp_endpoint, timeout=args.otlp_timeout)
        if args.out or getattr(args, "otlp_endpoint", None):
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        print(exporter.to_json(bundle))
        return
    exporter = TraceExporter()
    if args.out:
        path = exporter.write_jsonl(bundle, args.out)
        print(json.dumps({"run_id": args.run_id, "trace_path": str(path), "format": "jsonl", "span_count": len(exporter.spans(bundle))}, indent=2, ensure_ascii=False))
        return
    print(exporter.to_jsonl(bundle), end="")


def cmd_timetravel(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    report = TimeTravelDebugger(store=rt.store, blobs=rt.blobs).inspect(
        args.run_id,
        at_seq=args.at_seq,
        include_states=args.include_states,
        include_diffs=getattr(args, "include_diffs", False),
    )
    if getattr(args, "html", None):
        path = report.write_html(args.html)
        print(json.dumps({"run_id": args.run_id, "html_report": str(path), "event_count": report.event_count}, indent=2, ensure_ascii=False))
        return
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


def cmd_postgres_ddl(args: argparse.Namespace) -> None:
    print(PostgresStore.ddl())


def cmd_mysql_ddl(args: argparse.Namespace) -> None:
    print(MySQLStore.ddl())


def cmd_contract_export(args: argparse.Namespace) -> None:
    payload = contract_json()
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print(json.dumps({"contract_path": args.out}, indent=2))
        return
    print(payload)


def cmd_migrate_up(args: argparse.Namespace, *, postgres_connection=None, mysql_connection=None) -> None:
    if args.dialect == "sqlite":
        store = SQLiteStore(Path(args.root) / "state.db")
        try:
            store.init()
            print(json.dumps(store.migration_status().to_dict(), indent=2, ensure_ascii=False))
        finally:
            store.close()
        return
    if args.dialect == "postgres":
        config = PostgresStoreConfig.from_env(dsn=getattr(args, "dsn", None), schema=getattr(args, "schema", None))
        injected_connection = postgres_connection() if callable(postgres_connection) else postgres_connection
        store = PostgresStore(config, connection=injected_connection, owns_connection=postgres_connection is None or callable(postgres_connection))
        try:
            store.init()
            print(json.dumps({"config": config.to_dict(), "migration_status": store.migration_status().to_dict()}, indent=2, ensure_ascii=False))
        finally:
            store.close()
        return
    if args.dialect == "mysql":
        config = MySQLStoreConfig.from_env(dsn=getattr(args, "dsn", None), database=getattr(args, "database", None))
        injected_connection = _sql_connection_for(mysql_connection)
        store = MySQLStore(config, connection=injected_connection, owns_connection=mysql_connection is None or callable(mysql_connection))
        try:
            store.init()
            print(json.dumps({"config": config.to_dict(), "migration_status": store.migration_status().to_dict()}, indent=2, ensure_ascii=False))
        finally:
            store.close()
        return
    raise ValueError(f"unsupported migration dialect: {args.dialect}")


def cmd_migrate_status(args: argparse.Namespace, *, postgres_connection=None, mysql_connection=None) -> None:
    if args.dialect in {"postgres", "mysql"}:
        try:
            if args.dialect == "postgres":
                config = PostgresStoreConfig.from_env(dsn=getattr(args, "dsn", None), schema=getattr(args, "schema", None))
                injected_connection = _sql_connection_for(postgres_connection)
                store = PostgresStore(config, connection=injected_connection, owns_connection=postgres_connection is None or callable(postgres_connection))
            else:
                config = MySQLStoreConfig.from_env(dsn=getattr(args, "dsn", None), database=getattr(args, "database", None))
                injected_connection = _sql_connection_for(mysql_connection)
                store = MySQLStore(config, connection=injected_connection, owns_connection=mysql_connection is None or callable(mysql_connection))
        except ValueError:
            print(json.dumps({"dialect": args.dialect, "latest_version": latest_schema_version(args.dialect), "status": "dsn-not-configured"}, indent=2))
            return
        try:
            print(json.dumps({"config": config.to_dict(), "migration_status": store.migration_status().to_dict()}, indent=2, ensure_ascii=False))
        finally:
            store.close()
        return
    if args.dialect != "sqlite":
        print(json.dumps({"dialect": args.dialect, "latest_version": latest_schema_version(args.dialect), "status": "ddl-only in runtime-core"}, indent=2))
        return
    store = SQLiteStore(Path(args.root) / "state.db")
    try:
        store.init()
        print(json.dumps(store.migration_status().to_dict(), indent=2, ensure_ascii=False))
    finally:
        store.close()


def cmd_migrate_ddl(args: argparse.Namespace) -> None:
    print(ddl_for(args.dialect))


def cmd_policy_check(args: argparse.Namespace) -> None:
    policy = PolicyEngine.from_file(args.policy_file)
    print(json.dumps(policy.explain(args.role, args.tool, args.risk_level), indent=2, ensure_ascii=False))


def _approval_row(row):
    return {key: row[key] for key in row.keys() if key in {"approval_id", "tool_name", "risk_level", "status", "reason", "requested_by", "approved_by", "decision_reason", "created_at", "updated_at"}}


def cmd_approvals(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    print(json.dumps([_approval_row(row) for row in rt.store.approval_requests(args.run_id)], indent=2, ensure_ascii=False))


def cmd_approve(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    row = rt.store.approve_request(args.approval_id, approver=args.approver, reason=args.reason)
    print(json.dumps(_approval_row(row), indent=2, ensure_ascii=False))


def cmd_deny(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    row = rt.store.deny_request(args.approval_id, approver=args.approver, reason=args.reason)
    print(json.dumps(_approval_row(row), indent=2, ensure_ascii=False))


def cmd_retention_plan(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    print(json.dumps(RetentionPlanner(rt.store, rt.blobs).plan(args.run_id).to_dict(), indent=2, ensure_ascii=False))


def cmd_retention_mark(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    version = RetentionPlanner(rt.store, rt.blobs).mark_compacted(args.run_id, reason=args.reason)
    print(json.dumps({"run_id": args.run_id, "state_version": version, "marked_compacted": True}, indent=2, ensure_ascii=False))


def cmd_backup_check(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    report = BackupReadinessChecker(store=rt.store, blobs=rt.blobs).check_run(args.run_id)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if not report.passed:
        raise SystemExit(1)


def cmd_sandbox_inspect(args: argparse.Namespace) -> None:
    config = SandboxConfig.from_file(args.config) if args.config else SandboxConfig()
    executor = create_sandbox_executor(config)
    describe = executor.describe() if hasattr(executor, "describe") else {"executor": type(executor).__name__}
    print(json.dumps({"config": config.to_dict(), "runtime": describe}, indent=2, ensure_ascii=False))


def register_example_tool_catalog(rt: Runtime, example: str | None) -> None:
    if example is None:
        return
    if example == "examples/side_effect_idempotency":
        register_fake_github(rt, Path(rt.store.path).parent / "external_issues.json")
        return
    if example == "examples/docs":
        rt.register_tool(
            ToolSpec(
                name="docs.read",
                description="Read a document by path.",
                func=lambda args: {"path": args["path"], "content": ""},
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string", "minLength": 1}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["path", "content"],
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                },
            )
        )
        return
    if example == "examples/media_stream":
        register_media_tool_conventions(rt.registry)
        return
    raise SystemExit(f"unknown tool catalog example: {example}")


def cmd_tools_manifest(args: argparse.Namespace) -> None:
    if args.root == ".agentledger":
        with tempfile.TemporaryDirectory(prefix="agentledger-tools-") as tmp:
            rt = runtime_from_root(Path(tmp) / ".agentledger", args.policy, getattr(args, "sandbox_config", None))
            _emit_tools_manifest(rt, args)
        return
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    _emit_tools_manifest(rt, args)


def _emit_tools_manifest(rt: Runtime, args: argparse.Namespace) -> None:
    register_example_tool_catalog(rt, args.example)
    if args.format == "openai":
        payload = {"tools": rt.registry.openai_tools()}
    else:
        payload = rt.registry.manifest()
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"tool_count": len(payload["tools"]), "path": args.out}, indent=2, ensure_ascii=False))
        return
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def cmd_lint_boundary(args: argparse.Namespace) -> None:
    rules = None
    if getattr(args, "rules", None):
        rules = load_boundary_rules(args.rules, include_defaults=not getattr(args, "replace_defaults", False))
    report = RuntimeBoundaryLinter(rules=rules).scan(args.paths, exclude=args.exclude or ())
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if not report.passed and not args.no_fail:
        raise SystemExit(1)


def cmd_failure_inject(args: argparse.Namespace) -> None:
    report = FailureInjectionSuite(Path(args.root) / "failure-injection").run(args.scenario)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if not report.passed:
        raise SystemExit(1)


def cmd_failure_report(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    report = FailureAttributionReporter(rt.store).report(args.run_id)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


def cmd_failure_export(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root, args.policy, getattr(args, "sandbox_config", None))
    payload = FailureAttributionReporter(rt.store).report(args.run_id).to_dict()["failure_export"]
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"run_id": args.run_id, "failure_export": str(path), "schema_version": payload["schema_version"]}, indent=2, ensure_ascii=False))
        return
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_failure_regress(args: argparse.Namespace) -> None:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    current = json.loads(Path(args.current).read_text(encoding="utf-8"))
    report = FailureRegressionAnalyzer().compare(baseline, current)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"failure_regression": str(path), "same": report["same"], "schema_version": report["schema_version"]}, indent=2, ensure_ascii=False))
        return
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.fail_on_regression and report["summary"]["new_failure_count"]:
        raise SystemExit(1)


def _corpus(args: argparse.Namespace) -> GoldenCorpus:
    return GoldenCorpus(args.corpus_dir or (Path(args.root) / "golden-corpus"))


def cmd_corpus_add(args: argparse.Namespace) -> None:
    metadata = json.loads(args.metadata) if args.metadata else {}
    case = _corpus(args).add(args.name, args.evidence, metadata=metadata)
    print(json.dumps(case.to_dict(), indent=2, ensure_ascii=False))


def cmd_corpus_seed(args: argparse.Namespace) -> None:
    corpus = _corpus(args)
    if args.list_builtins:
        print(json.dumps({"builtins": corpus.builtin_names()}, indent=2, ensure_ascii=False))
        return
    case = corpus.seed_builtin(args.name)
    print(json.dumps(case.to_dict(), indent=2, ensure_ascii=False))


def cmd_corpus_list(args: argparse.Namespace) -> None:
    cases = [case.to_dict() for case in _corpus(args).list()]
    print(json.dumps({"cases": cases, "count": len(cases)}, indent=2, ensure_ascii=False))


def cmd_corpus_eval(args: argparse.Namespace) -> None:
    report = _corpus(args).evaluate(
        args.name,
        args.current,
        require_same_final_state=not args.allow_final_state_changes,
        require_same_event_types=not args.allow_event_type_changes,
        require_same_tool_ledger_statuses=not args.allow_tool_ledger_status_changes,
        require_same_media_artifacts=not getattr(args, "allow_media_artifact_changes", False),
        require_same_stream_checkpoints=not getattr(args, "allow_stream_checkpoint_changes", False),
        max_total_usd_delta=args.max_total_usd_delta,
    )
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if not report.passed:
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentledger",
        description="Durable execution and reliability runtime for production AI agents.",
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=".agentledger", help="runtime data root")
    parser.add_argument("--policy", help="optional policy YAML/JSON file")
    parser.add_argument("--sandbox-config", help="optional sandbox JSON/YAML config file")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.set_defaults(func=cmd_init)
    doctor = sub.add_parser("doctor")
    doctor.set_defaults(func=cmd_doctor)
    version = sub.add_parser("version")
    version.set_defaults(func=cmd_version)
    run = sub.add_parser("run")
    run.add_argument("example")
    run.set_defaults(func=cmd_run)
    debug = sub.add_parser("debug")
    debug.add_argument("run_id")
    debug.add_argument("--json", action="store_true", help="emit the time-travel debug timeline as JSON")
    debug.add_argument("--at-seq", type=int, help="also show reconstructed state at this event sequence")
    debug.add_argument("--include-diffs", action="store_true", help="include state diff details in the debug timeline")
    debug.add_argument("--include-states", action="store_true", help="include reconstructed state after each event")
    debug.add_argument("--html", help="write a static HTML debug report and print its path")
    debug.set_defaults(func=cmd_debug)
    ledger = sub.add_parser("ledger")
    ledger.add_argument("run_id")
    ledger.set_defaults(func=cmd_ledger)
    replay = sub.add_parser("replay")
    replay.add_argument("run_id")
    replay.set_defaults(func=cmd_replay)
    evidence = sub.add_parser("evidence")
    evidence.add_argument("run_id")
    evidence.add_argument("--out")
    evidence.add_argument("--dir")
    evidence.add_argument("--html", help="write a static HTML evidence report and print its path")
    evidence.set_defaults(func=cmd_evidence)

    inspector = sub.add_parser("inspector", help="read-only runtime and evidence inspector")
    inspector_sub = inspector.add_subparsers(dest="inspector_cmd", required=True)
    inspector_run = inspector_sub.add_parser("run", help="inspect one run from a read-only runtime store")
    inspector_run.add_argument("run_id")
    inspector_run.add_argument("--root", default=argparse.SUPPRESS, help="runtime data root; accepted here for inspector command ergonomics")
    inspector_run.add_argument("--backend", choices=["sqlite", "postgres", "mysql"], default="sqlite")
    inspector_run.add_argument("--db", help="SQLite database path; defaults to <root>/state.db")
    inspector_run.add_argument("--blob-root", help="local blob root; defaults to <root>/blobs")
    inspector_run.add_argument("--dsn", help="Postgres/MySQL DSN; falls back to AGENTLEDGER_POSTGRES_DSN or AGENTLEDGER_MYSQL_DSN")
    inspector_run.add_argument("--schema", default="agentledger", help="Postgres schema; defaults to agentledger")
    inspector_run.add_argument("--database", help="MySQL database; falls back to AGENTLEDGER_MYSQL_DATABASE")
    inspector_run.add_argument("--include-payloads", action="store_true", help="include raw event payloads in the report")
    inspector_run.add_argument("--redact-key", action="append", default=[], help="redact a sensitive key from Inspector JSON/HTML output; repeatable")
    inspector_run.add_argument("--redaction-policy", help="JSON redaction policy file with keys and optional replacement")
    inspector_run.add_argument("--redaction-replacement", default="<redacted>", help="replacement text for --redact-key values")
    inspector_run.add_argument("--out", help="write the Inspector JSON read model")
    inspector_run.add_argument("--html", help="write a static HTML Inspector report")
    inspector_run.set_defaults(func=cmd_inspector_run)
    inspector_runs = inspector_sub.add_parser("runs", help="inspect recent runs from a read-only runtime store")
    inspector_runs.add_argument("--root", default=argparse.SUPPRESS, help="runtime data root; accepted here for inspector command ergonomics")
    inspector_runs.add_argument("--backend", choices=["sqlite", "postgres", "mysql"], default="sqlite")
    inspector_runs.add_argument("--db", help="SQLite database path; defaults to <root>/state.db")
    inspector_runs.add_argument("--blob-root", help="optional local blob root used to extract agent run ids from event payloads")
    inspector_runs.add_argument("--dsn", help="Postgres/MySQL DSN; falls back to AGENTLEDGER_POSTGRES_DSN or AGENTLEDGER_MYSQL_DSN")
    inspector_runs.add_argument("--schema", default="agentledger", help="Postgres schema; defaults to agentledger")
    inspector_runs.add_argument("--database", help="MySQL database; falls back to AGENTLEDGER_MYSQL_DATABASE")
    inspector_runs.add_argument("--limit", type=int, default=100, help="maximum runs to list; capped by the store at 1000")
    inspector_runs.add_argument("--status", help="optional run status filter")
    inspector_runs.add_argument("--run-link-template", help="optional single-run Inspector link template, for example /runs/{run_id}/inspector.html")
    inspector_runs.add_argument("--out", help="write the Inspector run index JSON read model")
    inspector_runs.add_argument("--html", help="write a static HTML Inspector run index")
    inspector_runs.set_defaults(func=cmd_inspector_runs)
    inspector_evidence = inspector_sub.add_parser("evidence", help="inspect an exported evidence bundle file or directory")
    inspector_evidence.add_argument("path")
    inspector_evidence.add_argument("--include-payloads", action="store_true", help="include raw event payloads in the report")
    inspector_evidence.add_argument("--redact-key", action="append", default=[], help="redact a sensitive key from Inspector JSON/HTML output; repeatable")
    inspector_evidence.add_argument("--redaction-policy", help="JSON redaction policy file with keys and optional replacement")
    inspector_evidence.add_argument("--redaction-replacement", default="<redacted>", help="replacement text for --redact-key values")
    inspector_evidence.add_argument("--out", help="write the Inspector JSON read model")
    inspector_evidence.add_argument("--html", help="write a static HTML Inspector report")
    inspector_evidence.set_defaults(func=cmd_inspector_evidence)

    evidence_check = sub.add_parser("evidence-check")
    evidence_check.add_argument("run_id")
    evidence_check.add_argument("--max-total-usd", type=float)
    evidence_check.set_defaults(func=cmd_evidence_check)
    review = sub.add_parser("review")
    review_sub = review.add_subparsers(dest="review_cmd", required=True)
    review_checklist = review_sub.add_parser("checklist")
    review_checklist.add_argument("run_id")
    review_checklist.add_argument("--max-total-usd", type=float)
    review_checklist.add_argument("--fail-on-risk", action="store_true")
    review_checklist.set_defaults(func=cmd_review_checklist)
    cost = sub.add_parser("cost")
    cost_sub = cost.add_subparsers(dest="cost_cmd", required=True)
    cost_report = cost_sub.add_parser("report")
    cost_report.add_argument("run_id")
    cost_report.set_defaults(func=cmd_cost_report)
    evidence_regression = sub.add_parser("evidence-regression")
    evidence_regression.add_argument("golden", help="golden evidence bundle file or directory")
    evidence_regression.add_argument("current", help="current evidence bundle file or directory")
    evidence_regression.add_argument("--allow-final-state-changes", action="store_true")
    evidence_regression.add_argument("--allow-event-type-changes", action="store_true")
    evidence_regression.add_argument("--allow-tool-ledger-status-changes", action="store_true")
    evidence_regression.add_argument("--allow-media-artifact-changes", action="store_true")
    evidence_regression.add_argument("--allow-stream-checkpoint-changes", action="store_true")
    evidence_regression.add_argument("--max-total-usd-delta", type=float)
    evidence_regression.set_defaults(func=cmd_evidence_regression)
    shadow = sub.add_parser("shadow")
    shadow.add_argument("run_id")
    shadow.add_argument("example")
    shadow.set_defaults(func=cmd_shadow)

    status = sub.add_parser("status")
    status.add_argument("run_id")
    status.set_defaults(func=cmd_status)
    cancel = sub.add_parser("cancel")
    cancel.add_argument("run_id")
    cancel.add_argument("--reason", default="cancelled by user")
    cancel.set_defaults(func=cmd_cancel)
    recover = sub.add_parser("recover-expired")
    recover.set_defaults(func=cmd_recover_expired)

    conformance = sub.add_parser("conformance")
    conformance.set_defaults(func=cmd_conformance)

    adapter = sub.add_parser("adapter")
    adapter_sub = adapter.add_subparsers(dest="adapter_cmd", required=True)
    adapter_conf = adapter_sub.add_parser("conformance")
    adapter_conf.add_argument(
        "--kind",
        choices=["python-function", "langgraph-node", "langchain", "crewai", "autogen", "openai-agents", "llamaindex", "semantic-kernel"],
        default="python-function",
    )
    adapter_conf.set_defaults(func=cmd_adapter_conformance)
    adapter_cert = adapter_sub.add_parser("certify")
    adapter_cert.add_argument("--kind", choices=supported_adapter_certification_profiles(), required=True)
    adapter_cert.add_argument("--adapter-version", default="0.0.0-local")
    adapter_cert.add_argument("--package-name", help="override the package name recorded in the certification bundle")
    adapter_cert.add_argument("--out", help="write the certification bundle to a JSON file")
    adapter_cert.set_defaults(func=cmd_adapter_certify)

    state = sub.add_parser("state")
    state_sub = state.add_subparsers(dest="state_cmd", required=True)
    state_conf = state_sub.add_parser("conformance")
    state_conf.add_argument("--backend", choices=["sqlite", "postgres", "mysql"], default="sqlite")
    state_conf.add_argument("--dsn", help="Postgres/MySQL DSN; falls back to AGENTLEDGER_POSTGRES_DSN or AGENTLEDGER_MYSQL_DSN")
    state_conf.add_argument("--schema", help="Postgres schema; falls back to AGENTLEDGER_POSTGRES_SCHEMA")
    state_conf.add_argument("--database", help="MySQL database; falls back to AGENTLEDGER_MYSQL_DATABASE")
    state_conf.set_defaults(func=cmd_state_conformance)

    blob = sub.add_parser("blob")
    blob_sub = blob.add_subparsers(dest="blob_cmd", required=True)
    blob_conf = blob_sub.add_parser("conformance")
    blob_conf.add_argument("--backend", choices=["local", "s3"], default="local")
    blob_conf.add_argument("--path", help="local blob path; defaults to <root>/blobs")
    blob_conf.add_argument("--bucket", help="S3 bucket; falls back to AGENTLEDGER_S3_BUCKET")
    blob_conf.add_argument("--prefix", help="S3 prefix; falls back to AGENTLEDGER_S3_PREFIX")
    blob_conf.add_argument("--endpoint-url", help="S3-compatible endpoint; falls back to AGENTLEDGER_S3_ENDPOINT_URL")
    blob_conf.add_argument("--region", help="S3 region; falls back to AGENTLEDGER_S3_REGION")
    blob_conf.add_argument("--profile", help="AWS profile; falls back to AGENTLEDGER_S3_PROFILE")
    blob_conf.set_defaults(func=cmd_blob_conformance)

    worker = sub.add_parser("worker")
    worker_sub = worker.add_subparsers(dest="worker_cmd", required=True)
    worker_conf = worker_sub.add_parser("conformance")
    worker_conf.add_argument("--backend", choices=["sqlite", "postgres", "mysql"], default="sqlite")
    worker_conf.add_argument("--dsn", help="Postgres/MySQL DSN; falls back to AGENTLEDGER_POSTGRES_DSN or AGENTLEDGER_MYSQL_DSN")
    worker_conf.add_argument("--schema", help="Postgres schema; falls back to AGENTLEDGER_POSTGRES_SCHEMA")
    worker_conf.add_argument("--database", help="MySQL database; falls back to AGENTLEDGER_MYSQL_DATABASE")
    worker_conf.add_argument("--workers", type=int, default=4)
    worker_conf.add_argument("--concurrent", action="store_true", help="claim from separate worker connections concurrently")
    worker_conf.set_defaults(func=cmd_worker_conformance)
    worker_plan = worker_sub.add_parser("plan")
    worker_plan.add_argument("example")
    worker_plan.add_argument("--backend", choices=["sqlite", "postgres", "mysql"], default="sqlite")
    worker_plan.add_argument("--replicas", type=int, default=1)
    worker_plan.add_argument("--worker-id-prefix", default="worker")
    worker_plan.add_argument("--lease-seconds", type=int, default=60)
    worker_plan.add_argument("--max-idle-polls", type=int, default=1)
    worker_plan.add_argument("--idle-sleep-seconds", type=float, default=0.25)
    worker_plan.add_argument("--daemon", action="store_true", help="omit max idle stop from generated worker commands")
    worker_plan.set_defaults(func=cmd_worker_plan)
    worker_serve = worker_sub.add_parser("serve")
    worker_serve.add_argument("example")
    worker_serve.add_argument("--run-id")
    worker_serve.add_argument("--worker-id", default="worker-service")
    worker_serve.add_argument("--lease-seconds", type=int, default=60)
    worker_serve.add_argument("--max-loops", type=int, default=10)
    worker_serve.add_argument("--max-idle-polls", type=int, default=1, help="stop after this many idle polls; 0 disables idle stop")
    worker_serve.add_argument("--idle-sleep-seconds", type=float, default=0.25)
    worker_serve.add_argument("--max-attempts", type=int, default=3)
    worker_serve.add_argument("--install-signal-handlers", action="store_true")
    worker_serve.set_defaults(func=cmd_worker_serve)

    worker_run = sub.add_parser("worker-run")
    worker_run.add_argument("example")
    worker_run.add_argument("--worker-id", default="worker-local")
    worker_run.add_argument("--lease-seconds", type=int, default=60)
    worker_run.add_argument("--max-iterations", type=int, default=10)
    worker_run.add_argument("--max-attempts", type=int, default=3)
    worker_run.set_defaults(func=cmd_worker_run)

    diff = sub.add_parser("diff")
    diff.add_argument("left")
    diff.add_argument("right")
    diff.add_argument("--evidence-paths", action="store_true")
    diff.set_defaults(func=cmd_diff)
    divergence = sub.add_parser("divergence")
    divergence.add_argument("left")
    divergence.add_argument("right")
    divergence.add_argument("--evidence-paths", action="store_true")
    divergence.add_argument("--fail-on-divergence", action="store_true")
    divergence.set_defaults(func=cmd_divergence)
    trace = sub.add_parser("trace")
    trace.add_argument("run_id")
    trace.add_argument("--out")
    trace.add_argument("--format", choices=["jsonl", "otlp"], default="jsonl")
    trace.add_argument("--service-name", default="agentledger")
    trace.add_argument("--service-version")
    trace.add_argument("--otlp-endpoint", help="optional OTLP/JSON collector endpoint for --format otlp")
    trace.add_argument("--otlp-timeout", type=float, default=10.0)
    trace.set_defaults(func=cmd_trace)
    timetravel = sub.add_parser("timetravel")
    timetravel.add_argument("run_id")
    timetravel.add_argument("--at-seq", type=int)
    timetravel.add_argument("--include-states", action="store_true")
    timetravel.add_argument("--include-diffs", action="store_true")
    timetravel.add_argument("--html", help="write a static HTML debug report and print its path")
    timetravel.set_defaults(func=cmd_timetravel)

    approvals = sub.add_parser("approvals")
    approvals.add_argument("run_id")
    approvals.set_defaults(func=cmd_approvals)
    approve = sub.add_parser("approve")
    approve.add_argument("approval_id")
    approve.add_argument("--approver", default="operator")
    approve.add_argument("--reason", default="")
    approve.set_defaults(func=cmd_approve)
    deny = sub.add_parser("deny")
    deny.add_argument("approval_id")
    deny.add_argument("--approver", default="operator")
    deny.add_argument("--reason", default="")
    deny.set_defaults(func=cmd_deny)

    retention = sub.add_parser("retention")
    retention_sub = retention.add_subparsers(dest="retention_cmd", required=True)
    retention_plan = retention_sub.add_parser("plan")
    retention_plan.add_argument("run_id")
    retention_plan.set_defaults(func=cmd_retention_plan)
    retention_mark = retention_sub.add_parser("mark-compacted")
    retention_mark.add_argument("run_id")
    retention_mark.add_argument("--reason", default="manual compaction marker")
    retention_mark.set_defaults(func=cmd_retention_mark)

    backup = sub.add_parser("backup")
    backup_sub = backup.add_subparsers(dest="backup_cmd", required=True)
    backup_check = backup_sub.add_parser("check")
    backup_check.add_argument("run_id")
    backup_check.set_defaults(func=cmd_backup_check)

    sandbox_cmd = sub.add_parser("sandbox")
    sandbox_sub = sandbox_cmd.add_subparsers(dest="sandbox_cmd", required=True)
    sandbox_inspect = sandbox_sub.add_parser("inspect")
    sandbox_inspect.add_argument("config", nargs="?")
    sandbox_inspect.set_defaults(func=cmd_sandbox_inspect)

    tools_cmd = sub.add_parser("tools")
    tools_sub = tools_cmd.add_subparsers(dest="tools_cmd", required=True)
    tools_manifest = tools_sub.add_parser("manifest")
    tools_manifest.add_argument("--format", choices=["agentledger", "openai"], default="agentledger")
    tools_manifest.add_argument("--example", choices=["examples/side_effect_idempotency", "examples/docs", "examples/media_stream"])
    tools_manifest.add_argument("--out")
    tools_manifest.set_defaults(func=cmd_tools_manifest)

    lint = sub.add_parser("lint")
    lint_sub = lint.add_subparsers(dest="lint_cmd", required=True)
    lint_boundary = lint_sub.add_parser("boundary")
    lint_boundary.add_argument("paths", nargs="+", help="Python files or directories to scan")
    lint_boundary.add_argument("--exclude", action="append", default=[], help="path substring to skip; can be repeated")
    lint_boundary.add_argument("--rules", help="JSON boundary lint rule pack to append to the default rules")
    lint_boundary.add_argument("--replace-defaults", action="store_true", help="use only --rules instead of appending to defaults")
    lint_boundary.add_argument("--no-fail", action="store_true", help="emit findings but exit successfully")
    lint_boundary.set_defaults(func=cmd_lint_boundary)

    failure = sub.add_parser("failure")
    failure_sub = failure.add_subparsers(dest="failure_cmd", required=True)
    failure_inject = failure_sub.add_parser("inject")
    failure_inject.add_argument("--scenario", choices=["all", "side_effect_crash", "retry_exhaustion", "lease_fencing", "cancellation_fencing"], default="all")
    failure_inject.set_defaults(func=cmd_failure_inject)
    failure_report = failure_sub.add_parser("report")
    failure_report.add_argument("run_id")
    failure_report.set_defaults(func=cmd_failure_report)
    failure_export = failure_sub.add_parser("export")
    failure_export.add_argument("run_id")
    failure_export.add_argument("--out", help="write portable failure export JSON")
    failure_export.set_defaults(func=cmd_failure_export)
    failure_regress = failure_sub.add_parser("regress")
    failure_regress.add_argument("baseline", help="baseline failure export/report JSON")
    failure_regress.add_argument("current", help="current failure export/report JSON")
    failure_regress.add_argument("--out", help="write failure regression JSON")
    failure_regress.add_argument("--fail-on-regression", action="store_true", help="exit non-zero when new failures are present")
    failure_regress.set_defaults(func=cmd_failure_regress)

    corpus = sub.add_parser("corpus")
    corpus_sub = corpus.add_subparsers(dest="corpus_cmd", required=True)
    corpus_add = corpus_sub.add_parser("add")
    corpus_add.add_argument("name")
    corpus_add.add_argument("evidence", help="evidence bundle file or directory")
    corpus_add.add_argument("--corpus-dir")
    corpus_add.add_argument("--metadata", help="JSON object metadata for this golden case")
    corpus_add.set_defaults(func=cmd_corpus_add)
    corpus_seed = corpus_sub.add_parser("seed")
    corpus_seed.add_argument("name", nargs="?", default="minimal-success")
    corpus_seed.add_argument("--corpus-dir")
    corpus_seed.add_argument("--list-builtins", action="store_true")
    corpus_seed.set_defaults(func=cmd_corpus_seed)
    corpus_list = corpus_sub.add_parser("list")
    corpus_list.add_argument("--corpus-dir")
    corpus_list.set_defaults(func=cmd_corpus_list)
    corpus_check = corpus_sub.add_parser("check")
    corpus_check.add_argument("name")
    corpus_check.add_argument("current", help="current evidence bundle file or directory")
    corpus_check.add_argument("--corpus-dir")
    corpus_check.add_argument("--allow-final-state-changes", action="store_true")
    corpus_check.add_argument("--allow-event-type-changes", action="store_true")
    corpus_check.add_argument("--allow-tool-ledger-status-changes", action="store_true")
    corpus_check.add_argument("--allow-media-artifact-changes", action="store_true")
    corpus_check.add_argument("--allow-stream-checkpoint-changes", action="store_true")
    corpus_check.add_argument("--max-total-usd-delta", type=float)
    corpus_check.set_defaults(func=cmd_corpus_eval)
    postgres = sub.add_parser("postgres")
    postgres_sub = postgres.add_subparsers(dest="postgres_cmd", required=True)
    postgres_ddl = postgres_sub.add_parser("ddl")
    postgres_ddl.set_defaults(func=cmd_postgres_ddl)
    postgres_conf = postgres_sub.add_parser("conformance")
    postgres_conf.add_argument("--backend", choices=["postgres"], default="postgres")
    postgres_conf.add_argument("--dsn", help="Postgres DSN; falls back to AGENTLEDGER_POSTGRES_DSN")
    postgres_conf.add_argument("--schema", help="Postgres schema; falls back to AGENTLEDGER_POSTGRES_SCHEMA")
    postgres_conf.set_defaults(func=cmd_state_conformance)
    mysql = sub.add_parser("mysql")
    mysql_sub = mysql.add_subparsers(dest="mysql_cmd", required=True)
    mysql_ddl = mysql_sub.add_parser("ddl")
    mysql_ddl.set_defaults(func=cmd_mysql_ddl)
    mysql_conf = mysql_sub.add_parser("conformance")
    mysql_conf.add_argument("--backend", choices=["mysql"], default="mysql")
    mysql_conf.add_argument("--dsn", help="MySQL DSN; falls back to AGENTLEDGER_MYSQL_DSN")
    mysql_conf.add_argument("--database", help="MySQL database; falls back to AGENTLEDGER_MYSQL_DATABASE")
    mysql_conf.set_defaults(func=cmd_state_conformance)

    contract = sub.add_parser("contract")
    contract_sub = contract.add_subparsers(dest="contract_cmd", required=True)
    contract_export = contract_sub.add_parser("export")
    contract_export.add_argument("--out")
    contract_export.set_defaults(func=cmd_contract_export)

    migrate = sub.add_parser("migrate")
    migrate_sub = migrate.add_subparsers(dest="migrate_cmd", required=True)
    migrate_up = migrate_sub.add_parser("up")
    migrate_up.add_argument("--dialect", choices=["sqlite", "postgres", "mysql"], default="sqlite")
    migrate_up.add_argument("--dsn", help="Postgres/MySQL DSN; falls back to AGENTLEDGER_POSTGRES_DSN or AGENTLEDGER_MYSQL_DSN")
    migrate_up.add_argument("--schema", help="Postgres schema; falls back to AGENTLEDGER_POSTGRES_SCHEMA")
    migrate_up.add_argument("--database", help="MySQL database; falls back to AGENTLEDGER_MYSQL_DATABASE")
    migrate_up.set_defaults(func=cmd_migrate_up)
    migrate_status = migrate_sub.add_parser("status")
    migrate_status.add_argument("--dialect", choices=["sqlite", "postgres", "mysql"], default="sqlite")
    migrate_status.add_argument("--dsn", help="Postgres/MySQL DSN; falls back to AGENTLEDGER_POSTGRES_DSN or AGENTLEDGER_MYSQL_DSN")
    migrate_status.add_argument("--schema", help="Postgres schema; falls back to AGENTLEDGER_POSTGRES_SCHEMA")
    migrate_status.add_argument("--database", help="MySQL database; falls back to AGENTLEDGER_MYSQL_DATABASE")
    migrate_status.set_defaults(func=cmd_migrate_status)
    migrate_ddl = migrate_sub.add_parser("ddl")
    migrate_ddl.add_argument("--dialect", choices=["sqlite", "postgres", "mysql"], default="sqlite")
    migrate_ddl.set_defaults(func=cmd_migrate_ddl)

    policy = sub.add_parser("policy")
    policy_sub = policy.add_subparsers(dest="policy_cmd", required=True)
    policy_check = policy_sub.add_parser("check")
    policy_check.add_argument("policy_file")
    policy_check.add_argument("role")
    policy_check.add_argument("tool")
    policy_check.add_argument("risk_level")
    policy_check.set_defaults(func=cmd_policy_check)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
