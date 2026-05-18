from __future__ import annotations

import json
from typing import Any

from .media import MEDIA_KINDS, MEDIA_SCHEMA_VERSION, STREAM_SCHEMA_VERSION
from .media_tools import media_tool_specs

CONTRACT_VERSION = "1.0"


def runtime_contract() -> dict[str, Any]:
    """Return the language-neutral AgentLedger runtime contract.

    Python is the current reference implementation. Other runtimes should target
    this wire contract instead of copying Python internals.
    """

    return {
        "project": "agentledger",
        "contract_version": CONTRACT_VERSION,
        "status": "stable-runtime-core",
        "reference_implementation": {"language": "python", "package": "agentledger", "status": "active"},
        "language_targets": [
            {"language": "python", "role": "reference-runtime", "status": "active"},
            {"language": "typescript", "role": "node-runtime-preview", "status": "preview"},
            {"language": "rust", "role": "runtime-preview", "status": "preview"},
            {"language": "go", "role": "runtime-preview", "status": "preview"},
        ],
        "wire_format": {
            "encoding": "json",
            "timestamps": "unix_seconds_float",
            "ids": "string-with-prefix",
            "hashes": "sha256:<hex>",
            "state_patch": "json-merge-patch-compatible-object",
        },
        "core_objects": [
            "Run",
            "Session",
            "Step",
            "StepClaim",
            "AgentContext",
            "RuntimeEvent",
            "ToolRequest",
            "ToolResult",
            "ToolLedgerEntry",
            "ArtifactRef",
            "ArtifactLineage",
            "MediaArtifact",
            "MediaMetadata",
            "StreamChunkRef",
            "EventStreamCheckpoint",
            "CostRecord",
            "ApprovalRequest",
            "EvidenceBundle",
            "MigrationStatus",
        ],
        "required_event_fields": [
            "event_id",
            "run_id",
            "seq",
            "type",
            "timestamp",
            "payload_hash",
            "payload_ref",
        ],
        "event_types": [
            "run_created",
            "step_created",
            "step_claimed",
            "state_patch_committed",
            "tool_call_requested",
            "tool_permission_decided",
            "tool_approval_required",
            "tool_call_completed",
            "tool_call_failed",
            "sandbox_started",
            "sandbox_completed",
            "artifact_created",
            "step_completed",
            "step_failed",
            "step_retry_scheduled",
            "lease_heartbeat",
            "lease_expired",
            "run_cancel_requested",
            "step_cancelled",
            "run_cancelled",
            "agent_result_returned",
            "tool_approval_decided",
            "step_waiting_human",
            "model_call_completed",
            "cost_recorded",
            "budget_check_failed",
            "failure_classified",
        ],
        "state_store_operations": [
            "create_run",
            "claim_step",
            "heartbeat",
            "recover_expired_leases",
            "cancel_run",
            "load_state",
            "commit_state_patch",
            "append_event",
            "reserve_ledger",
            "update_ledger",
            "request_approval",
            "approve_request",
            "deny_request",
            "record_cost",
            "cost_summary",
        ],
        "invariants": [
            "append-only event ordering per run",
            "state commits require a valid lease token",
            "state commits require the expected base state version",
            "cancelled or expired workers are fenced from committing",
            "managed side-effect tools reserve a unique idempotency key",
            "PENDING_VERIFICATION side effects are not auto-retried",
            "replay and shadow mode must not create external side effects",
            "sandbox-required tools fail closed when the executor is missing or disabled",
            "media and stream artifacts store refs, metadata, lineage, and checkpoints instead of raw codec processing",
        ],
        "artifact_contracts": {
            "media_schema_version": MEDIA_SCHEMA_VERSION,
            "media_kinds": sorted(MEDIA_KINDS),
            "stream_schema_version": STREAM_SCHEMA_VERSION,
            "stream_checkpoint_fields": [
                "stream_id",
                "consumer_id",
                "offset",
                "watermark",
                "chunk",
                "partial_result_ref",
                "backpressure",
            ],
        },
        "tool_conventions": {
            "media_stream": [spec.to_dict() for spec in media_tool_specs()],
        },
        "conformance": {
            "required_for_storage_adapters": [
                "create_claim_commit",
                "stale_lease_rejected",
                "expired_lease_recovered",
                "cancel_fences_worker",
            ],
            "required_for_worker_adapters": [
                "multi_worker_claims_distinct_steps",
                "heartbeat_fences_wrong_owner",
                "recovery_fences_previous_owner",
            ],
            "required_for_media_runtime": [
                "media_evidence_replay_chain",
                "media_tool_ledger_chain",
            ],
            "golden_contract_path": "contracts/agentledger.runtime.v1.json",
            "runtime_semantics_manifest_path": "contracts/conformance/runtime_semantics.v1.json",
            "runtime_baseline_fixture_path": "contracts/conformance/runtime_baseline.v1.json",
            "runtime_core_fixture_paths": [
                "contracts/conformance/runtime_baseline.v1.json",
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
                "contracts/conformance/policy_approval_sandbox.v1.json",
                "contracts/conformance/cost_failure_attribution.v1.json",
                "contracts/conformance/media_stream_artifacts.v1.json",
            ],
        },
        "stability": {
            "stable": [
                "run/step/session state machine",
                "lease/fencing/cancellation semantics",
                "event log and evidence bundle shape",
                "Tool Ledger statuses and idempotency semantics",
                "StateStore and BlobStore conformance requirements",
                "AgentContext tool/model/artifact boundary",
                "sandbox policy/routing/fail-closed semantics",
            ],
            "preview": [
                "media and stream artifact schemas",
                "dependency-free framework facades",
                "evidence regression and golden corpus UX",
                "go/typescript/rust runtime-core parity preview baselines",
            ],
            "external": [
                "full eval systems",
                "workflow/planning engines",
                "RAG/vector memory systems",
                "sandbox infrastructure",
                "observability backends",
                "distributed schedulers",
            ],
        },
    }


def contract_json() -> str:
    return json.dumps(runtime_contract(), indent=2, sort_keys=True, ensure_ascii=False)
