from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .blobstore import LocalBlobStore
from .ids import now_ts
from .store import SQLiteStore


@dataclass(frozen=True)
class RetentionPlan:
    run_id: str
    event_count: int
    artifact_count: int
    media_artifact_count: int
    stream_checkpoint_count: int
    protected_blob_ref_count: int
    ledger_count: int
    estimated_event_bytes: int
    actions: list[str] = field(default_factory=list)
    destructive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_count": self.event_count,
            "artifact_count": self.artifact_count,
            "media_artifact_count": self.media_artifact_count,
            "stream_checkpoint_count": self.stream_checkpoint_count,
            "protected_blob_ref_count": self.protected_blob_ref_count,
            "ledger_count": self.ledger_count,
            "estimated_event_bytes": self.estimated_event_bytes,
            "actions": self.actions,
            "destructive": self.destructive,
        }


class RetentionPlanner:
    """Plan safe retention/compaction without deleting audit data by default."""

    def __init__(self, store: SQLiteStore, blobs: LocalBlobStore):
        self.store = store
        self.blobs = blobs

    def plan(self, run_id: str) -> RetentionPlan:
        events = self.store.events(run_id)
        artifacts = self.store.artifacts(run_id)
        ledger = self.store.ledger(run_id)
        media_artifact_count = 0
        stream_checkpoint_count = 0
        protected_blob_refs: list[str] = []
        for row in artifacts:
            metadata = self._decode_metadata(row["metadata_json"])
            if "agentledger_media" in metadata:
                media_artifact_count += 1
            if "agentledger_stream" in metadata:
                stream_checkpoint_count += 1
            self._append_refs_from_value(protected_blob_refs, metadata)
        estimated_event_bytes = sum(len(json.dumps({key: row[key] for key in row.keys()}, ensure_ascii=False)) for row in events)
        actions = [
            "export evidence bundle before destructive retention",
            "snapshot final state and manifest",
            "keep tool ledger and approval records until external retention policy expires",
            "preserve media/stream nested blob refs until evidence export and replay validation pass",
            "mark compacted runs before any physical deletion",
        ]
        return RetentionPlan(
            run_id=run_id,
            event_count=len(events),
            artifact_count=len(artifacts),
            media_artifact_count=media_artifact_count,
            stream_checkpoint_count=stream_checkpoint_count,
            protected_blob_ref_count=len(set(protected_blob_refs)),
            ledger_count=len(ledger),
            estimated_event_bytes=estimated_event_bytes,
            actions=actions,
            destructive=False,
        )

    def mark_compacted(self, run_id: str, *, reason: str = "manual compaction marker") -> int:
        marker = {"compacted": True, "reason": reason, "timestamp": now_ts()}
        return self.store.apply_system_state_patch(
            run_id=run_id,
            patch={"_agentledger": {"retention": marker}},
            reason="retention compaction marker",
        )

    def _decode_metadata(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                data = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}
        return {}

    def _append_refs_from_value(self, refs: list[str], value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                self._append_refs_from_value(refs, item)
            return
        if isinstance(value, list):
            for item in value:
                self._append_refs_from_value(refs, item)
            return
        if isinstance(value, str) and value.startswith("blob://"):
            refs.append(value)
