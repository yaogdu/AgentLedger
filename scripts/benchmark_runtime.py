#!/usr/bin/env python3
"""Run dependency-free AgentLedger runtime benchmarks.

The benchmark focuses on local runtime overhead and reliability-path behavior.
It does not contact model providers, external tools, databases, object stores,
or registries. Results are useful for regression tracking on the same machine;
they are not a cross-machine performance claim.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agentledger import (  # noqa: E402
    AdversarialReviewRunner,
    AgentContext,
    BackupReadinessChecker,
    DivergenceReporter,
    EvidenceDiffer,
    EvidenceExporter,
    EvidenceRegressionRunner,
    FailureInjectionSuite,
    GoldenCorpus,
    InspectorDataSource,
    LocalWorker,
    MethodFrameworkAdapter,
    OTLPTraceExporter,
    ReplayEngine,
    RetentionPlanner,
    Runtime,
    RuntimeBoundaryLinter,
    RuntimeScheduler,
    SimulatedCrash,
    TimeTravelDebugger,
    ToolSpec,
    TraceExporter,
    build_adapter_certification_bundle,
    ddl_for,
    latest_schema_version,
    migrations_for,
    supported_adapter_certification_profiles,
)
from agentledger.adapters_mcp import InMemoryMCPContextServer, InMemoryMCPToolServer, MCPContextAdapter, MCPToolAdapter  # noqa: E402
from agentledger.cost import CostAttributionReporter  # noqa: E402
from agentledger.failure import FailureAttributionReporter  # noqa: E402
from agentledger.shadow import ShadowRunner  # noqa: E402
from agentledger.storage_postgres import PostgresStore  # noqa: E402
from agentledger.storage_mysql import MySQLStore  # noqa: E402
from agentledger.tools import ToolValidationError  # noqa: E402


SEMANTIC_MANIFEST_PATH = ROOT / "contracts" / "conformance" / "runtime_semantics.v1.json"


DIRECT_COVERAGE: dict[str, list[str]] = {
    "runtime_smoke_evidence_replay": ["run_once_managed_tool", "evidence_export", "replay"],
    "local_persistence_smoke": ["create_run", "run_once_managed_tool", "scheduler_status"],
    "local_blob_store_smoke": ["local_blob_store_roundtrip"],
    "tool_schema_validation_smoke": ["tool_schema_validation"],
    "worker_service_smoke": ["local_worker_until_idle"],
    "tool_ledger_idempotent_retry": ["build_idempotent_side_effect_run", "shadow_run"],
    "policy_approval_sandbox_smoke": ["policy_approval_sandbox"],
    "cost_failure_attribution_smoke": ["cost_failure_reports"],
    "media_stream_artifacts_smoke": ["build_media_stream_run"],
    "evidence_consumers_smoke": ["evidence_consumers"],
    "simple_api_smoke": ["simple_api_run"],
    "otlp_trace_export_smoke": ["otlp_trace_export"],
    "static_debug_html_smoke": ["inspector_single_html", "inspector_run_index_html", "time_travel_html"],
    "ops_readiness_smoke": ["ops_readiness"],
    "storage_schema_smoke": ["storage_schema_helpers"],
    "mcp_adapters_smoke": ["mcp_adapters"],
    "framework_adapters_smoke": ["framework_adapter"],
    "boundary_lint_smoke": ["boundary_lint"],
    "scheduler_smoke": ["scheduler_status"],
    "adversarial_review_smoke": ["adversarial_review"],
    "evidence_regression_smoke": ["evidence_regression"],
    "failure_injection_smoke": ["failure_injection_suite"],
    "shadow_smoke": ["shadow_run"],
    "repro_golden_smoke": ["repro_golden_corpus"],
    "time_travel_timeline_smoke": ["time_travel_html"],
    "optional_adapters_smoke": ["adapter_certification_profiles"],
    "official_adapters_smoke": ["official_adapter_dry_run"],
}


@dataclass(frozen=True)
class Sample:
    name: str
    duration_ms: float
    metrics: dict[str, Any]


def now() -> float:
    return time.perf_counter()


def timed(name: str, func: Callable[[], dict[str, Any]]) -> Sample:
    started = now()
    metrics = func()
    return Sample(name=name, duration_ms=(now() - started) * 1000.0, metrics=metrics)


def summarize(samples: list[Sample]) -> dict[str, Any]:
    groups: dict[str, list[Sample]] = {}
    for sample in samples:
        groups.setdefault(sample.name, []).append(sample)
    result: dict[str, Any] = {}
    for name, rows in groups.items():
        values = [row.duration_ms for row in rows]
        result[name] = {
            "iterations": len(values),
            "min_ms": round(min(values), 3),
            "median_ms": round(statistics.median(values), 3),
            "mean_ms": round(statistics.fmean(values), 3),
            "max_ms": round(max(values), 3),
            "total_ms": round(sum(values), 3),
            "last_metrics": rows[-1].metrics,
        }
        if len(values) >= 2:
            result[name]["stdev_ms"] = round(statistics.stdev(values), 3)
    return result


def load_semantic_manifest() -> dict[str, Any]:
    manifest = json.loads(SEMANTIC_MANIFEST_PATH.read_text(encoding="utf-8"))
    checks = manifest.get("required_semantic_checks", [])
    if not isinstance(checks, list) or not checks:
        raise RuntimeError("semantic manifest has no required_semantic_checks")
    return manifest


def extract_json_object(output: str) -> dict[str, Any] | None:
    start = output.find("{")
    end = output.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        value = json.loads(output[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def remove_if_exists(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def make_runtime(root: Path) -> Runtime:
    remove_if_exists(root)
    rt = Runtime.local(root)
    rt.registry.register(
        ToolSpec(
            name="math.add",
            func=lambda args: {"value": int(args["left"]) + int(args["right"])},
            input_schema={"type": "object", "required": ["left", "right"]},
        )
    )
    side_effect_counter = {"count": 0}

    def send_email(args: dict[str, Any]) -> dict[str, Any]:
        side_effect_counter["count"] += 1
        return {
            "external_id": f"email-{side_effect_counter['count']}",
            "subject": args["subject"],
        }

    rt.registry.register(
        ToolSpec(
            name="email.send",
            func=send_email,
            side_effect="external_write",
            risk_level="medium",
            idempotency_required=True,
            input_schema={"type": "object", "required": ["subject"]},
        )
    )
    setattr(rt, "_benchmark_side_effect_counter", side_effect_counter)
    return rt


def run_async(coro: Any) -> Any:
    return asyncio.run(coro)


def bench_create_runs(rt: Runtime, iterations: int) -> list[Sample]:
    samples: list[Sample] = []
    for index in range(iterations):
        samples.append(
            timed(
                "create_run",
                lambda index=index: {
                    "run_id": rt.create_run(initial_state={"index": index})[0],
                },
            )
        )
    return samples


async def _tool_agent(ctx: AgentContext, state: dict[str, Any]) -> None:
    response = await ctx.call_tool("math.add", {"left": state.get("index", 1), "right": 2})
    ctx.write_state_patch("sum", response["value"])


def bench_managed_steps(rt: Runtime, iterations: int) -> list[Sample]:
    samples: list[Sample] = []
    for index in range(iterations):
        run_id, _ = rt.create_run(initial_state={"index": index})
        samples.append(
            timed(
                "run_once_managed_tool",
                lambda run_id=run_id: {
                    "ok": run_async(rt.run_once(_tool_agent, run_id=run_id, agent_role="BenchmarkAgent")),
                    "event_count": len(rt.store.events(run_id)),
                    "ledger_count": len(rt.store.ledger(run_id)),
                },
            )
        )
    return samples


def build_side_effect_run(rt: Runtime) -> str:
    marker = {"crashed": False}

    async def agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
        email = await ctx.call_tool(
            "email.send",
            {
                "subject": "benchmark retry",
                "_logical_operation": "benchmark-email-once",
            },
        )
        if not marker["crashed"]:
            marker["crashed"] = True
            raise SimulatedCrash("benchmark crash after side effect")
        ctx.write_state_patch("email", email)
        ctx.write_state_patch("recovered", True)

    run_id, _ = rt.create_run(initial_state={"scenario": "idempotent-side-effect"})
    first_ok = run_async(rt.run_once(agent, run_id=run_id, worker_id="before-crash", agent_role="BenchmarkAgent"))
    second_ok = run_async(rt.run_once(agent, run_id=run_id, worker_id="after-restart", agent_role="BenchmarkAgent"))
    if first_ok or not second_ok:
        raise RuntimeError("side-effect benchmark did not produce expected crash/retry flow")
    return run_id


async def _model_agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
    refs = ctx.record_model_call(
        provider="benchmark-provider",
        model="benchmark-model",
        request={"messages": [{"role": "user", "content": "summarize this run"}]},
        response={"content": "ok"},
        usage={"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
        total_usd=0.0003,
    )
    ctx.record_tool_call_proposal(
        tool_name="math.add",
        arguments={"left": 1, "right": 2},
        provider="benchmark-provider",
        model="benchmark-model",
        model_call_ref=refs["response_ref"],
        confidence=0.98,
        reason="synthetic benchmark proposal",
    )
    ctx.record_model_failure(
        provider="benchmark-provider",
        model="benchmark-model",
        error_type="RateLimitError",
        message="synthetic rate limit",
        retryable=True,
        request={"messages": [{"role": "user", "content": "retry"}]},
        usage={"total_tokens": 3},
        total_usd=0.0001,
    )
    ctx.write_state_patch("model_evidence", True)


def build_model_run(rt: Runtime) -> str:
    run_id, _ = rt.create_run(initial_state={"scenario": "model-evidence"})
    ok = run_async(rt.run_once(_model_agent, run_id=run_id, agent_role="BenchmarkAgent"))
    if not ok:
        raise RuntimeError("model evidence benchmark did not complete")
    return run_id


async def _media_agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
    _digest, ref = ctx.blobs.put_json({"frame": 1, "source": "benchmark"})
    await ctx.create_media_artifact(
        "benchmark-frame",
        "frame",
        content_ref=ref,
        media_metadata={"kind": "frame", "frame_index": 1, "timestamp_start_seconds": 1.0},
    )
    await ctx.create_stream_checkpoint(
        "benchmark-stream-checkpoint",
        stream_id="camera-1",
        consumer_id="vision-agent",
        offset=1,
        chunk={"stream_id": "camera-1", "chunk_id": "chunk-1", "offset": 1, "content_ref": ref},
    )
    ctx.write_state_patch("media_recorded", True)


def build_media_stream_run(rt: Runtime) -> str:
    run_id, _ = rt.create_run(initial_state={"scenario": "media-stream"})
    ok = run_async(rt.run_once(_media_agent, run_id=run_id, agent_role="BenchmarkAgent"))
    if not ok:
        raise RuntimeError("media stream benchmark did not complete")
    return run_id


async def _invalid_tool_agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
    await ctx.call_tool("math.add", {"left": 1})


async def _worker_agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
    ctx.write_state_patch("worker_completed", True)


async def _shadow_agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
    email = await ctx.call_tool(
        "email.send",
        {
            "subject": "benchmark retry",
            "_logical_operation": "benchmark-email-once",
        },
    )
    ctx.write_state_patch("email", email)
    ctx.write_state_patch("recovered", True)


async def _simple_benchmark_agent(ctx: AgentContext, _state: dict[str, Any]) -> dict[str, Any]:
    return {"hello": "benchmark"}


def bench_read_models(rt: Runtime, output_dir: Path, run_id: str, iterations: int) -> list[Sample]:
    samples: list[Sample] = []
    evidence_dir = output_dir / "evidence"
    html_path = output_dir / "inspector.html"
    runs_html_path = output_dir / "runs.html"
    for _ in range(iterations):
        samples.append(
            timed(
                "evidence_export",
                lambda: {
                    "path": str(EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).write_dir(evidence_dir)),
                    "event_count": len(rt.store.events(run_id)),
                },
            )
        )
        samples.append(
            timed(
                "replay",
                lambda: ReplayEngine(store=rt.store, blobs=rt.blobs).replay(run_id).__dict__,
            )
        )
        samples.append(
            timed(
                "failure_report",
                lambda: FailureAttributionReporter(rt.store).report(run_id).to_dict()["summary"],
            )
        )
        samples.append(
            timed(
                "inspector_single_html",
                lambda: {
                    "path": str(
                        InspectorDataSource()
                        .from_runtime_store(store=rt.store, blobs=rt.blobs, run_id=run_id, include_payloads=True)
                        .write_html(html_path)
                    )
                },
            )
        )
        samples.append(
            timed(
                "inspector_run_index_html",
                lambda: {
                    "path": str(
                        InspectorDataSource()
                        .runs_from_runtime_store(store=rt.store, blobs=rt.blobs, limit=50, run_link_template="inspector.html")
                        .write_html(runs_html_path)
                    )
                },
            )
        )
    return samples


def bench_auxiliary_capabilities(rt: Runtime, output_dir: Path, run_ids: dict[str, str]) -> list[Sample]:
    samples: list[Sample] = []
    coverage_dir = output_dir / "coverage"
    coverage_dir.mkdir(parents=True, exist_ok=True)
    evidence_exporter = EvidenceExporter(store=rt.store, blobs=rt.blobs)
    primary_run_id = run_ids["idempotent_side_effect"]
    media_run_id = run_ids["media_stream"]

    samples.append(
        timed(
            "local_blob_store_roundtrip",
            lambda: _blob_roundtrip(rt),
        )
    )
    samples.append(
        timed(
            "tool_schema_validation",
            lambda: _tool_schema_validation(rt),
        )
    )
    samples.append(
        timed(
            "local_worker_until_idle",
            lambda: _local_worker_until_idle(rt),
        )
    )
    samples.append(
        timed(
            "policy_approval_sandbox",
            lambda: _policy_approval_sandbox(rt),
        )
    )
    samples.append(
        timed(
            "cost_failure_reports",
            lambda: {
                "cost_total": CostAttributionReporter(rt.store).report(primary_run_id).to_dict()["total"],
                "failure_summary": FailureAttributionReporter(rt.store).report(primary_run_id).to_dict()["summary"],
            },
        )
    )
    samples.append(
        timed(
            "evidence_consumers",
            lambda: _evidence_consumers(evidence_exporter.export(primary_run_id).to_dict(), evidence_exporter.export(media_run_id).to_dict()),
        )
    )
    samples.append(
        timed(
            "simple_api_run",
            lambda: _simple_api_run(output_dir),
        )
    )
    samples.append(
        timed(
            "otlp_trace_export",
            lambda: _otlp_trace_export(evidence_exporter.export(media_run_id).to_dict(), coverage_dir / "trace.otlp.json"),
        )
    )
    samples.append(
        timed(
            "time_travel_html",
            lambda: {
                "path": str(
                    TimeTravelDebugger(store=rt.store, blobs=rt.blobs)
                    .inspect(primary_run_id, include_states=True, include_diffs=True)
                    .write_html(coverage_dir / "time-travel.html")
                )
            },
        )
    )
    samples.append(
        timed(
            "ops_readiness",
            lambda: {
                "retention": RetentionPlanner(rt.store, rt.blobs).plan(primary_run_id).to_dict(),
                "backup": BackupReadinessChecker(store=rt.store, blobs=rt.blobs).check_run(primary_run_id).to_dict(),
            },
        )
    )
    samples.append(timed("storage_schema_helpers", _storage_schema_helpers))
    samples.append(timed("mcp_adapters", _mcp_adapters))
    samples.append(timed("framework_adapter", lambda: _framework_adapter(output_dir)))
    samples.append(timed("boundary_lint", lambda: _boundary_lint(coverage_dir)))
    samples.append(timed("scheduler_status", lambda: RuntimeScheduler(rt.store).status(primary_run_id)))
    samples.append(timed("adversarial_review", lambda: AdversarialReviewRunner().evaluate(evidence_exporter.export(media_run_id).to_dict()).to_dict()))
    samples.append(
        timed(
            "evidence_regression",
            lambda: EvidenceRegressionRunner()
            .evaluate_regression(evidence_exporter.export(media_run_id).to_dict(), evidence_exporter.export(media_run_id).to_dict())
            .to_dict(),
        )
    )
    samples.append(timed("failure_injection_suite", lambda: FailureInjectionSuite(output_dir / "failure-injection").run().to_dict()))
    samples.append(timed("shadow_run", lambda: run_async(ShadowRunner(rt).run(_shadow_agent, source_run_id=primary_run_id)).to_dict()))
    samples.append(timed("repro_golden_corpus", lambda: _repro_golden_corpus(coverage_dir)))
    samples.append(timed("adapter_certification_profiles", _adapter_certification_profiles))
    samples.append(timed("official_adapter_dry_run", _official_adapter_dry_run))
    return samples


def _blob_roundtrip(rt: Runtime) -> dict[str, Any]:
    digest, ref = rt.blobs.put_json({"hello": "benchmark", "nested": {"ok": True}})
    value = rt.blobs.get_json(ref)
    bad_ref_rejected = False
    try:
        rt.blobs.get_json("unsupported://bad")
    except ValueError:
        bad_ref_rejected = True
    return {"digest": digest, "ref": ref, "roundtrip": value["nested"]["ok"], "bad_ref_rejected": bad_ref_rejected}


def _tool_schema_validation(rt: Runtime) -> dict[str, Any]:
    run_id, _ = rt.create_run(initial_state={"scenario": "invalid-tool-input"})
    rejected = False
    try:
        run_async(rt.run_once(_invalid_tool_agent, run_id=run_id, agent_role="BenchmarkAgent"))
    except ToolValidationError:
        rejected = True
    return {"run_id": run_id, "invalid_input_rejected": rejected, "status": rt.store.run(run_id)["status"]}


def _local_worker_until_idle(rt: Runtime) -> dict[str, Any]:
    run_id, _ = rt.create_run(initial_state={"scenario": "worker"})
    summary = run_async(LocalWorker(rt, _worker_agent, worker_id="benchmark-worker", agent_role="BenchmarkWorker").run_until_idle(run_id=run_id))
    return summary.to_dict()


async def _approval_agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
    await ctx.call_tool("security.approval", {"action": "approve-me"})


async def _sandbox_agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
    await ctx.call_tool("sandbox.required", {"action": "sandbox-me"})


def _policy_approval_sandbox(rt: Runtime) -> dict[str, Any]:
    try:
        rt.registry.get("security.approval")
    except KeyError:
        rt.registry.register(
            ToolSpec(
                name="security.approval",
                func=lambda args: {"ok": True, "action": args["action"]},
                risk_level="high",
                approval_required=True,
                input_schema={"type": "object", "required": ["action"]},
            )
        )
    try:
        rt.registry.get("sandbox.required")
    except KeyError:
        rt.registry.register(
            ToolSpec(
                name="sandbox.required",
                func=lambda args: {"ok": True, "action": args["action"]},
                risk_level="medium",
                sandbox_required=True,
                sandbox_executor="disabled",
                input_schema={"type": "object", "required": ["action"]},
            )
        )
    approval_run_id, _ = rt.create_run(initial_state={"scenario": "approval"})
    first_ok = run_async(rt.run_once(_approval_agent, run_id=approval_run_id, agent_role="BenchmarkAgent"))
    approvals = rt.store.approval_requests(approval_run_id)
    approved = False
    second_ok = False
    if approvals:
        rt.store.approve_request(approvals[0]["approval_id"], approver="benchmark", reason="benchmark approval")
        approved = True
        second_ok = run_async(rt.run_once(_approval_agent, run_id=approval_run_id, agent_role="BenchmarkAgent"))

    sandbox_rt = Runtime.local(Path(tempfile.mkdtemp(prefix="agentledger-benchmark-sandbox-")) / ".agentledger")
    sandbox_rt.registry.register(
        ToolSpec(
            name="sandbox.required",
            func=lambda args: {"ok": True, "action": args["action"]},
            risk_level="medium",
            sandbox_required=True,
            sandbox_executor="disabled",
            input_schema={"type": "object", "required": ["action"]},
        )
    )
    sandbox_run_id, _ = sandbox_rt.create_run(initial_state={"scenario": "sandbox"})
    sandbox_failed_closed = False
    try:
        run_async(sandbox_rt.run_once(_sandbox_agent, run_id=sandbox_run_id, agent_role="BenchmarkAgent"))
    except RuntimeError:
        sandbox_failed_closed = True
    finally:
        sandbox_rt.close()

    return {
        "approval_run_id": approval_run_id,
        "approval_first_ok": first_ok,
        "approval_created": bool(approvals),
        "approval_approved": approved,
        "approval_second_ok": second_ok,
        "sandbox_run_id": sandbox_run_id,
        "sandbox_failed_closed": sandbox_failed_closed,
    }


def _evidence_consumers(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    diff = EvidenceDiffer().compare(left, right).to_dict()
    divergence = DivergenceReporter().compare(left, right).to_dict()
    return {
        "trace_span_count": len(TraceExporter().spans(right)),
        "diff_same": diff["same"],
        "diff_change_keys": sorted(diff["changes"].keys()),
        "divergence": divergence["changed_dimensions"],
    }


def _simple_api_run(output_dir: Path) -> dict[str, Any]:
    import agentledger as al

    result = al.run(
        _simple_benchmark_agent,
        root=output_dir / "simple-api" / ".agentledger",
        initial_state={"scenario": "simple"},
        evidence_dir=output_dir / "simple-api" / "evidence",
    )
    return {"run_id": result.run_id, "ok": result.ok, "output": result.output, "evidence_path": str(result.evidence_path)}


def _otlp_trace_export(evidence: dict[str, Any], path: Path) -> dict[str, Any]:
    target = OTLPTraceExporter().write_json(evidence, path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    span_count = len(payload["resourceSpans"][0]["scopeSpans"][0]["spans"])
    return {"path": str(target), "span_count": span_count}


def _storage_schema_helpers() -> dict[str, Any]:
    return {
        dialect: {
            "latest_version": latest_schema_version(dialect),
            "migration_count": len(migrations_for(dialect)),
            "ddl_bytes": len(ddl_for(dialect)),
        }
        for dialect in ("sqlite", "postgres", "mysql")
    }


def _mcp_adapters() -> dict[str, Any]:
    tool_server = InMemoryMCPToolServer()
    tool_server.add_tool(
        {"name": "mcp.add", "description": "add two numbers", "inputSchema": {"type": "object", "required": ["left", "right"]}},
        lambda _name, args: {"value": args["left"] + args["right"]},
    )
    spec = MCPToolAdapter(tool_server.call_tool).tool_spec_from_descriptor(tool_server.list_tools()[0])
    context_server = InMemoryMCPContextServer()
    context_server.add_resource(uri="agentledger://benchmark", name="benchmark", reader=lambda: {"ok": True})
    read_spec = MCPContextAdapter(context_server.read_resource).read_tool_spec()
    return {
        "tool_name": spec.name,
        "tool_result": tool_server.call_tool("mcp.add", {"left": 1, "right": 2}),
        "resource_count": len(context_server.list_resources()),
        "context_tool_name": read_spec.name,
    }


def _framework_adapter(output_dir: Path) -> dict[str, Any]:
    class DemoFramework:
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {"received": payload.get("topic"), "ok": True}

    rt = Runtime.local(output_dir / "framework-adapter" / ".agentledger")
    adapter = MethodFrameworkAdapter(DemoFramework(), method_candidates=("invoke",), output_key="framework_output")
    run_id, _ = rt.create_run(initial_state={"topic": "benchmark"})
    try:
        ok = run_async(rt.run_once(adapter.as_agent(), run_id=run_id, agent_role=adapter.role))
        return {"run_id": run_id, "ok": ok, "spec": adapter.map_run_spec(), "state": rt.store.final_state(run_id)}
    finally:
        rt.close()


def _boundary_lint(output_dir: Path) -> dict[str, Any]:
    sample = output_dir / "boundary_bypass.py"
    sample.write_text("import os\nos.system('echo bypass')\n", encoding="utf-8")
    report = RuntimeBoundaryLinter().scan([sample])
    payload = report.to_dict()
    payload["expected_finding"] = True
    payload["detected_expected_bypass"] = payload["finding_count"] >= 1
    return payload


def _repro_golden_corpus(output_dir: Path) -> dict[str, Any]:
    corpus = GoldenCorpus(output_dir / "golden")
    case = corpus.seed_builtin("minimal-success")
    report = corpus.evaluate("minimal-success", case.path).to_dict()
    return {"case": case.to_dict(), "case_count": len(corpus.list()), "evaluation": report}


def _adapter_certification_profiles() -> dict[str, Any]:
    profiles = supported_adapter_certification_profiles()
    bundles = {
        profile: build_adapter_certification_bundle(profile, adapter_version=_version()).to_dict()["production_validation"]
        for profile in profiles
    }
    return {"profiles": profiles, "production_validation": bundles}


def _official_adapter_dry_run() -> dict[str, Any]:
    return {
        "postgres_ddl_bytes": len(PostgresStore.ddl()),
        "mysql_ddl_bytes": len(MySQLStore.ddl()),
        "docker_profile_present": "docker" in supported_adapter_certification_profiles(),
    }


def run_command(name: str, cmd: list[str], cwd: Path, timeout: int, *, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = now()
    try:
        completed = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout, check=False)
        status = "passed" if completed.returncode == 0 else "failed"
        output = (completed.stdout or "") + (completed.stderr or "")
        json_report = extract_json_object(output)
        reported_checks = json_report.get("checks") if isinstance(json_report, dict) and isinstance(json_report.get("checks"), list) else []
        return {
            "name": name,
            "status": status,
            "exit_code": completed.returncode,
            "duration_ms": round((now() - started) * 1000.0, 3),
            "command": cmd,
            "cwd": str(cwd.relative_to(ROOT) if cwd != ROOT else "."),
            "reported_check_count": len(reported_checks),
            "reported_checks": reported_checks,
            "output_tail": output[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "status": "timeout",
            "exit_code": None,
            "duration_ms": round((now() - started) * 1000.0, 3),
            "command": cmd,
            "cwd": str(cwd.relative_to(ROOT) if cwd != ROOT else "."),
            "output_tail": str(exc),
        }


def run_language_commands(timeout: int, output_dir: Path) -> list[dict[str, Any]]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src")
    env.setdefault("GOCACHE", str(output_dir / "go-cache"))
    env.setdefault("GOMODCACHE", str(output_dir / "go-mod-cache"))
    env.setdefault("npm_config_cache", str(output_dir / "npm-cache"))
    env.setdefault("CARGO_TARGET_DIR", str(output_dir / "cargo-target"))
    command_root = output_dir / "language-commands"
    command_root.mkdir(parents=True, exist_ok=True)
    commands: list[tuple[str, list[str], Path]] = [
        ("python_conformance", [sys.executable, "-m", "agentledger", "--root", str(command_root / "python"), "conformance"], ROOT),
        ("go_conformance", ["go", "run", "./cmd/agentledger-go", "conformance"], ROOT / "go"),
        ("typescript_conformance", ["npm", "run", "conformance"], ROOT / "typescript"),
        ("rust_conformance", ["cargo", "run", "--quiet", "--", "conformance"], ROOT / "rust"),
    ]
    results: list[dict[str, Any]] = []
    for name, cmd, cwd in commands:
        if not cwd.exists():
            continue
        if shutil.which(cmd[0]) is None:
            results.append({"name": name, "status": "skipped", "reason": f"missing executable: {cmd[0]}", "command": cmd})
            continue
        results.append(run_command(name, cmd, cwd, timeout, env=env))
    return results


def build_coverage_matrix(
    manifest: dict[str, Any],
    *,
    samples: list[Sample],
    language_commands: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    measured_names = {sample.name for sample in samples}
    language_by_check: dict[str, list[str]] = {}
    for command in language_commands:
        if command.get("status") != "passed":
            continue
        for check_id in command.get("reported_checks", []):
            if isinstance(check_id, str):
                language_by_check.setdefault(check_id, []).append(str(command["name"]))

    matrix: list[dict[str, Any]] = []
    for entry in manifest["required_semantic_checks"]:
        check_id = str(entry["id"])
        measured = [name for name in DIRECT_COVERAGE.get(check_id, []) if name in measured_names]
        language = language_by_check.get(check_id, [])
        if measured and language:
            status = "measured_and_language_conformance"
        elif measured:
            status = "measured_locally"
        elif language:
            status = "language_conformance"
        else:
            status = "manifest_only_not_run"
        matrix.append(
            {
                "id": check_id,
                "status": status,
                "measured_scenarios": measured,
                "language_commands": language,
                "fixture": entry.get("fixture"),
                "scenario_refs": entry.get("scenario_refs", []),
                "description": entry.get("description", ""),
            }
        )
    return matrix


def coverage_summary(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for row in matrix:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    covered = [row for row in matrix if row["status"] != "manifest_only_not_run"]
    return {
        "required_check_count": len(matrix),
        "covered_check_count": len(covered),
        "not_run_count": len(matrix) - len(covered),
        "by_status": by_status,
    }


def validate_report(report: dict[str, Any], *, require_full_coverage: bool) -> list[str]:
    failures: list[str] = []
    if require_full_coverage and report["coverage_summary"]["not_run_count"]:
        failures.append(f"semantic coverage has {report['coverage_summary']['not_run_count']} unrun required checks")

    summary = report["summary"]
    required_truthy = {
        "tool_schema_validation": ("invalid_input_rejected",),
        "policy_approval_sandbox": ("approval_created", "approval_approved", "approval_second_ok", "sandbox_failed_closed"),
        "failure_injection_suite": ("passed",),
        "adversarial_review": ("passed",),
        "evidence_regression": ("passed",),
        "boundary_lint": ("detected_expected_bypass",),
        "shadow_run": ("ok",),
        "simple_api_run": ("ok",),
    }
    for scenario, keys in required_truthy.items():
        metrics = summary.get(scenario, {}).get("last_metrics")
        if not isinstance(metrics, dict):
            failures.append(f"{scenario} did not produce metrics")
            continue
        for key in keys:
            if not metrics.get(key):
                failures.append(f"{scenario}.{key} was not truthy")

    for item in report.get("language_commands", []):
        if item.get("status") not in {"passed", "skipped"}:
            failures.append(f"{item.get('name')} status={item.get('status')}")
    return failures


def build_report(
    *,
    iterations: int,
    artifact_dir: Path,
    samples: list[Sample],
    scenario_run_ids: dict[str, str],
    language_commands: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = load_semantic_manifest()
    coverage = build_coverage_matrix(manifest, samples=samples, language_commands=language_commands)
    return {
        "schema_version": "agentledger.benchmark.v1",
        "project": "AgentLedger",
        "version": _version(),
        "generated_at_unix": int(time.time()),
        "iterations": iterations,
        "environment": {
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "methodology": {
            "scope": "dependency-free local runtime benchmark",
            "storage": "SQLite StateStore + LocalBlobStore",
            "network": "disabled for runtime scenarios; optional language commands are local CLI commands",
            "note": "Use this for same-machine regression tracking, not as a universal performance claim.",
            "artifact_dir": str(artifact_dir),
        },
        "semantic_manifest": {
            "path": str(SEMANTIC_MANIFEST_PATH.relative_to(ROOT)),
            "schema_version": manifest.get("schema_version"),
            "contract_version": manifest.get("contract_version"),
        },
        "coverage_summary": coverage_summary(coverage),
        "coverage_matrix": coverage,
        "scenario_run_ids": scenario_run_ids,
        "summary": summarize(samples),
        "samples": [
            {"name": sample.name, "duration_ms": round(sample.duration_ms, 3), "metrics": sample.metrics}
            for sample in samples
        ],
        "language_commands": language_commands,
    }


def _version() -> str:
    namespace: dict[str, Any] = {}
    version_file = ROOT / "src" / "agentledger" / "__init__.py"
    for line in version_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            exec(line, namespace)
            return str(namespace["__version__"])
    return "unknown"


def write_markdown(report: dict[str, Any], path: Path) -> Path:
    lines = [
        "# AgentLedger Benchmark Report",
        "",
        f"- Version: `{report['version']}`",
        f"- Passed: `{report.get('passed', True)}`",
        f"- Iterations: `{report['iterations']}`",
        f"- Platform: `{report['environment']['platform']}`",
        f"- Python: `{report['environment']['python']}`",
        "",
        "## Methodology",
        "",
        report["methodology"]["note"],
        "",
        "Runtime scenarios use local SQLite and LocalBlobStore only. They do not call model providers, external tools, registries, or real databases.",
        "",
        "## Validation",
        "",
    ]
    failures = report.get("validation_failures", [])
    if failures:
        lines.extend([f"- {failure}" for failure in failures])
    else:
        lines.append("- No validation failures.")
    lines.extend(
        [
            "",
        "## Runtime Summary",
        "",
        "| Scenario | Iterations | Median ms | Mean ms | Min ms | Max ms |",
        "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, item in sorted(report["summary"].items()):
        lines.append(
            f"| `{name}` | {item['iterations']} | {item['median_ms']} | {item['mean_ms']} | {item['min_ms']} | {item['max_ms']} |"
        )
    lines.extend(["", "## Language Command Baseline", "", "| Command | Status | Duration ms |", "|---|---|---:|"])
    for item in report.get("language_commands", []):
        lines.append(f"| `{item['name']}` | {item['status']} | {item.get('duration_ms', '-')} |")
    lines.extend(
        [
            "",
            "## Semantic Coverage",
            "",
            f"- Required semantic checks: `{report['coverage_summary']['required_check_count']}`",
            f"- Covered in this run: `{report['coverage_summary']['covered_check_count']}`",
            f"- Not run in this benchmark invocation: `{report['coverage_summary']['not_run_count']}`",
            "",
            "| Check | Status | Measured scenarios | Language commands |",
            "|---|---|---|---|",
        ]
    )
    for row in report["coverage_matrix"]:
        measured = ", ".join(f"`{name}`" for name in row["measured_scenarios"]) or "-"
        language = ", ".join(f"`{name}`" for name in row["language_commands"]) or "-"
        lines.append(f"| `{row['id']}` | {row['status']} | {measured} | {language} |")
    lines.extend(["", "## Scenario Runs", ""])
    for key, run_id in report["scenario_run_ids"].items():
        lines.append(f"- `{key}`: `{run_id}`")
    lines.extend(["", "---", "", "generated by codex cli", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run dependency-free AgentLedger runtime benchmarks.")
    parser.add_argument("--iterations", type=int, default=20, help="Iterations for repeated local runtime scenarios.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for benchmark artifacts.")
    parser.add_argument("--skip-language-commands", action="store_true", help="Skip Go/TypeScript/Rust/Python conformance command timing.")
    parser.add_argument("--command-timeout", type=int, default=60, help="Timeout in seconds for each optional language command.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.iterations < 1:
        raise SystemExit("--iterations must be >= 1")
    output_dir = args.output_dir or Path(tempfile.mkdtemp(prefix="agentledger-benchmark-"))
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = output_dir / f"run-{int(time.time() * 1000)}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    runtime_root = artifact_dir / ".agentledger"
    samples: list[Sample] = []
    scenario_run_ids: dict[str, str] = {}

    with make_runtime(runtime_root) as rt:
        samples.extend(bench_create_runs(rt, args.iterations))
        samples.extend(bench_managed_steps(rt, args.iterations))
        samples.append(timed("build_idempotent_side_effect_run", lambda: {"run_id": build_side_effect_run(rt)}))
        scenario_run_ids["idempotent_side_effect"] = samples[-1].metrics["run_id"]
        samples.append(timed("build_model_evidence_run", lambda: {"run_id": build_model_run(rt)}))
        scenario_run_ids["model_evidence"] = samples[-1].metrics["run_id"]
        samples.append(timed("build_media_stream_run", lambda: {"run_id": build_media_stream_run(rt)}))
        scenario_run_ids["media_stream"] = samples[-1].metrics["run_id"]
        samples.extend(bench_read_models(rt, artifact_dir, scenario_run_ids["idempotent_side_effect"], max(1, min(args.iterations, 10))))
        samples.extend(bench_auxiliary_capabilities(rt, artifact_dir, scenario_run_ids))

    language_commands = [] if args.skip_language_commands else run_language_commands(args.command_timeout, artifact_dir)
    report = build_report(
        iterations=args.iterations,
        artifact_dir=artifact_dir,
        samples=samples,
        scenario_run_ids=scenario_run_ids,
        language_commands=language_commands,
    )
    json_path = output_dir / "benchmark.json"
    md_path = output_dir / "benchmark.md"
    failures = validate_report(report, require_full_coverage=not args.skip_language_commands)
    report["passed"] = not failures
    report["validation_failures"] = failures
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, md_path)
    print(
        json.dumps(
            {
                "ok": not failures,
                "output_dir": str(output_dir),
                "artifact_dir": str(artifact_dir),
                "json": str(json_path),
                "markdown": str(md_path),
                "coverage_summary": report["coverage_summary"],
                "validation_failures": failures,
                "scenario_count": len(report["summary"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
