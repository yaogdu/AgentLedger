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
from agentledger.cost import BudgetController, BudgetExceeded, BudgetLimits, CostAttributionReporter  # noqa: E402
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
    "cost_failure_attribution_smoke": ["build_model_evidence_run", "cost_failure_reports", "budget_exhaustion"],
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


SCENARIO_DEPTH: dict[str, dict[str, str]] = {
    "create_run": {"level": "executable_local", "note": "creates durable local runtime state"},
    "run_once_managed_tool": {"level": "executable_local", "note": "runs through AgentContext and ToolGateway"},
    "build_idempotent_side_effect_run": {"level": "executable_local_fault", "note": "simulates crash after side effect and retries through Tool Ledger"},
    "build_model_evidence_run": {"level": "executable_local", "note": "records model request/response, proposed tool call, model failure, usage, and cost"},
    "build_media_stream_run": {"level": "executable_local", "note": "records media artifact and stream checkpoint evidence"},
    "evidence_export": {"level": "read_model_local", "note": "exports evidence from local persisted run"},
    "replay": {"level": "read_model_local", "note": "replays persisted evidence without executing side effects"},
    "failure_report": {"level": "read_model_local", "note": "builds failure attribution read model"},
    "inspector_single_html": {"level": "static_artifact_local", "note": "renders single-run static Inspector HTML"},
    "inspector_run_index_html": {"level": "static_artifact_local", "note": "renders read-only run index HTML"},
    "local_blob_store_roundtrip": {"level": "executable_local", "note": "round-trips content-addressed blob refs"},
    "tool_schema_validation": {"level": "negative_runtime_path", "note": "proves invalid tool input fails before tool execution"},
    "local_worker_until_idle": {"level": "executable_local", "note": "runs LocalWorker until terminal/idle"},
    "policy_approval_sandbox": {"level": "negative_runtime_path", "note": "checks approval pause/resume and sandbox fail-closed"},
    "cost_failure_reports": {"level": "read_model_local", "note": "checks cost and failure attribution from persisted records"},
    "budget_exhaustion": {"level": "negative_runtime_path", "note": "proves budget denial blocks tool execution before side effects"},
    "evidence_consumers": {"level": "read_model_local", "note": "checks trace, diff, and divergence consumers"},
    "simple_api_run": {"level": "executable_local", "note": "runs the one-function simple API"},
    "otlp_trace_export": {"level": "static_artifact_local", "note": "writes dependency-free OTLP JSON"},
    "time_travel_html": {"level": "static_artifact_local", "note": "renders time-travel static HTML"},
    "ops_readiness": {"level": "read_model_local", "note": "builds retention and backup-readiness read models"},
    "storage_schema_helpers": {"level": "static_helper", "note": "checks DDL/migration helper availability, not a live database"},
    "mcp_adapters": {"level": "contract_dry_run", "note": "uses in-memory MCP-style adapters, not a real MCP server"},
    "framework_adapter": {"level": "contract_dry_run", "note": "uses dependency-free method adapter, not framework SDK integration"},
    "boundary_lint": {"level": "synthetic_probe", "note": "scans a deliberately unsafe source file"},
    "scheduler_status": {"level": "read_model_local", "note": "checks scheduler facade over local store"},
    "adversarial_review": {"level": "read_model_local", "note": "runs side-effect-free evidence review"},
    "evidence_regression": {"level": "read_model_local", "note": "runs side-effect-free evidence regression"},
    "failure_injection_suite": {"level": "synthetic_probe", "note": "runs dependency-free failure probes"},
    "shadow_run": {"level": "executable_local_fault", "note": "runs shadow replay without external mutation"},
    "repro_golden_corpus": {"level": "static_artifact_local", "note": "checks built-in golden corpus primitives"},
    "adapter_certification_profiles": {"level": "contract_dry_run", "note": "checks certification profile metadata, not live services"},
    "official_adapter_dry_run": {"level": "contract_dry_run", "note": "checks official adapter static surfaces, not Postgres/MySQL/Docker services"},
}


