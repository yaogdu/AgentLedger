from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .diff import load_evidence_path
from .eval import EvidenceCheckReport, EvidenceRegressionRunner
from .jsonutil import sha256_json


@dataclass(frozen=True)
class GoldenCase:
    name: str
    path: str
    bundle_hash: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": self.path, "bundle_hash": self.bundle_hash, "metadata": self.metadata}


class GoldenCorpus:
    """File-based golden evidence corpus for regression and repro harnesses."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def add(self, name: str, evidence_path: str | Path, *, metadata: dict[str, Any] | None = None) -> GoldenCase:
        self._validate_name(name)
        evidence = load_evidence_path(evidence_path)
        return self._write_case(name, evidence, source_path=str(evidence_path), metadata=metadata or {})

    def seed_builtin(self, name: str = "minimal-success") -> GoldenCase:
        evidence = builtin_golden_evidence(name)
        return self._write_case(name, evidence, source_path=f"builtin:{name}", metadata={"builtin": True, "suite": "agentledger"})

    def builtin_names(self) -> list[str]:
        return sorted(BUILTIN_GOLDEN_CASES)

    def _write_case(self, name: str, evidence: dict[str, Any], *, source_path: str, metadata: dict[str, Any]) -> GoldenCase:
        self._validate_name(name)
        case_dir = self.root / name
        case_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = case_dir / "bundle.json"
        bundle_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {
            "name": name,
            "bundle_hash": evidence.get("bundle_hash"),
            "source_path": source_path,
            "metadata": metadata,
        }
        (case_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return GoldenCase(name=name, path=str(bundle_path), bundle_hash=evidence.get("bundle_hash"), metadata=metadata)

    def list(self) -> list[GoldenCase]:
        cases: list[GoldenCase] = []
        for manifest_path in sorted(self.root.glob("*/manifest.json")):
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            cases.append(
                GoldenCase(
                    name=data["name"],
                    path=str(manifest_path.parent / "bundle.json"),
                    bundle_hash=data.get("bundle_hash"),
                    metadata=data.get("metadata", {}),
                )
            )
        return cases

    def get(self, name: str) -> GoldenCase:
        self._validate_name(name)
        manifest_path = self.root / name / "manifest.json"
        if not manifest_path.exists():
            raise KeyError(f"golden case not found: {name}")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return GoldenCase(name=data["name"], path=str(manifest_path.parent / "bundle.json"), bundle_hash=data.get("bundle_hash"), metadata=data.get("metadata", {}))

    def evaluate(
        self,
        name: str,
        current_evidence_path: str | Path,
        *,
        require_same_final_state: bool = True,
        require_same_event_types: bool = True,
        require_same_tool_ledger_statuses: bool = True,
        require_same_media_artifacts: bool = True,
        require_same_stream_checkpoints: bool = True,
        max_total_usd_delta: float | None = None,
    ) -> EvidenceCheckReport:
        case = self.get(name)
        golden = load_evidence_path(case.path)
        current = load_evidence_path(current_evidence_path)
        return EvidenceRegressionRunner().evaluate_regression(
            golden,
            current,
            require_same_final_state=require_same_final_state,
            require_same_event_types=require_same_event_types,
            require_same_tool_ledger_statuses=require_same_tool_ledger_statuses,
            require_same_media_artifacts=require_same_media_artifacts,
            require_same_stream_checkpoints=require_same_stream_checkpoints,
            max_total_usd_delta=max_total_usd_delta,
        )

    def _validate_name(self, name: str) -> None:
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            raise ValueError("golden case name must be a simple path segment")


BUILTIN_GOLDEN_CASES = {"minimal-success", "tool-ledger-success", "media-stream-checkpoint"}


def builtin_golden_evidence(name: str) -> dict[str, Any]:
    builders = {
        "minimal-success": _builtin_minimal_success,
        "tool-ledger-success": _builtin_tool_ledger_success,
        "media-stream-checkpoint": _builtin_media_stream_checkpoint,
    }
    try:
        return builders[name]()
    except KeyError as exc:
        raise KeyError(f"unknown built-in golden case: {name}") from exc


def _finalize_bundle(data: dict[str, Any]) -> dict[str, Any]:
    data["bundle_hash"] = sha256_json({key: value for key, value in data.items() if key != "bundle_hash"})
    return data


def _base_summary(
    *,
    event_count: int,
    step_count: int = 1,
    tool_ledger_count: int = 0,
    artifact_count: int = 0,
    media_artifact_count: int = 0,
    stream_checkpoint_count: int = 0,
    approval_count: int = 0,
    tool_calls: float = 0.0,
    total_usd: float = 0.0,
) -> dict[str, Any]:
    by_category: dict[str, float] = {}
    if tool_calls:
        by_category["tool"] = tool_calls
    if total_usd:
        by_category["total_usd"] = total_usd
    return {
        "event_count": event_count,
        "step_count": step_count,
        "tool_ledger_count": tool_ledger_count,
        "artifact_count": artifact_count,
        "media_artifact_count": media_artifact_count,
        "stream_checkpoint_count": stream_checkpoint_count,
        "approval_count": approval_count,
        "has_pending_approvals": False,
        "has_pending_verification": False,
        "has_failed_steps": False,
        "cost_summary": {"tool_calls": tool_calls, "model_tokens": 0.0, "total_usd": total_usd, "by_category": by_category},
    }


def _builtin_minimal_success() -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "agentledger.evidence.v1",
        "bundle_hash": None,
        "run": {
            "run_id": "run_golden_minimal_success",
            "session_id": "sess_golden_minimal_success",
            "status": "completed",
            "state_json": "{\"answer\":\"ok\"}",
            "state_version": 1,
            "created_at": 0.0,
            "updated_at": 1.0,
            "initial_state": {},
        },
        "steps": [
            {
                "step_id": "step_golden_minimal_success",
                "run_id": "run_golden_minimal_success",
                "session_id": "sess_golden_minimal_success",
                "status": "completed",
                "attempt": 1,
                "state_version": 0,
                "last_error_type": None,
                "last_error": None,
            }
        ],
        "events": [
            {"seq": 1, "type": "run_created", "step_id": None, "agent_role": None, "payload": {"initial_state": {}}},
            {"seq": 2, "type": "step_created", "step_id": "step_golden_minimal_success", "agent_role": None, "payload": {"step_id": "step_golden_minimal_success"}},
            {"seq": 3, "type": "step_claimed", "step_id": "step_golden_minimal_success", "agent_role": None, "payload": {"attempt": 1}},
            {"seq": 4, "type": "agent_started", "step_id": "step_golden_minimal_success", "agent_role": "GoldenAgent", "payload": {"agent_role": "GoldenAgent"}},
            {"seq": 5, "type": "state_patch_proposed", "step_id": "step_golden_minimal_success", "agent_role": "GoldenAgent", "payload": {"key": "answer", "patch": "ok"}},
            {"seq": 6, "type": "state_committed", "step_id": "step_golden_minimal_success", "agent_role": None, "payload": {"patch": {"answer": "ok"}, "state_version": 1}},
            {"seq": 7, "type": "step_completed", "step_id": "step_golden_minimal_success", "agent_role": None, "payload": {"step_id": "step_golden_minimal_success"}},
        ],
        "tool_ledger": [],
        "approval_requests": [],
        "artifacts": [],
        "media_artifacts": [],
        "stream_checkpoints": [],
        "cost_records": [],
        "summary": _base_summary(event_count=7),
        "final_state": {"answer": "ok"},
    }
    return _finalize_bundle(data)


def _builtin_tool_ledger_success() -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "agentledger.evidence.v1",
        "bundle_hash": None,
        "run": {
            "run_id": "run_golden_tool_ledger_success",
            "session_id": "sess_golden_tool_ledger_success",
            "status": "completed",
            "state_json": "{\"issue_id\":\"ISSUE-1\"}",
            "state_version": 1,
            "created_at": 0.0,
            "updated_at": 1.0,
            "initial_state": {},
        },
        "steps": [
            {
                "step_id": "step_golden_tool_ledger_success",
                "run_id": "run_golden_tool_ledger_success",
                "session_id": "sess_golden_tool_ledger_success",
                "status": "completed",
                "attempt": 1,
                "state_version": 0,
                "last_error_type": None,
                "last_error": None,
            }
        ],
        "events": [
            {"seq": 1, "type": "run_created", "step_id": None, "agent_role": None, "payload": {"initial_state": {}}},
            {"seq": 2, "type": "step_created", "step_id": "step_golden_tool_ledger_success", "agent_role": None, "payload": {"step_id": "step_golden_tool_ledger_success"}},
            {"seq": 3, "type": "step_claimed", "step_id": "step_golden_tool_ledger_success", "agent_role": None, "payload": {"attempt": 1}},
            {"seq": 4, "type": "agent_started", "step_id": "step_golden_tool_ledger_success", "agent_role": "ExecutorAgent", "payload": {"agent_role": "ExecutorAgent"}},
            {"seq": 5, "type": "tool_call_requested", "step_id": "step_golden_tool_ledger_success", "agent_role": "ExecutorAgent", "payload": {"tool": "github.create_issue", "args": {"title": "golden"}}},
            {"seq": 6, "type": "tool_call_completed", "step_id": "step_golden_tool_ledger_success", "agent_role": "ExecutorAgent", "payload": {"tool": "github.create_issue", "idempotency_key": "idem-golden-tool"}},
            {"seq": 7, "type": "state_committed", "step_id": "step_golden_tool_ledger_success", "agent_role": None, "payload": {"patch": {"issue_id": "ISSUE-1"}, "state_version": 1}},
            {"seq": 8, "type": "step_completed", "step_id": "step_golden_tool_ledger_success", "agent_role": None, "payload": {"step_id": "step_golden_tool_ledger_success"}},
        ],
        "tool_ledger": [
            {
                "tool_name": "github.create_issue",
                "tool_version": "v1",
                "status": "SUCCEEDED",
                "idempotency_key": "idem-golden-tool",
                "external_id": "ISSUE-1",
                "request_hash": "sha256:golden-request",
                "request_ref": "blob://sha256/golden-request.json",
                "response_hash": "sha256:golden-response",
                "response_ref": "blob://sha256/golden-response.json",
                "error_type": None,
            }
        ],
        "approval_requests": [],
        "artifacts": [],
        "media_artifacts": [],
        "stream_checkpoints": [],
        "cost_records": [
            {"category": "tool", "name": "github.create_issue", "amount": 1.0, "unit": "call", "metadata": {"side_effect": "external_write"}}
        ],
        "summary": _base_summary(event_count=8, tool_ledger_count=1, tool_calls=1.0),
        "final_state": {"issue_id": "ISSUE-1"},
    }
    return _finalize_bundle(data)


def _builtin_media_stream_checkpoint() -> dict[str, Any]:
    media = {
        "name": "golden-video-frame",
        "kind": "frame",
        "uri": None,
        "content_ref": "blob://sha256/golden-frame-0001.jpg",
        "blob_hash": "sha256:golden-frame-0001",
        "metadata": {"mime_type": "image/jpeg", "frame_index": 1, "timestamp_ms": 1000},
        "lineage": {"source_ref": "blob://sha256/golden-video.mp4", "tool_name": "video.extract_frames", "tool_call_id": "toolcall_golden_video"},
    }
    checkpoint = {
        "name": "golden-stream-checkpoint",
        "stream_id": "camera-1",
        "consumer_id": "agentledger-golden-consumer",
        "offset": 42,
        "watermark": "1970-01-01T00:00:42Z",
        "chunk": {"chunk_id": "chunk-42", "offset": 42, "content_ref": "blob://sha256/golden-stream-chunk", "content_hash": "sha256:golden-stream-chunk"},
        "partial_result_ref": "blob://sha256/golden-partial-result.json",
    }
    data: dict[str, Any] = {
        "schema_version": "agentledger.evidence.v1",
        "bundle_hash": None,
        "run": {
            "run_id": "run_golden_media_stream_checkpoint",
            "session_id": "sess_golden_media_stream_checkpoint",
            "status": "completed",
            "state_json": "{\"processed_offset\":42}",
            "state_version": 1,
            "created_at": 0.0,
            "updated_at": 1.0,
            "initial_state": {},
        },
        "steps": [
            {
                "step_id": "step_golden_media_stream_checkpoint",
                "run_id": "run_golden_media_stream_checkpoint",
                "session_id": "sess_golden_media_stream_checkpoint",
                "status": "completed",
                "attempt": 1,
                "state_version": 0,
                "last_error_type": None,
                "last_error": None,
            }
        ],
        "events": [
            {"seq": 1, "type": "run_created", "step_id": None, "agent_role": None, "payload": {"initial_state": {}}},
            {"seq": 2, "type": "step_created", "step_id": "step_golden_media_stream_checkpoint", "agent_role": None, "payload": {"step_id": "step_golden_media_stream_checkpoint"}},
            {"seq": 3, "type": "step_claimed", "step_id": "step_golden_media_stream_checkpoint", "agent_role": None, "payload": {"attempt": 1}},
            {"seq": 4, "type": "media_artifact_created", "step_id": "step_golden_media_stream_checkpoint", "agent_role": "MediaAgent", "payload": media},
            {"seq": 5, "type": "stream_checkpoint_created", "step_id": "step_golden_media_stream_checkpoint", "agent_role": "MediaAgent", "payload": checkpoint},
            {"seq": 6, "type": "state_committed", "step_id": "step_golden_media_stream_checkpoint", "agent_role": None, "payload": {"patch": {"processed_offset": 42}, "state_version": 1}},
            {"seq": 7, "type": "step_completed", "step_id": "step_golden_media_stream_checkpoint", "agent_role": None, "payload": {"step_id": "step_golden_media_stream_checkpoint"}},
        ],
        "tool_ledger": [],
        "approval_requests": [],
        "artifacts": [],
        "media_artifacts": [media],
        "stream_checkpoints": [checkpoint],
        "cost_records": [],
        "summary": _base_summary(event_count=7, media_artifact_count=1, stream_checkpoint_count=1),
        "final_state": {"processed_offset": 42},
    }
    return _finalize_bundle(data)
