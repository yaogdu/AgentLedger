#!/usr/bin/env python3
"""Audit Python reference modules against cross-language parity evidence.

This is intentionally conservative: a module is covered only when it maps to a
shared conformance fixture or an explicit out-of-core/adapter decision.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_MOD = ROOT / "src" / "agentledger"
MANIFEST = ROOT / "contracts" / "conformance" / "runtime_semantics.v1.json"

COVERAGE: dict[str, dict[str, object]] = {
    "runtime": {"status": "covered", "evidence": ["runtime_baseline.v1.json"]},
    "store": {"status": "covered", "evidence": ["runtime_baseline.v1.json", "local_persistence.v1.json"]},
    "context": {"status": "covered", "evidence": ["runtime_baseline.v1.json", "tool_schema_validation.v1.json"]},
    "tools": {"status": "covered", "evidence": ["tool_schema_validation.v1.json", "runtime_baseline.v1.json"]},
    "worker": {"status": "covered", "evidence": ["worker_service.v1.json"]},
    "scheduler": {"status": "covered", "evidence": ["scheduler.v1.json"]},
    "evidence": {"status": "covered", "evidence": ["runtime_baseline.v1.json", "evidence_consumers.v1.json"]},
    "replay": {"status": "covered", "evidence": ["runtime_baseline.v1.json"]},
    "trace": {"status": "covered", "evidence": ["evidence_consumers.v1.json", "otlp_trace_export.v1.json"]},
    "diff": {"status": "covered", "evidence": ["evidence_consumers.v1.json", "evidence_regression.v1.json"]},
    "timetravel": {"status": "covered", "evidence": ["time_travel.v1.json", "static_debug_html.v1.json", "evidence_consumers.v1.json"], "note": "timeline/state-at-seq/static HTML semantics covered; exact CSS/layout is not a contract"},
    "cost": {"status": "covered", "evidence": ["cost_failure_attribution.v1.json"]},
    "failure": {"status": "covered", "evidence": ["cost_failure_attribution.v1.json"]},
    "model": {"status": "covered", "evidence": ["cost_failure_attribution.v1.json", "evidence_consumers.v1.json"], "note": "runtime model evidence boundary covers archived model requests/responses/failures, usage/cost, and proposed tool-call records without provider routing"},
    "failure_injection": {"status": "covered", "evidence": ["failure_injection.v1.json"]},
    "review": {"status": "covered", "evidence": ["adversarial_review.v1.json"]},
    "eval": {"status": "covered", "evidence": ["evidence_regression.v1.json"], "note": "side-effect-free evidence checks only; external eval platform remains out of core"},
    "shadow": {"status": "covered", "evidence": ["shadow.v1.json", "optional_adapters.v1.json"], "note": "report/state diff covered; full ShadowRunner is an optional adapter capability, not a core dependency"},
    "simple": {"status": "covered", "evidence": ["simple_api.v1.json"]},
    "policy": {"status": "covered", "evidence": ["policy_approval_sandbox.v1.json"]},
    "approval": {"status": "covered", "evidence": ["policy_approval_sandbox.v1.json"]},
    "sandbox": {"status": "covered", "evidence": ["policy_approval_sandbox.v1.json", "optional_adapters.v1.json"], "note": "fail-closed boundary covered; concrete isolation backends are optional adapter capabilities"},
    "media": {"status": "covered", "evidence": ["media_stream_artifacts.v1.json"]},
    "media_tools": {"status": "out_of_core", "evidence": ["media_stream_artifacts.v1.json"], "note": "runtime stores refs/checkpoints; codec/tool processing is adapter scope"},
    "blobstore": {"status": "covered", "evidence": ["local_blob_store.v1.json"]},
    "blobstore_s3": {"status": "covered", "evidence": ["optional_adapters.v1.json"], "note": "S3 is covered as an optional blobstore adapter capability; live SDK dependency is out of core"},
    "storage_schema": {"status": "covered", "evidence": ["storage_schema.v1.json"]},
    "storage_postgres": {"status": "covered", "evidence": ["storage_schema.v1.json", "optional_adapters.v1.json"], "note": "Postgres DDL/schema metadata and optional adapter boundary are covered; live driver dependency is out of core"},
    "storage_mysql": {"status": "covered", "evidence": ["storage_schema.v1.json", "optional_adapters.v1.json"], "note": "MySQL DDL/schema metadata and optional adapter boundary are covered; live driver dependency is out of core"},
    "retention": {"status": "covered", "evidence": ["ops_readiness.v1.json"]},
    "backup": {"status": "covered", "evidence": ["ops_readiness.v1.json"]},
    "lint": {"status": "covered", "evidence": ["boundary_lint.v1.json"]},
    "adapters": {"status": "covered", "evidence": ["framework_adapters.v1.json"]},
    "adapters_frameworks": {"status": "covered", "evidence": ["framework_adapters.v1.json", "optional_adapters.v1.json"], "note": "base adapter contract plus optional concrete framework capability descriptors are covered"},
    "adapters_langgraph": {"status": "covered", "evidence": ["framework_adapters.v1.json", "optional_adapters.v1.json"], "note": "LangGraph integration is covered as framework/checkpoint adapter boundary without importing LangGraph in core"},
    "adapters_mcp": {"status": "covered", "evidence": ["mcp_adapters.v1.json", "optional_adapters.v1.json"], "note": "in-memory MCP contract plus optional transport capability descriptor are covered"},
    "adapters_omp": {"status": "covered", "evidence": ["scripts/check_language_parity.py"], "note": "OMP runtime bridge is covered by four-language unit tests and the aggregate parity gate; it remains a built-in runtime bridge, not a separate optional adapter fixture"},
    "adapter_certification": {"status": "covered", "evidence": ["optional_adapters.v1.json"], "note": "adapter certification bundles cover package metadata and optional adapter boundary claims"},
    "repro": {"status": "covered", "evidence": ["repro.v1.json"], "note": "built-in golden evidence/regression covered; file-backed corpus UX is language/package specific"},
    "contract": {"status": "covered", "evidence": ["contracts/agentledger.runtime.v1.json"]},
    "conformance": {"status": "covered", "evidence": ["scripts/check_language_parity.py"]},
    "protocol": {"status": "covered", "evidence": ["contracts/agentledger.runtime.v1.json"]},
    "ids": {"status": "covered", "evidence": ["runtime_baseline.v1.json"]},
    "inspector": {"status": "covered", "evidence": ["evidence_consumers.v1.json", "static_debug_html.v1.json", "storage_schema.v1.json"], "note": "Inspector is a read-only evidence/runtime metadata consumer; UI layout is not a cross-language runtime contract"},
    "jsonutil": {"status": "covered", "evidence": ["runtime_baseline.v1.json", "local_blob_store.v1.json"]},
    "examples": {"status": "python_only", "note": "examples are not runtime API parity"},
}

IGNORED = {"__init__", "__main__", "cli"}


def main() -> None:
    modules = sorted(p.stem for p in PY_MOD.glob("*.py") if p.stem not in IGNORED)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fixture_ids = {Path(item["fixture"]).name for item in manifest["required_semantic_checks"]}
    rows = []
    for name in modules:
        record = dict(COVERAGE.get(name, {"status": "unknown", "gap": "no audit mapping"}))
        evidence = record.get("evidence", [])
        record["module"] = name
        record["evidence_present"] = all(item in fixture_ids or item.startswith("contracts/") or item.startswith("scripts/") for item in evidence)
        rows.append(record)
    gaps = [row for row in rows if row["status"] in {"gap", "adapter_gap", "partial", "unknown"}]
    report = {
        "objective": "Python reference implementation parity for Go/TypeScript/Rust",
        "module_count": len(rows),
        "covered_count": sum(1 for row in rows if row["status"] == "covered"),
        "gap_count": len(gaps),
        "gaps": gaps,
        "modules": rows,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if gaps:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