DEPTH_ORDER = {
    "contract_dry_run": 0,
    "static_helper": 1,
    "static_artifact_local": 2,
    "read_model_local": 3,
    "synthetic_probe": 4,
    "negative_runtime_path": 5,
    "executable_local": 6,
    "executable_local_fault": 7,
    "language_conformance": 8,
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


def build_side_effect_run_metrics(rt: Runtime) -> dict[str, Any]:
    run_id = build_side_effect_run(rt)
    side_effect_counter = getattr(rt, "_benchmark_side_effect_counter", {"count": None})
    ledger = rt.store.ledger(run_id)
    final_state = rt.store.final_state(run_id)
    return {
        "run_id": run_id,
        "run_status": rt.store.run(run_id)["status"],
        "external_side_effect_count": side_effect_counter["count"],
        "ledger_count": len(ledger),
        "completed": final_state.get("recovered") is True,
    }


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


def build_model_run_metrics(rt: Runtime) -> dict[str, Any]:
    run_id = build_model_run(rt)
    events = [dict(row) for row in rt.store.events(run_id)]
    cost = CostAttributionReporter(rt.store).report(run_id).to_dict()
    failure = FailureAttributionReporter(rt.store).report(run_id).to_dict()
    return {
        "run_id": run_id,
        "run_status": rt.store.run(run_id)["status"],
        "model_call_requested_count": sum(1 for event in events if event["type"] == "model_call_requested"),
        "model_call_completed_count": sum(1 for event in events if event["type"] == "model_call_completed"),
        "model_call_failed_count": sum(1 for event in events if event["type"] == "model_call_failed"),
        "tool_call_proposed_count": sum(1 for event in events if event["type"] == "tool_call_proposed"),
        "model_tokens": cost["total"]["model_tokens"],
        "model_total_usd": cost["total"]["total_usd"],
        "model_failure_category_present": any(item.get("category") == "model" for item in failure["failure_envelopes"]),
        "model_evidence_refs": len(failure["failure_export"]["model_evidence_refs"]),
        "tool_proposal_refs": len(failure["failure_export"]["tool_proposal_refs"]),
    }


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
            lambda: _cost_failure_reports(rt, primary_run_id, run_ids["model_evidence"]),
        )
    )
    samples.append(timed("budget_exhaustion", lambda: _budget_exhaustion(output_dir)))
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
    status = rt.store.run(run_id)["status"]
    return {"run_id": run_id, "invalid_input_rejected": rejected, "status": status, "run_failed": status == "failed"}


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


def _cost_failure_reports(rt: Runtime, primary_run_id: str, model_run_id: str) -> dict[str, Any]:
    primary_cost = CostAttributionReporter(rt.store).report(primary_run_id).to_dict()
    primary_failure = FailureAttributionReporter(rt.store).report(primary_run_id).to_dict()
    model_cost = CostAttributionReporter(rt.store).report(model_run_id).to_dict()
    model_failure = FailureAttributionReporter(rt.store).report(model_run_id).to_dict()
    return {
        "side_effect_tool_calls": primary_cost["total"]["tool_calls"],
        "side_effect_failure_count": primary_failure["summary"]["failure_envelope_count"],
        "model_tokens": model_cost["total"]["model_tokens"],
        "model_total_usd": model_cost["total"]["total_usd"],
        "model_tokens_present": model_cost["total"]["model_tokens"] > 0,
        "model_cost_present": model_cost["total"]["total_usd"] > 0,
        "model_failure_category_present": any(item.get("category") == "model" for item in model_failure["failure_envelopes"]),
        "model_failure_export_refs": len(model_failure["failure_export"]["model_evidence_refs"]),
        "tool_proposal_export_refs": len(model_failure["failure_export"]["tool_proposal_refs"]),
    }


async def _budget_blocked_agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
    await ctx.call_tool("budget.blocked", {"value": 1})


