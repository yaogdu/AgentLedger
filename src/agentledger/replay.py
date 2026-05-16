from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .blobstore import LocalBlobStore
from .jsonutil import sha256_json
from .store import SQLiteStore


@dataclass
class ReplaySummary:
    run_id: str
    event_count: int
    tool_call_count: int
    final_state: dict[str, Any]
    event_hash: str
    replay_safe: bool
    artifact_count: int = 0
    media_artifact_count: int = 0
    stream_checkpoint_count: int = 0


class ReplayEngine:
    def __init__(self, *, store: SQLiteStore, blobs: LocalBlobStore):
        self.store = store
        self.blobs = blobs

    def replay(self, run_id: str) -> ReplaySummary:
        events = self.store.events(run_id)
        tools = [e for e in events if e["type"].startswith("tool_call_")]
        # Replay validates evidence availability but never calls providers/tools.
        digest_input: list[dict[str, Any]] = []
        for event in events:
            ref = event["payload_ref"]
            if isinstance(ref, str) and ref.startswith("blob://"):
                self.blobs.get_json(ref)
            digest_input.append({"seq": event["seq"], "type": event["type"], "payload_hash": event["payload_hash"], "payload_ref": event["payload_ref"]})
        artifacts = self.store.artifacts(run_id)
        media_artifact_count = 0
        stream_checkpoint_count = 0
        for row in artifacts:
            ref = row["blob_ref"]
            if isinstance(ref, str) and ref.startswith("blob://"):
                self.blobs.get_json(ref)
            metadata = _decode_metadata(row["metadata_json"])
            if "agentledger_media" in metadata:
                media_artifact_count += 1
            if "agentledger_stream" in metadata:
                stream_checkpoint_count += 1
        return ReplaySummary(
            run_id=run_id,
            event_count=len(events),
            tool_call_count=len(tools),
            final_state=self.store.final_state(run_id),
            event_hash=sha256_json(digest_input),
            replay_safe=True,
            artifact_count=len(artifacts),
            media_artifact_count=media_artifact_count,
            stream_checkpoint_count=stream_checkpoint_count,
        )


def _decode_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}
