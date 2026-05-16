from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import EvidenceBundle


@dataclass(frozen=True)
class DiffReport:
    left_run_id: str | None
    right_run_id: str | None
    same: bool
    changes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_run_id": self.left_run_id,
            "right_run_id": self.right_run_id,
            "same": self.same,
            "changes": self.changes,
        }


@dataclass(frozen=True)
class DivergenceReport:
    left_run_id: str | None
    right_run_id: str | None
    same: bool
    changed_dimensions: list[str]
    dimensions: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_run_id": self.left_run_id,
            "right_run_id": self.right_run_id,
            "same": self.same,
            "changed_dimensions": self.changed_dimensions,
            "dimensions": self.dimensions,
        }


def load_evidence_path(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_dir():
        source = source / "bundle.json"
    return json.loads(source.read_text(encoding="utf-8"))


class EvidenceDiffer:
    """Compare evidence bundles for replay/shadow regression analysis."""

    def compare(self, left: EvidenceBundle | dict[str, Any], right: EvidenceBundle | dict[str, Any]) -> DiffReport:
        left_data = left.to_dict() if isinstance(left, EvidenceBundle) else left
        right_data = right.to_dict() if isinstance(right, EvidenceBundle) else right
        changes = {
            "bundle_hash_changed": left_data.get("bundle_hash") != right_data.get("bundle_hash"),
            "summary": diff_dict(left_data.get("summary", {}), right_data.get("summary", {})),
            "final_state": diff_dict(left_data.get("final_state", {}), right_data.get("final_state", {})),
            "event_types": diff_sequence([e.get("type") for e in left_data.get("events", [])], [e.get("type") for e in right_data.get("events", [])]),
            "tool_ledger": diff_sequence([row.get("status") for row in left_data.get("tool_ledger", [])], [row.get("status") for row in right_data.get("tool_ledger", [])]),
            "media_artifacts": diff_sequence(_media_artifact_fingerprints(left_data), _media_artifact_fingerprints(right_data)),
            "stream_checkpoints": diff_sequence(_stream_checkpoint_fingerprints(left_data), _stream_checkpoint_fingerprints(right_data)),
            "cost_summary": diff_dict(left_data.get("summary", {}).get("cost_summary", {}), right_data.get("summary", {}).get("cost_summary", {})),
        }
        same = not _has_changes(changes)
        return DiffReport(
            left_run_id=left_data.get("run", {}).get("run_id"),
            right_run_id=right_data.get("run", {}).get("run_id"),
            same=same,
            changes=changes,
        )


class DivergenceReporter:
    """Compare evidence bundles across runtime dimensions for rerun analysis."""

    def compare(self, left: EvidenceBundle | dict[str, Any], right: EvidenceBundle | dict[str, Any]) -> DivergenceReport:
        left_data = left.to_dict() if isinstance(left, EvidenceBundle) else left
        right_data = right.to_dict() if isinstance(right, EvidenceBundle) else right
        dimensions = {
            "events": diff_sequence([event.get("type") for event in left_data.get("events", [])], [event.get("type") for event in right_data.get("events", [])]),
            "state": diff_dict(left_data.get("final_state", {}), right_data.get("final_state", {})),
            "artifacts": diff_sequence(_artifact_fingerprints(left_data), _artifact_fingerprints(right_data)),
            "media_artifacts": diff_sequence(_media_artifact_fingerprints(left_data), _media_artifact_fingerprints(right_data)),
            "stream_checkpoints": diff_sequence(_stream_checkpoint_fingerprints(left_data), _stream_checkpoint_fingerprints(right_data)),
            "ledger": diff_sequence(_ledger_fingerprints(left_data), _ledger_fingerprints(right_data)),
            "cost": diff_dict(left_data.get("summary", {}).get("cost_summary", {}), right_data.get("summary", {}).get("cost_summary", {})),
            "model_outputs": diff_sequence(_model_outputs(left_data), _model_outputs(right_data)),
        }
        changed_dimensions = [name for name, value in dimensions.items() if _dimension_changed(value)]
        return DivergenceReport(
            left_run_id=left_data.get("run", {}).get("run_id"),
            right_run_id=right_data.get("run", {}).get("run_id"),
            same=not changed_dimensions,
            changed_dimensions=changed_dimensions,
            dimensions=dimensions,
        )


def diff_dict(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(left) | set(right))
    changed = {key: {"left": left.get(key), "right": right.get(key)} for key in keys if left.get(key) != right.get(key)}
    return {"changed_count": len(changed), "changed": changed}


def diff_sequence(left: list[Any], right: list[Any]) -> dict[str, Any]:
    max_len = max(len(left), len(right))
    changed = []
    for idx in range(max_len):
        left_value = left[idx] if idx < len(left) else None
        right_value = right[idx] if idx < len(right) else None
        if left_value != right_value:
            changed.append({"index": idx, "left": left_value, "right": right_value})
    return {"left_count": len(left), "right_count": len(right), "changed_count": len(changed), "changed": changed}


def _has_changes(changes: dict[str, Any]) -> bool:
    if changes.get("bundle_hash_changed"):
        return True
    for key, value in changes.items():
        if key == "bundle_hash_changed":
            continue
        if isinstance(value, dict) and value.get("changed_count", 0):
            return True
    return False


def _dimension_changed(value: dict[str, Any]) -> bool:
    return bool(value.get("changed_count", 0))


def _artifact_fingerprints(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": row.get("name"),
            "blob_hash": row.get("blob_hash"),
            "metadata_json": row.get("metadata_json"),
        }
        for row in evidence.get("artifacts", [])
    ]


def _media_artifact_fingerprints(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": row.get("name"),
            "kind": row.get("kind"),
            "uri": row.get("uri"),
            "content_ref": row.get("content_ref"),
            "blob_hash": row.get("blob_hash"),
            "lineage": row.get("lineage"),
        }
        for row in evidence.get("media_artifacts", [])
    ]


def _stream_checkpoint_fingerprints(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": row.get("name"),
            "stream_id": row.get("stream_id"),
            "consumer_id": row.get("consumer_id"),
            "offset": row.get("offset"),
            "watermark": row.get("watermark"),
            "chunk": row.get("chunk"),
            "partial_result_ref": row.get("partial_result_ref"),
        }
        for row in evidence.get("stream_checkpoints", [])
    ]


def _ledger_fingerprints(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "tool_name": row.get("tool_name"),
            "status": row.get("status"),
            "external_id": row.get("external_id"),
            "error_type": row.get("error_type"),
            "request_hash": row.get("request_hash"),
            "response_hash": row.get("response_hash"),
        }
        for row in evidence.get("tool_ledger", [])
    ]


def _model_outputs(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for event in evidence.get("events", []):
        if event.get("type") != "model_call_completed":
            continue
        payload = event.get("payload")
        if isinstance(payload, dict):
            outputs.append(
                {
                    "provider": payload.get("provider"),
                    "content": payload.get("content"),
                    "usage": payload.get("usage"),
                }
            )
        else:
            outputs.append({"payload": payload})
    return outputs