def _budget_exhaustion(output_dir: Path) -> dict[str, Any]:
    calls = {"count": 0}
    rt = Runtime.local(output_dir / "budget-exhaustion" / ".agentledger", budget=BudgetController(BudgetLimits(max_tool_calls=0)))
    rt.registry.register(
        ToolSpec(
            name="budget.blocked",
            func=lambda args: calls.__setitem__("count", calls["count"] + 1) or {"ok": True},
            side_effect="external_write",
            risk_level="medium",
            input_schema={"type": "object", "required": ["value"]},
        )
    )
    run_id, _ = rt.create_run(initial_state={"scenario": "budget-exhaustion"})
    blocked = False
    try:
        run_async(rt.run_once(_budget_blocked_agent, run_id=run_id, agent_role="BudgetAgent"))
    except BudgetExceeded:
        blocked = True
    failure = FailureAttributionReporter(rt.store).report(run_id).to_dict()
    status = rt.store.run(run_id)["status"]
    rt.close()
    return {
        "run_id": run_id,
        "blocked_before_tool_execution": blocked,
        "tool_executed": calls["count"] > 0,
        "tool_execution_count": calls["count"],
        "run_status": status,
        "run_failed": status == "failed",
        "failure_categories": sorted({item.get("category") for item in failure["failure_envelopes"]}),
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
        measured_depths = sorted({SCENARIO_DEPTH.get(name, {"level": "unclassified"})["level"] for name in measured}, key=lambda item: DEPTH_ORDER.get(item, -1), reverse=True)
        measured_notes = {
            name: SCENARIO_DEPTH.get(name, {"level": "unclassified", "note": "scenario has no verification-depth metadata"})
            for name in measured
        }
        if language:
            measured_depths = sorted(set(measured_depths + ["language_conformance"]), key=lambda item: DEPTH_ORDER.get(item, -1), reverse=True)
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
                "verification_depths": measured_depths,
                "primary_verification_depth": measured_depths[0] if measured_depths else None,
                "scenario_depth_notes": measured_notes,
                "language_commands": language,
                "fixture": entry.get("fixture"),
                "scenario_refs": entry.get("scenario_refs", []),
                "description": entry.get("description", ""),
            }
        )
    return matrix


def coverage_summary(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_depth: dict[str, int] = {}
    by_local_depth: dict[str, int] = {}
    for row in matrix:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        depth = row.get("primary_verification_depth") or "none"
        by_depth[depth] = by_depth.get(depth, 0) + 1
        local_depths = [item for item in row.get("verification_depths", []) if item != "language_conformance"]
        local_depth = local_depths[0] if local_depths else "none"
        by_local_depth[local_depth] = by_local_depth.get(local_depth, 0) + 1
    covered = [row for row in matrix if row["status"] != "manifest_only_not_run"]
    return {
        "required_check_count": len(matrix),
        "covered_check_count": len(covered),
        "not_run_count": len(matrix) - len(covered),
        "by_status": by_status,
        "by_primary_verification_depth": by_depth,
        "by_local_verification_depth": by_local_depth,
    }


def benchmark_warnings(report: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    shallow_depths = {"contract_dry_run", "static_helper"}
    for row in report["coverage_matrix"]:
        depths = set(row.get("verification_depths", [])) - {"language_conformance"}
        if depths and depths.issubset(shallow_depths):
            warnings.append(f"{row['id']} is covered only by {', '.join(sorted(depths))}; run service-backed validation before production claims")
    if report.get("execution_claim") == "local_runtime_smoke":
        warnings.append("language conformance commands were skipped; this report is a local runtime smoke, not a full release gate")
    return warnings


def validate_report(report: dict[str, Any], *, require_full_coverage: bool, allow_language_skips: bool) -> list[str]:
    failures: list[str] = []
    if require_full_coverage and report["coverage_summary"]["not_run_count"]:
        failures.append(f"semantic coverage has {report['coverage_summary']['not_run_count']} unrun required checks")
    if require_full_coverage and not report.get("language_commands"):
        failures.append("language conformance commands did not run")

    summary = report["summary"]
    required_truthy = {
        "build_idempotent_side_effect_run": ("completed",),
        "build_model_evidence_run": ("model_failure_category_present", "model_evidence_refs", "tool_proposal_refs"),
        "tool_schema_validation": ("invalid_input_rejected", "run_failed"),
        "policy_approval_sandbox": ("approval_created", "approval_approved", "approval_second_ok", "sandbox_failed_closed"),
        "cost_failure_reports": ("model_tokens_present", "model_cost_present", "model_failure_category_present", "model_failure_export_refs", "tool_proposal_export_refs"),
        "budget_exhaustion": ("blocked_before_tool_execution", "run_failed"),
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
    required_falsey = {
        "policy_approval_sandbox": ("approval_first_ok",),
        "budget_exhaustion": ("tool_executed",),
    }
    for scenario, keys in required_falsey.items():
        metrics = summary.get(scenario, {}).get("last_metrics")
        if not isinstance(metrics, dict):
            continue
        for key in keys:
            if metrics.get(key):
                failures.append(f"{scenario}.{key} was unexpectedly truthy")
    expected_values = {
        "build_idempotent_side_effect_run": {"external_side_effect_count": 1, "ledger_count": 1},
        "build_model_evidence_run": {"model_call_requested_count": 1, "model_call_completed_count": 1, "model_call_failed_count": 1, "tool_call_proposed_count": 1},
        "budget_exhaustion": {"tool_execution_count": 0},
    }
    for scenario, pairs in expected_values.items():
        metrics = summary.get(scenario, {}).get("last_metrics")
        if not isinstance(metrics, dict):
            continue
        for key, expected in pairs.items():
            if metrics.get(key) != expected:
                failures.append(f"{scenario}.{key} expected {expected!r}, got {metrics.get(key)!r}")

    for item in report.get("language_commands", []):
        if item.get("status") == "skipped" and not allow_language_skips:
            failures.append(f"{item.get('name')} status=skipped")
        elif item.get("status") not in {"passed", "skipped"}:
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
        "execution_claim": "release_gate" if language_commands else "local_runtime_smoke",
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
    warnings = report.get("warnings", [])
    lines.extend(["", "## Warnings", ""])
    if warnings:
        lines.extend([f"- {warning}" for warning in warnings])
    else:
        lines.append("- No benchmark warnings.")
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
            f"- Primary verification depth: `{report['coverage_summary']['by_primary_verification_depth']}`",
            "",
            "| Check | Status | Verification depth | Measured scenarios | Language commands |",
            "|---|---|---|---|---|",
        ]
    )
    for row in report["coverage_matrix"]:
        measured = ", ".join(f"`{name}`" for name in row["measured_scenarios"]) or "-"
        language = ", ".join(f"`{name}`" for name in row["language_commands"]) or "-"
        depth = ", ".join(f"`{name}`" for name in row.get("verification_depths", [])) or "-"
        lines.append(f"| `{row['id']}` | {row['status']} | {depth} | {measured} | {language} |")
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
    parser.add_argument("--allow-language-skips", action="store_true", help="Do not fail the release gate if a local language toolchain is missing.")
    parser.add_argument("--command-timeout", type=int, default=60, help="Timeout in seconds for each optional language command.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.iterations < 1:
        raise SystemExit("--iterations must be >= 1")
    output_dir = args.output_dir or Path(tempfile.mkdtemp(prefix="agentledger-benchmark-"))
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = output_dir / f"run-{int(time.time() * 1000)}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    runtime_root = artifact_dir / ".agentledger"
    samples: list[Sample] = []
    scenario_run_ids: dict[str, str] = {}

    with make_runtime(runtime_root) as rt:
        samples.extend(bench_create_runs(rt, args.iterations))
        samples.extend(bench_managed_steps(rt, args.iterations))
        samples.append(timed("build_idempotent_side_effect_run", lambda: build_side_effect_run_metrics(rt)))
        scenario_run_ids["idempotent_side_effect"] = samples[-1].metrics["run_id"]
        samples.append(timed("build_model_evidence_run", lambda: build_model_run_metrics(rt)))
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
    warnings = benchmark_warnings(report)
    failures = validate_report(report, require_full_coverage=not args.skip_language_commands, allow_language_skips=args.allow_language_skips)
    report["passed"] = not failures
    report["validation_failures"] = failures
    report["warnings"] = warnings
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
                "warnings": warnings,
                "scenario_count": len(report["summary"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
